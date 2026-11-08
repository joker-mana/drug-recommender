from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher


SALT_AND_ESTER_WORDS = {
    "acetate",
    "besylate",
    "bisulfate",
    "bitartrate",
    "calcium",
    "citrate",
    "dihydrate",
    "disodium",
    "fumarate",
    "hbr",
    "hcl",
    "hydrate",
    "hydrobromide",
    "hydrochloride",
    "magnesium",
    "maleate",
    "mesylate",
    "monohydrate",
    "phosphate",
    "potassium",
    "sodium",
    "succinate",
    "sulfate",
    "tartrate",
    "tosylate",
    "anhydrous",
}

FORM_WORDS = {
    "actuat",
    "aerosol",
    "auto",
    "chewable",
    "capsule",
    "cream",
    "delayed",
    "dose",
    "drops",
    "dry",
    "extended",
    "film",
    "gel",
    "inhalation",
    "inhaler",
    "implant",
    "injectable",
    "injection",
    "intrauterine",
    "inert",
    "kit",
    "liquid",
    "lotion",
    "metered",
    "mucosal",
    "nasal",
    "ointment",
    "ophthalmic",
    "oral",
    "otic",
    "pack",
    "patch",
    "prefilled",
    "powder",
    "rectal",
    "release",
    "solution",
    "spray",
    "sublingual",
    "suppository",
    "suspension",
    "syringe",
    "system",
    "tablet",
    "topical",
    "transdermal",
    "vaginal",
}

UNIT_PATTERN = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*)?"
    r"(?:mg|mcg|g|kg|ml|mL|l|unt|units?|%|meq|mmol|"
    r"mg/ml|mg/g|mg/mg|unt/ml|actuat|hr|hours?|day|days|week|weeks)\b",
    flags=re.IGNORECASE,
)


def basic_normalize(value: object) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = UNIT_PATTERN.sub(" ", text)
    text = re.sub(r"\bnda\d+\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token]
    tokens = [
        token
        for token in tokens
        if token not in SALT_AND_ESTER_WORDS and token not in FORM_WORDS
    ]
    return " ".join(tokens).strip()


def drug_id_for_key(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:14]
    return f"drg_{digest}"


def flatten_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten_text(item) for item in value.values())
    if isinstance(value, Iterable):
        return " ".join(flatten_text(item) for item in value)
    return str(value)


def clean_whitespace(value: object, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", flatten_text(value)).strip()
    if limit is not None:
        return text[:limit]
    return text


def close_match(
    query: str,
    choices: Iterable[str],
    threshold: float = 0.90,
) -> tuple[str | None, float]:
    """Return the closest key, constrained to candidates sharing a first token."""
    first_token = query.split(" ", 1)[0] if query else ""
    best_key = None
    best_score = 0.0
    for key in choices:
        if not key:
            continue
        if first_token and key.split(" ", 1)[0] != first_token:
            continue
        if abs(len(key) - len(query)) > max(8, len(query) // 2):
            continue
        score = SequenceMatcher(None, query, key).ratio()
        if score > best_score:
            best_key = key
            best_score = score
    if best_score >= threshold:
        return best_key, best_score
    return None, best_score

