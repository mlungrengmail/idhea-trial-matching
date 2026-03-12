"""Shared helpers for the trial-matching data pipeline."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUTPUTS = ROOT / "outputs"
TESTS = ROOT / "tests"

CONDITION_PRIORITY = [
    "dme",
    "wet_amd",
    "rvo",
    "ga",
    "glaucoma",
    "dr",
    "pathologic_myopia",
    "macular_hole",
    "uveitic_me",
    "stargardt",
    "vma",
]

# Distinguish "seed query terms" (ClinicalTrials.gov search inputs)
# from "mapped condition categories" (curated output categories).
# These numbers diverge because condition_membership deduplication
# and sub-condition grouping produce more categories than seeds.
SEED_CONDITION_COUNT = 11  # len(CONDITION_SPECS) in fetch_trials.py
MAPPED_CATEGORY_COUNT = len(CONDITION_PRIORITY)  # curated categories

CONDITION_LABELS = {
    "dme": "Diabetic Macular Edema",
    "dr": "Diabetic Retinopathy",
    "wet_amd": "Wet/Neovascular AMD",
    "ga": "Geographic Atrophy",
    "glaucoma": "Glaucoma",
    "rvo": "Retinal Vein Occlusion",
    "pathologic_myopia": "Pathological Myopia",
    "macular_hole": "Macular Hole",
    "uveitic_me": "Uveitic Macular Edema",
    "stargardt": "Stargardt Disease",
    "vma": "Vitreomacular Adhesion",
}

RECRUITING_NOW_STATUSES = {"RECRUITING"}
PIPELINE_OPEN_STATUSES = {
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ENROLLING_BY_INVITATION",
}
ACTIVE_STATUSES = PIPELINE_OPEN_STATUSES | {"ACTIVE_NOT_RECRUITING"}

KNOWN_NOISY_NCTS = {
    "NCT01997255",
    "NCT05753189",
    "NCT06045299",
}


def ensure_directories() -> None:
    DATA.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    OUTPUTS.mkdir(exist_ok=True)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return value.strip("_")


def normalize_space(text: str) -> str:
    return " ".join((text or "").split())


def flatten_text(value: object) -> str:
    """Flatten Strapi-style rich text nodes into plain text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"])
        children = value.get("children")
        if children:
            return "".join(flatten_text(child) for child in children)
    return ""


def unique_list(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def condition_label(key: str) -> str:
    return CONDITION_LABELS.get(key, key)


def choose_primary_condition(conditions: Iterable[str]) -> str:
    condition_set = set(conditions)
    for key in CONDITION_PRIORITY:
        if key in condition_set:
            return key
    return sorted(condition_set)[0] if condition_set else ""


def is_recruiting_now(status: str) -> bool:
    return status in RECRUITING_NOW_STATUSES


def is_pipeline_open(status: str) -> bool:
    return status in PIPELINE_OPEN_STATUSES


def is_active(status: str) -> bool:
    return status in ACTIVE_STATUSES
