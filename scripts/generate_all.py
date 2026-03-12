"""Run the full data pipeline end to end."""

from __future__ import annotations

import sys

try:
    from export_csv import generate as export_csv
    from extract_trial_rules import generate as extract_trial_rules
    from fetch_idhea_metadata import generate as fetch_idhea_metadata
    from fetch_trials import generate as fetch_trials
    from generate_metrics import generate as generate_metrics
    from generate_xlsx import generate as generate_xlsx
    from validate import run_validation
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.export_csv import generate as export_csv
    from scripts.extract_trial_rules import generate as extract_trial_rules
    from scripts.fetch_idhea_metadata import generate as fetch_idhea_metadata
    from scripts.fetch_trials import generate as fetch_trials
    from scripts.generate_metrics import generate as generate_metrics
    from scripts.generate_xlsx import generate as generate_xlsx
    from scripts.validate import run_validation


def main() -> None:
    steps = [
        ("Sync iDHEA metadata", fetch_idhea_metadata),
        ("Fetch and curate trials", fetch_trials),
        ("Extract trial rules", extract_trial_rules),
        ("Generate metrics", generate_metrics),
        ("Export CSV outputs", export_csv),
        ("Generate QA workbook", generate_xlsx),
        ("Validate outputs", run_validation),
    ]

    print("=" * 60)
    print("Running iDHEA trial-matching pipeline")
    print("=" * 60)
    for index, (label, func) in enumerate(steps, start=1):
        print(f"\n[{index}/{len(steps)}] {label}...")
        result = func()
        if isinstance(result, dict):
            print(result)
        elif isinstance(result, list):
            print(f"{len(result)} rows")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
