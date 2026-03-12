"""Extract per-trial rule mappings from eligibility text.

Output:
  data/trial_rule_mappings.json

Usage:
  uv run python scripts/extract_trial_rules.py
"""

from __future__ import annotations

import re
import sys

try:
    from load_data import (
        load_criterion_catalog,
        load_eligibility_text,
        load_memberships,
        load_trials,
    )
    from pipeline_utils import CONDITION_PRIORITY, normalize_space, slugify, write_json, DATA
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.load_data import (
        load_criterion_catalog,
        load_eligibility_text,
        load_memberships,
        load_trials,
    )
    from scripts.pipeline_utils import CONDITION_PRIORITY, normalize_space, slugify, write_json, DATA

LINE_SPLIT_RE = re.compile(r"[\r\n]+|;\s+(?=[A-Z0-9])")


def eligibility_lines(text: str) -> list[str]:
    clean = text.replace("\u2022", "\n").replace("\u00b7", "\n")
    parts = LINE_SPLIT_RE.split(clean)
    lines: list[str] = []
    for part in parts:
        line = normalize_space(part.strip(" -*\t"))
        if len(line) < 4:
            continue
        if line.lower() in {"inclusion criteria", "exclusion criteria", "eligibility criteria"}:
            continue
        lines.append(line)
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        lowered = line.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(line)
    return deduped


def catalog_lookup(rows: list[dict]) -> dict[str, dict]:
    return {row["criterion_id"]: row for row in rows}


def create_rule(
    *,
    nct_id: str,
    condition_category: str,
    criterion_id: str,
    criterion_text_original: str,
    operator: str,
    value: str,
    unit: str,
    confidence: str,
    manual_review_required: bool,
    evidence_url: str,
    catalog: dict[str, dict],
) -> dict:
    spec = catalog[criterion_id]
    return {
        "mapping_id": slugify(f"{nct_id}_{condition_category}_{criterion_id}_{criterion_text_original[:40]}"),
        "nct_id": nct_id,
        "condition_category": condition_category,
        "criterion_id": criterion_id,
        "criterion_text_original": criterion_text_original,
        "criterion_type": spec["criterion_type"],
        "operator": operator,
        "value": value,
        "unit": unit,
        "idhea_fields": spec.get("idhea_fields", []),
        "external_dependencies": spec.get("external_dependencies", []),
        "confidence": confidence,
        "manual_review_required": manual_review_required,
        "human_verified": False,
        "evidence_url": evidence_url,
        "extraction_method": "deterministic",
        "evidence_excerpt": criterion_text_original,
        "reasoning": "",
        "model_name": "",
    }


def parse_range(line: str, unit_hints: list[str] | None = None) -> tuple[str, str, str, bool]:
    lowered = line.lower()
    unit_hints = unit_hints or []

    between = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-|through|and)\s*(\d+(?:\.\d+)?)", lowered)
    if between:
        unit = ""
        for hint in unit_hints:
            if hint in lowered:
                unit = hint
                break
        return "between", f"{between.group(1)}-{between.group(2)}", unit, False

    gte = re.search(r"(?:>=|at least|greater than or equal to|minimum of)\s*(\d+(?:\.\d+)?)", lowered)
    if gte:
        unit = ""
        for hint in unit_hints:
            if hint in lowered:
                unit = hint
                break
        return ">=", gte.group(1), unit, False

    lte = re.search(r"(?:<=|at most|less than or equal to|maximum of)\s*(\d+(?:\.\d+)?)", lowered)
    if lte:
        unit = ""
        for hint in unit_hints:
            if hint in lowered:
                unit = hint
                break
        return "<=", lte.group(1), unit, False

    numbers = re.findall(r"\d+(?:\.\d+)?", lowered)
    if numbers:
        unit = ""
        for hint in unit_hints:
            if hint in lowered:
                unit = hint
                break
        return "contains", ",".join(numbers), unit, True

    return "", "", "", True


