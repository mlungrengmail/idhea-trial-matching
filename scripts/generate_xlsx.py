"""Generate the internal QA workbook from structured data sources.

Output: outputs/trial_prescreening_qa.xlsx

Sheets:
  1. Trials          -- one row per unique NCT ID
  2. Condition Map   -- many-to-many trial-condition pairs
  3. Criteria        -- per-criterion mapping with confidence labels
  4. iDHEA Fields    -- field catalog
  5. Not Evaluable   -- data gaps
  6. Summary         -- counts, overlaps, caveats
"""

from datetime import date

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    raise SystemExit("openpyxl not installed. Run: uv sync")

from load_data import (
    load_trials, load_memberships, load_fields, load_criteria,
    load_not_evaluable, unique_trial_count, trials_per_condition,
    trials_by_status, recruiting_trials, active_trials,
    condition_label, ensure_outputs, OUTPUTS,
)

HEADER_FILL = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Calibri", size=10)
ALT_FILL = PatternFill(start_color="F2F7FB", end_color="F2F7FB", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)

CONFIDENCE_FILLS = {
    "direct": PatternFill(start_color="DFF0D8", end_color="DFF0D8", fill_type="solid"),
    "partial": PatternFill(start_color="FCF8E3", end_color="FCF8E3", fill_type="solid"),
    "not_evaluable": PatternFill(start_color="F2DEDE", end_color="F2DEDE", fill_type="solid"),
}


def style_header(ws, row, ncols):
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def style_body(ws, start_row, end_row, ncols):
    for r in range(start_row, end_row + 1):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = THIN_BORDER
            if (r - start_row) % 2 == 1:
                cell.fill = ALT_FILL


