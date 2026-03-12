from scripts.export_csv import (
    TRIALS_LABELED_COLUMNS,
    build_missing_requirements_rows,
    build_trials_labeled_rows,
    summarize_rules_by_trial,
)


def test_trials_labeled_schema_matches_required_columns():
    assert TRIALS_LABELED_COLUMNS == [
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


def test_trials_labeled_rows_include_fit_and_missing_data_flags():
    trials = [
        {
            "nct_id": "NCTCSV0001",
            "title": "Retinal Trial",
            "phase": "PHASE2",
            "status": "RECRUITING",
            "sponsor": "Sponsor",
            "source_url": "https://clinicaltrials.gov/study/NCTCSV0001",
        }
    ]
    memberships = [{"nct_id": "NCTCSV0001", "condition_category": "dme"}]
    rules = [
        {
            "nct_id": "NCTCSV0001",
            "condition_category": "dme",
            "criterion_id": "cst_threshold",
            "criterion_text_original": "CST >= 320 um",
            "confidence": "direct",
            "idhea_fields": ["etdrs_grid"],
            "external_dependencies": [],
            "manual_review_required": False,
            "human_verified": False,
        },
        {
            "nct_id": "NCTCSV0001",
            "condition_category": "dme",
            "criterion_id": "bcva_range",
            "criterion_text_original": "BCVA between 24 and 78 letters",
            "confidence": "not_evaluable",
            "idhea_fields": [],
            "external_dependencies": ["bcva"],
            "manual_review_required": False,
            "human_verified": False,
        },
    ]

    summaries = summarize_rules_by_trial(rules, {"bcva"})
    rows = build_trials_labeled_rows(trials, memberships, summaries)

    assert rows[0]["primary_condition"] == "dme"
    assert rows[0]["missing_data_fields"] == "bcva"
    assert rows[0]["prescreening_fit"] == "medium"


def test_missing_requirements_summary_aggregates_by_dependency_condition_and_status():
    trials = [
        {
            "nct_id": "NCTCSV0002",
            "title": "Glaucoma Trial",
            "status": "RECRUITING",
            "source_url": "https://clinicaltrials.gov/study/NCTCSV0002",
        }
    ]
    memberships = [{"nct_id": "NCTCSV0002", "condition_category": "glaucoma"}]
    rules = [
        {
            "nct_id": "NCTCSV0002",
            "condition_category": "glaucoma",
            "criterion_id": "iop_criteria",
            "external_dependencies": ["iop"],
        },
        {
            "nct_id": "NCTCSV0002",
            "condition_category": "glaucoma",
            "criterion_id": "visual_field_requirement",
            "external_dependencies": ["visual_field"],
        },
    ]

    rows, summary = build_missing_requirements_rows(
        rules,
        {"NCTCSV0002": trials[0]},
        memberships,
    )

    assert len(rows) == 2
    assert {
        (row["missing_dependency"], row["condition_category"], row["status"], row["trial_count"])
        for row in summary
    } == {
        ("iop", "glaucoma", "RECRUITING", 1),
        ("visual_field", "glaucoma", "RECRUITING", 1),
    }
