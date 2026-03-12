# CLAUDE.md

## Purpose

This repo builds a trustworthy labeled ophthalmic trial dataset for feasibility work. It syncs the public iDHEA Primary Eye Care metadata, curates ClinicalTrials.gov studies, extracts per-trial rule mappings, and exports CSV/XLSX artifacts.

## Commands

```bash
uv sync
uv run python scripts/generate_all.py
uv run python scripts/validate.py
uv run pytest
```

Optional LLM-assisted extraction:

```bash
$env:TRIAL_MATCHING_EXTRACTOR_MODE="hybrid"
$env:TRIAL_MATCHING_LLM_API_KEY="..."
$env:TRIAL_MATCHING_LLM_MODEL="gpt-4.1-mini"
uv run python scripts/generate_all.py
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
- `outputs/metrics.json`
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

## Guardrails

- Do not call a fetched trial “mapped” unless it has per-trial rule rows.
- Do not claim iDHEA determines full eligibility; say `anatomy-first pre-screening` or `feasibility support`.
- Keep outputs under `outputs/` and canonical data under `data/`.
- If a count changes, trace it back to the canonical JSON/CSV layers instead of patching presentation assets by hand.
- The deterministic extractor is the baseline, not the ceiling. If `TRIAL_MATCHING_EXTRACTOR_MODE` is set to `llm` or `hybrid`, treat the scripts as the orchestration layer around evidence-backed LLM reasoning, not as a regex-only system.
