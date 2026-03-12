from scripts.fetch_trials import build_curation_outputs, trial_matches_condition


def make_trial(nct_id: str, title: str, conditions: list[str]) -> dict:
    return {
        "nct_id": nct_id,
        "title": title,
        "official_title": title,
        "status": "RECRUITING",
        "phase": "PHASE2",
        "phase_list": ["PHASE2"],
        "sponsor": "Test Sponsor",
        "enrollment": 100,
        "start_date": "2025-01",
        "completion_date": "",
        "eligibility_criteria": "Age >= 18 years",
        "conditions": conditions,
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "last_verified_at": "2026-03-11T00:00:00+00:00",
    }


def test_trial_filter_excludes_sturge_weber_false_positive():
    matched, reason = trial_matches_condition(
        make_trial(
            "NCT01997255",
            "Adjunctive Everolimus for Epilepsy in Children With Sturge-Weber Syndrome",
            ["Epilepsy"],
        ),
        "glaucoma",
    )
    assert not matched
    assert "missing glaucoma" in reason


def test_trial_filter_excludes_presbyopia_false_positive():
    matched, reason = trial_matches_condition(
        make_trial("NCT05753189", "Study of Drug X for Presbyopia", ["Presbyopia"]),
        "pathologic_myopia",
    )
    assert not matched
    assert reason == "explicit presbyopia exclusion"


def test_build_curation_outputs_applies_manual_override():
    good_trial = make_trial(
        "NCT99999999",
        "Study in Neovascular Age-Related Macular Degeneration",
        ["Neovascular Age-Related Macular Degeneration"],
    )
    noisy_trial = make_trial(
        "NCT05753189",
        "Study of Drug X for Presbyopia",
        ["Presbyopia"],
    )
    trials_by_nct = {good_trial["nct_id"]: good_trial, noisy_trial["nct_id"]: noisy_trial}
    raw_hits = [
        {
            "nct_id": good_trial["nct_id"],
            "condition_category": "wet_amd",
            "condition_query": "neovascular age-related macular degeneration",
        },
        {
            "nct_id": noisy_trial["nct_id"],
            "condition_category": "pathologic_myopia",
            "condition_query": "pathological myopia",
        },
    ]
    overrides = [
        {
            "nct_id": "NCT05753189",
            "condition_category": "pathologic_myopia",
            "action": "exclude",
            "corrected_conditions": [],
            "reason": "Presbyopia study is out of scope",
            "source": "manual_review",
        }
    ]
    curated_trials, memberships, eligibility_rows, audit_rows = build_curation_outputs(
        trials_by_nct, raw_hits, overrides
    )

    assert [row["nct_id"] for row in curated_trials] == ["NCT99999999"]
    assert memberships == [{"nct_id": "NCT99999999", "condition_category": "wet_amd"}]
    assert [row["nct_id"] for row in eligibility_rows] == ["NCT99999999"]
    assert any(row["decision"] == "exclude" for row in audit_rows)
