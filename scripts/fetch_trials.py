"""Fetch, curate, and normalize ophthalmic trial data from ClinicalTrials.gov.

Outputs:
  data/raw/trials_raw.json
  data/raw/condition_hits.json
  data/trials.json
  data/condition_membership.json
  data/eligibility_text.json

Usage:
  uv run python scripts/fetch_trials.py
  uv run python scripts/fetch_trials.py --recruiting-only
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import requests
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(f"Missing dependency: {exc}. Run: uv sync")

try:
    from pipeline_utils import (
        CONDITION_PRIORITY,
        KNOWN_NOISY_NCTS,
        ensure_directories,
        normalize_space,
        unique_list,
        utc_now_iso,
        write_json,
        DATA,
        RAW,
    )
    from load_data import load_review_overrides
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.pipeline_utils import (
        CONDITION_PRIORITY,
        KNOWN_NOISY_NCTS,
        ensure_directories,
        normalize_space,
        unique_list,
        utc_now_iso,
        write_json,
        DATA,
        RAW,
    )
    from scripts.load_data import load_review_overrides

API_BASE = "https://clinicaltrials.gov/api/v2/studies"
PHASES = ["PHASE2", "PHASE3"]

CONDITION_SPECS = [
    {"condition_category": "dme", "condition_query": "diabetic macular edema"},
    {"condition_category": "dr", "condition_query": "diabetic retinopathy"},
    {"condition_category": "wet_amd", "condition_query": "neovascular age-related macular degeneration"},
    {"condition_category": "ga", "condition_query": "geographic atrophy"},
    {"condition_category": "glaucoma", "condition_query": "glaucoma"},
    {"condition_category": "rvo", "condition_query": "retinal vein occlusion"},
    {"condition_category": "pathologic_myopia", "condition_query": "pathological myopia"},
    {"condition_category": "macular_hole", "condition_query": "macular hole"},
    {"condition_category": "uveitic_me", "condition_query": "uveitic macular edema"},
    {"condition_category": "stargardt", "condition_query": "Stargardt disease"},
    {"condition_category": "vma", "condition_query": "vitreomacular adhesion"},
]


def fetch_condition(
    session: requests.Session,
    condition_query: str,
    phases: list[str],
    page_size: int = 100,
    max_pages: int = 10,
    recruiting_only: bool = False,
) -> list[dict]:
    """Fetch all studies for a single condition query."""
    all_studies: list[dict] = []
    page_token = None
    statuses = ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]
    if not recruiting_only:
        statuses.extend(
            [
                "ACTIVE_NOT_RECRUITING",
                "COMPLETED",
                "SUSPENDED",
                "TERMINATED",
                "WITHDRAWN",
            ]
        )

    phase_terms = " OR ".join(phases)
    for _ in range(max_pages):
        params = {
            "query.cond": condition_query,
            "filter.overallStatus": ",".join(statuses),
            "query.term": f"AREA[Phase]({phase_terms})",
            "pageSize": page_size,
        }
        if page_token:
            params["pageToken"] = page_token

        response = session.get(API_BASE, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        studies = payload.get("studies", [])
        all_studies.extend(studies)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.25)
    return all_studies


def parse_study(study: dict, verified_at: str) -> dict:
    """Extract normalized trial fields from a ClinicalTrials.gov study payload."""
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
    design_mod = proto.get("designModule", {})
    eligibility_mod = proto.get("eligibilityModule", {})
    conditions_mod = proto.get("conditionsModule", {})

    nct_id = ident.get("nctId", "")
    phases = design_mod.get("phases", [])
    lead_sponsor = sponsor_mod.get("leadSponsor", {})

    return {
        "nct_id": nct_id,
        "title": ident.get("briefTitle", ""),
        "official_title": ident.get("officialTitle", ""),
        "status": status_mod.get("overallStatus", ""),
        "phase": " / ".join(phases) if phases else "N/A",
        "phase_list": phases,
        "sponsor": lead_sponsor.get("name", ""),
        "enrollment": design_mod.get("enrollmentInfo", {}).get("count"),
        "start_date": status_mod.get("startDateStruct", {}).get("date", ""),
        "completion_date": status_mod.get("completionDateStruct", {}).get("date", ""),
        "eligibility_criteria": eligibility_mod.get("eligibilityCriteria", ""),
        "conditions": conditions_mod.get("conditions", []),
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "last_verified_at": verified_at,
    }


def trial_search_text(trial: dict) -> str:
    chunks = [trial.get("title", ""), trial.get("official_title", "")]
    chunks.extend(trial.get("conditions", []))
    return normalize_space(" ".join(chunks)).lower()


def contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def trial_matches_condition(trial: dict, condition_category: str) -> tuple[bool, str]:
    """Deterministic post-filter for broad ClinicalTrials.gov query results."""
    text = trial_search_text(trial)

    if condition_category == "dme":
        matched = (
            "diabetic macular edema" in text
            or "diabetic macular oedema" in text
            or ("diabetic" in text and ("macular edema" in text or "macular oedema" in text))
        )
        return matched, "matched diabetic + macular edema terms" if matched else "missing DME terms"

    if condition_category == "dr":
        matched = contains_any(
            text,
            [
                "diabetic retinopathy",
                "nonproliferative diabetic retinopathy",
                "proliferative diabetic retinopathy",
                "npdr",
                "pdr",
            ],
        )
        return matched, "matched diabetic retinopathy terms" if matched else "missing DR terms"

    if condition_category == "wet_amd":
        matched = contains_any(
            text,
            [
                "wet age-related macular degeneration",
                "neovascular age-related macular degeneration",
                "neovascular amd",
                "wet amd",
                "choroidal neovascularization secondary to amd",
            ],
        )
        return matched, "matched wet AMD terms" if matched else "missing wet AMD terms"

    if condition_category == "ga":
        matched = "geographic atrophy" in text
        return matched, "matched geographic atrophy" if matched else "missing GA terms"

    if condition_category == "glaucoma":
        matched = contains_any(text, ["glaucoma", "ocular hypertension", "intraocular pressure"])
        return matched, "matched glaucoma / ocular hypertension terms" if matched else "missing glaucoma terms"

    if condition_category == "rvo":
        matched = contains_any(
            text,
            [
                "retinal vein occlusion",
                "branch retinal vein occlusion",
                "central retinal vein occlusion",
                "brvo",
                "crvo",
            ],
        )
        return matched, "matched RVO terms" if matched else "missing RVO terms"

    if condition_category == "pathologic_myopia":
        if "presbyopia" in text:
            return False, "explicit presbyopia exclusion"
        matched = contains_any(
            text,
            [
                "pathological myopia",
                "pathologic myopia",
                "high myopia",
                "myopic choroidal neovascularization",
                "myopic cnv",
                "degenerative myopia",
            ],
        )
        return matched, "matched pathologic myopia terms" if matched else "missing pathologic myopia terms"

    if condition_category == "macular_hole":
        matched = "macular hole" in text
        return matched, "matched macular hole" if matched else "missing macular hole terms"

    if condition_category == "uveitic_me":
        matched = contains_any(text, ["uveitic macular edema", "uveitic macular oedema"]) or (
            "uveitis" in text and ("macular edema" in text or "macular oedema" in text)
        )
        return matched, "matched uveitic macular edema terms" if matched else "missing uveitic ME terms"

    if condition_category == "stargardt":
        matched = "stargardt" in text
        return matched, "matched Stargardt terms" if matched else "missing Stargardt terms"

    if condition_category == "vma":
        matched = contains_any(
            text,
            ["vitreomacular adhesion", "vitreomacular traction", "vma", "vmt"],
        )
        return matched, "matched VMA/VMT terms" if matched else "missing VMA/VMT terms"

    return False, f"unknown condition category {condition_category}"


def build_override_index(overrides: list[dict]) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for row in overrides:
        condition_category = row.get("condition_category")
        if condition_category:
            index[(row["nct_id"], condition_category)] = row
    return index


def build_curation_outputs(
    trials_by_nct: dict[str, dict],
    raw_hits: list[dict],
    overrides: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    override_index = build_override_index(overrides)
    curated_pairs: set[tuple[str, str]] = set()
    audit_rows: list[dict] = []

    for hit in raw_hits:
        nct_id = hit["nct_id"]
        condition_category = hit["condition_category"]
        trial = trials_by_nct[nct_id]
        override = override_index.get((nct_id, condition_category))
        corrected_conditions = []

        if override:
            action = override.get("action", "exclude")
            reason = override.get("reason", "manual review override")
            corrected_conditions = override.get("corrected_conditions", [])
            if action == "include":
                curated_pairs.add((nct_id, condition_category))
                decision = "include"
            elif action == "reassign":
                for corrected in corrected_conditions:
                    curated_pairs.add((nct_id, corrected))
                decision = "reassign"
            else:
                decision = "exclude"
            override_source = override.get("source", "manual_review")
        else:
            matched, reason = trial_matches_condition(trial, condition_category)
            if matched:
                curated_pairs.add((nct_id, condition_category))
                decision = "include"
            else:
                decision = "exclude"
            override_source = ""

        audit_rows.append(
            {
                "nct_id": nct_id,
                "condition_category": condition_category,
                "condition_query": hit["condition_query"],
                "title": trial["title"],
                "status": trial["status"],
                "decision": decision,
                "reason": reason,
                "override_source": override_source,
                "corrected_conditions": "; ".join(corrected_conditions),
            }
        )

    curated_trials = []
    eligibility_rows = []
    curated_trial_ids = {nct_id for nct_id, _ in curated_pairs}
    for nct_id in sorted(curated_trial_ids):
        trial = trials_by_nct[nct_id]
        curated_trials.append(
            {
                key: value
                for key, value in trial.items()
                if key != "eligibility_criteria" and key != "phase_list"
            }
        )
        if trial.get("eligibility_criteria"):
            eligibility_rows.append(
                {
                    "nct_id": nct_id,
                    "eligibility_criteria": trial["eligibility_criteria"],
                }
            )

    curated_memberships = [
        {"nct_id": nct_id, "condition_category": condition_category}
        for nct_id, condition_category in sorted(
            curated_pairs,
            key=lambda pair: (CONDITION_PRIORITY.index(pair[1]), pair[0])
            if pair[1] in CONDITION_PRIORITY
            else (999, pair[0]),
        )
    ]
    return curated_trials, curated_memberships, eligibility_rows, audit_rows


def build_outputs(
    page_size: int,
    max_pages: int,
    recruiting_only: bool,
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    ensure_directories()
    overrides = load_review_overrides()
    fetched_at = utc_now_iso()
    raw_hits: list[dict] = []
    raw_trials_index: dict[str, dict] = {}
    parsed_trials_by_nct: dict[str, dict] = {}

    with requests.Session() as session:
        for spec in CONDITION_SPECS:
            condition_category = spec["condition_category"]
            condition_query = spec["condition_query"]
            print(f"Fetching: {condition_category} ({condition_query})...")
            studies = fetch_condition(
                session,
                condition_query,
                PHASES,
                page_size=page_size,
                max_pages=max_pages,
                recruiting_only=recruiting_only,
            )
            print(f"  -> {len(studies)} raw hits")

            for study in studies:
                parsed = parse_study(study, fetched_at)
                nct_id = parsed["nct_id"]
                if not nct_id:
                    continue

                parsed_trials_by_nct.setdefault(nct_id, parsed)
                raw_trial = raw_trials_index.setdefault(
                    nct_id,
                    {
                        "nct_id": nct_id,
                        "condition_queries": [],
                        "fetched_at": fetched_at,
                        "study": study,
                    },
                )
                raw_trial["condition_queries"] = unique_list(
                    list(raw_trial["condition_queries"]) + [condition_category]
                )
                raw_hits.append(
                    {
                        "nct_id": nct_id,
                        "condition_category": condition_category,
                        "condition_query": condition_query,
                        "title": parsed["title"],
                        "official_title": parsed["official_title"],
                        "conditions": parsed["conditions"],
                        "status": parsed["status"],
                        "phase": parsed["phase"],
                        "source_url": parsed["source_url"],
                        "fetched_at": fetched_at,
                    }
                )

            time.sleep(0.4)

    raw_trials = sorted(raw_trials_index.values(), key=lambda row: row["nct_id"])
    curated_trials, curated_memberships, eligibility_rows, audit_rows = build_curation_outputs(
        parsed_trials_by_nct,
        raw_hits,
        overrides,
    )

    known_noisy_pairs = {
        (row["nct_id"], row["condition_category"]) for row in curated_memberships
    }
    leaked_noisy = [nct for nct in KNOWN_NOISY_NCTS if any(pair[0] == nct for pair in known_noisy_pairs)]
    if leaked_noisy:
        raise ValueError(f"Known noisy NCTs leaked into curated memberships: {', '.join(sorted(leaked_noisy))}")

    return raw_trials, raw_hits, curated_trials, curated_memberships, eligibility_rows, audit_rows


def generate(
    page_size: int = 100,
    max_pages: int = 10,
    recruiting_only: bool = False,
) -> dict:
    (
        raw_trials,
        raw_hits,
        curated_trials,
        curated_memberships,
        eligibility_rows,
        audit_rows,
    ) = build_outputs(page_size, max_pages, recruiting_only)

    write_json(RAW / "trials_raw.json", raw_trials)
    write_json(RAW / "condition_hits.json", raw_hits)
    write_json(DATA / "trials.json", curated_trials)
    write_json(DATA / "condition_membership.json", curated_memberships)
    write_json(DATA / "eligibility_text.json", eligibility_rows)

    return {
        "raw_trials": len(raw_trials),
        "raw_hits": len(raw_hits),
        "curated_trials": len(curated_trials),
        "curated_memberships": len(curated_memberships),
        "eligibility_rows": len(eligibility_rows),
        "audit_rows": len(audit_rows),
    }


def diff_trials(new_trials: list[dict], old_path=None) -> dict:
    """Compare newly fetched trials against existing data/trials.json.

    Returns a summary of added, removed, and changed trials.
    """
    import json as json_mod

    old_path = old_path or (DATA / "trials.json")
    if not old_path.exists():
        return {
            "added": [t["nct_id"] for t in new_trials],
            "removed": [],
            "status_changed": [],
            "enrollment_changed": [],
            "old_count": 0,
            "new_count": len(new_trials),
        }

    old_trials = json_mod.loads(old_path.read_text(encoding="utf-8"))
    old_by_nct = {t["nct_id"]: t for t in old_trials}
    new_by_nct = {t["nct_id"]: t for t in new_trials}

    added = sorted(set(new_by_nct) - set(old_by_nct))
    removed = sorted(set(old_by_nct) - set(new_by_nct))

    status_changed = []
    enrollment_changed = []
    for nct_id in sorted(set(old_by_nct) & set(new_by_nct)):
        old = old_by_nct[nct_id]
        new = new_by_nct[nct_id]
        if old.get("status") != new.get("status"):
            status_changed.append({
                "nct_id": nct_id,
                "old_status": old.get("status"),
                "new_status": new.get("status"),
            })
        old_enrollment = old.get("enrollment") or 0
        new_enrollment = new.get("enrollment") or 0
        if old_enrollment != new_enrollment:
            enrollment_changed.append({
                "nct_id": nct_id,
                "old_enrollment": old_enrollment,
                "new_enrollment": new_enrollment,
            })

    return {
        "added": added,
        "removed": removed,
        "status_changed": status_changed,
        "enrollment_changed": enrollment_changed,
        "old_count": len(old_trials),
        "new_count": len(new_trials),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and curate ophthalmic trials")
    parser.add_argument("--recruiting-only", action="store_true", help="Fetch only open recruiting statuses")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Fetch new data and compare against existing trials.json without overwriting",
    )
    args = parser.parse_args()

    try:
        if args.diff:
            (
                _raw_trials,
                _raw_hits,
                curated_trials,
                _curated_memberships,
                _eligibility_rows,
                _audit_rows,
            ) = build_outputs(args.page_size, args.max_pages, args.recruiting_only)
            diff = diff_trials(curated_trials)
            print("\n" + "=" * 60)
            print("DIFF vs existing data/trials.json")
            print("=" * 60)
            print(f"Previous: {diff['old_count']} trials")
            print(f"Current:  {diff['new_count']} trials")
            print(f"Added:    {len(diff['added'])}")
            for nct_id in diff["added"][:20]:
                print(f"  + {nct_id}")
            print(f"Removed:  {len(diff['removed'])}")
            for nct_id in diff["removed"][:20]:
                print(f"  - {nct_id}")
            print(f"Status changed: {len(diff['status_changed'])}")
            for item in diff["status_changed"][:20]:
                print(f"  ~ {item['nct_id']}: {item['old_status']} -> {item['new_status']}")
            print(f"Enrollment changed: {len(diff['enrollment_changed'])}")
            for item in diff["enrollment_changed"][:10]:
                print(f"  ~ {item['nct_id']}: {item['old_enrollment']} -> {item['new_enrollment']}")
        else:
            summary = generate(
                page_size=args.page_size,
                max_pages=args.max_pages,
                recruiting_only=args.recruiting_only,
            )
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            for key, value in summary.items():
                print(f"{key:20s} {value:>6d}")
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
