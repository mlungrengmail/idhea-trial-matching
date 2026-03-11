"""Shared data loading for all generation scripts."""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"


def load_json(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run: uv run python scripts/fetch_trials.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_trials() -> list[dict]:
    return load_json("trials.json")


def load_memberships() -> list[dict]:
    return load_json("condition_membership.json")


def load_fields() -> list[dict]:
    return load_json("idhea_fields.json")


def load_criteria() -> list[dict]:
    return load_json("criteria_mappings.json")


def load_not_evaluable() -> list[dict]:
    return load_json("not_evaluable_fields.json")


def unique_trial_count(trials: list[dict]) -> int:
    return len({t["nct_id"] for t in trials})


def trials_by_status(trials: list[dict]) -> dict[str, int]:
    return dict(Counter(t["status"] for t in trials).most_common())


def trials_per_condition(memberships: list[dict]) -> dict[str, int]:
    return dict(Counter(m["condition_category"] for m in memberships).most_common())


def recruiting_trials(trials: list[dict]) -> list[dict]:
    return [t for t in trials if t["status"] in (
        "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"
    )]


def active_trials(trials: list[dict]) -> list[dict]:
    return [t for t in trials if t["status"] in (
        "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION",
        "ACTIVE_NOT_RECRUITING",
    )]


def condition_label(key: str) -> str:
    labels = {
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
    return labels.get(key, key)


def ensure_outputs():
    OUTPUTS.mkdir(exist_ok=True)
