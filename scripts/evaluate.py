from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from drugrec.evaluation import evaluate_system, save_evaluation  # noqa: E402
from drugrec.paths import REPORT_DIR  # noqa: E402
from drugrec.ranker import DrugRankingSystem  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    system = DrugRankingSystem()
    result = evaluate_system(system, limit=args.limit, k=args.k)
    save_evaluation(result, REPORT_DIR)
    print(f"scenarios={result['scenario_count']}")
    for row in result["summary"]:
        print(
            f"{row['model']}: "
            f"recall@{args.k}={row.get(f'recall@{args.k}_mean', 0):.4f}, "
            f"ndcg@{args.k}={row.get(f'ndcg@{args.k}_mean', 0):.4f}, "
            f"unsafe@10={row.get('unsafe@10_mean', 0):.4f}"
        )


if __name__ == "__main__":
    main()
