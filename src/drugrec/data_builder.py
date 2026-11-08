from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .io_utils import iter_json_array
from .normalize import basic_normalize, clean_whitespace, drug_id_for_key, flatten_text
from .paths import (
    FRDB_DIR,
    OPENFDA_LABEL_PATH,
    PROCESSED_DIR,
    SYNTHEA_DIR,
    ZENODO_DDI_DIR,
)


OPENFDA_RELEVANCE_SECTIONS = (
    "indications_and_usage",
    "purpose",
    "uses",
    "mechanism_of_action",
    "clinical_pharmacology",
)

OPENFDA_SAFETY_SECTIONS = (
    "contraindications",
    "warnings",
    "boxed_warning",
    "drug_interactions",
    "adverse_reactions",
    "precautions",
)

HIGH_RISK_PATTERNS = re.compile(
    r"\b("
    r"life[ -]?threatening|fatal|death|serious|sever|contraindicat|"
    r"hemorrhag|bleeding|respiratory depression|cardiac arrest|"
    r"arrhythm|qt prolong|torsades|serotonin syndrome|"
    r"hypertensive crisis|acute kidney|renal failure|seizure|coma|"
    r"aplastic anemia|agranulocytosis|neutropenia|thrombosis|"
    r"do not|must not|avoid"
    r")\b",
    flags=re.IGNORECASE,
)

SERIOUS_AE_PATTERN = re.compile(
    r"serious|severe|fatal|grade\s*[3-5]|life[ -]?threatening",
    flags=re.IGNORECASE,
)

MANUAL_ALIASES = {
    "aspirin": "acetylsalicylic acid",
    "alendronate": "alendronic acid",
    "paracetamol": "acetaminophen",
    "adrenaline": "epinephrine",
    "noradrenaline": "norepinephrine",
}


def _naive_datetime(values: object) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", utc=True).dt.tz_localize(None)


@dataclass
class DrugRecord:
    drug_id: str
    norm_key: str
    canonical_name: str
    aliases: set[str] = field(default_factory=set)
    cids: set[str] = field(default_factory=set)
    atc_codes: set[str] = field(default_factory=set)
    rxcui: set[str] = field(default_factory=set)
    unii: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)


class DrugRegistry:
    def __init__(self) -> None:
        self.records: dict[str, DrugRecord] = {}
        self.alias_to_id: dict[str, str] = {}

    def add(
        self,
        name: object,
        source: str,
        *,
        display_name: object | None = None,
        cid: object | None = None,
        atc: object | None = None,
        rxcui: object | None = None,
        unii: object | None = None,
    ) -> str | None:
        norm_key = basic_normalize(name)
        if not norm_key:
            return None
        existing_id = self.alias_to_id.get(norm_key)
        if existing_id is None:
            drug_id = drug_id_for_key(norm_key)
            display = clean_whitespace(display_name or name)
            self.records[drug_id] = DrugRecord(
                drug_id=drug_id,
                norm_key=norm_key,
                canonical_name=display,
            )
            existing_id = drug_id

        record = self.records[existing_id]
        record.aliases.add(norm_key)
        record.sources.add(source)
        self.alias_to_id[norm_key] = existing_id
        for target, value in (
            (record.cids, cid),
            (record.atc_codes, atc),
            (record.rxcui, rxcui),
            (record.unii, unii),
        ):
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            if isinstance(value, (list, tuple, set)):
                target.update(str(item) for item in value if str(item).strip())
            else:
                text = str(value).strip()
                if text:
                    target.add(text)
        return existing_id

    def add_alias(self, alias: object, drug_id: str) -> None:
        key = basic_normalize(alias)
        if key:
            self.alias_to_id.setdefault(key, drug_id)
            self.records[drug_id].aliases.add(key)

    def resolve(self, name: object) -> str | None:
        return self.alias_to_id.get(basic_normalize(name))

    def keys(self) -> list[str]:
        return list(self.alias_to_id)

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for record in self.records.values():
            rows.append(
                {
                    "drug_id": record.drug_id,
                    "norm_key": record.norm_key,
                    "canonical_name": record.canonical_name,
                    "aliases": sorted(record.aliases),
                    "cids": sorted(record.cids),
                    "atc_codes": sorted(record.atc_codes),
                    "rxcui": sorted(record.rxcui),
                    "unii": sorted(record.unii),
                    "sources": sorted(record.sources),
                }
            )
        return pd.DataFrame(rows).sort_values("canonical_name").reset_index(drop=True)


