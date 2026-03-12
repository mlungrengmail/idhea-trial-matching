"""Shared data loading helpers for generation and validation scripts."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

try:
    from pipeline_utils import (
        DATA,
        OUTPUTS,
        RAW,
        ACTIVE_STATUSES,
        PIPELINE_OPEN_STATUSES,
        RECRUITING_NOW_STATUSES,
        condition_label,
        ensure_directories,
        read_json,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.pipeline_utils import (
        DATA,
        OUTPUTS,
        RAW,
        ACTIVE_STATUSES,
        PIPELINE_OPEN_STATUSES,
        RECRUITING_NOW_STATUSES,
        condition_label,
        ensure_directories,
        read_json,
    )


def _load_json(name: str, base: Path = DATA) -> list[dict] | dict:
    path = base / name
    if not path.exists():
        raise FileNotFoundError(path)
    return read_json(path)


def load_trials() -> list[dict]:
    return _load_json("trials.json")  # type: ignore[return-value]


def load_memberships() -> list[dict]:
    return _load_json("condition_membership.json")  # type: ignore[return-value]


def load_fields() -> list[dict]:
    return _load_json("idhea_fields.json")  # type: ignore[return-value]


def load_dataset_metadata() -> dict:
    return _load_json("idhea_dataset_metadata.json")  # type: ignore[return-value]


def load_criterion_catalog() -> list[dict]:
    return _load_json("criterion_catalog.json")  # type: ignore[return-value]


def load_trial_rules() -> list[dict]:
    return _load_json("trial_rule_mappings.json")  # type: ignore[return-value]


def load_not_evaluable() -> list[dict]:
    return _load_json("not_evaluable_fields.json")  # type: ignore[return-value]


def load_review_overrides() -> list[dict]:
    return _load_json("review_overrides.json")  # type: ignore[return-value]


def load_raw_trials() -> list[dict]:
    return _load_json("trials_raw.json", RAW)  # type: ignore[return-value]


def load_condition_hits() -> list[dict]:
    return _load_json("condition_hits.json", RAW)  # type: ignore[return-value]


def load_metrics() -> dict:
    return _load_json("metrics.json", OUTPUTS)  # type: ignore[return-value]


def load_eligibility_text() -> list[dict]:
    return _load_json("eligibility_text.json")  # type: ignore[return-value]


def load_csv_output(name: str) -> list[dict]:
    path = OUTPUTS / name
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def unique_trial_count(trials: list[dict]) -> int:
    return len({t["nct_id"] for t in trials})


def trials_by_status(trials: list[dict]) -> dict[str, int]:
    return dict(Counter(t["status"] for t in trials).most_common())


def trials_per_condition(memberships: list[dict]) -> dict[str, int]:
    return dict(Counter(m["condition_category"] for m in memberships).most_common())


def recruiting_now_trials(trials: list[dict]) -> list[dict]:
    return [t for t in trials if t["status"] in RECRUITING_NOW_STATUSES]


def pipeline_open_trials(trials: list[dict]) -> list[dict]:
    return [t for t in trials if t["status"] in PIPELINE_OPEN_STATUSES]


def active_trials(trials: list[dict]) -> list[dict]:
    return [t for t in trials if t["status"] in ACTIVE_STATUSES]


__all__ = [
    "DATA",
    "RAW",
    "OUTPUTS",
    "ACTIVE_STATUSES",
    "PIPELINE_OPEN_STATUSES",
    "RECRUITING_NOW_STATUSES",
    "ensure_directories",
    "condition_label",
    "load_trials",
    "load_memberships",
    "load_fields",
    "load_dataset_metadata",
    "load_criterion_catalog",
    "load_trial_rules",
    "load_not_evaluable",
    "load_review_overrides",
    "load_raw_trials",
    "load_condition_hits",
    "load_metrics",
    "load_eligibility_text",
    "load_csv_output",
    "unique_trial_count",
    "trials_by_status",
    "trials_per_condition",
    "recruiting_now_trials",
    "pipeline_open_trials",
    "active_trials",
]
