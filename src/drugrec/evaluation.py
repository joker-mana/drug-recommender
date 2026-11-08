from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .cf_model import CollaborativeFilter
from .ranker import DrugRankingSystem, _minmax


@dataclass
class EvaluationScenario:
    patient_id: str
    snapshot: pd.Timestamp
    history_ids: list[str]
    current_names: list[str]
    current_ids: list[str]
    unresolved_current: list[str]
    conditions: list[str]
    allergy_names: list[str]
    allergy_ids: list[str]
    target_id: str
    target_name: str
    query: str


def build_scenarios(
    system: DrugRankingSystem,
    limit: int | None = None,
) -> tuple[list[EvaluationScenario], set[int]]:
    meds = system.medications.dropna(subset=["START", "drug_id"]).copy()
    meds = meds.sort_values(["PATIENT", "START"]).reset_index()
    heldout_rows = meds.groupby("PATIENT").tail(1)
    heldout_indices = set(heldout_rows["index"].tolist())
    scenarios = []
    for row in heldout_rows.sort_values("PATIENT").itertuples(index=False):
        patient_id = row.PATIENT
        snapshot = row.START
        previous = meds[
            (meds["PATIENT"] == patient_id)
            & (meds["START"] < snapshot)
        ].copy()
        if previous.empty:
            continue
        active = previous[
            previous["STOP"].isna() | previous["STOP"].ge(snapshot)
        ]
        if active.empty:
            active = previous.nlargest(5, "START")
        conditions = system.conditions[
            (system.conditions["PATIENT"] == patient_id)
            & system.conditions["START"].le(snapshot)
            & (
                system.conditions["STOP"].isna()
                | system.conditions["STOP"].ge(snapshot)
            )
        ]["DESCRIPTION"].drop_duplicates().tolist()
        reasons = []
        if getattr(row, "REASONDESCRIPTION", None) not in (None, ""):
            reasons.append(str(row.REASONDESCRIPTION))
        query = " ".join(reasons + conditions)
        current_names = active["DESCRIPTION"].drop_duplicates().tolist()
        current_ids = active["drug_id"].drop_duplicates().tolist()
        resolved_ids, unresolved = system.resolve_many(current_names)
        current_ids = list(dict.fromkeys(current_ids + resolved_ids))
        patient_allergies = system.allergies[
            system.allergies["PATIENT"] == patient_id
        ]
        allergy_names = patient_allergies["DESCRIPTION"].drop_duplicates().tolist()
        allergy_ids = (
            patient_allergies["drug_id"].dropna().drop_duplicates().tolist()
        )
        scenarios.append(
            EvaluationScenario(
                patient_id=patient_id,
                snapshot=snapshot,
                history_ids=previous["drug_id"].drop_duplicates().tolist(),
                current_names=current_names,
                current_ids=current_ids,
                unresolved_current=unresolved,
                conditions=conditions,
                allergy_names=allergy_names,
                allergy_ids=allergy_ids,
                target_id=row.drug_id,
                target_name=row.DESCRIPTION,
                query=query,
            )
        )
        if limit is not None and len(scenarios) >= limit:
            break
    return scenarios, heldout_indices


def _rank_metrics(
    scores: np.ndarray,
    candidate_ids: list[str],
    target_id: str,
    blocked_mask: np.ndarray | None,
    k: int,
) -> dict[str, float]:
    ranking = np.argsort(-scores, kind="stable")
    if blocked_mask is not None:
        ranking = ranking[~blocked_mask[ranking]]
    top_k = ranking[:k]
    target_position = np.flatnonzero(ranking == candidate_ids.index(target_id))
    if target_position.size:
        rank = int(target_position[0]) + 1
        recall = float(rank <= k)
        ndcg = 1.0 / math.log2(rank + 1) if rank <= k else 0.0
        rr = 1.0 / rank
    else:
        recall = ndcg = rr = 0.0
    block_source = np.zeros(len(scores), dtype=bool) if blocked_mask is None else blocked_mask
    unsafe = float(block_source[top_k].sum() / max(1, len(top_k)))
    return {
        f"recall@{k}": recall,
        f"ndcg@{k}": ndcg,
        "mrr": rr,
        "unsafe@10": unsafe,
    }


