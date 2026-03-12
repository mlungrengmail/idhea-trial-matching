import pytest

from scripts.extract_trial_rules import build_trial_rules
from scripts.load_data import load_criterion_catalog


@pytest.mark.parametrize(
    ("condition_category", "eligibility_text", "expected_ids"),
    [
        (
            "dme",
            "Age >= 18 years.\nBCVA between 24 and 78 ETDRS letters.\nCentral subfield thickness >= 320 um.\nPresence of intraretinal fluid on OCT.\nType 2 diabetes mellitus with HbA1c <= 10%.",
            {"age_range", "bcva_range", "cst_threshold", "intraretinal_fluid", "diabetes_diagnosis"},
        ),
        (
            "wet_amd",
            "Subjects with neovascular AMD must have subretinal fluid and pigment epithelial detachment on OCT.",
            {"subretinal_fluid", "ped_presence"},
        ),
        (
            "ga",
            "Presence of geographic atrophy with lesion area between 2.5 and 17.5 mm2.",
            {"ga_presence", "ga_area_range"},
        ),
        (
            "glaucoma",
            "Intraocular pressure <= 24 mmHg. Visual field mean deviation required. RNFL thinning and cup-to-disc ratio >= 0.7.",
            {"iop_criteria", "visual_field_requirement", "rnfl_thinning", "cd_ratio_elevated"},
        ),
        (
            "dr",
            "Diabetic retinopathy severity scale score between 47 and 53 steps.",
            {"drss_severity"},
        ),
        (
            "rvo",
            "Central retinal thickness >= 300 um with intraretinal fluid.",
            {"cst_threshold", "intraretinal_fluid"},
        ),
    ],
)
def test_build_trial_rules_extracts_expected_condition_specific_rules(
    condition_category: str, eligibility_text: str, expected_ids: set[str]
):
    trials = [
        {
            "nct_id": "NCTTEST0001",
            "title": "Test Trial",
            "source_url": "https://clinicaltrials.gov/study/NCTTEST0001",
        }
    ]
    memberships = [{"nct_id": "NCTTEST0001", "condition_category": condition_category}]
    eligibility_rows = [{"nct_id": "NCTTEST0001", "eligibility_criteria": eligibility_text}]
    catalog = load_criterion_catalog()

    rules = build_trial_rules(trials, memberships, eligibility_rows, catalog)
    rule_ids = {row["criterion_id"] for row in rules}
    assert expected_ids <= rule_ids


def test_build_trial_rules_sets_evidence_url_and_manual_review_flags():
    trials = [
        {
            "nct_id": "NCTTEST0002",
            "title": "Test Trial",
            "source_url": "https://clinicaltrials.gov/study/NCTTEST0002",
        }
    ]
    memberships = [{"nct_id": "NCTTEST0002", "condition_category": "ga"}]
    eligibility_rows = [{"nct_id": "NCTTEST0002", "eligibility_criteria": "Geographic atrophy lesion area study"}]
    catalog = load_criterion_catalog()

    rules = build_trial_rules(trials, memberships, eligibility_rows, catalog)
    assert all(row["evidence_url"] == "https://clinicaltrials.gov/study/NCTTEST0002" for row in rules)
    assert any(row["manual_review_required"] for row in rules)
