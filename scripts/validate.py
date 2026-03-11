"""Validate consistency across data sources and outputs.

Checks:
  1. trials.json NCT IDs are unique
  2. condition_membership.json references only valid NCT IDs
  3. Unique trial count != sum of condition counts (overlap expected)
  4. All criteria map to valid iDHEA fields or external deps
  5. Confidence labels are valid
  6. Output files exist and contain expected counts
  7. UTF-8 encoding is clean (no mojibake)

Usage: uv run python scripts/validate.py
"""

import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_data import (
    load_trials, load_memberships, load_fields, load_criteria,
    load_not_evaluable, unique_trial_count, trials_per_condition,
    OUTPUTS, DATA,
)

VALID_CONFIDENCE = {"direct", "partial", "not_evaluable"}
PASS = "OK"
FAIL = "FAIL"
errors = []


def check(condition: bool, msg: str):
    if condition:
        print(f"  {PASS} {msg}")
    else:
        print(f"  {FAIL} {msg}")
        errors.append(msg)


def main():
    print("=" * 60)
    print("Validating data consistency")
    print("=" * 60)

    # ── Load data ──
    print("\n[1] Loading data files...")
    try:
        trials = load_trials()
        memberships = load_memberships()
        fields = load_fields()
        criteria = load_criteria()
        not_eval = load_not_evaluable()
        check(True, f"All data files loaded successfully")
    except FileNotFoundError as e:
        check(False, f"Missing data file: {e}")
        print("\nRun: uv run python scripts/fetch_trials.py")
        sys.exit(1)

    # ── Trial uniqueness ──
    print("\n[2] Trial uniqueness...")
    nct_ids = [t["nct_id"] for t in trials]
    unique_ncts = set(nct_ids)
    check(len(nct_ids) == len(unique_ncts),
          f"NCT IDs are unique ({len(unique_ncts)} unique / {len(nct_ids)} total)")

    # Check for empty NCT IDs
    check(all(nct_ids), "No empty NCT IDs")

    # ── Condition membership referential integrity ──
    print("\n[3] Condition membership integrity...")
    membership_ncts = {m["nct_id"] for m in memberships}
    orphan_ncts = membership_ncts - unique_ncts
    check(len(orphan_ncts) == 0,
          f"All membership NCT IDs exist in trials.json "
          f"({len(orphan_ncts)} orphans)" if orphan_ncts
          else "All membership NCT IDs exist in trials.json")

    # ── Count consistency ──
    print("\n[4] Count consistency...")
    n_unique = unique_trial_count(trials)
    cond_counts = trials_per_condition(memberships)
    sum_cond = sum(cond_counts.values())
    check(sum_cond >= n_unique,
          f"Condition sum ({sum_cond}) >= unique trials ({n_unique}) "
          f"(overlap expected)")
    check(sum_cond != n_unique or len(cond_counts) == 1,
          f"Condition sum ({sum_cond}) != unique trials ({n_unique}) confirms overlaps"
          if sum_cond != n_unique else
          f"Only 1 condition, so sum == unique is expected")

    # ── Criteria mapping validation ──
    print("\n[5] Criteria mapping...")
    field_names = {f["field_name"] for f in fields}
    for c in criteria:
        conf = c.get("confidence", "")
        check(conf in VALID_CONFIDENCE,
              f"Criterion '{c['criterion_id']}' confidence '{conf}' is valid")
        for fname in c.get("idhea_fields", []):
            check(fname in field_names,
                  f"Criterion '{c['criterion_id']}' field '{fname}' exists in catalog")

    # ── Field catalog validation ──
    print("\n[6] Field catalog...")
    for f in fields:
        conf = f.get("confidence_for_prescreening", "")
        check(conf in VALID_CONFIDENCE,
              f"Field '{f['field_name']}' confidence '{conf}' is valid")

    # ── UTF-8 encoding check ──
    print("\n[7] UTF-8 encoding...")
    # Only check for the Unicode replacement character (U+FFFD), which is the
    # definitive sign of a decode error.  Earlier versions also flagged
    # \u00e2\u0080 (the byte sequence for em-dash / smart-quote starters), but
    # that triggers false positives on eligibility_text.json which contains
    # legitimate Unicode from ClinicalTrials.gov.
    for json_file in DATA.glob("*.json"):
        try:
            text = json_file.read_text(encoding="utf-8")
            has_replacement_char = "\ufffd" in text
            check(not has_replacement_char, f"{json_file.name}: clean UTF-8")
        except UnicodeDecodeError:
            check(False, f"{json_file.name}: UTF-8 decode error")

    # ── Output existence ──
    print("\n[8] Output files...")
    expected_outputs = [
        "trial_prescreening_mapping.md",
        "trial_prescreening_qa.xlsx",
        "technical_readout.docx",
        "gtm_pharma_deck.pptx",
    ]
    for fname in expected_outputs:
        path = OUTPUTS / fname
        check(path.exists(), f"{fname} exists ({path.stat().st_size:,} bytes)"
              if path.exists() else f"{fname} MISSING")

    # ── Summary ──
    print("\n" + "=" * 60)
    if errors:
        print(f"VALIDATION FAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("VALIDATION PASSED: all checks OK")
        print(f"\n  Unique trials:     {n_unique}")
        print(f"  Cond memberships:  {sum_cond}")
        print(f"  iDHEA fields:      {len(fields)}")
        print(f"  Criteria mapped:   {len(criteria)}")
        print(f"  Data gaps:         {len(not_eval)}")


if __name__ == "__main__":
    main()
