"""Tests for compute_coverage module."""

from scripts.compute_coverage import (
    build_tier_dependency_sets,
    compute_aggregate_coverage,
    compute_trial_coverage,
    model_criteria_set,
)


def _make_rule(
    nct_id="NCT00000001",
    condition_category="dme",
    criterion_id="age_range",
    criterion_text="Age >= 18",
    confidence="direct",
    external_dependencies=None,
):
    return {
        "nct_id": nct_id,
        "condition_category": condition_category,
        "criterion_id": criterion_id,
        "criterion_text_original": criterion_text,
        "confidence": confidence,
        "external_dependencies": external_dependencies or [],
        "idhea_fields": ["age"] if confidence == "direct" else [],
    }


def _make_not_evaluable(field_name, tier):
    return {"field_name": field_name, "acquisition_tier": tier}


class TestModelCriteriaSet:
    def test_only_available_now(self):
        models = [
            {"model_id": "a", "availability": "available_now", "criteria_covered": ["ga_presence"]},
            {"model_id": "b", "availability": "in_development", "criteria_covered": ["drss_severity"]},
        ]
        result = model_criteria_set(models)
        assert result == {"ga_presence"}

    def test_empty(self):
        assert model_criteria_set([]) == set()


class TestBuildTierDependencySets:
    def test_groups_by_tier(self):
        fields = [
            _make_not_evaluable("bcva", "od_clinical"),
            _make_not_evaluable("iop", "od_clinical"),
            _make_not_evaluable("hba1c", "lab_ehr"),
            _make_not_evaluable("treatment_history", "patient_questionnaire"),
        ]
        result = build_tier_dependency_sets(fields)
        assert result["od_clinical"] == {"bcva", "iop"}
        assert result["lab_ehr"] == {"hba1c"}
        assert result["patient_questionnaire"] == {"treatment_history"}


class TestComputeTrialCoverage:
    def test_all_direct_is_100_pct(self):
        rules = [
            _make_rule(confidence="direct", criterion_id="age_range"),
            _make_rule(confidence="direct", criterion_id="sex_specific", criterion_text="Male or Female"),
        ]
        result = compute_trial_coverage("NCT00000001", rules, set(), {})
        assert result["tier_0_imaging_only"]["pct"] == 100.0
        assert result["tier_4_plus_questionnaire"]["pct"] == 100.0

    def test_not_evaluable_needs_tier_unlock(self):
        rules = [
            _make_rule(confidence="direct"),
            _make_rule(
                confidence="not_evaluable",
                criterion_id="bcva_range",
                criterion_text="BCVA >= 20",
                external_dependencies=["bcva"],
            ),
        ]
        tier_deps = {"od_clinical": {"bcva"}, "lab_ehr": set(), "patient_questionnaire": set()}
        result = compute_trial_coverage("NCT00000001", rules, set(), tier_deps)
        assert result["tier_0_imaging_only"]["pct"] == 50.0
        assert result["tier_2_plus_od_clinical"]["pct"] == 100.0

    def test_model_criteria_covers_partial(self):
        rules = [
            _make_rule(confidence="direct"),
            _make_rule(
                confidence="partial",
                criterion_id="ga_presence",
                criterion_text="GA presence",
            ),
        ]
        model_criteria = {"ga_presence"}
        result = compute_trial_coverage("NCT00000001", rules, model_criteria, {})
        assert result["tier_0_imaging_only"]["pct"] == 50.0
        assert result["tier_1_plus_models"]["pct"] == 100.0

    def test_empty_rules(self):
        result = compute_trial_coverage("NCT00000001", [], set(), {})
        assert result["total_criteria"] == 0
        assert result["tier_0_imaging_only"]["pct"] == 0.0

    def test_persistent_gaps(self):
        rules = [
            _make_rule(
                confidence="not_evaluable",
                criterion_id="visual_field_requirement",
                criterion_text="Humphrey 24-2",
                external_dependencies=["visual_field"],
            ),
        ]
        # visual_field is specialized_equipment, not in the first 3 tiers
        tier_deps = {
            "od_clinical": {"bcva"},
            "lab_ehr": {"hba1c"},
            "patient_questionnaire": {"treatment_history"},
        }
        result = compute_trial_coverage("NCT00000001", rules, set(), tier_deps)
        assert result["tier_4_plus_questionnaire"]["pct"] == 0.0
        assert "visual_field_requirement" in result["persistent_gaps"]

    def test_deduplicates_criteria(self):
        """Same criterion_id + text from different conditions should be counted once."""
        rules = [
            _make_rule(condition_category="dme"),
            _make_rule(condition_category="dr"),  # same criterion_id and text
        ]
        result = compute_trial_coverage("NCT00000001", rules, set(), {})
        assert result["total_criteria"] == 1


class TestComputeAggregateCoverage:
    def test_averages(self):
        per_trial = [
            {
                "nct_id": "NCT00000001",
                "total_criteria": 2,
                "tier_0_imaging_only": {"covered": 1, "total": 2, "pct": 50.0},
                "tier_1_plus_models": {"covered": 2, "total": 2, "pct": 100.0},
                "tier_2_plus_od_clinical": {"covered": 2, "total": 2, "pct": 100.0},
                "tier_3_plus_lab_ehr": {"covered": 2, "total": 2, "pct": 100.0},
                "tier_4_plus_questionnaire": {"covered": 2, "total": 2, "pct": 100.0},
            },
            {
                "nct_id": "NCT00000002",
                "total_criteria": 2,
                "tier_0_imaging_only": {"covered": 0, "total": 2, "pct": 0.0},
                "tier_1_plus_models": {"covered": 0, "total": 2, "pct": 0.0},
                "tier_2_plus_od_clinical": {"covered": 2, "total": 2, "pct": 100.0},
                "tier_3_plus_lab_ehr": {"covered": 2, "total": 2, "pct": 100.0},
                "tier_4_plus_questionnaire": {"covered": 2, "total": 2, "pct": 100.0},
            },
        ]
        result = compute_aggregate_coverage(per_trial)
        assert result["trials_analyzed"] == 2
        assert result["tier_0_imaging_only_avg_pct"] == 25.0
        assert result["tier_1_plus_models_avg_pct"] == 50.0
        assert result["trials_at_100_pct"]["tier_2_plus_od_clinical"] == 2

    def test_empty(self):
        result = compute_aggregate_coverage([])
        assert result["trials_analyzed"] == 0
