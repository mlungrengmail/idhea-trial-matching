from bs4 import BeautifulSoup
import pytest

from scripts.fetch_idhea_metadata import (
    build_dataset_metadata,
    extract_metrics,
    extract_page_last_updated,
    parse_dictionary_fields,
)


SAMPLE_HTML = """
<html>
  <body>
    <h1>Primary Eye Care</h1>
    <div>Last updated October 2025</div>
    <div class="metric__container"><h2 class="metric__amount">64</h2><p class="metric__name">Locations</p></div>
    <div class="metric__container"><h2 class="metric__amount">368K</h2><p class="metric__name">Subjects</p></div>
    <div class="metric__container"><h2 class="metric__amount">734K</h2><p class="metric__name">Eyes</p></div>
    <div class="metric__container"><h2 class="metric__amount">1.2M</h2><p class="metric__name">Images</p></div>

    <h2>TIER 1 FOUNDATION: Subject data</h2>
    <table>
      <thead><tr><th>Item</th><th>Description</th><th>Units</th></tr></thead>
      <tbody>
        <tr><td>Subject ID</td><td>Anonymized subject identifier</td><td></td></tr>
        <tr><td>Sex</td><td>Biological sex</td><td></td></tr>
        <tr><td>Date of Birth</td><td>Date of birth</td><td></td></tr>
        <tr><td>Eye</td><td>Laterality</td><td></td></tr>
        <tr><td>Capture Date</td><td>Capture date</td><td></td></tr>
        <tr><td>Capture Time</td><td>Capture time</td><td></td></tr>
        <tr><td>Age</td><td>Age at capture</td><td>years</td></tr>
      </tbody>
    </table>

    <h2>TIER 1 FOUNDATION: Optical coherence tomography analysis</h2>
    <table>
      <thead><tr><th>Item</th><th>Description</th><th>Units</th></tr></thead>
      <tbody>
        <tr><td>TSNIT Circle</td><td>RNFL sectors</td><td>um</td></tr>
        <tr><td>Disc Topography</td><td>Disc metrics</td><td></td></tr>
        <tr><td>ETDRS Grid</td><td>Macular thickness zones</td><td>um</td></tr>
      </tbody>
    </table>

    <h2>TIER 2 INTELLIGENCE: Optical coherence tomography models</h2>
    <h3>RETscreenAI</h3>
    <table>
      <thead><tr><th>Item</th><th>Description</th><th>Units</th></tr></thead>
      <tbody>
        <tr><td>IRO</td><td>Intraretinal fluid</td><td></td></tr>
        <tr><td>SRO</td><td>Subretinal fluid</td><td></td></tr>
        <tr><td>PED</td><td>Pigment epithelial detachment</td><td></td></tr>
        <tr><td>RPE Loss</td><td>RPE atrophy</td><td></td></tr>
        <tr><td>Multi-factorial OCT Score</td><td>Glaucoma risk score</td><td></td></tr>
        <tr><td>Axial length estimate</td><td>Estimated axial length</td><td>mm</td></tr>
      </tbody>
    </table>

    <h2>TIER 2 INTELLIGENCE: Color fundus photography models</h2>
    <table>
      <thead><tr><th>Item</th><th>Description</th><th>Units</th></tr></thead>
      <tbody>
        <tr><td>Image Quality</td><td>Image quality grade</td><td></td></tr>
        <tr><td>Disc Features</td><td>Optic disc features</td><td></td></tr>
        <tr><td>Vessel Features</td><td>Retinal vessel features</td><td></td></tr>
        <tr><td>CIELAB vectors</td><td>Color vectors</td><td></td></tr>
        <tr><td>Pigmentation</td><td>Pigmentation score</td><td></td></tr>
      </tbody>
    </table>

    <h2>TIER 2 INTELLIGENCE: Foundation models</h2>
    <h3>RETFound</h3>
    <table>
      <thead><tr><th>Item</th><th>Description</th><th>Units</th></tr></thead>
      <tbody>
        <tr><td>OCT features</td><td>Foundation features</td><td></td></tr>
        <tr><td>CFP features</td><td>Foundation features</td><td></td></tr>
      </tbody>
    </table>
  </body>
</html>
"""


def test_parse_dictionary_fields_extracts_required_rows():
    page_last_updated = extract_page_last_updated(BeautifulSoup(SAMPLE_HTML, "html.parser").get_text("\n"))
    fields = parse_dictionary_fields(
        SAMPLE_HTML,
        "https://idhea.net/en/dataset/primaryeyecare/data-dictionary#dataDictionary",
        page_last_updated,
        "2026-03-11T00:00:00+00:00",
    )
    field_names = {row["field_name"] for row in fields}

    assert page_last_updated == "October 2025"
    assert {"subject_id", "age", "etdrs_grid", "iro", "rpe_loss", "oct_features"} <= field_names
    assert all(row["source_url"] for row in fields)
    assert all(row["source_section"] for row in fields)


def test_extract_metrics_and_build_metadata():
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    metrics = extract_metrics(soup)
    metadata = build_dataset_metadata(
        {
            "id": 1,
            "documentId": "doc",
            "title": "Primary Eye Care",
            "slug": "primaryeyecare",
            "lastUpdated": "2025-10-03",
            "published": "2025-10-03",
            "updateInfo": "Additional subjects and new labels",
            "previewButtonText": "OCT / FUNDUS",
            "tags": "REAL-WORLD DATA, Optometry",
            "content": [{"type": "paragraph", "children": [{"text": "Dataset summary"}]}],
        },
        metrics,
        field_count=19,
        source_url="https://idhea.net/en/dataset/primaryeyecare/data-dictionary#dataDictionary",
        page_last_updated="October 2025",
        synced_at="2026-03-11T00:00:00+00:00",
    )
    assert metrics[0] == {"name": "Locations", "value": "64"}
    assert metadata["dataset_slug"] == "primaryeyecare"
    assert metadata["field_count"] == 19
    assert metadata["tags"] == ["REAL-WORLD DATA", "Optometry"]


def test_parse_dictionary_fields_fails_loudly_on_schema_drift():
    broken_html = SAMPLE_HTML.replace("<td>IRO</td><td>Intraretinal fluid</td><td></td></tr>", "")
    with pytest.raises(ValueError):
        parse_dictionary_fields(
            broken_html,
            "https://idhea.net/en/dataset/primaryeyecare/data-dictionary#dataDictionary",
            "October 2025",
            "2026-03-11T00:00:00+00:00",
        )
