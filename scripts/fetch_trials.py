"""Fetch Phase II/III ophthalmic trials from ClinicalTrials.gov API.

Populates:
  data/trials.json              -- one row per unique NCT ID
  data/condition_membership.json -- many-to-many trial-condition pairs

Usage:
  uv run python scripts/fetch_trials.py
  uv run python scripts/fetch_trials.py --recruiting-only
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: uv sync", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

API_BASE = "https://clinicaltrials.gov/api/v2/studies"

CONDITIONS = [
    ("dme", "diabetic macular edema"),
    ("dr", "diabetic retinopathy"),
    ("wet_amd", "neovascular age-related macular degeneration"),
    ("ga", "geographic atrophy"),
    ("glaucoma", "glaucoma"),
    ("rvo", "retinal vein occlusion"),
    ("pathologic_myopia", "pathological myopia"),
    ("macular_hole", "macular hole"),
    ("uveitic_me", "uveitic macular edema"),
    ("stargardt", "Stargardt disease"),
    ("vma", "vitreomacular adhesion"),
]

PHASES = ["PHASE2", "PHASE3"]


def fetch_condition(condition_query: str, phases: list[str],
                    page_size: int = 100, max_pages: int = 10,
                    recruiting_only: bool = False) -> list[dict]:
    """Fetch trials for a single condition from ClinicalTrials.gov API v2."""
    all_studies = []
    page_token = None

    statuses = ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]
    if not recruiting_only:
        statuses.extend([
            "ACTIVE_NOT_RECRUITING", "COMPLETED", "SUSPENDED",
            "TERMINATED", "WITHDRAWN",
        ])

    # Build phase filter as part of the condition query
    # ClinicalTrials.gov API v2 does not have a filter.phase param
    phase_terms = " OR ".join(phases)

    for page in range(max_pages):
        params = {
            "query.cond": condition_query,
            "filter.overallStatus": ",".join(statuses),
            "query.term": f"AREA[Phase]({phase_terms})",
            "pageSize": page_size,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        studies = data.get("studies", [])
        all_studies.extend(studies)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

        time.sleep(0.3)  # rate limit courtesy

    return all_studies


def parse_study(study: dict) -> dict:
    """Extract structured fields from a ClinicalTrials.gov API v2 study."""
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
    design_mod = proto.get("designModule", {})
    elig_mod = proto.get("eligibilityModule", {})
    conditions_mod = proto.get("conditionsModule", {})

    nct_id = ident.get("nctId", "")
    phases = design_mod.get("phases", [])
    phase_str = " / ".join(phases) if phases else "N/A"

    lead_sponsor = sponsor_mod.get("leadSponsor", {})

    return {
        "nct_id": nct_id,
        "title": ident.get("briefTitle", ""),
        "official_title": ident.get("officialTitle", ""),
        "status": status_mod.get("overallStatus", ""),
        "phase": phase_str,
        "sponsor": lead_sponsor.get("name", ""),
        "enrollment": design_mod.get("enrollmentInfo", {}).get("count"),
        "start_date": status_mod.get("startDateStruct", {}).get("date", ""),
        "completion_date": status_mod.get("completionDateStruct", {}).get("date", ""),
        "eligibility_criteria": elig_mod.get("eligibilityCriteria", ""),
        "conditions": conditions_mod.get("conditions", []),
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "last_verified_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch ophthalmic trials from ClinicalTrials.gov")
    parser.add_argument("--recruiting-only", action="store_true",
                        help="Only fetch currently recruiting trials")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)

    trials_by_nct = {}  # nct_id -> parsed trial
    condition_memberships = []  # list of {nct_id, condition_category}

    for condition_key, condition_query in CONDITIONS:
        print(f"Fetching: {condition_key} ({condition_query})...")
        studies = fetch_condition(
            condition_query, PHASES,
            page_size=args.page_size,
            max_pages=args.max_pages,
            recruiting_only=args.recruiting_only,
        )
        print(f"  -> {len(studies)} results")

        for study in studies:
            parsed = parse_study(study)
            nct_id = parsed["nct_id"]
            if not nct_id:
                continue

            # Store trial (dedup by nct_id, keep first seen)
            if nct_id not in trials_by_nct:
                trials_by_nct[nct_id] = parsed

            # Record condition membership (allows duplicates across conditions)
            condition_memberships.append({
                "nct_id": nct_id,
                "condition_category": condition_key,
            })

        time.sleep(0.5)

    # Deduplicate condition memberships
    seen_pairs = set()
    unique_memberships = []
    for m in condition_memberships:
        pair = (m["nct_id"], m["condition_category"])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            unique_memberships.append(m)

    # Write trials.json (one row per unique NCT ID, without eligibility_criteria blob)
    trials_list = []
    for t in sorted(trials_by_nct.values(), key=lambda x: x["nct_id"]):
        trials_list.append({
            "nct_id": t["nct_id"],
            "title": t["title"],
            "official_title": t["official_title"],
            "status": t["status"],
            "phase": t["phase"],
            "sponsor": t["sponsor"],
            "enrollment": t["enrollment"],
            "start_date": t["start_date"],
            "completion_date": t["completion_date"],
            "conditions": t["conditions"],
            "source_url": t["source_url"],
            "last_verified_at": t["last_verified_at"],
        })

    trials_path = DATA / "trials.json"
    trials_path.write_text(json.dumps(trials_list, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(trials_list)} unique trials -> {trials_path}")

    # Write condition_membership.json
    membership_path = DATA / "condition_membership.json"
    membership_path.write_text(
        json.dumps(unique_memberships, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(unique_memberships)} condition memberships -> {membership_path}")

    # Write eligibility text separately (large, useful for criteria mapping)
    elig_list = []
    for t in sorted(trials_by_nct.values(), key=lambda x: x["nct_id"]):
        if t.get("eligibility_criteria"):
            elig_list.append({
                "nct_id": t["nct_id"],
                "eligibility_criteria": t["eligibility_criteria"],
            })
    elig_path = DATA / "eligibility_text.json"
    elig_path.write_text(json.dumps(elig_list, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(elig_list)} eligibility texts -> {elig_path}")

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"Unique trials:          {len(trials_list)}")
    print(f"Condition memberships:  {len(unique_memberships)}")

    # Per-condition counts
    from collections import Counter
    cond_counts = Counter(m["condition_category"] for m in unique_memberships)
    for cond_key, _ in CONDITIONS:
        count = cond_counts.get(cond_key, 0)
        print(f"  {cond_key:25s} {count:>4d} trials")

    # Status breakdown
    status_counts = Counter(t["status"] for t in trials_list)
    print(f"\nBy status:")
    for status, count in status_counts.most_common():
        print(f"  {status:30s} {count:>4d}")


if __name__ == "__main__":
    main()
