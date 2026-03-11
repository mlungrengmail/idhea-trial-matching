# CLAUDE.md

## Purpose

Pipeline that maps iDHEA Primary Eye Care dataset fields against Phase II/III
ophthalmic clinical trials. Generates three artifacts from one structured
evidence base: QA workbook, technical readout, GTM deck.

## Commands

```bash
uv sync
uv run python scripts/fetch_trials.py
uv run python scripts/generate_all.py
uv run python scripts/validate.py
```

## Architecture

Single source of truth lives in `data/`:

- `idhea_fields.json` -- field catalog
- `trials.json` -- one row per unique NCT ID
- `condition_membership.json` -- many-to-many trial-condition pairs
- `criteria_mappings.json` -- per-trial criteria with confidence labels

Generation scripts read `data/`, write to `outputs/`. Never hand-edit outputs.

## Guardrails

- Do not say "eligibility determination" -- say "pre-screening" or "feasibility"
- Do not claim embeddings (RETFound, AutoMorph) are validated pre-screening
  features -- they are future classifier inputs
- Do not conflate unique trial counts with condition-membership counts
- Every headline number must trace back to a `data/` row or cited external source
- "No new imaging capture needed for anatomy-only pre-screening" -- not
  "zero new data capture needed"
- All outputs go to `outputs/` -- never repo root
