"""Export analyst-friendly CSV outputs from curated data."""

from __future__ import annotations

from collections import Counter, defaultdict
import sys

try:
    from fetch_trials import trial_matches_condition
    from load_data import (
        load_condition_hits,
        load_memberships,
        load_not_evaluable,
        load_raw_trials,
        load_review_overrides,
        load_trial_rules,
        load_trials,
    )
    from pipeline_utils import (
        choose_primary_condition,
        condition_label,
        is_active,
        is_pipeline_open,
        is_recruiting_now,
        unique_list,
        write_csv,
        OUTPUTS,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.fetch_trials import trial_matches_condition
    from scripts.load_data import (
        load_condition_hits,
        load_memberships,
        load_not_evaluable,
        load_raw_trials,
        load_review_overrides,
        load_trial_rules,
        load_trials,
    )
    from scripts.pipeline_utils import (
        choose_primary_condition,
        condition_label,
        is_active,
        is_pipeline_open,
        is_recruiting_now,
        unique_list,
        write_csv,
        OUTPUTS,
    )

TRIALS_LABELED_COLUMNS = [
    "nct_id",
    "title",
    "phase",
    "status",
    "sponsor",
    "source_url",
    "primary_condition",
    "all_conditions",
    "recruiting_now",
    "pipeline_open",
    "active",
    "mapped",
    "verified_mapped",
    "direct_rule_count",
    "partial_rule_count",
    "not_evaluable_rule_count",
    "direct_idhea_fields",
    "missing_external_dependencies",
    "missing_data_fields",
    "manual_review_required",
    "prescreening_fit",
]


def override_index(rows: list[dict]) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for row in rows:
        condition_category = row.get("condition_category")
        if condition_category:
            index[(row["nct_id"], condition_category)] = row
    return index


def build_curation_audit_rows(
    raw_hits: list[dict],
    curated_memberships: list[dict],
    overrides: list[dict],
) -> list[dict]:
    curated_pairs = {(row["nct_id"], row["condition_category"]) for row in curated_memberships}
    overrides_by_pair = override_index(overrides)
    audit_rows: list[dict] = []
    for hit in sorted(raw_hits, key=lambda row: (row["condition_category"], row["nct_id"])):
        pair = (hit["nct_id"], hit["condition_category"])
        override = overrides_by_pair.get(pair)
        trial_view = {
            "title": hit.get("title", ""),
            "official_title": hit.get("official_title", ""),
            "conditions": hit.get("conditions", []),
        }
        matched, heuristic_reason = trial_matches_condition(trial_view, hit["condition_category"])
        if override:
            decision = override.get("action", "exclude")
            reason = override.get("reason", heuristic_reason)
            override_source = override.get("source", "manual_review")
            corrected = "; ".join(override.get("corrected_conditions", []))
        else:
            decision = "include" if pair in curated_pairs else "exclude"
            reason = heuristic_reason if matched or decision == "exclude" else "included"
            override_source = ""
            corrected = ""

        audit_rows.append(
            {
                "nct_id": hit["nct_id"],
                "condition_category": hit["condition_category"],
                "condition_label": condition_label(hit["condition_category"]),
                "condition_query": hit["condition_query"],
                "title": hit["title"],
                "status": hit["status"],
                "source_url": hit["source_url"],
                "decision": decision,
                "reason": reason,
                "override_source": override_source,
                "corrected_conditions": corrected,
            }
        )
    return audit_rows


def summarize_rules_by_trial(rules: list[dict], known_missing_fields: set[str]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rules:
        grouped[row["nct_id"]].append(row)

    summaries: dict[str, dict] = {}
    for nct_id, trial_rules in grouped.items():
        unique_rule_keys = set()
        direct_fields: list[str] = []
        missing_external_dependencies: list[str] = []
        missing_data_fields: list[str] = []
        direct = partial = not_evaluable = 0
        manual_review_required = False
        verified_mapped = False

        for row in trial_rules:
            unique_key = (row["criterion_id"], row["criterion_text_original"])
            if unique_key in unique_rule_keys:
                continue
            unique_rule_keys.add(unique_key)

            confidence = row["confidence"]
            if confidence == "direct":
                direct += 1
                direct_fields.extend(row.get("idhea_fields", []))
            elif confidence == "partial":
                partial += 1
            else:
                not_evaluable += 1

            missing_external_dependencies.extend(row.get("external_dependencies", []))
            missing_data_fields.extend(
                dep for dep in row.get("external_dependencies", []) if dep in known_missing_fields
            )
            manual_review_required = manual_review_required or bool(row.get("manual_review_required"))
            verified_mapped = verified_mapped or bool(row.get("human_verified"))

        summaries[nct_id] = {
            "mapped": bool(trial_rules),
            "verified_mapped": verified_mapped,
            "direct_rule_count": direct,
            "partial_rule_count": partial,
            "not_evaluable_rule_count": not_evaluable,
            "direct_idhea_fields": unique_list(sorted(direct_fields)),
            "missing_external_dependencies": unique_list(sorted(missing_external_dependencies)),
            "missing_data_fields": unique_list(sorted(missing_data_fields)),
            "manual_review_required": manual_review_required,
        }
    return summaries


def prescreening_fit(summary: dict) -> str:
    direct = summary["direct_rule_count"]
    partial = summary["partial_rule_count"]
    not_evaluable = summary["not_evaluable_rule_count"]
    manual_review_required = summary["manual_review_required"]

    if direct >= 2 and direct >= partial and direct >= not_evaluable and not manual_review_required:
        return "high"
    if direct >= 1 or partial >= 1:
        return "medium"
    return "low"


def build_trials_labeled_rows(
    trials: list[dict],
    memberships: list[dict],
    rule_summaries: dict[str, dict],
) -> list[dict]:
    conditions_by_nct: dict[str, list[str]] = defaultdict(list)
    for row in memberships:
        conditions_by_nct[row["nct_id"]].append(row["condition_category"])

    rows: list[dict] = []
    for trial in sorted(trials, key=lambda row: row["nct_id"]):
        nct_id = trial["nct_id"]
        conditions = unique_list(sorted(conditions_by_nct.get(nct_id, [])))
        summary = rule_summaries.get(
            nct_id,
            {
                "mapped": False,
                "verified_mapped": False,
                "direct_rule_count": 0,
                "partial_rule_count": 0,
                "not_evaluable_rule_count": 0,
                "direct_idhea_fields": [],
                "missing_external_dependencies": [],
                "missing_data_fields": [],
                "manual_review_required": False,
            },
        )
        fit = prescreening_fit(summary)
        rows.append(
            {
                "nct_id": nct_id,
                "title": trial["title"],
                "phase": trial["phase"],
                "status": trial["status"],
                "sponsor": trial["sponsor"],
                "source_url": trial["source_url"],
                "primary_condition": choose_primary_condition(conditions),
                "all_conditions": "; ".join(conditions),
                "recruiting_now": is_recruiting_now(trial["status"]),
                "pipeline_open": is_pipeline_open(trial["status"]),
                "active": is_active(trial["status"]),
                "mapped": summary["mapped"],
                "verified_mapped": summary["verified_mapped"],
                "direct_rule_count": summary["direct_rule_count"],
                "partial_rule_count": summary["partial_rule_count"],
                "not_evaluable_rule_count": summary["not_evaluable_rule_count"],
                "direct_idhea_fields": "; ".join(summary["direct_idhea_fields"]),
                "missing_external_dependencies": "; ".join(summary["missing_external_dependencies"]),
                "missing_data_fields": "; ".join(summary["missing_data_fields"]),
                "manual_review_required": summary["manual_review_required"],
                "prescreening_fit": fit,
            }
        )
    return rows


def build_trial_rules_rows(rules: list[dict], trial_lookup: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for row in sorted(
        rules,
        key=lambda item: (
            item["nct_id"],
            item["condition_category"],
            item["criterion_id"],
            item["criterion_text_original"],
        ),
    ):
        trial = trial_lookup.get(row["nct_id"], {})
        rows.append(
            {
                "mapping_id": row["mapping_id"],
                "nct_id": row["nct_id"],
                "title": trial.get("title", ""),
                "status": trial.get("status", ""),
                "condition_category": row["condition_category"],
                "criterion_id": row["criterion_id"],
                "criterion_type": row["criterion_type"],
                "criterion_text_original": row["criterion_text_original"],
                "operator": row["operator"],
                "value": row["value"],
                "unit": row["unit"],
                "idhea_fields": "; ".join(row.get("idhea_fields", [])),
                "external_dependencies": "; ".join(row.get("external_dependencies", [])),
                "confidence": row["confidence"],
                "manual_review_required": row["manual_review_required"],
                "human_verified": row["human_verified"],
                "extraction_method": row.get("extraction_method", ""),
                "model_name": row.get("model_name", ""),
                "evidence_excerpt": row.get("evidence_excerpt", ""),
                "reasoning": row.get("reasoning", ""),
                "evidence_url": row["evidence_url"],
            }
        )
    return rows


def build_missing_requirements_rows(
    rules: list[dict],
    trial_lookup: dict[str, dict],
    memberships: list[dict],
) -> tuple[list[dict], list[dict]]:
    conditions_by_nct: dict[str, list[str]] = defaultdict(list)
    for membership in memberships:
        conditions_by_nct[membership["nct_id"]].append(membership["condition_category"])

    rows: list[dict] = []
    summary_counter: Counter[tuple[str, str, str]] = Counter()
    seen_pairs: set[tuple[str, str, str]] = set()

    for rule in rules:
        trial = trial_lookup.get(rule["nct_id"], {})
        for dependency in rule.get("external_dependencies", []):
            row_key = (rule["nct_id"], rule["condition_category"], dependency)
            if row_key in seen_pairs:
                continue
            seen_pairs.add(row_key)
            rows.append(
                {
                    "nct_id": rule["nct_id"],
                    "title": trial.get("title", ""),
                    "status": trial.get("status", ""),
                    "primary_condition": choose_primary_condition(conditions_by_nct.get(rule["nct_id"], [])),
                    "condition_category": rule["condition_category"],
                    "missing_dependency": dependency,
                    "source_rule_ids": rule["criterion_id"],
                    "source_url": trial.get("source_url", ""),
                }
            )
            summary_counter[(dependency, rule["condition_category"], trial.get("status", ""))] += 1

    summary_rows = [
        {
            "missing_dependency": dependency,
            "condition_category": condition_category,
            "status": status,
            "trial_count": count,
        }
        for (dependency, condition_category, status), count in sorted(summary_counter.items())
    ]
    return rows, summary_rows


def generate() -> dict:
    trials = load_trials()
    raw_trials = load_raw_trials()
    raw_hits = load_condition_hits()
    memberships = load_memberships()
    rules = load_trial_rules()
    overrides = load_review_overrides()
    not_evaluable_fields = load_not_evaluable()
    known_missing_fields = {row["field_name"] for row in not_evaluable_fields}
    trial_lookup = {trial["nct_id"]: trial for trial in trials}

    rule_summaries = summarize_rules_by_trial(rules, known_missing_fields)
    trials_labeled_rows = build_trials_labeled_rows(trials, memberships, rule_summaries)
    trial_rules_rows = build_trial_rules_rows(rules, trial_lookup)
    missing_rows, missing_summary_rows = build_missing_requirements_rows(rules, trial_lookup, memberships)
    curation_audit_rows = build_curation_audit_rows(raw_hits, memberships, overrides)

    write_csv(OUTPUTS / "trials_labeled.csv", trials_labeled_rows, TRIALS_LABELED_COLUMNS)
    write_csv(
        OUTPUTS / "trial_rules.csv",
        trial_rules_rows,
        [
            "mapping_id",
            "nct_id",
            "title",
            "status",
            "condition_category",
            "criterion_id",
            "criterion_type",
            "criterion_text_original",
            "operator",
            "value",
            "unit",
            "idhea_fields",
            "external_dependencies",
            "confidence",
            "manual_review_required",
            "human_verified",
            "extraction_method",
            "model_name",
            "evidence_excerpt",
            "reasoning",
            "evidence_url",
        ],
    )
    write_csv(
        OUTPUTS / "missing_requirements_by_trial.csv",
        missing_rows,
        [
            "nct_id",
            "title",
            "status",
            "primary_condition",
            "condition_category",
            "missing_dependency",
            "source_rule_ids",
            "source_url",
        ],
    )
    write_csv(
        OUTPUTS / "missing_requirements_summary.csv",
        missing_summary_rows,
        ["missing_dependency", "condition_category", "status", "trial_count"],
    )
    write_csv(
        OUTPUTS / "curation_audit.csv",
        curation_audit_rows,
        [
            "nct_id",
            "condition_category",
            "condition_label",
            "condition_query",
            "title",
            "status",
            "source_url",
            "decision",
            "reason",
            "override_source",
            "corrected_conditions",
        ],
    )

    return {
        "trials_labeled": len(trials_labeled_rows),
        "trial_rules": len(trial_rules_rows),
        "missing_requirements": len(missing_rows),
        "missing_summary": len(missing_summary_rows),
        "curation_audit": len(curation_audit_rows),
        "raw_trials_seen": len(raw_trials),
    }


def main() -> None:
    try:
        summary = generate()
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
