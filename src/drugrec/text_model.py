from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


@dataclass
class TextArtifacts:
    vectorizer: TfidfVectorizer
    svd: TruncatedSVD
    drug_ids: list[str]
    embeddings: np.ndarray


class TextModel:
    def __init__(self, artifacts: TextArtifacts) -> None:
        self.artifacts = artifacts
        self.id_to_index = {
            drug_id: index for index, drug_id in enumerate(artifacts.drug_ids)
        }

    @classmethod
    def fit(
        cls,
        documents: pd.DataFrame,
        *,
        max_features: int = 60_000,
        min_df: int = 2,
        max_df: float = 0.95,
        ngram_max: int = 2,
        lsa_components: int = 128,
    ) -> "TextModel":
        data = documents[
            documents["document_text"].fillna("").str.len().ge(20)
        ].reset_index(drop=True)
        vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, ngram_max),
            min_df=min_df,
            max_df=max_df,
            max_features=max_features,
            sublinear_tf=True,
            strip_accents="unicode",
            stop_words="english",
        )
        matrix = vectorizer.fit_transform(data["document_text"])
        components = max(2, min(lsa_components, min(matrix.shape) - 1))
        svd = TruncatedSVD(n_components=components, random_state=42)
        embeddings = normalize(svd.fit_transform(matrix)).astype(np.float32)
        return cls(
            TextArtifacts(
                vectorizer=vectorizer,
                svd=svd,
                drug_ids=data["drug_id"].tolist(),
                embeddings=embeddings,
            )
        )

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.artifacts.vectorizer, directory / "tfidf.joblib")
        joblib.dump(self.artifacts.svd, directory / "lsa.joblib")
        np.save(directory / "embeddings.npy", self.artifacts.embeddings)
        (directory / "drug_ids.txt").write_text(
            "\n".join(self.artifacts.drug_ids),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path) -> "TextModel":
        vectorizer = joblib.load(directory / "tfidf.joblib")
        svd = joblib.load(directory / "lsa.joblib")
        embeddings = np.load(directory / "embeddings.npy")
        drug_ids = (directory / "drug_ids.txt").read_text(encoding="utf-8").splitlines()
        return cls(TextArtifacts(vectorizer, svd, drug_ids, embeddings))

    def score(self, query: str, drug_ids: list[str]) -> np.ndarray:
        scores = np.zeros(len(drug_ids), dtype=np.float32)
        if not query.strip() or not drug_ids:
            return scores
        query_vector = self.artifacts.vectorizer.transform([query])
        query_embedding = self.artifacts.svd.transform(query_vector)
        query_embedding = normalize(query_embedding).astype(np.float32)[0]
        indices = np.array(
            [
                self.id_to_index[drug_id]
                for drug_id in drug_ids
                if drug_id in self.id_to_index
            ],
            dtype=np.int32,
        )
        present = np.array(
            [drug_id in self.id_to_index for drug_id in drug_ids],
            dtype=bool,
        )
        if indices.size:
            scores[present] = self.artifacts.embeddings[indices] @ query_embedding
        return np.clip(scores, 0, 1)

