"""Generate canonical trial-matching metrics.

Output:
  outputs/metrics.json

Usage:
  uv run python scripts/generate_metrics.py
"""

from __future__ import annotations

import sys

try:
    from load_data import load_memberships, load_trial_rules, load_trials, trials_per_condition
    from pipeline_utils import (
        is_active,
        is_pipeline_open,
        is_recruiting_now,
        utc_now_iso,
        write_json,
        OUTPUTS,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.load_data import load_memberships, load_trial_rules, load_trials, trials_per_condition
    from scripts.pipeline_utils import (
        is_active,
        is_pipeline_open,
        is_recruiting_now,
        utc_now_iso,
        write_json,
        OUTPUTS,
    )


def build_metrics(trials: list[dict], memberships: list[dict], rules: list[dict]) -> dict:
    mapped_trials = {row["nct_id"] for row in rules}
    verified_mapped_trials = {row["nct_id"] for row in rules if row.get("human_verified")}
    confidence_counts = {
        "direct": sum(1 for row in rules if row["confidence"] == "direct"),
        "partial": sum(1 for row in rules if row["confidence"] == "partial"),
        "not_evaluable": sum(1 for row in rules if row["confidence"] == "not_evaluable"),
    }
    return {
        "generated_at": utc_now_iso(),
        "unique_trials_total": len(trials),
        "condition_memberships_total": len(memberships),
        "recruiting_now_total": sum(1 for trial in trials if is_recruiting_now(trial["status"])),
        "pipeline_open_total": sum(1 for trial in trials if is_pipeline_open(trial["status"])),
        "active_total": sum(1 for trial in trials if is_active(trial["status"])),
        "mapped_trials_total": len(mapped_trials),
        "verified_mapped_trials_total": len(verified_mapped_trials),
        "condition_counts": trials_per_condition(memberships),
        "rule_confidence_counts": confidence_counts,
    }


def generate() -> dict:
    trials = load_trials()
    memberships = load_memberships()
    rules = load_trial_rules()
    metrics = build_metrics(trials, memberships, rules)
    write_json(OUTPUTS / "metrics.json", metrics)
    return metrics


def main() -> None:
    try:
        metrics = generate()
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {OUTPUTS / 'metrics.json'}")
    print(metrics)


if __name__ == "__main__":
    main()