def _first_text(values: object) -> str:
    text = clean_whitespace(values)
    return text.split(" ; ", 1)[0] if " ; " in text else text


def _extract_label_sections(record: dict[str, Any]) -> tuple[str, str]:
    relevance = []
    safety = []
    for key in OPENFDA_RELEVANCE_SECTIONS:
        value = clean_whitespace(record.get(key))
        if value:
            relevance.append(f"{key}: {value}")
    for key in OPENFDA_SAFETY_SECTIONS:
        value = clean_whitespace(record.get(key))
        if value:
            safety.append(f"{key}: {value}")
    return " ".join(relevance), " ".join(safety)


def parse_openfda_labels(
    path: Path,
    registry: DrugRegistry,
    max_text_chars: int = 80_000,
) -> tuple[pd.DataFrame, dict[str, str]]:
    label_rows: list[dict[str, Any]] = []
    rxcui_to_drug: dict[str, str] = {}
    for index, record in enumerate(iter_json_array(path, "results")):
        openfda = record.get("openfda") or {}
        generic_names = openfda.get("generic_name") or []
        substance_names = openfda.get("substance_name") or []
        brand_names = openfda.get("brand_name") or []
        rxcui_values = [str(item) for item in (openfda.get("rxcui") or [])]

        primary_name = (
            _first_text(generic_names)
            or _first_text(substance_names)
            or _first_text(brand_names)
        )
        if not primary_name:
            continue
        drug_id = registry.add(
            primary_name,
            source="openfda_label",
            display_name=primary_name,
            rxcui=rxcui_values,
        )
        if drug_id is None:
            continue
        # Generic and brand names identify the labeled product. Individual
        # substance names inside a combination label must not turn a single
        # ingredient into an alias for the whole combination product.
        aliases = list(generic_names) + list(brand_names)
        if len(generic_names) <= 1 and len(substance_names) <= 1:
            aliases += list(substance_names)
        for alias in aliases:
            registry.add_alias(alias, drug_id)
        for code in rxcui_values:
            rxcui_to_drug.setdefault(code, drug_id)

        relevance_text, safety_text = _extract_label_sections(record)
        label_rows.append(
            {
                "record_index": index,
                "set_id": record.get("set_id"),
                "effective_time": record.get("effective_time"),
                "drug_id": drug_id,
                "primary_name": primary_name,
                "generic_names": generic_names,
                "brand_names": brand_names,
                "substance_names": substance_names,
                "rxcui": rxcui_values,
                "relevance_text": relevance_text[:max_text_chars],
                "safety_text": safety_text[:max_text_chars],
            }
        )
    return pd.DataFrame(label_rows), rxcui_to_drug


def _severity_for_interaction(text: str) -> tuple[str, float]:
    normalized = clean_whitespace(text)
    if HIGH_RISK_PATTERNS.search(normalized):
        return "high", 1.0
    # The row itself is evidence of a known interaction. It is therefore a
    # review signal, not a green "safe" label.
    return "moderate", 0.55


