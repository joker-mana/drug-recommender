from __future__ import annotations

from drugrec.ranker import DrugRankingSystem


def test_real_artifacts_rank_without_blocked_candidates() -> None:
    system = DrugRankingSystem()
    patients = system.patient_options()
    patient_id = patients.loc[patients["medication_count"].gt(0), "PATIENT"].iloc[0]
    context = system.patient_context(patient_id)
    result = system.rank(
        target_indication=context["target_indication"],
        conditions=context["conditions"],
        current_medications=context["current_medications"],
        allergies=context["allergies"],
        top_k=5,
    )
    assert result.payload["results"]
    assert all(
        item["status"] != "blocked" for item in result.payload["results"]
    )
    assert all("disclaimer" in result.payload["meta"] for _ in [0])


def test_real_high_ddi_pair_is_blocked() -> None:
    system = DrugRankingSystem()
    high_pair = system.ddi_pairs[system.ddi_pairs["severity"] == "high"].iloc[0]
    assessment = system.safety_model.assess(
        str(high_pair["drug_a_id"]),
        current_ids=[str(high_pair["drug_b_id"])],
        allergy_ids=set(),
        unresolved_medications=[],
    )
    assert assessment.status == "blocked"

