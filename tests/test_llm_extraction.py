from scripts.extract_trial_rules_llm import build_trial_rules
from scripts.llm_client import extract_json_payload
from scripts.load_data import load_criterion_catalog


class FakeLLMClient:
    model_name = "fake-llm"

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def extract_rules(self, *, system_prompt: str, user_prompt: str) -> dict:
        assert "criterion_catalog" in user_prompt
        self.calls += 1
        return self.payload


def test_extract_json_payload_handles_fenced_json():
    payload = extract_json_payload(
        "```json\n{\"rules\": [{\"criterion_id\": \"age_range\"}]}\n```"
    )
    assert payload == {"rules": [{"criterion_id": "age_range"}]}


def test_llm_hybrid_mode_adds_reasoned_rules():
    catalog = load_criterion_catalog()
    trials = [
        {
            "nct_id": "NCTLLM0001",
            "title": "LLM Trial",
            "source_url": "https://clinicaltrials.gov/study/NCTLLM0001",
        }
    ]
    memberships = [{"nct_id": "NCTLLM0001", "condition_category": "ga"}]
    eligibility_rows = [
        {
            "nct_id": "NCTLLM0001",
            "eligibility_criteria": "Presence of geographic atrophy with lesion area between 2.5 and 17.5 mm2.",
        }
    ]
    client = FakeLLMClient(
        {
            "rules": [
                {
                    "criterion_id": "ga_area_range",
                    "criterion_text_original": "lesion area between 2.5 and 17.5 mm2",
                    "operator": "between",
                    "value": "2.5-17.5",
                    "unit": "mm2",
                    "confidence": "partial",
                    "manual_review_required": False,
                    "evidence_excerpt": "lesion area between 2.5 and 17.5 mm2",
                    "reasoning": "This is a lesion-size threshold for GA.",
                }
            ]
        }
    )

    rules = build_trial_rules(
        trials,
        memberships,
        eligibility_rows,
        catalog,
        mode="hybrid",
        llm_client=client,
    )

    assert client.calls == 1
    llm_rules = [row for row in rules if row.get("extraction_method") == "llm"]
    assert len(llm_rules) == 1
    assert llm_rules[0]["model_name"] == "fake-llm"
    assert llm_rules[0]["reasoning"] == "This is a lesion-size threshold for GA."


def test_llm_only_mode_filters_unknown_criteria():
    catalog = load_criterion_catalog()
    trials = [
        {
            "nct_id": "NCTLLM0002",
            "title": "LLM Trial",
            "source_url": "https://clinicaltrials.gov/study/NCTLLM0002",
        }
    ]
    memberships = [{"nct_id": "NCTLLM0002", "condition_category": "dme"}]
    eligibility_rows = [{"nct_id": "NCTLLM0002", "eligibility_criteria": "Age >= 18 years."}]
    client = FakeLLMClient(
        {
            "rules": [
                {
                    "criterion_id": "made_up_rule",
                    "criterion_text_original": "fake",
                    "operator": ">=",
                    "value": "1",
                    "unit": "",
                    "confidence": "direct",
                    "manual_review_required": False,
                    "evidence_excerpt": "fake",
                    "reasoning": "fake",
                }
            ]
        }
    )

    rules = build_trial_rules(
        trials,
        memberships,
        eligibility_rows,
        catalog,
        mode="llm",
        llm_client=client,
    )

    assert rules == []
