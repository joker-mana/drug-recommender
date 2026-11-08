from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class CFArtifacts:
    drug_ids: list[str]
    similarity: np.ndarray
    popularity: np.ndarray


class CollaborativeFilter:
    def __init__(self, artifacts: CFArtifacts) -> None:
        self.artifacts = artifacts
        self.id_to_index = {
            drug_id: index for index, drug_id in enumerate(artifacts.drug_ids)
        }

    @classmethod
    def fit(
        cls,
        medications: pd.DataFrame,
        eligible_drug_ids: list[str],
    ) -> "CollaborativeFilter":
        events = medications.dropna(subset=["drug_id"]).copy()
        valid_ids = [
            drug_id
            for drug_id in eligible_drug_ids
            if drug_id in set(events["drug_id"])
        ]
        id_to_index = {drug_id: index for index, drug_id in enumerate(valid_ids)}
        patient_ids = sorted(events["PATIENT"].dropna().unique().tolist())
        patient_to_index = {
            patient_id: index for index, patient_id in enumerate(patient_ids)
        }
        rows = events["PATIENT"].map(patient_to_index).to_numpy()
        cols = events["drug_id"].map(id_to_index).to_numpy()
        matrix = sparse.csr_matrix(
            (
                np.ones(len(events), dtype=np.float32),
                (rows, cols),
            ),
            shape=(len(patient_ids), len(valid_ids)),
        )
        matrix.sum_duplicates()
        matrix.data = np.log1p(matrix.data)
        item_user = matrix.T.tocsr()
        similarity = cosine_similarity(item_user, dense_output=True).astype(np.float32)
        np.fill_diagonal(similarity, 0.0)
        popularity = np.asarray(matrix.sum(axis=0)).ravel().astype(np.float32)
        return cls(CFArtifacts(valid_ids, similarity, popularity))

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "item_similarity.npy", self.artifacts.similarity)
        np.save(directory / "popularity.npy", self.artifacts.popularity)
        (directory / "drug_ids.json").write_text(
            json.dumps(self.artifacts.drug_ids, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path) -> "CollaborativeFilter":
        drug_ids = json.loads((directory / "drug_ids.json").read_text(encoding="utf-8"))
        return cls(
            CFArtifacts(
                drug_ids=drug_ids,
                similarity=np.load(directory / "item_similarity.npy"),
                popularity=np.load(directory / "popularity.npy"),
            )
        )

    def score(self, context_drug_ids: list[str], candidate_drug_ids: list[str]) -> np.ndarray:
        context_indices = [
            self.id_to_index[drug_id]
            for drug_id in dict.fromkeys(context_drug_ids)
            if drug_id in self.id_to_index
        ]
        scores = np.zeros(len(candidate_drug_ids), dtype=np.float32)
        if not context_indices:
            return scores
        context_scores = self.artifacts.similarity[context_indices].sum(axis=0)
        maximum = float(context_scores.max())
        if maximum > 0:
            context_scores = context_scores / maximum
        for index, drug_id in enumerate(candidate_drug_ids):
            if drug_id in self.id_to_index:
                scores[index] = context_scores[self.id_to_index[drug_id]]
        return np.clip(scores, 0, 1)

    def popularity_score(self, candidate_drug_ids: list[str]) -> np.ndarray:
        scores = np.zeros(len(candidate_drug_ids), dtype=np.float32)
        for index, drug_id in enumerate(candidate_drug_ids):
            if drug_id in self.id_to_index:
                scores[index] = self.artifacts.popularity[
                    self.id_to_index[drug_id]
                ]
        maximum = float(scores.max())
        if maximum > 0:
            scores = scores / maximum
        return scores

