# iDHEA Trial Matching Pipeline

This repo syncs the public iDHEA Primary Eye Care [data dictionary](https://idhea.net/) from the public iDHEA site, fetches and curates ophthalmic trials from ClinicalTrials.gov, extracts per-trial eligibility rules, and exports analyst-friendly CSVs plus a QA workbook.

## What it produces

- `data/idhea_dataset_metadata.json`
- `data/idhea_fields.json`
- `data/trials.json`
- `data/condition_membership.json`
- `data/trial_rule_mappings.json`
- `outputs/metrics.json`
- `outputs/trials_labeled.csv`
- `outputs/trial_rules.csv`
- `outputs/missing_requirements_by_trial.csv`
- `outputs/missing_requirements_summary.csv`
- `outputs/curation_audit.csv`
- `outputs/trial_prescreening_qa.xlsx`

## Quick start

```bash
uv sync
uv run python scripts/generate_all.py
```

Optional LLM-assisted extraction:

```bash
$env:TRIAL_MATCHING_EXTRACTOR_MODE="hybrid"
$env:TRIAL_MATCHING_LLM_API_KEY="..."
$env:TRIAL_MATCHING_LLM_MODEL="gpt-4.1-mini"
uv run python scripts/generate_all.py
```

The LLM path uses an OpenAI-compatible chat endpoint and keeps the rest of the pipeline unchanged. `deterministic` remains the default when no LLM settings are supplied.

Or run the pipeline in stages:

```bash
uv run python scripts/fetch_idhea_metadata.py
uv run python scripts/fetch_trials.py
uv run python scripts/extract_trial_rules.py
uv run python scripts/generate_metrics.py
uv run python scripts/export_csv.py
uv run python scripts/generate_xlsx.py
uv run python scripts/validate.py
```

## Data flow

1. `fetch_idhea_metadata.py`
   Scrapes the public iDHEA Primary Eye Care data dictionary HTML and normalizes dataset metadata plus field definitions.
2. `fetch_trials.py`
   Fetches raw ClinicalTrials.gov hits, saves raw snapshots, applies deterministic condition filtering, and writes curated trial outputs.
3. `extract_trial_rules.py`
   Builds `NCT x criterion` rule mappings from eligibility text.
   `extract_trial_rules_llm.py` adds optional `llm` or `hybrid` reasoning when an API key and model are configured.
4. `generate_metrics.py`
   Freezes canonical counts used everywhere else.
5. `export_csv.py`
   Produces the main GTM-friendly trial CSV plus audit/supporting CSVs.
6. `generate_xlsx.py`
   Builds a workbook that mirrors the canonical CSV and JSON outputs.
7. `validate.py`
   Regenerates key derived views and checks for drift, referential integrity, and noisy-trial regressions.

## Output semantics

- `trials.json`
  Curated unique trial table, one row per NCT ID.
- `condition_membership.json`
  Curated many-to-many condition table. Counts here can exceed unique trials.
- `trial_rule_mappings.json`
  Per-trial rule rows with confidence labels:
  - `direct`: iDHEA has a directly relevant field for anatomy-first pre-screening.
  - `partial`: iDHEA has a useful proxy but not a protocol-complete measure.
  - `not_evaluable`: the criterion depends on data outside the public iDHEA field set.
  Rows can be produced by deterministic parsing, LLM extraction, or hybrid union; the `extraction_method`, `model_name`, `evidence_excerpt`, and `reasoning` fields keep that audit trail visible.
- `trials_labeled.csv`
  One row per curated trial with GTM-oriented labels such as `prescreening_fit`, `gtm_priority`, and missing-data flags.

## Guardrails

- Treat this as `anatomy-first pre-screening` and `feasibility support`, not full eligibility determination.
- Use `unique_trials_total` and `condition_memberships_total` separately; do not conflate them.
- The public iDHEA website is the source of truth for dataset metadata and field dictionary in this repo.
- ClinicalTrials.gov is the source of truth for trial metadata and eligibility text.
