"""Optional LLM-assisted rule extraction.

Modes:
  - llm: LLM-only
  - hybrid: deterministic + LLM union

Environment:
  TRIAL_MATCHING_LLM_API_KEY
  TRIAL_MATCHING_LLM_MODEL
  TRIAL_MATCHING_LLM_BASE_URL   (optional)
  TRIAL_MATCHING_LLM_TIMEOUT_SECONDS (optional)
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from extract_trial_rules import build_trial_rules as build_deterministic_trial_rules
    from llm_client import create_llm_client, load_llm_config_from_env
    from load_data import (
        load_criterion_catalog,
        load_eligibility_text,
        load_memberships,
        load_trials,
    )
    from pipeline_utils import normalize_space, slugify, write_json, DATA
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.extract_trial_rules import build_trial_rules as build_deterministic_trial_rules
    from scripts.llm_client import create_llm_client, load_llm_config_from_env
    from scripts.load_data import (
        load_criterion_catalog,
        load_eligibility_text,
        load_memberships,
        load_trials,
    )
    from scripts.pipeline_utils import normalize_space, slugify, write_json, DATA

VALID_MODES = {"llm", "hybrid"}
VALID_CONFIDENCE = {"direct", "partial", "not_evaluable"}


def catalog_lookup(rows: list[dict]) -> dict[str, dict]:
    return {row["criterion_id"]: row for row in rows}


def llm_catalog_for_condition(catalog_rows: list[dict], condition_category: str) -> list[dict]:
    rows: list[dict] = []
    for row in catalog_rows:
        if condition_category in row["applicable_conditions"]:
            rows.append(
                {
                    "criterion_id": row["criterion_id"],
                    "description": row["description"],
                    "criterion_type": row["criterion_type"],
                    "default_confidence": row["default_confidence"],
                    "idhea_fields": row.get("idhea_fields", []),
                    "external_dependencies": row.get("external_dependencies", []),
                }
            )
    return rows


def llm_system_prompt() -> str:
    return (
        "You extract structured ophthalmic trial rules from ClinicalTrials.gov eligibility text. "
        "Return JSON only. Only use criterion IDs from the provided catalog. "
        "Use exact evidence excerpts from the source text where possible. "
        "If a rule is ambiguous, set manual_review_required to true."
    )


def llm_user_prompt(*, nct_id: str, condition_category: str, eligibility_text: str, catalog_rows: list[dict]) -> str:
    payload = {
        "task": "Extract structured trial rules",
        "nct_id": nct_id,
        "condition_category": condition_category,
        "criterion_catalog": catalog_rows,
        "eligibility_text": eligibility_text,
        "response_schema": {
            "rules": [
                {
                    "criterion_id": "string",
                    "criterion_text_original": "exact or near-exact source sentence/span",
                    "operator": "normalized operator",
                    "value": "normalized string value",
                    "unit": "normalized unit or empty string",
                    "confidence": "direct|partial|not_evaluable",
                    "manual_review_required": True,
                    "evidence_excerpt": "exact source excerpt",
                    "reasoning": "short explanation",
                }
            ]
        },
    }
    return json.dumps(payload, indent=2)


def sanitize_llm_rule(
    *,
    item: dict,
    nct_id: str,
    condition_category: str,
    evidence_url: str,
    catalog: dict[str, dict],
    model_name: str,
) -> dict | None:
    criterion_id = str(item.get("criterion_id", "")).strip()
    if criterion_id not in catalog:
        return None
    if condition_category not in catalog[criterion_id]["applicable_conditions"]:
        return None

    criterion_text_original = normalize_space(str(item.get("criterion_text_original", "")).strip())
    evidence_excerpt = normalize_space(str(item.get("evidence_excerpt", "")).strip())
    if not criterion_text_original:
        criterion_text_original = evidence_excerpt
    if not criterion_text_original:
        return None

    confidence = str(item.get("confidence", "")).strip()
    if confidence not in VALID_CONFIDENCE:
        confidence = catalog[criterion_id]["default_confidence"]

    return {
        "mapping_id": slugify(f"{nct_id}_{condition_category}_{criterion_id}_{criterion_text_original[:40]}"),
        "nct_id": nct_id,
        "condition_category": condition_category,
        "criterion_id": criterion_id,
        "criterion_text_original": criterion_text_original,
        "criterion_type": catalog[criterion_id]["criterion_type"],
        "operator": normalize_space(str(item.get("operator", "")).strip()),
        "value": normalize_space(str(item.get("value", "")).strip()),
        "unit": normalize_space(str(item.get("unit", "")).strip()),
        "idhea_fields": catalog[criterion_id].get("idhea_fields", []),
        "external_dependencies": catalog[criterion_id].get("external_dependencies", []),
        "confidence": confidence,
        "manual_review_required": bool(item.get("manual_review_required", False)),
        "human_verified": False,
        "evidence_url": evidence_url,
        "extraction_method": "llm",
        "evidence_excerpt": evidence_excerpt or criterion_text_original,
        "reasoning": normalize_space(str(item.get("reasoning", "")).strip()),
        "model_name": model_name,
    }


def dedupe_rules(rules: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for rule in sorted(
        rules,
        key=lambda item: (
            item["nct_id"],
            item["condition_category"],
            item["criterion_id"],
            item["criterion_text_original"],
            item.get("extraction_method", ""),
        ),
    ):
        key = (
            rule["nct_id"],
            rule["condition_category"],
            rule["criterion_id"],
            rule["criterion_text_original"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rule)
    return deduped


def build_llm_trial_rules(
    trials: list[dict],
    memberships: list[dict],
    eligibility_rows: list[dict],
    catalog_rows: list[dict],
    llm_client,
) -> list[dict]:
    catalog = catalog_lookup(catalog_rows)
    conditions_by_nct: dict[str, list[str]] = {}
    for membership in memberships:
        conditions_by_nct.setdefault(membership["nct_id"], []).append(membership["condition_category"])
    trial_url = {trial["nct_id"]: trial["source_url"] for trial in trials}

    rules: list[dict] = []
    for eligibility_row in eligibility_rows:
        nct_id = eligibility_row["nct_id"]
        eligibility_text = eligibility_row.get("eligibility_criteria", "")
        if not eligibility_text.strip():
            continue
        for condition_category in conditions_by_nct.get(nct_id, []):
            payload = llm_client.extract_rules(
                system_prompt=llm_system_prompt(),
                user_prompt=llm_user_prompt(
                    nct_id=nct_id,
                    condition_category=condition_category,
                    eligibility_text=eligibility_text,
                    catalog_rows=llm_catalog_for_condition(catalog_rows, condition_category),
                ),
            )
            for item in payload.get("rules", []):
                sanitized = sanitize_llm_rule(
                    item=item,
                    nct_id=nct_id,
                    condition_category=condition_category,
                    evidence_url=trial_url.get(nct_id, f"https://clinicaltrials.gov/study/{nct_id}"),
                    catalog=catalog,
                    model_name=getattr(llm_client, "model_name", ""),
                )
                if sanitized:
                    rules.append(sanitized)
    return rules


def build_trial_rules(
    trials: list[dict],
    memberships: list[dict],
    eligibility_rows: list[dict],
    catalog_rows: list[dict],
    *,
    mode: str,
    llm_client,
) -> list[dict]:
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported LLM extraction mode: {mode}")

    rules: list[dict] = []
    if mode == "hybrid":
        rules.extend(
            build_deterministic_trial_rules(
                trials,
                memberships,
                eligibility_rows,
                catalog_rows,
            )
        )
    rules.extend(build_llm_trial_rules(trials, memberships, eligibility_rows, catalog_rows, llm_client))
    return dedupe_rules(rules)


def generate(mode: str = "hybrid") -> list[dict]:
    config = load_llm_config_from_env()
    if config is None:
        raise ValueError(
            "LLM extraction requires TRIAL_MATCHING_LLM_API_KEY and TRIAL_MATCHING_LLM_MODEL."
        )
    llm_client = create_llm_client(config)
    trials = load_trials()
    memberships = load_memberships()
    eligibility_rows = load_eligibility_text()
    catalog_rows = load_criterion_catalog()
    rules = build_trial_rules(
        trials,
        memberships,
        eligibility_rows,
        catalog_rows,
        mode=mode,
        llm_client=llm_client,
    )
    write_json(DATA / "trial_rule_mappings.json", rules)
    return rules


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-assisted trial rule extraction")
    parser.add_argument("--mode", choices=sorted(VALID_MODES), default="hybrid")
    args = parser.parse_args()

    try:
        rules = generate(mode=args.mode)
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {DATA / 'trial_rule_mappings.json'} ({len(rules)} rows) via {args.mode} mode")


if __name__ == "__main__":
    main()
