# iDHEA Clinical Trial Pre-Screening Pipeline

Maps the [iDHEA Primary Eye Care dataset](https://idhea.net/en/dataset/primaryeyecare/data-dictionary) against Phase II/III ophthalmic clinical trials to identify which eligibility criteria can be pre-screened from existing imaging data.

## What this does

1. **Fetches** trial data from ClinicalTrials.gov (Phase II/III, 8 ophthalmic conditions)
2. **Maps** trial eligibility criteria against iDHEA data fields with `direct`, `partial`, or `not_evaluable` confidence labels
3. **Generates** three artifacts from a single structured evidence base:
   - **Internal QA workbook** (`.xlsx`) -- unique counts, overlaps, caveats, spot-check status
   - **Technical readout** (`.docx`) -- methodology, field mappings, validation appendix
   - **GTM deck** (`.pptx`) -- active trials, top sponsors, pre-screening capabilities

All outputs land in `outputs/`.

## Quick start

```bash
# Install
uv sync

# Fetch trials from ClinicalTrials.gov (populates data/)
uv run python scripts/fetch_trials.py

# Generate all outputs
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
  generate_all.py             # Generate all three output artifacts
  generate_markdown.py        # Mapping document
  generate_docx.py            # Technical readout
  generate_pptx.py            # GTM deck
  generate_xlsx.py            # QA workbook
  validate.py                 # Consistency checks

outputs/                      # Generated artifacts (gitignored)
```

## Key design decisions

- **One evidence base, three views.** Every number in the docx, pptx, and markdown resolves to a row in `data/`. No hand-typed stats.
- **Unique trials vs condition memberships.** `trials.json` has one row per NCT ID. `condition_membership.json` has one row per trial-condition pair. Totals are never conflated.
- **Three confidence levels.** Each criterion mapping is labeled `direct` (iDHEA field maps to criterion with no external data), `partial` (suggestive but not definitive), or `not_evaluable` (requires clinical data outside iDHEA).
- **Pre-screening, not eligibility determination.** iDHEA data can pre-screen for anatomical criteria. It cannot determine full eligibility alone.
- **Embeddings are future work.** RETFound and other model embeddings are positioned as classifier inputs pending validation, not current pre-screening features.

## Framing

This pipeline supports two use cases:

1. **Internal DS validation** -- verify field mappings, audit trial criteria, track spot-check status
2. **External pharma/CRO conversations** -- feasibility reports, site-level population counts, pre-screening capabilities

The commercial story is "feasibility and pre-screening" rather than "eligibility determination."
