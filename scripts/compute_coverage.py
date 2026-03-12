"""Compute per-trial and aggregate coverage at each data enrichment tier.

Coverage tiers (cumulative):
  Tier 0 - iDHEA imaging only: OCT/CFP fields in the dataset
  Tier 1 - + AI models: RetinSight, RETFound, Toku CLAiR (available now, $0)
  Tier 2 - + OD clinical data: BCVA, IOP, slit lamp, refraction, diagnosis ($30-50K/site integration)
  Tier 3 - + Lab/medical EHR: HbA1c, eGFR, systemic history (varies, hospital integration)
  Tier 4 - + Patient questionnaire: treatment history, pregnancy status (~$0)

Output:
  outputs/coverage_analysis.json

Usage:
  uv run python scripts/compute_coverage.py
"""

from __future__ import annotations

import sys
from collections import defaultdict

try:
    from load_data import (
        load_memberships,
        load_not_evaluable,
        load_trial_rules,
        load_trials,
    )
    from pipeline_utils import (
        read_json,
        write_json,
        utc_now_iso,
        DATA,
        OUTPUTS,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.load_data import (
        load_memberships,
        load_not_evaluable,
        load_trial_rules,
        load_trials,
    )
    from scripts.pipeline_utils import (
        read_json,
        write_json,
        utc_now_iso,
        DATA,
        OUTPUTS,
    )

TIER_ORDER = ["od_clinical", "lab_ehr", "patient_questionnaire", "specialized_equipment"]

TIER_LABELS = {
    "od_clinical": "OD Clinical Data Integration",
    "lab_ehr": "Lab / Medical EHR Integration",
    "patient_questionnaire": "Patient Questionnaire",
    "specialized_equipment": "Specialized Equipment / Testing",
}


def load_enrichment_models() -> list[dict]:
    path = DATA / "enrichment_models.json"
    if not path.exists():
        return []
    return read_json(path)  # type: ignore[return-value]


def model_criteria_set(models: list[dict]) -> set[str]:
    """Return the set of criterion_ids addressable by available AI models."""
    criteria: set[str] = set()
    for model in models:
        if model.get("availability") == "available_now":
            criteria.update(model.get("criteria_covered", []))
    return criteria


def build_tier_dependency_sets(not_evaluable: list[dict]) -> dict[str, set[str]]:
    """Group external dependencies by acquisition tier."""
    tier_deps: dict[str, set[str]] = defaultdict(set)
    for field in not_evaluable:
        tier = field.get("acquisition_tier", "specialized_equipment")
        tier_deps[tier].add(field["field_name"])
    return dict(tier_deps)


def compute_trial_coverage(
    nct_id: str,
    trial_rules: list[dict],
    model_criteria: set[str],
    tier_deps: dict[str, set[str]],
) -> dict:
    """Compute coverage for a single trial at each tier.

    A criterion is 'covered' at a given tier if:
      - It has confidence='direct' (iDHEA can evaluate it), OR
      - It has confidence='partial' and a model can address it (tier 1+), OR
      - Its external_dependencies are all satisfied by tiers unlocked so far.
    """
    if not trial_rules:
        return {
            "nct_id": nct_id,
            "total_criteria": 0,
            "tier_0_imaging_only": {"covered": 0, "total": 0, "pct": 0.0},
            "tier_1_plus_models": {"covered": 0, "total": 0, "pct": 0.0},
            "tier_2_plus_od_clinical": {"covered": 0, "total": 0, "pct": 0.0},
            "tier_3_plus_lab_ehr": {"covered": 0, "total": 0, "pct": 0.0},
            "tier_4_plus_questionnaire": {"covered": 0, "total": 0, "pct": 0.0},
            "persistent_gaps": [],
        }

    # Deduplicate criteria by (criterion_id, criterion_text_original)
    unique_criteria: dict[tuple[str, str], dict] = {}
    for rule in trial_rules:
        key = (rule["criterion_id"], rule["criterion_text_original"])
        if key not in unique_criteria:
            unique_criteria[key] = rule

    total = len(unique_criteria)
    rules_list = list(unique_criteria.values())

    # Tier 0: imaging only (direct confidence from iDHEA fields)
    tier_0_covered = sum(1 for r in rules_list if r["confidence"] == "direct")

    # Tier 1: + AI models (partial criteria that models can address)
    tier_1_covered = tier_0_covered
    for r in rules_list:
        if r["confidence"] == "direct":
            continue
        if r["confidence"] == "partial" and r["criterion_id"] in model_criteria:
            tier_1_covered += 1

    # Tiers 2-4: progressively unlock external dependencies
    unlocked_deps: set[str] = set()
    tier_coverages = [tier_1_covered]

    for tier_name in ["od_clinical", "lab_ehr", "patient_questionnaire"]:
        unlocked_deps |= tier_deps.get(tier_name, set())
        covered = 0
        for r in rules_list:
            if r["confidence"] == "direct":
                covered += 1
            elif r["confidence"] == "partial" and r["criterion_id"] in model_criteria:
                covered += 1
            else:
                ext_deps = set(r.get("external_dependencies", []))
                if ext_deps and ext_deps.issubset(unlocked_deps):
                    covered += 1
        tier_coverages.append(covered)

    # Persistent gaps: criteria not covered even at tier 4
    all_unlocked = set()
    for tier_name in TIER_ORDER:
        all_unlocked |= tier_deps.get(tier_name, set())

    persistent_gaps = []
    for r in rules_list:
        if r["confidence"] == "direct":
            continue
        if r["confidence"] == "partial" and r["criterion_id"] in model_criteria:
            continue
        ext_deps = set(r.get("external_dependencies", []))
        if not ext_deps or not ext_deps.issubset(all_unlocked):
            persistent_gaps.append(r["criterion_id"])

    def pct(n: int) -> float:
        return round(n / total * 100, 1) if total > 0 else 0.0

    return {
        "nct_id": nct_id,
        "total_criteria": total,
        "tier_0_imaging_only": {"covered": tier_0_covered, "total": total, "pct": pct(tier_0_covered)},
        "tier_1_plus_models": {"covered": tier_1_covered, "total": total, "pct": pct(tier_1_covered)},
        "tier_2_plus_od_clinical": {"covered": tier_coverages[1], "total": total, "pct": pct(tier_coverages[1])},
        "tier_3_plus_lab_ehr": {"covered": tier_coverages[2], "total": total, "pct": pct(tier_coverages[2])},
        "tier_4_plus_questionnaire": {"covered": tier_coverages[3], "total": total, "pct": pct(tier_coverages[3])},
        "persistent_gaps": sorted(set(persistent_gaps)),
    }


def compute_aggregate_coverage(per_trial: list[dict]) -> dict:
    """Compute aggregate coverage percentages across all trials."""
    trials_with_criteria = [t for t in per_trial if t["total_criteria"] > 0]
    n = len(trials_with_criteria)
    if n == 0:
        return {
            "trials_analyzed": 0,
            "tier_0_imaging_only_avg_pct": 0.0,
            "tier_1_plus_models_avg_pct": 0.0,
            "tier_2_plus_od_clinical_avg_pct": 0.0,
            "tier_3_plus_lab_ehr_avg_pct": 0.0,
            "tier_4_plus_questionnaire_avg_pct": 0.0,
            "trials_at_100_pct": {},
        }

    def avg(tier_key: str) -> float:
        return round(sum(t[tier_key]["pct"] for t in trials_with_criteria) / n, 1)

    def count_full(tier_key: str) -> int:
        return sum(1 for t in trials_with_criteria if t[tier_key]["pct"] >= 100.0)

    return {
        "trials_analyzed": n,
        "tier_0_imaging_only_avg_pct": avg("tier_0_imaging_only"),
        "tier_1_plus_models_avg_pct": avg("tier_1_plus_models"),
        "tier_2_plus_od_clinical_avg_pct": avg("tier_2_plus_od_clinical"),
        "tier_3_plus_lab_ehr_avg_pct": avg("tier_3_plus_lab_ehr"),
        "tier_4_plus_questionnaire_avg_pct": avg("tier_4_plus_questionnaire"),
        "trials_at_100_pct": {
            "tier_0_imaging_only": count_full("tier_0_imaging_only"),
            "tier_1_plus_models": count_full("tier_1_plus_models"),
            "tier_2_plus_od_clinical": count_full("tier_2_plus_od_clinical"),
            "tier_3_plus_lab_ehr": count_full("tier_3_plus_lab_ehr"),
            "tier_4_plus_questionnaire": count_full("tier_4_plus_questionnaire"),
        },
    }


def compute_gap_summary(per_trial: list[dict], rules: list[dict]) -> dict:
    """Compute aggregate gap analysis: how many trials are affected by each gap category."""
    # Count trials affected by each external dependency
    dep_trials: dict[str, set[str]] = defaultdict(set)
    for rule in rules:
        if rule["confidence"] == "not_evaluable":
            for dep in rule.get("external_dependencies", []):
                dep_trials[dep].add(rule["nct_id"])

    gap_counts = {
        dep: len(trials)
        for dep, trials in sorted(dep_trials.items(), key=lambda x: -len(x[1]))
    }

    # Persistent gaps (not closeable even at tier 4)
    all_persistent = defaultdict(int)
    for t in per_trial:
        for gap in t.get("persistent_gaps", []):
            all_persistent[gap] += 1

    return {
        "trials_affected_by_gap": gap_counts,
        "total_gap_criterion_occurrences": sum(gap_counts.values()),
        "persistent_gaps_by_criterion": dict(sorted(all_persistent.items(), key=lambda x: -x[1])),
    }


def generate() -> dict:
    trials = load_trials()
    rules = load_trial_rules()
    not_evaluable = load_not_evaluable()
    models = load_enrichment_models()

    model_criteria = model_criteria_set(models)
    tier_deps = build_tier_dependency_sets(not_evaluable)

    # Group rules by trial
    rules_by_nct: dict[str, list[dict]] = defaultdict(list)
    for rule in rules:
        rules_by_nct[rule["nct_id"]].append(rule)

    # Compute per-trial coverage
    per_trial = []
    for trial in sorted(trials, key=lambda t: t["nct_id"]):
        nct_id = trial["nct_id"]
        trial_rules = rules_by_nct.get(nct_id, [])
        per_trial.append(compute_trial_coverage(nct_id, trial_rules, model_criteria, tier_deps))

    aggregate = compute_aggregate_coverage(per_trial)
    gap_summary = compute_gap_summary(per_trial, rules)

    output = {
        "generated_at": utc_now_iso(),
        "tier_definitions": {
            "tier_0": "iDHEA imaging only (OCT/CFP fields in dataset)",
            "tier_1": "+ AI models (RetinSight, RETFound, Toku CLAiR — available now, $0)",
            "tier_2": "+ OD clinical data (BCVA, IOP, slit lamp, refraction — $30-50K/site integration)",
            "tier_3": "+ Lab/medical EHR (HbA1c, eGFR, systemic history — hospital integration)",
            "tier_4": "+ Patient questionnaire (treatment history, pregnancy — ~$0)",
        },
        "models_used": [
            {"model_id": m["model_id"], "name": m["name"], "criteria_covered": m["criteria_covered"]}
            for m in models
            if m.get("availability") == "available_now"
        ],
        "aggregate": aggregate,
        "gap_summary": gap_summary,
        "per_trial": per_trial,
    }

    write_json(OUTPUTS / "coverage_analysis.json", output)
    return output


def main() -> None:
    try:
        output = generate()
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    agg = output["aggregate"]
    print(f"Coverage analysis for {agg['trials_analyzed']} trials")
    print(f"  Tier 0 (imaging only):       {agg['tier_0_imaging_only_avg_pct']}%")
    print(f"  Tier 1 (+ models):           {agg['tier_1_plus_models_avg_pct']}%")
    print(f"  Tier 2 (+ OD clinical):      {agg['tier_2_plus_od_clinical_avg_pct']}%")
    print(f"  Tier 3 (+ lab/EHR):          {agg['tier_3_plus_lab_ehr_avg_pct']}%")
    print(f"  Tier 4 (+ questionnaire):    {agg['tier_4_plus_questionnaire_avg_pct']}%")
    print(f"\nTrials at 100% coverage:")
    for tier, count in agg.get("trials_at_100_pct", {}).items():
        print(f"  {tier}: {count}")

    gaps = output["gap_summary"]
    print(f"\nTop gaps by trials affected:")
    for dep, count in list(gaps["trials_affected_by_gap"].items())[:10]:
        print(f"  {dep}: {count} trials")

    print(f"\nWrote {OUTPUTS / 'coverage_analysis.json'}")


if __name__ == "__main__":
    main()
