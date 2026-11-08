from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .normalize import basic_normalize


@dataclass
class SafetyAssessment:
    status: str
    risk_score: float
    evidence_score: float
    reasons: list[str]
    interactions: list[dict[str, str]]


class SafetyModel:
    def __init__(
        self,
        catalog: pd.DataFrame,
        ddi_pairs: pd.DataFrame,
        toxicity_summary: pd.DataFrame,
        labeled_drug_ids: set[str] | None = None,
    ) -> None:
        self.catalog = catalog.set_index("drug_id", drop=False)
        self.ddi_pairs = ddi_pairs
        self.pair_lookup = ddi_pairs.set_index("pair_key").to_dict(orient="index")
        self.toxicity = toxicity_summary.set_index("drug_id").to_dict(orient="index")
        self.labeled_drug_ids = labeled_drug_ids or set()
        self.alias_to_id: dict[str, str] = {}
        for row in catalog.itertuples(index=False):
            self.alias_to_id[basic_normalize(row.canonical_name)] = row.drug_id
            for alias in row.aliases:
                self.alias_to_id.setdefault(basic_normalize(alias), row.drug_id)

    def resolve(self, name: str) -> str | None:
        return self.alias_to_id.get(basic_normalize(name))

    def assess(
        self,
        candidate_id: str,
        current_ids: list[str],
        allergy_ids: set[str],
        unresolved_medications: list[str],
        unresolved_allergies: list[str] | None = None,
    ) -> SafetyAssessment:
        unresolved_allergies = unresolved_allergies or []
        reasons: list[str] = []
        interactions: list[dict[str, str]] = []
        if candidate_id in allergy_ids:
            return SafetyAssessment(
                status="blocked",
                risk_score=1.0,
                evidence_score=1.0,
                reasons=["候选药命中已知过敏记录"],
                interactions=[],
            )

        max_severity = 0.0
        for current_id in current_ids:
            if current_id == candidate_id:
                continue
            pair_key = "|".join(sorted((candidate_id, current_id)))
            pair = self.pair_lookup.get(pair_key)
            if not pair:
                continue
            severity = str(pair.get("severity", "moderate"))
            score = float(pair.get("severity_score", 0.55))
            max_severity = max(max_severity, score)
            interactions.append(
                {
                    "drug_id": current_id,
                    "drug_name": self._name(current_id),
                    "severity": severity,
                    "description": str(pair.get("interaction_text", ""))[:1000],
                }
            )
            reasons.append(
                f"与当前用药 {self._name(current_id)} 存在{self._severity_zh(severity)}相互作用"
            )

        tox = self.toxicity.get(candidate_id, {})
        toxicity_prior = float(tox.get("toxicity_prior", 0.0) or 0.0)
        serious_count = int(tox.get("serious_adverse_event_records", 0) or 0)
        if serious_count:
            reasons.append(f"NCATS 记录到 {serious_count} 条严重不良反应记录")

        evidence_score = 1.0
        if unresolved_medications:
            evidence_score -= 0.35
            reasons.append("部分当前用药未能映射，DDI 检查不完整")
        if unresolved_allergies:
            evidence_score -= 0.35
            reasons.append("部分过敏记录未能映射，过敏检查不完整")
        row = self.catalog.loc[candidate_id]
        if not bool(row["candidate_eligible"]):
            evidence_score -= 0.25
        if candidate_id not in self.labeled_drug_ids:
            evidence_score -= 0.05
        evidence_score = float(np.clip(evidence_score, 0.0, 1.0))

        if max_severity >= 1.0:
            status = "blocked"
        elif (
            interactions
            or unresolved_medications
            or unresolved_allergies
            or toxicity_prior >= 0.80
        ):
            status = "pharmacist_review"
        elif evidence_score < 0.65:
            status = "pharmacist_review"
        else:
            status = "eligible_for_review"
        if status != "blocked" and toxicity_prior > 0:
            reasons.append("候选药具有不良反应先验，需要人工复核")
        if not reasons:
            reasons.append("未检索到明确严重 DDI 或过敏冲突，但仍需人工复核")
        risk_score = float(
            np.clip(max(max_severity, 0.35 * toxicity_prior) + 0.15 * (1 - evidence_score), 0, 1)
        )
        return SafetyAssessment(
            status=status,
            risk_score=risk_score,
            evidence_score=evidence_score,
            reasons=reasons,
            interactions=interactions,
        )

    def _name(self, drug_id: str) -> str:
        if drug_id in self.catalog.index:
            return str(self.catalog.loc[drug_id, "canonical_name"])
        return drug_id

    @staticmethod
    def _severity_zh(severity: str) -> str:
        return {"high": "高风险", "moderate": "需关注"}.get(severity, "潜在")

