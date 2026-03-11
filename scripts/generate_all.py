"""Generate all output artifacts from structured data sources.

Usage: uv run python scripts/generate_all.py
"""

import sys
from pathlib import Path

# Ensure scripts/ is on path for load_data imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_markdown import generate as gen_md
from generate_docx import generate as gen_docx
from generate_pptx import generate as gen_pptx
from generate_xlsx import generate as gen_xlsx


def main():
    print("=" * 60)
    print("Generating all outputs from data/")
    print("=" * 60)

    print("\n[1/4] Markdown mapping...")
    gen_md()

    print("\n[2/4] QA workbook (xlsx)...")
    gen_xlsx()

    print("\n[3/4] Technical readout (docx)...")
    gen_docx()

    print("\n[4/4] GTM deck (pptx)...")
    gen_pptx()

    print("\n" + "=" * 60)
    print("Done. All outputs in outputs/")
    print("=" * 60)


if __name__ == "__main__":
    main()
