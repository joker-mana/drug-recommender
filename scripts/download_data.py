from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

DOWNLOAD_SPECS = {
    "ddi": {
        "url": "https://zenodo.org/records/19685458/files/ddi_2026.csv?download=1",
        "path": RAW_DIR / "zenodo_19685458" / "ddi_2026.csv",
        "sha256": "6015A98025B79307505E4F9A1D63B1108DD154FAF1A4D63F4098FEDC6779AD79",
    },
    "ddi_drugs": {
        "url": "https://zenodo.org/records/19685458/files/drugs_atc_cid.csv?download=1",
        "path": RAW_DIR / "zenodo_19685458" / "drugs_atc_cid.csv",
        "sha256": "0B38E8CA6BAC3B07EB786CF0644B7B739B6214D8779E29591A0DD6E1C24F1878",
    },
    "frdb": {
        "url": "https://drugs.ncats.io/downloads-public/frdb-v2024-12-30.zip",
        "path": RAW_DIR / "frdb_v2024-12-30.zip",
        "sha256": "647B80D9CDAC4A0517CE649570517DC1AFF40545BDC84617EC9F1A56405F9C7A",
    },
    "synthea": {
        "url": (
            "https://raw.githubusercontent.com/synthetichealth/"
            "synthea-sample-data/main/downloads/latest/"
            "synthea_sample_data_csv_latest.zip"
        ),
        "path": RAW_DIR / "synthea" / "synthea_sample_data_csv_latest.zip",
        "sha256": "990D52064037BBF83D10F13163DA428964B56AE673B7F39BF549D78C1E7EDA16",
    },
    "openfda": {
        "url": (
            "https://download.open.fda.gov/drug/label/"
            "drug-label-0001-of-0014.json.zip"
        ),
        "path": RAW_DIR / "openfda" / "drug-label-0001-of-0014.json.zip",
        "sha256": "D46C999C1947092F6E18E5233482E6D1C02312C89D32CE906E3B19672A696546",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def download(url: str, path: Path, expected_sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and sha256(path) == expected_sha256:
        print(f"verified: {path.relative_to(ROOT)}")
        return
    temporary = path.with_suffix(path.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "drug-recommender-reproduction/0.1"},
    )
    print(f"downloading: {url}")
    with urllib.request.urlopen(request, timeout=120) as response:
        total = int(response.headers.get("Content-Length", 0))
        received = 0
        with temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                received += len(chunk)
                if total:
                    print(
                        f"\r  {received / 1024 / 1024:.1f}/"
                        f"{total / 1024 / 1024:.1f} MiB",
                        end="",
                        flush=True,
                    )
    print()
    actual = sha256(temporary)
    if actual != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"SHA-256 mismatch for {path}: expected {expected_sha256}, got {actual}"
        )
    temporary.replace(path)
    print(f"saved: {path.relative_to(ROOT)}")


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"Unsafe ZIP member: {member.filename}")
        handle.extractall(destination)
    print(f"extracted: {destination.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-openfda",
        action="store_true",
        help="Skip the 130 MB openFDA label partition.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing files without downloading.",
    )
    args = parser.parse_args()
    selected = [
        name
        for name in DOWNLOAD_SPECS
        if name != "openfda" or not args.skip_openfda
    ]
    for name in selected:
        spec = DOWNLOAD_SPECS[name]
        if args.verify_only:
            actual = sha256(spec["path"])
            if actual != spec["sha256"]:
                raise RuntimeError(
                    f"SHA-256 mismatch for {spec['path']}: {actual}"
                )
            print(f"verified: {spec['path'].relative_to(ROOT)}")
        else:
            download(spec["url"], spec["path"], spec["sha256"])

    if not args.verify_only:
        safe_extract(
            DOWNLOAD_SPECS["frdb"]["path"],
            RAW_DIR / "frdb_v2024-12-30",
        )
        safe_extract(
            DOWNLOAD_SPECS["synthea"]["path"],
            RAW_DIR / "synthea" / "synthea_sample_data_csv_latest",
        )
        if "openfda" in selected:
            safe_extract(
                DOWNLOAD_SPECS["openfda"]["path"],
                RAW_DIR / "openfda" / "drug-label-0001-of-0014",
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