def generate():
    trials = load_trials()
    memberships = load_memberships()
    fields = load_fields()
    criteria = load_criteria()
    not_eval = load_not_evaluable()
    ensure_outputs()

    wb = Workbook()

    # ── Sheet 1: Trials ──
    ws = wb.active
    ws.title = "Trials"
    headers = ["NCT ID", "Title", "Status", "Phase", "Sponsor", "Enrollment",
               "Start Date", "Completion Date", "Source URL", "Last Verified"]
    ws.append(headers)
    style_header(ws, 1, len(headers))
    for t in sorted(trials, key=lambda x: x["nct_id"]):
        ws.append([
            t["nct_id"], t["title"], t["status"], t["phase"],
            t["sponsor"], t.get("enrollment"), t.get("start_date", ""),
            t.get("completion_date", ""), t["source_url"],
            t.get("last_verified_at", ""),
        ])
    style_body(ws, 2, len(trials) + 1, len(headers))
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 25
    ws.column_dimensions["I"].width = 40

    # ── Sheet 2: Condition Map ──
    ws2 = wb.create_sheet("Condition Map")
    headers2 = ["NCT ID", "Condition Category", "Condition Label"]
    ws2.append(headers2)
    style_header(ws2, 1, len(headers2))
    for m in sorted(memberships, key=lambda x: (x["condition_category"], x["nct_id"])):
        ws2.append([m["nct_id"], m["condition_category"],
                    condition_label(m["condition_category"])])
    style_body(ws2, 2, len(memberships) + 1, len(headers2))
    ws2.column_dimensions["A"].width = 16
    ws2.column_dimensions["B"].width = 22
    ws2.column_dimensions["C"].width = 28

    # ── Sheet 3: Criteria ──
    ws3 = wb.create_sheet("Criteria Mappings")
    headers3 = ["Criterion ID", "Criterion Text", "Type", "Applicable Conditions",
                "iDHEA Fields", "External Dependencies", "Confidence",
                "Notes", "Human Verified"]
    ws3.append(headers3)
    style_header(ws3, 1, len(headers3))
    for i, c in enumerate(criteria):
        row_num = i + 2
        ws3.append([
            c["criterion_id"], c["criterion_text"], c["criterion_type"],
            ", ".join(c.get("applicable_conditions", [])),
            ", ".join(c.get("idhea_fields", [])) or "None",
            ", ".join(c.get("external_dependencies", [])) or "None",
            c["confidence"], c.get("notes", ""),
            "Yes" if c.get("human_verified") else "No",
        ])
        # Color the confidence cell
        conf_fill = CONFIDENCE_FILLS.get(c["confidence"])
        if conf_fill:
            ws3.cell(row=row_num, column=7).fill = conf_fill
    style_body(ws3, 2, len(criteria) + 1, len(headers3))
    ws3.column_dimensions["A"].width = 22
    ws3.column_dimensions["B"].width = 50
    ws3.column_dimensions["D"].width = 30
    ws3.column_dimensions["E"].width = 25
    ws3.column_dimensions["F"].width = 25
    ws3.column_dimensions["G"].width = 16
    ws3.column_dimensions["H"].width = 60

    # ── Sheet 4: iDHEA Fields ──
    ws4 = wb.create_sheet("iDHEA Fields")
    headers4 = ["Field Name", "Modality", "Tier", "Pre-Screen Confidence",
                "Direct Use", "Limitations"]
    ws4.append(headers4)
    style_header(ws4, 1, len(headers4))
    for i, f in enumerate(fields):
        row_num = i + 2
        ws4.append([
            f["field_name"], f["modality"], f.get("tier", ""),
            f["confidence_for_prescreening"],
            f["direct_use"], f["limitations"],
        ])
        conf_fill = CONFIDENCE_FILLS.get(f["confidence_for_prescreening"])
        if conf_fill:
            ws4.cell(row=row_num, column=4).fill = conf_fill
    style_body(ws4, 2, len(fields) + 1, len(headers4))
    ws4.column_dimensions["A"].width = 28
    ws4.column_dimensions["B"].width = 14
    ws4.column_dimensions["D"].width = 20
    ws4.column_dimensions["E"].width = 45
    ws4.column_dimensions["F"].width = 60

    # ── Sheet 5: Not Evaluable ──
    ws5 = wb.create_sheet("Not Evaluable")
    headers5 = ["Field", "Description", "Trial Prevalence", "Impact", "Remediation"]
    ws5.append(headers5)
    style_header(ws5, 1, len(headers5))
    for ne in not_eval:
        ws5.append([
            ne["field_name"], ne["description"], ne["trial_prevalence"],
            ne["impact"], ne["remediation"],
        ])
    style_body(ws5, 2, len(not_eval) + 1, len(headers5))
    ws5.column_dimensions["A"].width = 22
    ws5.column_dimensions["B"].width = 40
    ws5.column_dimensions["C"].width = 22
    ws5.column_dimensions["D"].width = 55
    ws5.column_dimensions["E"].width = 40

    # ── Sheet 6: Summary ──
    ws6 = wb.create_sheet("Summary")
    ws6.append(["Metric", "Value"])
    style_header(ws6, 1, 2)

    n_unique = unique_trial_count(trials)
    n_recruiting = len(recruiting_trials(trials))
    n_active = len(active_trials(trials))
    status_counts = trials_by_status(trials)
    cond_counts = trials_per_condition(memberships)

    summary_rows = [
        ("Generated", date.today().isoformat()),
        ("Unique trials (NCT IDs)", n_unique),
        ("Total condition memberships", len(memberships)),
        ("Currently recruiting", n_recruiting),
        ("Active (recruiting + enrolling + active not recruiting)", n_active),
        ("", ""),
        ("BY CONDITION (includes overlaps)", ""),
    ]
    for cond_key, count in sorted(cond_counts.items(), key=lambda x: -x[1]):
        summary_rows.append((f"  {condition_label(cond_key)}", count))
    summary_rows.append(("", ""))
    summary_rows.append(("BY STATUS", ""))
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        summary_rows.append((f"  {status}", count))
    summary_rows.append(("", ""))
    summary_rows.append(("CAVEATS", ""))
    summary_rows.append(("", "Condition membership counts include overlaps "
                         "(one trial can appear in multiple conditions)."))
    summary_rows.append(("", "Unique trial count is deduplicated on NCT ID."))
    summary_rows.append(("", "'Direct' pre-screening means the iDHEA field maps "
                         "to the criterion without external data, but does NOT mean "
                         "the criterion alone determines eligibility."))
    summary_rows.append(("", "Embeddings (RETFound, AutoMorph) are future classifier "
                         "inputs, not current pre-screening features."))

    for label, val in summary_rows:
        ws6.append([label, val])
    style_body(ws6, 2, len(summary_rows) + 1, 2)
    ws6.column_dimensions["A"].width = 50
    ws6.column_dimensions["B"].width = 80

    out_path = OUTPUTS / "trial_prescreening_qa.xlsx"
    wb.save(str(out_path))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    generate()
