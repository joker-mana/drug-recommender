from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
REPORT_DIR = PROJECT_ROOT / "reports"

ZENODO_DDI_DIR = RAW_DIR / "zenodo_19685458"
FRDB_DIR = RAW_DIR / "frdb_v2024-12-30" / "frdb"
SYNTHEA_DIR = RAW_DIR / "synthea" / "synthea_sample_data_csv_latest"
OPENFDA_LABEL_PATH = (
    RAW_DIR
    / "openfda"
    / "drug-label-0001-of-0014"
    / "drug-label-0001-of-0014.json"
)


def ensure_directories() -> None:
    for path in (PROCESSED_DIR, ARTIFACT_DIR, REPORT_DIR):
        path.mkdir(parents=True, exist_ok=True)

