from __future__ import annotations

import pandas as pd

from .ranker import DrugRankingSystem


class RecommendationService:
    def __init__(self) -> None:
        self.system = DrugRankingSystem()

    def rank_patient(
        self,
        patient_id: str,
        *,
        target_indication: str | None = None,
        top_k: int = 10,
    ) -> dict:
        context = self.system.patient_context(patient_id)
        return self.system.rank(
            target_indication=target_indication or context["target_indication"],
            current_medications=context["current_medications"],
            conditions=context["conditions"],
            allergies=context["allergies"],
            top_k=top_k,
        ).payload

    def catalog_search(self, query: str, limit: int = 30) -> pd.DataFrame:
        if not query.strip():
            return self.system.catalog[
                self.system.catalog["candidate_eligible"]
            ].head(limit)
        mask = self.system.catalog["canonical_name"].str.contains(
            query, case=False, na=False, regex=False
        )
        return self.system.catalog[mask].head(limit)
