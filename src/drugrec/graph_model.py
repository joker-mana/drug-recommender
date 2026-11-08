from __future__ import annotations

import pickle
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


class GraphRecommender:
    def __init__(self, graph: nx.Graph, alpha: float = 0.15) -> None:
        self.graph = graph
        self.alpha = alpha
        self._cache: dict[tuple[str, ...], dict[str, float]] = {}

    @classmethod
    def fit(
        cls,
        catalog: pd.DataFrame,
        frdb_ddi: pd.DataFrame,
        alpha: float = 0.15,
    ) -> "GraphRecommender":
        graph = nx.Graph()
        for row in catalog.itertuples(index=False):
            drug_node = f"drug:{row.drug_id}"
            graph.add_node(drug_node, kind="drug", name=row.canonical_name)
            for code in row.atc_codes:
                code = str(code).strip()
                if not code:
                    continue
                for size in (1, 3, 4, 5, 7):
                    if len(code) < size:
                        continue
                    level = {1: 1, 3: 2, 4: 3, 5: 4, 7: 5}[size]
                    atc_node = f"atc:{code[:size]}"
                    graph.add_node(atc_node, kind="atc", level=level)
                    graph.add_edge(drug_node, atc_node, weight=1.0, relation="atc")

        if not frdb_ddi.empty:
            targets = frdb_ddi.dropna(subset=["drug_id", "ddi_target"]).copy()
            for row in targets.itertuples(index=False):
                target = str(row.ddi_target).strip().lower()
                if not target:
                    continue
                target_node = f"target:{target}"
                graph.add_node(target_node, kind="target")
                graph.add_edge(
                    f"drug:{row.drug_id}",
                    target_node,
                    weight=1.0,
                    relation="target",
                )
        return cls(graph, alpha=alpha)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump({"graph": self.graph, "alpha": self.alpha}, handle)

    @classmethod
    def load(cls, path: Path) -> "GraphRecommender":
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        return cls(payload["graph"], alpha=payload["alpha"])

    def page_rank(self, seed_drug_ids: list[str]) -> dict[str, float]:
        seed_key = tuple(sorted(dict.fromkeys(seed_drug_ids)))
        if seed_key in self._cache:
            return self._cache[seed_key]
        personalization = {}
        for drug_id in seed_key:
            node = f"drug:{drug_id}"
            if node in self.graph:
                personalization[node] = 1.0
        if personalization:
            total = sum(personalization.values())
            personalization = {
                node: value / total for node, value in personalization.items()
            }
            scores = nx.pagerank(
                self.graph,
                alpha=self.alpha,
                personalization=personalization,
                weight="weight",
                max_iter=100,
                tol=1e-08,
            )
        else:
            scores = {}
        self._cache[seed_key] = scores
        return scores

    def score(self, seed_drug_ids: list[str], candidate_drug_ids: list[str]) -> np.ndarray:
        scores = self.page_rank(seed_drug_ids)
        values = np.array(
            [scores.get(f"drug:{drug_id}", 0.0) for drug_id in candidate_drug_ids],
            dtype=np.float32,
        )
        maximum = float(values.max())
        if maximum > 0:
            values = values / maximum
        return values

