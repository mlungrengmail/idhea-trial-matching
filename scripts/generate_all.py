"""Generate all output artifacts from structured data sources.

Usage: uv run python scripts/generate_all.py
"""

import sys
from pathlib import Path

# Ensure scripts/ is on path for load_data imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_xlsx import generate as gen_xlsx


def main():
    print("=" * 60)
    print("Generating outputs from data/")
    print("=" * 60)

    print("\n[1/1] QA workbook (xlsx)...")
    gen_xlsx()

    print("\n" + "=" * 60)
    print("Done. All outputs in outputs/")
    print("=" * 60)


if __name__ == "__main__":
    main()
