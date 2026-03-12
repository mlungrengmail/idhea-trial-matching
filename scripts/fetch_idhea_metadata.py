"""Fetch public iDHEA dataset metadata and data dictionary fields.

Outputs:
  data/raw/idhea_primary_eye_care.html
  data/idhea_dataset_metadata.json
  data/idhea_fields.json

Usage:
  uv run python scripts/fetch_idhea_metadata.py
"""

from __future__ import annotations

import json
import re
import sys

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(f"Missing dependency: {exc}. Run: uv sync")

try:
    from pipeline_utils import (
        flatten_text,
        ensure_directories,
        normalize_space,
        slugify,
        unique_list,
        utc_now_iso,
        write_json,
        DATA,
        RAW,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.pipeline_utils import (
        flatten_text,
        ensure_directories,
        normalize_space,
        slugify,
        unique_list,
        utc_now_iso,
        write_json,
        DATA,
        RAW,
    )

PRIMARY_EYE_CARE_URL = "https://idhea.net/en/dataset/primaryeyecare/data-dictionary#dataDictionary"
DATASETS_API_URL = "https://api.idhea.net/api/datasets"

FIELD_NAME_MAP = {
    "subject id": "subject_id",
    "sex": "sex",
    "date of birth": "date_of_birth",
    "eye": "eye",
    "capture date": "capture_date",
    "capture time": "capture_time",
    "age": "age",
    "tsnit circle": "tsnit_circle",
    "disc topography": "disc_topography",
    "etdrs grid": "etdrs_grid",
    "iro": "iro",
    "sro": "sro",
    "ped": "ped",
    "rpe loss": "rpe_loss",
    "multi-factorial oct score": "multifactorial_oct_score",
    "axial length estimate": "axial_length_estimate",
    "image quality": "image_quality",
    "disc features": "disc_features",
    "vessel features": "vessel_features",
    "cielab vectors": "cielab_vectors",
    "pigmentation": "pigmentation",
    "oct features": "oct_features",
    "cfp features": "cfp_features",
}

REQUIRED_FIELD_NAMES = {
    "subject_id",
    "sex",
    "age",
    "tsnit_circle",
    "disc_topography",
    "etdrs_grid",
    "iro",
    "sro",
    "ped",
    "rpe_loss",
    "multifactorial_oct_score",
    "axial_length_estimate",
    "image_quality",
    "disc_features",
    "vessel_features",
    "cielab_vectors",
    "pigmentation",
    "oct_features",
    "cfp_features",
}


def fetch_json(session: requests.Session, url: str) -> dict:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def find_primary_eye_care_record(payload: dict) -> dict:
    rows = payload.get("data", [])
    for row in rows:
        if row.get("slug") == "primaryeyecare":
            return row
    raise ValueError("Primary Eye Care dataset not found in iDHEA API payload")


def extract_page_last_updated(page_text: str) -> str:
    match = re.search(r"Last updated\s+([A-Za-z]+\s+\d{4})", page_text)
    if not match:
        raise ValueError("Could not extract 'Last updated' value from iDHEA page")
    return match.group(1)


def extract_metrics(soup: BeautifulSoup) -> list[dict]:
    metrics: list[dict] = []
    for container in soup.find_all(
        class_=lambda value: isinstance(value, str) and "metric__container" in value
    ):
        amount = container.find(
            class_=lambda value: isinstance(value, str) and "metric__amount" in value
        )
        name = container.find(
            class_=lambda value: isinstance(value, str) and "metric__name" in value
        )
        metric_name = normalize_space(name.get_text(" ", strip=True) if name else "")
        metric_value = normalize_space(amount.get_text(" ", strip=True) if amount else "")
        if metric_name and metric_value:
            metrics.append({"name": metric_name, "value": metric_value})
    if not metrics:
        raise ValueError("Could not extract dataset metrics from iDHEA page")
    return metrics


def infer_modality(section: str, subsection: str, label: str) -> str:
    section_key = f"{section} {subsection}".lower()
    label_key = label.lower()
    if "subject data" in section_key:
        return "demographics"
    if "optical coherence tomography analysis" in section_key:
        return "oct"
    if "foundation models" in section_key:
        return "foundation_model"
    if "color fundus photography" in section_key:
        return "cfp_ai"
    if "oct score" in label_key or "axial length" in label_key:
        return "oct_derived"
    if label_key in {"iro", "sro", "ped", "rpe loss"}:
        return "oct_ai"
    return "dataset_field"


def canonical_field_name(label: str) -> str:
    normalized = normalize_space(label).lower()
    return FIELD_NAME_MAP.get(normalized, slugify(normalized))


def parse_dictionary_fields(
    html: str,
    source_url: str,
    page_last_updated: str,
    synced_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    current_section = ""
    current_subsection = ""
    rows: list[dict] = []

    for node in soup.find_all(["h2", "h3", "table"]):
        if node.name == "h2":
            current_section = normalize_space(node.get_text(" ", strip=True))
            current_subsection = ""
            continue
        if node.name == "h3":
            current_subsection = normalize_space(node.get_text(" ", strip=True))
            continue
        if node.name != "table":
            continue

        header_cells = [
            normalize_space(cell.get_text(" ", strip=True)).lower()
            for cell in node.find_all("th")
        ]
        if not header_cells:
            continue

        table_headers = header_cells[:3]
        if "item" not in table_headers[0] and "field" not in table_headers[0]:
            continue

        for row in node.find_all("tr"):
            cells = [normalize_space(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
            if len(cells) < 2:
                continue

            source_label = cells[0]
            description = cells[1]
            units = cells[2] if len(cells) > 2 else ""
            field_name = canonical_field_name(source_label)
            rows.append(
                {
                    "field_name": field_name,
                    "source_label": source_label,
                    "definition": description,
                    "description": description,
                    "units": units,
                    "modality": infer_modality(current_section, current_subsection, source_label),
                    "source_section": current_section,
                    "source_subsection": current_subsection,
                    "source_url": source_url,
                    "page_last_updated": page_last_updated,
                    "synced_at": synced_at,
                }
            )

    deduped: list[dict] = []
    seen_names: set[str] = set()
    for row in rows:
        if row["field_name"] in seen_names:
            continue
        seen_names.add(row["field_name"])
        deduped.append(row)

    missing = sorted(REQUIRED_FIELD_NAMES - {row["field_name"] for row in deduped})
    if missing:
        raise ValueError(f"Missing expected iDHEA field rows: {', '.join(missing)}")
    return deduped


def build_dataset_metadata(
    dataset_record: dict,
    metrics: list[dict],
    field_count: int,
    source_url: str,
    page_last_updated: str,
    synced_at: str,
) -> dict:
    tags = dataset_record.get("tags", "")
    if isinstance(tags, str):
        tag_list = [normalize_space(tag) for tag in tags.split(",") if normalize_space(tag)]
    else:
        tag_list = []

    content_summary = normalize_space(flatten_text(dataset_record.get("content", [])))
    metadata = {
        "dataset_id": dataset_record.get("id"),
        "document_id": dataset_record.get("documentId"),
        "dataset_title": dataset_record.get("title"),
        "dataset_slug": dataset_record.get("slug"),
        "source_url": source_url,
        "api_source_url": DATASETS_API_URL,
        "page_last_updated": page_last_updated,
        "api_last_updated": dataset_record.get("lastUpdated"),
        "published": dataset_record.get("published"),
        "update_info": dataset_record.get("updateInfo"),
        "preview_button_text": dataset_record.get("previewButtonText"),
        "tags": unique_list(tag_list),
        "content_summary": content_summary,
        "metrics": metrics,
        "field_count": field_count,
        "synced_at": synced_at,
    }

    required_values = [
        metadata["dataset_title"],
        metadata["dataset_slug"],
        metadata["source_url"],
        metadata["page_last_updated"],
        metadata["synced_at"],
    ]
    if not all(required_values):
        raise ValueError("iDHEA dataset metadata is missing one or more required values")
    return metadata


def generate() -> tuple[dict, list[dict]]:
    ensure_directories()
    synced_at = utc_now_iso()
    with requests.Session() as session:
        dataset_payload = fetch_json(session, DATASETS_API_URL)
        dataset_record = find_primary_eye_care_record(dataset_payload)
        html = fetch_text(session, PRIMARY_EYE_CARE_URL)

    raw_html_path = RAW / "idhea_primary_eye_care.html"
    raw_html_path.write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)
    page_last_updated = extract_page_last_updated(page_text)
    metrics = extract_metrics(soup)
    fields = parse_dictionary_fields(html, PRIMARY_EYE_CARE_URL, page_last_updated, synced_at)
    metadata = build_dataset_metadata(
        dataset_record,
        metrics,
        len(fields),
        PRIMARY_EYE_CARE_URL,
        page_last_updated,
        synced_at,
    )

    write_json(DATA / "idhea_dataset_metadata.json", metadata)
    write_json(DATA / "idhea_fields.json", fields)
    return metadata, fields


def main() -> None:
    try:
        metadata, fields = generate()
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {DATA / 'idhea_dataset_metadata.json'}")
    print(f"Wrote {DATA / 'idhea_fields.json'} ({len(fields)} fields)")
    print(f"Wrote {RAW / 'idhea_primary_eye_care.html'}")
    print(json.dumps({"dataset_title": metadata["dataset_title"], "field_count": len(fields)}, indent=2))


if __name__ == "__main__":
    main()
