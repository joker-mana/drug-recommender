from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from drugrec.cf_model import CollaborativeFilter  # noqa: E402
from drugrec.graph_model import GraphRecommender  # noqa: E402
from drugrec.paths import ARTIFACT_DIR, PROCESSED_DIR  # noqa: E402
from drugrec.text_model import TextModel  # noqa: E402


def main() -> None:
    config = json.loads((ROOT / "configs" / "default.json").read_text(encoding="utf-8"))
    catalog = pd.read_parquet(PROCESSED_DIR / "drug_catalog.parquet")
    documents = pd.read_parquet(PROCESSED_DIR / "drug_documents.parquet")
    medications = pd.read_parquet(PROCESSED_DIR / "synthea_medications.parquet")
    frdb_ddi = pd.read_parquet(PROCESSED_DIR / "frdb_ddi.parquet")
    eligible = catalog.loc[catalog["candidate_eligible"], "drug_id"].tolist()

    text_config = {
        key: value
        for key, value in config["text"].items()
        if key != "max_text_chars"
    }
    text_model = TextModel.fit(documents, **text_config)
    text_model.save(ARTIFACT_DIR / "text")

    cf_model = CollaborativeFilter.fit(medications, eligible)
    cf_model.save(ARTIFACT_DIR / "cf")

    graph_model = GraphRecommender.fit(
        catalog,
        frdb_ddi,
        alpha=float(config["graph"]["alpha"]),
    )
    graph_model.save(ARTIFACT_DIR / "graph.pkl")

    summary = {
        "text_documents": len(text_model.artifacts.drug_ids),
        "text_components": text_model.artifacts.embeddings.shape[1],
        "cf_items": len(cf_model.artifacts.drug_ids),
        "graph_nodes": graph_model.graph.number_of_nodes(),
        "graph_edges": graph_model.graph.number_of_edges(),
        "eligible_candidates": len(eligible),
    }
    (ARTIFACT_DIR / "training_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
