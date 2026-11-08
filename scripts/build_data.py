from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from drugrec.data_builder import build_processed_data  # noqa: E402


if __name__ == "__main__":
    summary = build_processed_data()
    print(json.dumps(summary, indent=2))