def build_ddi(
    registry: DrugRegistry,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(ZENODO_DDI_DIR / "ddi_2026.csv")
    raw = raw.rename(columns={"drug 1": "drug_a_name", "drug 2": "drug_b_name"})
    raw["drug_a_id"] = raw["drug_a_name"].map(registry.resolve)
    raw["drug_b_id"] = raw["drug_b_name"].map(registry.resolve)
    raw = raw.dropna(subset=["drug_a_id", "drug_b_id"]).copy()
    raw["severity"], raw["severity_score"] = zip(
        *raw["interaction"].map(_severity_for_interaction)
    )
    left = raw[["drug_a_id", "drug_b_id"]].min(axis=1)
    right = raw[["drug_a_id", "drug_b_id"]].max(axis=1)
    raw["drug_a_id"] = left
    raw["drug_b_id"] = right
    raw["pair_key"] = raw["drug_a_id"] + "|" + raw["drug_b_id"]

    severity_rank = {"moderate": 1, "high": 2}
    rows = []
    for pair_key, group in raw.groupby("pair_key", sort=False):
        drug_a, drug_b = pair_key.split("|", 1)
        descriptions = list(dict.fromkeys(group["interaction"].astype(str)))
        max_rank = max(severity_rank.get(item, 0) for item in group["severity"])
        severity = "high" if max_rank >= 2 else "moderate"
        rows.append(
            {
                "pair_key": pair_key,
                "drug_a_id": drug_a,
                "drug_b_id": drug_b,
                "severity": severity,
                "severity_score": 1.0 if severity == "high" else 0.55,
                "interaction_text": " || ".join(descriptions)[:8000],
                "record_count": len(group),
            }
        )
    pairs = pd.DataFrame(rows)
    return raw, pairs


def build_frdb(
    registry: DrugRegistry,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    drugs = pd.read_csv(FRDB_DIR / "frdb-drugs.tsv", sep="\t")
    drugs["drug_id"] = drugs["compound_name"].map(registry.resolve)
    drugs["unii"] = drugs["compound_unii"]
    for row in drugs.itertuples(index=False):
        if pd.notna(row.drug_id):
            registry.records[row.drug_id].unii.add(str(row.unii))

    ddi = pd.read_csv(FRDB_DIR / "frdb-ddi.tsv", sep="\t", low_memory=False)
    ddi = ddi.merge(
        drugs[["compound_id", "compound_name", "drug_id"]],
        on="compound_id",
        how="left",
    )

    toxicity = pd.read_csv(FRDB_DIR / "frdb-toxicity.tsv", sep="\t", low_memory=False)
    adverse = pd.read_csv(
        FRDB_DIR / "frdb-adverseevents.tsv", sep="\t", low_memory=False
    )
    adverse["is_serious"] = (
        adverse["adverseevents_severity"]
        .fillna("")
        .astype(str)
        .str.contains(SERIOUS_AE_PATTERN)
    )
    joined = adverse.merge(
        toxicity[["id", "compound_id"]].rename(columns={"id": "tox_id"}),
        on="tox_id",
        how="left",
    ).merge(
        drugs[["compound_id", "compound_name", "drug_id"]],
        on="compound_id",
        how="left",
    )
    summary = (
        joined.dropna(subset=["drug_id"])
        .groupby("drug_id", as_index=False)
        .agg(
            compound_name=("compound_name", "first"),
            adverse_event_records=("id", "count"),
            serious_adverse_event_records=("is_serious", "sum"),
            toxicity_study_records=("tox_id", "nunique"),
        )
    )
    max_serious = summary["serious_adverse_event_records"].max()
    if max_serious and max_serious > 0:
        summary["toxicity_prior"] = (
            summary["serious_adverse_event_records"].map(math.log1p)
            / math.log1p(float(max_serious))
        ).clip(0, 1)
    else:
        summary["toxicity_prior"] = 0.0
    return drugs, ddi, summary


def build_synthea(
    registry: DrugRegistry,
    rxcui_to_drug: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    patients = pd.read_csv(SYNTHEA_DIR / "patients.csv")
    medications = pd.read_csv(SYNTHEA_DIR / "medications.csv")
    conditions = pd.read_csv(SYNTHEA_DIR / "conditions.csv")
    allergies = pd.read_csv(SYNTHEA_DIR / "allergies.csv")

    def map_medication(row: pd.Series) -> str | None:
        code = str(row["CODE"]).split(",")[0].strip()
        drug_id = rxcui_to_drug.get(code)
        if drug_id is None:
            drug_id = registry.resolve(row["DESCRIPTION"])
        if drug_id is None:
            drug_id = registry.add(
                row["DESCRIPTION"],
                source="synthea",
                display_name=row["DESCRIPTION"],
                rxcui=code,
            )
        return drug_id

    medications["drug_id"] = medications.apply(map_medication, axis=1)
    medications["START"] = _naive_datetime(medications["START"])
    medications["STOP"] = _naive_datetime(medications["STOP"])
    conditions["START"] = _naive_datetime(conditions["START"])
    conditions["STOP"] = _naive_datetime(conditions["STOP"])
    allergies["START"] = _naive_datetime(allergies["START"])
    allergies["STOP"] = _naive_datetime(allergies["STOP"])
    allergies["drug_id"] = allergies["DESCRIPTION"].map(registry.resolve)

    # Keep a compact clinical history; claims and billing tables are unnecessary
    # for the ranking and safety demonstration.
    med_columns = [
        "START",
        "STOP",
        "PATIENT",
        "ENCOUNTER",
        "CODE",
        "DESCRIPTION",
        "REASONCODE",
        "REASONDESCRIPTION",
        "drug_id",
    ]
    cond_columns = [
        "START",
        "STOP",
        "PATIENT",
        "ENCOUNTER",
        "CODE",
        "DESCRIPTION",
    ]
    allergy_columns = [
        "START",
        "STOP",
        "PATIENT",
        "CODE",
        "DESCRIPTION",
        "SEVERITY1",
        "REACTION1",
        "drug_id",
    ]
    patients = patients.rename(columns={"Id": "PATIENT"})
    patients["BIRTHDATE"] = _naive_datetime(patients["BIRTHDATE"])
    return (
        medications[med_columns],
        conditions[cond_columns],
        patients[["PATIENT", "BIRTHDATE", "GENDER", "RACE", "ETHNICITY"]],
        allergies[allergy_columns],
    )


def _combine_nonempty(values: pd.Series) -> str:
    parts = []
    for value in values:
        text = clean_whitespace(value)
        if text:
            parts.append(text)
    return " ".join(dict.fromkeys(parts))


def build_documents(
    registry: DrugRegistry,
    labels: pd.DataFrame,
    ddi_raw: pd.DataFrame,
    frdb_ddi: pd.DataFrame,
) -> pd.DataFrame:
    label_relevance = (
        labels.groupby("drug_id")["relevance_text"].agg(_combine_nonempty).to_dict()
    )
    label_safety = (
        labels.groupby("drug_id")["safety_text"].agg(_combine_nonempty).to_dict()
    )

    ddi_context: dict[str, list[str]] = defaultdict(list)
    for row in ddi_raw.itertuples(index=False):
        ddi_context[row.drug_a_id].append(str(row.interaction))
        ddi_context[row.drug_b_id].append(str(row.interaction))

    target_context: dict[str, list[str]] = defaultdict(list)
    for row in frdb_ddi.dropna(subset=["drug_id"]).itertuples(index=False):
        target = clean_whitespace(getattr(row, "ddi_target", ""))
        relation = clean_whitespace(getattr(row, "ddi_relation", ""))
        if target:
            target_context[row.drug_id].append(f"{relation} {target}".strip())

    rows = []
    for record in registry.records.values():
        relevance = label_relevance.get(record.drug_id, "")
        safety = label_safety.get(record.drug_id, "")
        interactions = " ".join(dict.fromkeys(ddi_context.get(record.drug_id, [])))
        targets = " ".join(dict.fromkeys(target_context.get(record.drug_id, [])))
        if not relevance:
            relevance = f"{interactions} {safety}".strip()
        text = " ".join(
            part for part in (record.canonical_name, relevance, safety, targets) if part
        )[:80_000]
        rows.append(
            {
                "drug_id": record.drug_id,
                "canonical_name": record.canonical_name,
                "drug_name_text": record.canonical_name,
                "relevance_text": relevance[:80_000],
                "safety_text": safety[:80_000],
                "interaction_text": interactions[:40_000],
                "target_text": targets[:20_000],
                "document_text": text,
                "has_label": record.drug_id in label_relevance,
                "has_ddi": record.drug_id in ddi_context,
            }
        )
    return pd.DataFrame(rows)


def build_processed_data() -> dict[str, Any]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    registry = DrugRegistry()

    catalog_raw = pd.read_csv(ZENODO_DDI_DIR / "drugs_atc_cid.csv")
    for row in catalog_raw.itertuples(index=False):
        registry.add(
            row.drug_name,
            source="zenodo_catalog",
            display_name=row.drug_name,
            cid=row.cid,
            atc=row.atc_codes,
        )
    for alias, canonical in MANUAL_ALIASES.items():
        canonical_id = registry.resolve(canonical)
        if canonical_id:
            registry.add_alias(alias, canonical_id)

    labels, rxcui_to_drug = parse_openfda_labels(OPENFDA_LABEL_PATH, registry)
    medications, conditions, patients, allergies = build_synthea(
        registry, rxcui_to_drug
    )

    # Add remaining DDI names after openFDA aliases have been registered.
    ddi_names = pd.read_csv(ZENODO_DDI_DIR / "ddi_2026.csv")
    for column in ("drug 1", "drug 2"):
        for name in ddi_names[column].dropna().unique():
            if registry.resolve(name) is None:
                registry.add(name, source="zenodo_ddi")

    frdb_drugs, frdb_ddi, toxicity = build_frdb(registry)
    for row in frdb_drugs.itertuples(index=False):
        if pd.isna(row.drug_id):
            registry.add(
                row.compound_name,
                source="ncats_frdb",
                display_name=row.compound_name,
                unii=row.unii,
            )

    ddi_raw, ddi_pairs = build_ddi(registry)
    documents = build_documents(registry, labels, ddi_raw, frdb_ddi)

    registry_frame = registry.to_frame()
    medication_popularity = (
        medications.dropna(subset=["drug_id"])
        .groupby("drug_id", as_index=False)
        .size()
        .rename(columns={"size": "synthea_prescription_count"})
    )
    registry_frame = registry_frame.merge(
        medication_popularity, on="drug_id", how="left"
    ).fillna({"synthea_prescription_count": 0})
    registry_frame["synthea_prescription_count"] = registry_frame[
        "synthea_prescription_count"
    ].astype(int)
    registry_frame["candidate_eligible"] = (
        registry_frame["atc_codes"].map(len).gt(0)
        | registry_frame["drug_id"].isin(documents.loc[documents["has_label"], "drug_id"])
        | registry_frame["synthea_prescription_count"].gt(0)
    )
    registry_frame = registry_frame.merge(toxicity, on="drug_id", how="left")
    registry_frame["toxicity_prior"] = registry_frame["toxicity_prior"].fillna(0.0)
    registry_frame["adverse_event_records"] = registry_frame[
        "adverse_event_records"
    ].fillna(0).astype(int)
    registry_frame["serious_adverse_event_records"] = registry_frame[
        "serious_adverse_event_records"
    ].fillna(0).astype(int)
    registry_frame["toxicity_study_records"] = registry_frame[
        "toxicity_study_records"
    ].fillna(0).astype(int)
    registry_frame = registry_frame.drop(columns=["compound_name"], errors="ignore")

    outputs = {
        "drug_catalog": registry_frame,
        "drug_documents": documents,
        "openfda_label_documents": labels,
        "ddi_raw": ddi_raw,
        "ddi_pairs": ddi_pairs,
        "frdb_drugs": frdb_drugs,
        "frdb_ddi": frdb_ddi,
        "toxicity_summary": toxicity,
        "synthea_medications": medications,
        "synthea_conditions": conditions,
        "synthea_patients": patients,
        "synthea_allergies": allergies,
    }
    for name, frame in outputs.items():
        frame.to_parquet(PROCESSED_DIR / f"{name}.parquet", index=False)

    summary = {
        "labels": int(len(labels)),
        "label_drugs": int(labels["drug_id"].nunique()),
        "registry_drugs": int(len(registry_frame)),
        "candidate_drugs": int(registry_frame["candidate_eligible"].sum()),
        "ddi_raw_rows": int(len(ddi_raw)),
        "ddi_unique_pairs": int(len(ddi_pairs)),
        "synthea_medication_rows": int(len(medications)),
        "synthea_medications_mapped": int(medications["drug_id"].notna().sum()),
        "synthea_unique_drugs": int(medications["drug_id"].nunique()),
        "synthea_patients_with_meds": int(medications["PATIENT"].nunique()),
        "toxicity_drugs": int(len(toxicity)),
    }
    (PROCESSED_DIR / "build_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary

