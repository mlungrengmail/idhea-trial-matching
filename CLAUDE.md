# CLAUDE.md

## Purpose

This repo builds a trustworthy labeled ophthalmic trial dataset for feasibility work. It syncs the public iDHEA Primary Eye Care metadata, curates ClinicalTrials.gov studies, extracts per-trial rule mappings, computes enrichment-tier coverage analysis, and exports CSV/XLSX artifacts.

## Commands

```bash
uv sync
uv run python scripts/generate_all.py
uv run python scripts/validate.py
uv run pytest
```

Optional LLM-assisted extraction (API key via environment variable only — never hardcode):

```bash
# OpenAI-compatible
export TRIAL_MATCHING_EXTRACTOR_MODE="hybrid"
export TRIAL_MATCHING_LLM_API_KEY="$YOUR_KEY"
export TRIAL_MATCHING_LLM_MODEL="gpt-4.1-mini"
uv run python scripts/generate_all.py

# Anthropic Claude
export TRIAL_MATCHING_LLM_PROVIDER="anthropic"
export TRIAL_MATCHING_LLM_API_KEY="$YOUR_KEY"
export TRIAL_MATCHING_LLM_MODEL="claude-sonnet-4-20250514"
export TRIAL_MATCHING_EXTRACTOR_MODE="hybrid"
uv run python scripts/generate_all.py
```

Incremental diff (does not overwrite existing data):

```bash
uv run python scripts/fetch_trials.py --diff
```

## Canonical files

- `data/raw/idhea_primary_eye_care.html`
- `data/raw/trials_raw.json`
- `data/raw/condition_hits.json`
- `data/idhea_dataset_metadata.json`
- `data/idhea_fields.json`
- `data/trials.json`
- `data/condition_membership.json`
- `data/eligibility_text.json`
- `data/criterion_catalog.json`
- `data/trial_rule_mappings.json`
- `data/review_overrides.json`
- `data/not_evaluable_fields.json` — gap fields with `acquisition_tier`
- `data/enrichment_models.json` — AI model catalog for coverage tiers
- `outputs/metrics.json`
- `outputs/coverage_analysis.json` — per-trial and aggregate coverage
- `outputs/trials_labeled.csv`
- `outputs/trial_rules.csv`
- `outputs/missing_requirements_by_trial.csv`
- `outputs/missing_requirements_summary.csv`
- `outputs/curation_audit.csv`
- `outputs/trial_prescreening_qa.xlsx`

## Metric definitions

- `unique_trials_total`: unique curated NCT IDs
- `condition_memberships_total`: curated trial-condition rows
- `recruiting_now_total`: status exactly `RECRUITING`
- `pipeline_open_total`: `RECRUITING + NOT_YET_RECRUITING + ENROLLING_BY_INVITATION`
- `active_total`: `pipeline_open_total + ACTIVE_NOT_RECRUITING`
- `mapped_trials_total`: trials with at least one row in `trial_rule_mappings.json`
- `verified_mapped_trials_total`: mapped trials with at least one `human_verified=true` rule row
- `unique_sponsors_total`: unique sponsor organizations across curated trials
- `pipeline_open_enrollment_total`: total enrollment across pipeline-open trials
- `top_sponsors`: top 25 sponsors by trial count

## Coverage tiers

| Tier | What it adds | Cost |
|------|-------------|------|
| 0 | iDHEA imaging (OCT/CFP) | $0 |
| 1 | + AI models (RetinSight, RETFound, Toku CLAiR) | $0 |
| 2 | + OD clinical data (BCVA, IOP, slit lamp, refraction) | $30-50K/site |
| 3 | + Lab/medical EHR (HbA1c, eGFR, systemic history) | Varies |
| 4 | + Patient questionnaire (treatment history, pregnancy) | ~$0 |

## Guardrails

- Do not call a fetched trial "mapped" unless it has per-trial rule rows.
- Do not claim iDHEA determines full eligibility; say `anatomy-first pre-screening` or `feasibility support`.
- Keep outputs under `outputs/` and canonical data under `data/`.
- If a count changes, trace it back to the canonical JSON/CSV layers instead of patching presentation assets by hand.
- The deterministic extractor is the baseline, not the ceiling. If `TRIAL_MATCHING_EXTRACTOR_MODE` is set to `llm` or `hybrid`, treat the scripts as the orchestration layer around evidence-backed LLM reasoning, not as a regex-only system.
- **Never commit API keys or secrets.** All credentials are read from environment variables.
- When referencing condition counts in documents, distinguish "11 seed queries" from "N mapped condition categories" (see `SEED_CONDITION_COUNT` and `MAPPED_CATEGORY_COUNT` in `pipeline_utils.py`).
- Gap counts in downstream artifacts must match `outputs/coverage_analysis.json` — do not hand-maintain derived numbers.
