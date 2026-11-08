from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from drugrec.service import RecommendationService  # noqa: E402


def comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--target", default=None)
    parser.add_argument("--medications", default="")
    parser.add_argument("--allergies", default="")
    parser.add_argument("--candidates", default="")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    service = RecommendationService()
    context = service.system.patient_context(args.patient_id)
    current = comma_list(args.medications) or context["current_medications"]
    allergies = comma_list(args.allergies) or context["allergies"]
    candidates = comma_list(args.candidates) or None
    result = service.system.rank(
        target_indication=args.target or context["target_indication"],
        conditions=context["conditions"],
        current_medications=current,
        allergies=allergies,
        candidate_drugs=candidates,
        top_k=args.top_k,
    ).payload
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"written: {args.output}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()

