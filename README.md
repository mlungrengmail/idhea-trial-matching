# iDHEA Clinical Trial Pre-Screening Pipeline

Maps the [iDHEA Primary Eye Care dataset](https://idhea.net/en/dataset/primaryeyecare/data-dictionary) against Phase II/III ophthalmic clinical trials to identify which eligibility criteria can be pre-screened from existing imaging data.

## What this does

1. **Fetches** trial data from ClinicalTrials.gov (Phase II/III, 11 ophthalmic conditions)
2. **Maps** trial eligibility criteria against iDHEA data fields with `direct`, `partial`, or `not_evaluable` confidence labels
3. **Generates** a QA workbook (`.xlsx`) from a single structured evidence base — unique counts, overlaps, caveats, spot-check status

## Quick start

```bash
# Install
uv sync

# Fetch trials from ClinicalTrials.gov (populates data/)
uv run python scripts/fetch_trials.py

# Generate QA workbook
uv run python scripts/generate_all.py

# Validate consistency across data and outputs
uv run python scripts/validate.py
```

## Repo structure

```
data/
  idhea_fields.json           # iDHEA field catalog (field_name, modality, definition, direct_use, limitations)
  trials.json                 # Trial inventory (nct_id, title, phase, status, sponsor, source_url, last_verified_at)
  condition_membership.json   # Many-to-many trial-condition mapping (nct_id, condition)
  criteria_mappings.json      # Per-trial criteria mapping (nct_id, criterion_text, criterion_type, idhea_fields, ...)

scripts/
  fetch_trials.py             # Pull trials from ClinicalTrials.gov API
  generate_all.py             # Generate QA workbook
  generate_xlsx.py            # QA workbook generator
  validate.py                 # Consistency checks

outputs/                      # Generated artifacts (gitignored)
```

## Key design decisions

- **One evidence base, one view.** Every number in the workbook resolves to a row in `data/`. No hand-typed stats.
- **Unique trials vs condition memberships.** `trials.json` has one row per NCT ID. `condition_membership.json` has one row per trial-condition pair. Totals are never conflated.
- **Three confidence levels.** Each criterion mapping is labeled `direct` (iDHEA field maps to criterion with no external data), `partial` (suggestive but not definitive), or `not_evaluable` (requires clinical data outside iDHEA).
- **Pre-screening, not eligibility determination.** iDHEA data can pre-screen for anatomical criteria. It cannot determine full eligibility alone.
- **Embeddings are future work.** RETFound and other model embeddings are positioned as classifier inputs pending validation, not current pre-screening features.
