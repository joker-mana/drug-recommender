from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .cf_model import CollaborativeFilter
from .graph_model import GraphRecommender
from .paths import ARTIFACT_DIR, PROJECT_ROOT, PROCESSED_DIR
from .safety import SafetyModel
from .text_model import TextModel


def _minmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return values
    low = float(np.min(values))
    high = float(np.max(values))
    if high - low <= 1e-12:
        return np.zeros_like(values)
    return (values - low) / (high - low)


@dataclass
class RankResult:
    payload: dict[str, Any]
    all_candidates: list[dict[str, Any]]


class DrugRankingSystem:
    def __init__(self) -> None:
        self.config = json.loads(
            (PROJECT_ROOT / "configs" / "default.json").read_text(encoding="utf-8")
        )
        self.catalog = pd.read_parquet(PROCESSED_DIR / "drug_catalog.parquet")
        self.documents = pd.read_parquet(PROCESSED_DIR / "drug_documents.parquet")
        self.ddi_pairs = pd.read_parquet(PROCESSED_DIR / "ddi_pairs.parquet")
        self.toxicity = pd.read_parquet(PROCESSED_DIR / "toxicity_summary.parquet")
        self.medications = pd.read_parquet(
            PROCESSED_DIR / "synthea_medications.parquet"
        )
        self.conditions = pd.read_parquet(PROCESSED_DIR / "synthea_conditions.parquet")
        self.patients = pd.read_parquet(PROCESSED_DIR / "synthea_patients.parquet")
        self.allergies = pd.read_parquet(PROCESSED_DIR / "synthea_allergies.parquet")
        self.catalog_by_id = self.catalog.set_index("drug_id", drop=False)
        self.eligible_ids = self.catalog.loc[
            self.catalog["candidate_eligible"], "drug_id"
        ].tolist()
        self.text_model = TextModel.load(ARTIFACT_DIR / "text")
        self.cf_model = CollaborativeFilter.load(ARTIFACT_DIR / "cf")
        self.graph_model = GraphRecommender.load(ARTIFACT_DIR / "graph.pkl")
        labeled_ids = set(
            self.documents.loc[self.documents["has_label"], "drug_id"].tolist()
        )
        self.safety_model = SafetyModel(
            self.catalog,
            self.ddi_pairs,
            self.toxicity,
            labeled_drug_ids=labeled_ids,
        )

    def resolve_drug(self, name: str) -> str | None:
        return self.safety_model.resolve(name)

    def resolve_many(self, names: list[str]) -> tuple[list[str], list[str]]:
        resolved: list[str] = []
        unresolved: list[str] = []
        for name in names:
            cleaned = str(name).strip()
            if not cleaned:
                continue
            drug_id = self.resolve_drug(cleaned)
            if drug_id is None:
                unresolved.append(cleaned)
            elif drug_id not in resolved:
                resolved.append(drug_id)
        return resolved, unresolved

    def patient_options(self) -> pd.DataFrame:
        counts = (
            self.medications.groupby("PATIENT")
            .size()
            .rename("medication_count")
            .reset_index()
        )
        frame = self.patients.merge(counts, on="PATIENT", how="left")
        frame["BIRTHDATE"] = frame["BIRTHDATE"].astype(str)
        return frame.sort_values("PATIENT")

    @lru_cache(maxsize=256)
    def patient_context(self, patient_id: str) -> dict[str, Any]:
        patient_meds = self.medications[
            self.medications["PATIENT"] == patient_id
        ].dropna(subset=["START", "drug_id"])
        if patient_meds.empty:
            return {
                "patient_id": patient_id,
                "as_of": None,
                "current_medications": [],
                "current_medication_ids": [],
                "conditions": [],
                "allergies": [],
                "allergy_ids": [],
                "target_indication": "",
            }
        as_of = patient_meds["START"].max()
        active = patient_meds[
            patient_meds["START"].le(as_of)
            & (
                patient_meds["STOP"].isna()
                | patient_meds["STOP"].ge(as_of)
            )
        ]
        if active.empty:
            active = patient_meds.nlargest(5, "START")
        current_names = active["DESCRIPTION"].drop_duplicates().tolist()
        current_ids = active["drug_id"].drop_duplicates().tolist()

        patient_conditions = self.conditions[
            self.conditions["PATIENT"] == patient_id
        ].copy()
        active_conditions = patient_conditions[
            patient_conditions["START"].le(as_of)
            & (
                patient_conditions["STOP"].isna()
                | patient_conditions["STOP"].ge(as_of)
            )
        ]
        condition_names = (
            active_conditions["DESCRIPTION"].drop_duplicates().tolist()
            if not active_conditions.empty
            else patient_conditions["DESCRIPTION"].drop_duplicates().tail(8).tolist()
        )
        patient_allergies = self.allergies[
            self.allergies["PATIENT"] == patient_id
        ]
        allergy_names = patient_allergies["DESCRIPTION"].drop_duplicates().tolist()
        allergy_ids = (
            patient_allergies["drug_id"].dropna().drop_duplicates().tolist()
        )
        return {
            "patient_id": patient_id,
            "as_of": as_of.isoformat(),
            "current_medications": current_names,
            "current_medication_ids": current_ids,
            "conditions": condition_names,
            "allergies": allergy_names,
            "allergy_ids": allergy_ids,
            "target_indication": "; ".join(condition_names[-6:]),
        }

    def rank(
        self,
        *,
        target_indication: str,
        current_medications: list[str],
        conditions: list[str] | None = None,
        allergies: list[str] | None = None,
        candidate_drugs: list[str] | None = None,
        top_k: int | None = None,
        include_blocked: bool = True,
    ) -> RankResult:
        conditions = conditions or []
        allergies = allergies or []
        top_k = top_k or int(self.config["ranking"]["default_top_k"])
        current_ids, unresolved_current = self.resolve_many(current_medications)
        allergy_ids, unresolved_allergies = self.resolve_many(allergies)

        if candidate_drugs:
            candidate_ids, unresolved_candidates = self.resolve_many(candidate_drugs)
        else:
            candidate_ids, unresolved_candidates = self.eligible_ids.copy(), []
        candidate_ids = [
            drug_id
            for drug_id in dict.fromkeys(candidate_ids)
            if drug_id not in current_ids and drug_id in self.catalog_by_id.index
        ]
        if not candidate_ids:
            payload = {
                "results": [],
                "meta": {
                    "candidate_count": 0,
                    "blocked_count": 0,
                    "review_count": 0,
                    "unresolved_medications": unresolved_current,
                    "unresolved_allergies": unresolved_allergies,
                    "unresolved_candidates": unresolved_candidates,
                    "disclaimer": self.disclaimer(),
                },
            }
            return RankResult(payload, [])

        query = " ".join(
            part
            for part in [target_indication, *conditions]
            if str(part).strip()
        )
        text_scores = _minmax(self.text_model.score(query, candidate_ids))
        cf_scores = _minmax(self.cf_model.score(current_ids, candidate_ids))
        graph_scores = _minmax(self.graph_model.score(current_ids, candidate_ids))
        popularity_scores = _minmax(
            self.cf_model.popularity_score(candidate_ids)
        )

        weights = self.config["ranking"]["weights"]
        risk_penalty = float(self.config["ranking"]["risk_penalty"])
        unknown_penalty = float(self.config["ranking"]["unknown_evidence_penalty"])
        all_candidates = []
        for index, drug_id in enumerate(candidate_ids):
            assessment = self.safety_model.assess(
                drug_id,
                current_ids,
                set(allergy_ids),
                unresolved_current,
                unresolved_allergies,
            )
            score = (
                weights["text"] * text_scores[index]
                + weights["collaborative"] * cf_scores[index]
                + weights["graph"] * graph_scores[index]
                + weights["popularity"] * popularity_scores[index]
                - risk_penalty * assessment.risk_score
                - unknown_penalty * (1 - assessment.evidence_score)
            )
            row = self.catalog_by_id.loc[drug_id]
            all_candidates.append(
                {
                    "drug_id": drug_id,
                    "name": row["canonical_name"],
                    "atc_codes": [str(item) for item in row["atc_codes"]],
                    "status": assessment.status,
                    "score": round(float(score), 6),
                    "risk_score": round(assessment.risk_score, 6),
                    "evidence_score": round(assessment.evidence_score, 6),
                    "scores": {
                        "text": round(float(text_scores[index]), 6),
                        "collaborative": round(float(cf_scores[index]), 6),
                        "graph": round(float(graph_scores[index]), 6),
                        "popularity": round(float(popularity_scores[index]), 6),
                    },
                    "reasons": assessment.reasons,
                    "interactions": assessment.interactions,
                }
            )

        ranked = sorted(all_candidates, key=lambda item: item["score"], reverse=True)
        safe_ranked = [
            item for item in ranked if item["status"] != "blocked"
        ]
        blocked = [item for item in ranked if item["status"] == "blocked"]
        selected = safe_ranked[:top_k]
        for rank, item in enumerate(selected, start=1):
            item["rank"] = rank
        payload = {
            "results": selected,
            "blocked_preview": blocked[: min(5, top_k)] if include_blocked else [],
            "meta": {
                "candidate_count": len(candidate_ids),
                "blocked_count": len(blocked),
                "review_count": sum(
                    item["status"] == "pharmacist_review"
                    for item in all_candidates
                ),
                "resolved_current_medications": current_ids,
                "unresolved_medications": unresolved_current,
                "unresolved_allergies": unresolved_allergies,
                "unresolved_candidates": unresolved_candidates,
                "weights": weights,
                "disclaimer": self.disclaimer(),
            },
        }
        return RankResult(payload, ranked)

    @staticmethod
    def disclaimer() -> str:
        return (
            "仅供科研和人工复核，不构成处方建议。DDI 严重度由公开数据描述规则推断，"
            "缺失数据不等于安全。"
        )