def match_line(
    *,
    nct_id: str,
    condition_category: str,
    line: str,
    evidence_url: str,
    catalog: dict[str, dict],
) -> list[dict]:
    lowered = line.lower()
    rules: list[dict] = []

    def allowed(criterion_id: str) -> bool:
        return condition_category in catalog[criterion_id]["applicable_conditions"]

    if allowed("age_range") and "age" in lowered:
        operator, value, unit, manual = parse_range(lowered, ["years", "year"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="age_range",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit or "years",
                confidence="direct",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("sex_specific"):
        mentions_female = "female" in lowered or "women" in lowered
        mentions_male = "male" in lowered or "men" in lowered
        generic_both = (
            ("male or female" in lowered)
            or ("female or male" in lowered)
            or (mentions_female and mentions_male and "childbearing" not in lowered)
        )
        if (mentions_female or mentions_male) and not generic_both:
            rules.append(
                create_rule(
                    nct_id=nct_id,
                    condition_category=condition_category,
                    criterion_id="sex_specific",
                    criterion_text_original=line,
                    operator="in",
                    value="female" if mentions_female and not mentions_male else "male",
                    unit="",
                    confidence="direct",
                    manual_review_required=False,
                    evidence_url=evidence_url,
                    catalog=catalog,
                )
            )

    if allowed("bcva_range") and (
        "best corrected visual acuity" in lowered
        or "bcva" in lowered
        or "etdrs" in lowered
        or "letter score" in lowered
    ):
        operator, value, unit, manual = parse_range(lowered, ["letters", "letter", "20/"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="bcva_range",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit,
                confidence="not_evaluable",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("cst_threshold") and (
        "central subfield thickness" in lowered
        or "central retinal thickness" in lowered
        or "central foveal thickness" in lowered
        or re.search(r"\bcst\b", lowered)
        or re.search(r"\bcrt\b", lowered)
    ):
        operator, value, unit, manual = parse_range(lowered, ["um", "microns", "micron", "μm"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="cst_threshold",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit or "um",
                confidence="direct",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("intraretinal_fluid") and ("intraretinal fluid" in lowered or "intraretinal cyst" in lowered):
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="intraretinal_fluid",
                criterion_text_original=line,
                operator="present",
                value="true",
                unit="",
                confidence="direct",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("subretinal_fluid") and "subretinal fluid" in lowered:
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="subretinal_fluid",
                criterion_text_original=line,
                operator="present",
                value="true",
                unit="",
                confidence="direct",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("ped_presence") and (
        "pigment epithelial detachment" in lowered or re.search(r"\bped\b", lowered)
    ):
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="ped_presence",
                criterion_text_original=line,
                operator="present",
                value="true",
                unit="",
                confidence="direct",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("ga_area_range") and (
        "lesion area" in lowered or "mm2" in lowered or "mm^2" in lowered or "square millimeter" in lowered
    ):
        operator, value, unit, manual = parse_range(lowered, ["mm2", "mm^2"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="ga_area_range",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit or "mm2",
                confidence="partial",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("ga_presence") and ("geographic atrophy" in lowered or "rpe loss" in lowered):
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="ga_presence",
                criterion_text_original=line,
                operator="present",
                value="true",
                unit="",
                confidence="partial",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("rnfl_thinning") and "rnfl" in lowered:
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="rnfl_thinning",
                criterion_text_original=line,
                operator="contains",
                value="rnfl",
                unit="",
                confidence="partial",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("gcl_thinning") and ("ganglion cell layer" in lowered or re.search(r"\bgcl\b", lowered)):
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="gcl_thinning",
                criterion_text_original=line,
                operator="contains",
                value="gcl",
                unit="",
                confidence="partial",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("cd_ratio_elevated") and (
        "cup-to-disc" in lowered or "cup to disc" in lowered or "c/d" in lowered
    ):
        operator, value, unit, manual = parse_range(lowered, [])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="cd_ratio_elevated",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit,
                confidence="partial",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("high_myopia_exclusion") and (
        "axial length" in lowered or "diopter" in lowered or "myopia" in lowered
    ):
        operator, value, unit, manual = parse_range(lowered, ["mm", "diopter", "d"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="high_myopia_exclusion",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit,
                confidence="partial",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("iop_criteria") and ("intraocular pressure" in lowered or re.search(r"\biop\b", lowered)):
        operator, value, unit, manual = parse_range(lowered, ["mmhg"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="iop_criteria",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit or "mmHg",
                confidence="not_evaluable",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("visual_field_requirement") and (
        "visual field" in lowered or "perimetry" in lowered or "humphrey" in lowered
    ):
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="visual_field_requirement",
                criterion_text_original=line,
                operator="required",
                value="true",
                unit="",
                confidence="not_evaluable",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("diabetes_diagnosis") and ("diabetes" in lowered or "hba1c" in lowered or "glycated hemoglobin" in lowered):
        operator, value, unit, manual = parse_range(lowered, ["%", "percent"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="diabetes_diagnosis",
                criterion_text_original=line,
                operator=operator or "required",
                value=value or "diabetes_confirmation",
                unit=unit,
                confidence="not_evaluable",
                manual_review_required=manual and not value,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("treatment_naive") and (
        "treatment-naive" in lowered
        or "anti-vegf" in lowered
        or "washout" in lowered
        or "prior treatment" in lowered
        or "laser" in lowered
        or "intravitreal" in lowered
    ):
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="treatment_naive",
                criterion_text_original=line,
                operator="history",
                value="required",
                unit="",
                confidence="not_evaluable",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("pregnancy_exclusion") and (
        "pregnan" in lowered or "lactat" in lowered or "breastfeeding" in lowered or "childbearing" in lowered
    ):
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="pregnancy_exclusion",
                criterion_text_original=line,
                operator="exclude_if",
                value="pregnancy_related",
                unit="",
                confidence="not_evaluable",
                manual_review_required=False,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    if allowed("drss_severity") and (
        "drss" in lowered
        or "diabetic retinopathy severity scale" in lowered
        or "etdrs severity" in lowered
    ):
        operator, value, unit, manual = parse_range(lowered, ["steps"])
        rules.append(
            create_rule(
                nct_id=nct_id,
                condition_category=condition_category,
                criterion_id="drss_severity",
                criterion_text_original=line,
                operator=operator,
                value=value,
                unit=unit,
                confidence="not_evaluable",
                manual_review_required=manual,
                evidence_url=evidence_url,
                catalog=catalog,
            )
        )

    return rules


def build_trial_rules(
    trials: list[dict],
    memberships: list[dict],
    eligibility_rows: list[dict],
    catalog_rows: list[dict],
) -> list[dict]:
    catalog = catalog_lookup(catalog_rows)
    trial_url = {trial["nct_id"]: trial["source_url"] for trial in trials}
    conditions_by_nct: dict[str, list[str]] = {}
    for membership in memberships:
        conditions_by_nct.setdefault(membership["nct_id"], []).append(membership["condition_category"])

    rules: list[dict] = []
    for row in eligibility_rows:
        nct_id = row["nct_id"]
        source_url = trial_url.get(nct_id, f"https://clinicaltrials.gov/study/{nct_id}")
        conditions = sorted(
            conditions_by_nct.get(nct_id, []),
            key=lambda key: CONDITION_PRIORITY.index(key) if key in CONDITION_PRIORITY else 999,
        )
        lines = eligibility_lines(row.get("eligibility_criteria", ""))
        for condition_category in conditions:
            for line in lines:
                rules.extend(
                    match_line(
                        nct_id=nct_id,
                        condition_category=condition_category,
                        line=line,
                        evidence_url=source_url,
                        catalog=catalog,
                    )
                )

    deduped: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for rule in sorted(
        rules,
        key=lambda item: (
            item["nct_id"],
            item["condition_category"],
            item["criterion_id"],
            item["criterion_text_original"],
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


def generate() -> list[dict]:
    trials = load_trials()
    memberships = load_memberships()
    eligibility_rows = load_eligibility_text()
    catalog_rows = load_criterion_catalog()
    rules = build_trial_rules(trials, memberships, eligibility_rows, catalog_rows)
    write_json(DATA / "trial_rule_mappings.json", rules)
    return rules


def main() -> None:
    try:
        rules = generate()
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {DATA / 'trial_rule_mappings.json'} ({len(rules)} rows)")


if __name__ == "__main__":
    main()
