#!/usr/bin/env python3
"""Triage XBRL concept continuity gaps — determine if each is fixable or dismissable.

For each filer/concept pair flagged by find_continuity_gaps(), this script:
1. Fetches the filer's most recent 10-K from SEC EDGAR companyfacts API
2. Checks if the missing concept has a synonym that IS present
3. Classifies the gap as:
   - SYNONYM_FOUND: we fetch a synonym, no action needed
   - MISSING_ENTIRELY: legitimate absence (final filing, bankruptcy, etc.) — dismissable
   - UNCLEAR: requires manual inspection

Usage:
    python scripts/triage_xbrl_continuity_gaps.py
    python scripts/triage_xbrl_continuity_gaps.py --cik 0000350894 --concept "Assets"
"""

import logging

import requests

from utils.external.xbrl_concept_coverage import find_continuity_gaps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Synonym mappings: if we're missing A, look for these fallbacks in order
CONCEPT_SYNONYMS = {
    "Assets": ["AssetsCurrentAndNoncurrent"],
    "Liabilities": ["LiabilitiesCurrent", "LiabilitiesNoncurrent"],
    "Equity": ["StockholdersEquity"],
    "NetIncomeLoss": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxes"],
}

SEC_COMPANYCONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik_padded}/us-gaap-{concept}.json"


def fetch_sec_companyconcept(cik: str, concept: str) -> dict | None:
    """Fetch a filer's specific concept from SEC companyconcept API."""
    try:
        cik_padded = cik.lstrip("0").zfill(10)
        url = SEC_COMPANYCONCEPT_URL.format(cik_padded=cik_padded, concept=concept.lower())
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return None
        else:
            logger.warning(f"SEC API returned {resp.status_code} for {cik}/{concept}")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch {cik}/{concept} from SEC: {e}")
        return None


def check_synonym_exists(cik: str, missing_concept: str) -> str | None:
    """Check if a synonym for the missing concept is present."""
    synonyms = CONCEPT_SYNONYMS.get(missing_concept, [])
    for synonym in synonyms:
        data = fetch_sec_companyconcept(cik, synonym)
        if data:
            logger.info(f"  → Found synonym '{synonym}'")
            return synonym
    return None


def triage_gap(gap_data: dict) -> dict:
    """Triage a single filer/concept gap."""
    cik = gap_data["cik"]
    concept = gap_data["concept"].replace("us-gaap:", "")
    years_present = gap_data["prior_years_present"]
    entity_name = gap_data.get("entity_name", "Unknown")

    result = {
        "cik": cik,
        "entity_name": entity_name,
        "concept": concept,
        "years_present": years_present,
        "status": "UNKNOWN",
        "notes": "",
    }

    logger.info(f"\nTriaging {entity_name} ({cik}) / us-gaap:{concept}")
    logger.info(f"  Was present in: {years_present}")

    # Check if concept data exists in SEC API (should be null if truly absent)
    data = fetch_sec_companyconcept(cik, concept)
    if data:
        # Concept exists in SEC data, but our cache doesn't have it for the latest year
        # This could mean:
        # 1. Stale cache (loader hasn't re-fetched yet)
        # 2. Real filer change
        result["status"] = "POSSIBLY_STALE_CACHE"
        result["notes"] = "Concept exists in SEC API but not in our cached companyfacts"
    else:
        # Concept truly absent in SEC data for this filer
        synonym = check_synonym_exists(cik, concept)
        if synonym:
            result["status"] = "SYNONYM_FOUND"
            result["notes"] = (
                f"Synonym '{synonym}' is available — no action needed (will be picked up on next loader run)"
            )
        else:
            result["status"] = "MISSING_ENTIRELY"
            result["notes"] = "No synonym found — likely legitimate (final filing, bankruptcy, going-private, etc.)"

    return result


def main() -> None:
    """Triage all active continuity gaps."""
    gaps = find_continuity_gaps(min_prior_years=3)
    if not gaps:
        logger.info("No continuity gaps found.")
        return

    logger.info(f"\nTriaging {len(gaps)} continuity gaps...\n")

    results = []
    for gap_data in gaps:
        triage = triage_gap(gap_data)
        results.append(triage)
        logger.info(f"  Result: {triage['status']}")
        if triage["notes"]:
            logger.info(f"  {triage['notes']}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TRIAGE SUMMARY")
    logger.info("=" * 80)

    by_status = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)

    for status in sorted(by_status.keys()):
        count = len(by_status[status])
        logger.info(f"\n{status}: {count}")
        for r in by_status[status]:
            logger.info(f"  {r['cik']} / us-gaap:{r['concept']} — {r['notes']}")

    # Suggest dismissals
    logger.info("\n" + "=" * 80)
    logger.info("MANUAL DISMISSAL INSTRUCTIONS")
    logger.info("=" * 80)

    dismissals = [r for r in results if r["status"] == "MISSING_ENTIRELY"]
    if dismissals:
        logger.info(f"\nFor each of these {len(dismissals)} gap(s), MANUALLY verify via SEC filing, then run:")
        for r in dismissals:
            logger.info(f"\npython scripts/xbrl_concept_continuity_scan.py --dismiss '{r['cik']}:{r['concept']}' \\")
            logger.info("  --reason 'Manually verified: [your reason, e.g., final filing, bankruptcy, etc.]'")
    else:
        logger.info("No gaps require dismissal (all have synonyms or are in stale cache).")


if __name__ == "__main__":
    main()
