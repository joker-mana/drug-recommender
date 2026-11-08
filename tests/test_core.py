from __future__ import annotations

import numpy as np
import pandas as pd

from drugrec.cf_model import CFArtifacts, CollaborativeFilter
from drugrec.normalize import basic_normalize
from drugrec.safety import SafetyModel


def test_drug_name_normalization() -> None:
    assert basic_normalize("Lisinopril 10 MG Oral Tablet") == "lisinopril"
    assert basic_normalize("Clopidogrel Bisulfate 75 mg") == "clopidogrel"
    assert basic_normalize("Alendronate sodium") == "alendronate"


def _safety_model() -> SafetyModel:
    catalog = pd.DataFrame(
        [
            {
                "drug_id": "drug:a",
                "canonical_name": "Drug A",
                "aliases": ["drug a"],
                "candidate_eligible": True,
            },
            {
                "drug_id": "drug:b",
                "canonical_name": "Drug B",
                "aliases": ["drug b"],
                "candidate_eligible": True,
            },
        ]
    )
    ddi = pd.DataFrame(
        [
            {
                "pair_key": "drug:a|drug:b",
                "drug_a_id": "drug:a",
                "drug_b_id": "drug:b",
                "severity": "high",
                "severity_score": 1.0,
                "interaction_text": "severe bleeding risk",
            }
        ]
    )
    toxicity = pd.DataFrame(
        [
            {
                "drug_id": "drug:a",
                "toxicity_prior": 0.0,
                "serious_adverse_event_records": 0,
            },
            {
                "drug_id": "drug:b",
                "toxicity_prior": 0.0,
                "serious_adverse_event_records": 0,
            },
        ]
    )
    return SafetyModel(
        catalog,
        ddi,
        toxicity,
        labeled_drug_ids={"drug:a", "drug:b"},
    )


def test_safety_gate_blocks_high_ddi() -> None:
    assessment = _safety_model().assess(
        "drug:a",
        current_ids=["drug:b"],
        allergy_ids=set(),
        unresolved_medications=[],
    )
    assert assessment.status == "blocked"
    assert assessment.risk_score == 1.0


def test_safety_gate_blocks_allergy() -> None:
    assessment = _safety_model().assess(
        "drug:a",
        current_ids=[],
        allergy_ids={"drug:a"},
        unresolved_medications=[],
    )
    assert assessment.status == "blocked"


def test_collaborative_filter_scores_shared_history() -> None:
    model = CollaborativeFilter(
        CFArtifacts(
            drug_ids=["a", "b", "c"],
            similarity=np.array(
                [
                    [0.0, 0.9, 0.1],
                    [0.9, 0.0, 0.2],
                    [0.1, 0.2, 0.0],
                ],
                dtype=np.float32,
            ),
            popularity=np.array([2.0, 2.0, 1.0], dtype=np.float32),
        )
    )
    scores = model.score(["a"], ["b", "c"])
    assert scores[0] > scores[1]