def evaluate_system(
    system: DrugRankingSystem,
    *,
    limit: int | None = None,
    k: int = 10,
) -> dict:
    scenarios, heldout_indices = build_scenarios(system, limit=limit)
    evaluation_meds = system.medications.drop(index=heldout_indices, errors="ignore")
    evaluation_cf = CollaborativeFilter.fit(
        evaluation_meds,
        system.eligible_ids,
    )
    rows = []
    for index, scenario in enumerate(scenarios, start=1):
        candidates = [
            drug_id
            for drug_id in system.eligible_ids
            if drug_id not in scenario.current_ids
        ]
        if scenario.target_id not in candidates:
            candidates.append(scenario.target_id)
        text_scores = _minmax(system.text_model.score(scenario.query, candidates))
        cf_scores = _minmax(
            evaluation_cf.score(scenario.current_ids, candidates)
        )
        popularity = _minmax(
            evaluation_cf.popularity_score(candidates)
        )
        graph = _minmax(
            system.graph_model.score(scenario.current_ids, candidates)
        )
        assessments = [
            system.safety_model.assess(
                drug_id,
                scenario.current_ids,
                set(scenario.allergy_ids),
                scenario.unresolved_current,
            )
            for drug_id in candidates
        ]
        blocked = np.array(
            [item.status == "blocked" for item in assessments],
            dtype=bool,
        )
        risk = np.array([item.risk_score for item in assessments])
        evidence = np.array([item.evidence_score for item in assessments])
        weights = system.config["ranking"]["weights"]
        relevance_hybrid = (
            weights["text"] * text_scores
            + weights["collaborative"] * cf_scores
            + weights["graph"] * graph
            + weights["popularity"] * popularity
        )
        hybrid = (
            relevance_hybrid
            - float(system.config["ranking"]["risk_penalty"]) * risk
            - float(system.config["ranking"]["unknown_evidence_penalty"])
            * (1 - evidence)
        )
        model_scores = {
            "popularity": popularity,
            "text": text_scores,
            "cf": cf_scores,
            "graph": graph,
            "relevance_hybrid": relevance_hybrid,
            "hybrid": hybrid,
        }
        for model_name, scores in model_scores.items():
            metrics = _rank_metrics(
                scores,
                candidates,
                scenario.target_id,
                None,
                k,
            )
            rows.append(
                {
                    "patient_id": scenario.patient_id,
                    "snapshot": scenario.snapshot,
                    "model": model_name,
                    "candidate_count": len(candidates),
                    "blocked_count": int(blocked.sum()),
                    **metrics,
                }
            )
        metrics = _rank_metrics(
            relevance_hybrid,
            candidates,
            scenario.target_id,
            blocked,
            k,
        )
        rows.append(
            {
                "patient_id": scenario.patient_id,
                "snapshot": scenario.snapshot,
                "model": "hybrid_safe",
                "candidate_count": len(candidates),
                "blocked_count": int(blocked.sum()),
                **metrics,
            }
        )
        if index % 20 == 0:
            print(f"evaluated {index}/{len(scenarios)} patients", flush=True)

    detail = pd.DataFrame(rows)
    summary = (
        detail.drop(columns=["patient_id", "snapshot"])
        .groupby("model")
        .agg(["mean", "std", "count"])
    )
    summary.columns = [f"{column}_{stat}" for column, stat in summary.columns]
    flat_summary = summary.reset_index()
    return {
        "scenario_count": len(scenarios),
        "heldout_medication_rows": len(heldout_indices),
        "k": k,
        "summary": flat_summary.to_dict(orient="records"),
        "detail": detail,
    }


def save_evaluation(result: dict, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    detail = result["detail"]
    detail.to_csv(report_dir / "evaluation_detail.csv", index=False)
    summary = pd.DataFrame(result["summary"])
    summary.to_csv(report_dir / "evaluation_summary.csv", index=False)
    metadata = {
        key: value
        for key, value in result.items()
        if key not in {"detail", "summary"}
    }
    metadata["summary"] = result["summary"]
    (report_dir / "evaluation_summary.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

