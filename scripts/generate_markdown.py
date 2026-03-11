"""Generate the mapping document (markdown) from structured data sources.

Output: outputs/trial_prescreening_mapping.md
"""

from datetime import date
from pathlib import Path

from load_data import (
    load_trials, load_memberships, load_fields, load_criteria,
    load_not_evaluable, unique_trial_count, trials_per_condition,
    recruiting_trials, active_trials, condition_label, ensure_outputs,
    OUTPUTS,
)


def generate():
    trials = load_trials()
    memberships = load_memberships()
    fields = load_fields()
    criteria = load_criteria()
    not_eval = load_not_evaluable()
    ensure_outputs()

    n_unique = unique_trial_count(trials)
    n_recruiting = len(recruiting_trials(trials))
    n_active = len(active_trials(trials))
    cond_counts = trials_per_condition(memberships)

    # Build trial lookup
    trial_map = {t["nct_id"]: t for t in trials}

    # Group memberships by condition
    cond_trials: dict[str, list[dict]] = {}
    for m in memberships:
        cond = m["condition_category"]
        t = trial_map.get(m["nct_id"])
        if t:
            cond_trials.setdefault(cond, []).append(t)

    lines = []
    w = lines.append

    w("# iDHEA Primary Eye Care Dataset: Clinical Trial Pre-Screening Mapping")
    w("")
    w("## Overview")
    w("")
    w(f"This document maps the **iDHEA Primary Eye Care dataset** (paired OCT + "
      f"color fundus photography from 368K subjects across 64 US/Australian "
      f"optometry sites) against **{n_unique} unique Phase II/III ophthalmic "
      f"clinical trials** to identify which eligibility criteria can be "
      f"pre-screened from existing imaging data.")
    w("")
    w(f"- **Unique trials:** {n_unique}")
    w(f"- **Currently recruiting:** {n_recruiting}")
    w(f"- **Active (recruiting + not yet + active not recruiting):** {n_active}")
    w(f"- **Generated:** {date.today().isoformat()}")
    w(f"- **Data source:** [iDHEA Primary Eye Care Data Dictionary]"
      f"(https://idhea.net/en/dataset/primaryeyecare/data-dictionary)")
    w(f"- **Trial source:** ClinicalTrials.gov (Phase II and III, all statuses)")
    w("")
    w("> **Important:** iDHEA data can pre-screen for anatomical criteria. "
      "It cannot determine full clinical trial eligibility alone. "
      "Fields such as BCVA, IOP, HbA1c, treatment history, and pregnancy "
      "status are not available and require chart review or site-level data.")
    w("")
    w("---")
    w("")

    # iDHEA field catalog
    w("## iDHEA Field Catalog")
    w("")
    w("### Fields Available for Pre-Screening")
    w("")
    w("| Field | Modality | Pre-Screen Confidence | Direct Use | Limitations |")
    w("|-------|----------|----------------------|------------|-------------|")
    for f in fields:
        conf = f["confidence_for_prescreening"]
        conf_label = {"direct": "Direct", "partial": "Partial", "not_evaluable": "Not evaluable"}.get(conf, conf)
        w(f"| {f['field_name']} | {f['modality']} | **{conf_label}** | "
          f"{f['direct_use']} | {f['limitations']} |")
    w("")

    w("### Fields NOT Available (Common Trial Requirements)")
    w("")
    w("| Missing Field | Trial Prevalence | Impact | Remediation Path |")
    w("|---------------|-----------------|--------|------------------|")
    for ne in not_eval:
        w(f"| {ne['description']} | {ne['trial_prevalence']} | "
          f"{ne['impact']} | {ne['remediation']} |")
    w("")
    w("---")
    w("")

    # Criteria mapping
    w("## Criteria Mapping")
    w("")
    for conf_level, label in [("direct", "Direct"), ("partial", "Partial"),
                               ("not_evaluable", "Not Evaluable")]:
        relevant = [c for c in criteria if c["confidence"] == conf_level]
        if not relevant:
            continue
        w(f"### {label} Pre-Screening Criteria")
        w("")
        w("| Criterion | Type | iDHEA Fields | External Dependencies | Notes |")
        w("|-----------|------|-------------|----------------------|-------|")
        for c in relevant:
            idhea = ", ".join(c["idhea_fields"]) if c["idhea_fields"] else "None"
            ext = ", ".join(c["external_dependencies"]) if c["external_dependencies"] else "None"
            conditions = ", ".join(c["applicable_conditions"])
            w(f"| {c['criterion_text']} | {c['criterion_type']} | "
              f"{idhea} | {ext} | {c['notes'][:120]}{'...' if len(c['notes']) > 120 else ''} |")
        w("")

    w("---")
    w("")

    # Trial inventory by condition
    w("## Trial Inventory by Condition")
    w("")
    w(f"**{n_unique} unique trials** across "
      f"**{len(cond_counts)} condition categories.** "
      f"Note: a trial may appear in multiple condition categories.")
    w("")

    # Summary table
    w("| Condition | Trial Count (incl. overlaps) | Recruiting | Key iDHEA Fields |")
    w("|-----------|----------------------------|------------|------------------|")
    cond_field_map = {
        "dme": "CST, IRO, SRO, Age, Sex",
        "dr": "ETDRS Grid, Vessel Features, Age, Sex",
        "wet_amd": "IRO, SRO, PED, CST, Age, Sex",
        "ga": "RPE Loss, ETDRS Grid, Age, Sex",
        "glaucoma": "RNFL, GCL, C/D, OCT Score, Age, Sex",
        "rvo": "CST, IRO, SRO, Age, Sex",
        "pathologic_myopia": "Axial Length, CST, IRO, SRO, Age, Sex",
    }
    for cond_key, count in sorted(cond_counts.items(), key=lambda x: -x[1]):
        cond_label_str = condition_label(cond_key)
        trial_list = cond_trials.get(cond_key, [])
        n_rec = len([t for t in trial_list if t["status"] == "RECRUITING"])
        key_fields = cond_field_map.get(cond_key, "Various")
        w(f"| {cond_label_str} | {count} | {n_rec} | {key_fields} |")
    w("")

    # Per-condition trial tables
    for cond_key in sorted(cond_counts.keys(),
                           key=lambda k: -cond_counts.get(k, 0)):
        cond_label_str = condition_label(cond_key)
        trial_list = cond_trials.get(cond_key, [])
        if not trial_list:
            continue

        w(f"### {cond_label_str} ({len(trial_list)} trials)")
        w("")
        w("| NCT ID | Status | Phase | Sponsor | Title |")
        w("|--------|--------|-------|---------|-------|")
        for t in sorted(trial_list, key=lambda x: x["nct_id"]):
            title_short = t["title"][:80] + ("..." if len(t["title"]) > 80 else "")
            w(f"| [{t['nct_id']}]({t['source_url']}) | {t['status']} | "
              f"{t['phase']} | {t['sponsor']} | {title_short} |")
        w("")

    w("---")
    w("")
    w("## Pre-Screening Methodology")
    w("")
    w("### What iDHEA Can Do Today")
    w("")
    w("1. **Demographic filtering** (Age, Sex) -- applies to nearly all trials")
    w("2. **CST threshold comparison** (ETDRS Grid center zone) -- applies to "
      "DME, RVO, and some AMD trials")
    w("3. **Retinal fluid detection** (IRO, SRO from RETscreenAI) -- applies to "
      "DME, RVO, wet AMD trials")
    w("4. **PED detection** (RETscreenAI) -- applies to wet AMD trials")
    w("5. **RPE loss detection** (RETscreenAI) -- suggestive for GA trials "
      "(does not quantify lesion area)")
    w("6. **Structural glaucoma indicators** (RNFL, GCL, C/D ratio) -- "
      "suggestive for glaucoma trials (requires IOP and visual field for diagnosis)")
    w("7. **Axial length estimation** -- applies to myopia exclusion criteria")
    w("")
    w("### What Requires Additional Data")
    w("")
    w("- BCVA / visual acuity (not captured -- highest-impact gap)")
    w("- Diabetes diagnosis / HbA1c (not captured)")
    w("- IOP (not captured)")
    w("- Prior treatment history (not captured)")
    w("- Fluorescein angiography findings (not available in primary care)")
    w("- DR severity grading on ETDRS scale (potential future classifier)")
    w("- Pregnancy status (not captured)")
    w("")
    w("### Future Augmentation Opportunities")
    w("")
    w("- **RETFound embeddings** (1024-dim OCT and CFP vectors) are computed "
      "for all images but require validated downstream classifiers to be "
      "useful for pre-screening. No such classifiers currently exist in the "
      "iDHEA pipeline.")
    w("- **AutoMorph vessel features** provide indirect vascular disease "
      "indicators but are not equivalent to DRSS grading.")
    w("")

    out_path = OUTPUTS / "trial_prescreening_mapping.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path} ({len(lines)} lines)")


if __name__ == "__main__":
    generate()
