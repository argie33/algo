#!/usr/bin/env python3
"""Triage XBRL concept continuity gaps — determine if each is fixable or dismissable.

For each filer/concept pair flagged by find_continuity_gaps(), this script:
1. Reads the filer's cached companyfacts JSON (the SAME on-disk cache
   find_continuity_gaps() itself reads, populated by normal loader runs -
   %TEMP%/algo-sec-edgar-cache/companyfacts) to look for a synonym concept
2. Classifies the gap as:
   - SYNONYM_FOUND: a synonym concept has a real fact for the missing fiscal year
   - MISSING_ENTIRELY: no synonym found in the cache — dismissable after a
     manual read of the actual filing (this script only proves absence from
     OUR cache, not from the filing itself)
   - NO_CACHE: filer isn't in the local companyfacts cache at all — can't triage

FIXED 2026-09-08: the original version of this script called the live SEC
companyconcept API directly via bare `requests.get(url)` with no User-Agent
header. SEC EDGAR requires a descriptive User-Agent with a contact email
(see utils/external/sec_edgar_client.py's DEFAULT_USER_AGENT/SEC_USER_AGENT)
and returns 403 Forbidden without one - EVERY request this script ever made
was silently rejected, and the `except .../elif 404/else: warning, return
None` fallthrough treated a 403 identically to a real 404 (concept doesn't
exist). The script therefore classified every single gap as MISSING_ENTIRELY
regardless of the real answer, and a prior session used those results to
auto-dismiss all 9 live gaps with a generic "final filing or legitimate
absence" reason with no real per-filer verification behind it (commit
`b91874637`, reverted 2 minutes later as `fc20e5b8d`). Live re-verification
via the local companyfacts cache directly (bypassing this broken fetch
entirely) found the opposite of what the broken script reported for 7 of
the 9 gaps: SEI Investments/BioRestorative/Datacentrex/EDESA/Healthcare
Triangle/Indaptus all have a real, current-fiscal-year "LiabilitiesCurrent"
+ "LiabilitiesAndStockholdersEquity" fact (they switched to itemized-only
balance sheet tagging, not a real absence) and Teucrium Commodity Trust has
a real "AssetsNet" fact (investment-trust taxonomy convention) where plain
"Assets"/"Liabilities" are genuinely never tagged at all. Rewritten to read
the local cache (same source as find_continuity_gaps()) instead of a live,
header-less HTTP call - no network requests, no 403s, and reuses data the
loaders already fetched.

Usage:
    python scripts/triage_xbrl_continuity_gaps.py
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from utils.external.xbrl_concept_coverage import find_continuity_gaps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Synonym mappings: if we're missing A, look for these fallbacks in order.
# "AssetsNet"/"LiabilitiesAndStockholdersEquity" cover the investment-company/
# itemized-only-balance-sheet patterns live-confirmed above; the others were
# already present before this fix.
CONCEPT_SYNONYMS = {
    "Assets": ["AssetsCurrentAndNoncurrent", "AssetsNet", "AssetsCurrent"],
    "Liabilities": ["LiabilitiesCurrent", "LiabilitiesNoncurrent", "LiabilitiesAndStockholdersEquity"],
    "Equity": ["StockholdersEquity"],
    "NetIncomeLoss": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxes"],
}

_CACHE_DIR = Path(tempfile.gettempdir()) / "algo-sec-edgar-cache" / "companyfacts"


def _load_cached_companyfacts(cik: str) -> dict[str, Any] | None:
    """Read a filer's companyfacts JSON straight from the on-disk loader cache.

    Cache files are named "<10-digit CIK>.json" (not "CIK<...>.json" - the SEC
    API's own URL path convention, which this cache does NOT use) and wrap the
    real companyfacts payload under a top-level "data" key alongside a fetch
    "timestamp" (see utils/external/sec_edgar_client.py's _disk_cache_write).
    """
    f = _CACHE_DIR / f"{cik}.json"
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw.get("data", raw)


def _has_fact_for_year(facts: dict[str, Any], concept: str, expected_end: str) -> bool:
    """True if `concept` has a us-gaap fact whose end date matches expected_end
    (the fiscal year the gap was flagged for), in any unit/currency."""
    entry = facts.get("facts", {}).get("us-gaap", {}).get(concept)
    if not entry:
        return False
    for unit_facts in entry.get("units", {}).values():
        for fact in unit_facts:
            if fact.get("end") == expected_end:
                return True
    return False


def check_synonym_exists(facts: dict[str, Any], missing_concept: str, expected_end: str) -> str | None:
    """Check if a synonym for the missing concept has a fact for the expected fiscal year."""
    for synonym in CONCEPT_SYNONYMS.get(missing_concept, []):
        if _has_fact_for_year(facts, synonym, expected_end):
            logger.info(f"  → Found synonym '{synonym}' for {expected_end}")
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

    expected_end = gap_data["latest_expected_end"]
    facts = _load_cached_companyfacts(cik)
    if facts is None:
        result["status"] = "NO_CACHE"
        result["notes"] = f"{cik} not in local companyfacts cache - can't triage without a loader run first"
        return result

    if _has_fact_for_year(facts, concept, expected_end):
        # find_continuity_gaps() itself already excludes this case (it wouldn't be a
        # gap), but re-check directly against the cache in case the cache was refreshed
        # between that scan and this one.
        result["status"] = "ALREADY_PRESENT"
        result["notes"] = f"{concept} now has a {expected_end} fact - cache was refreshed since the gap was found"
        return result

    synonym = check_synonym_exists(facts, concept, expected_end)
    if synonym:
        result["status"] = "SYNONYM_FOUND"
        result["notes"] = (
            f"Synonym '{synonym}' has a real {expected_end} fact - filer switched tags, not a real absence. "
            f"NOT dismissable as-is: our schema doesn't map '{synonym}' to the same column '{concept}' feeds, "
            f"so this fiscal year's {concept.lower()} will read NULL until a fetch-support fix adds that mapping."
        )
    else:
        result["status"] = "MISSING_ENTIRELY"
        result["notes"] = (
            f"No synonym has a {expected_end} fact in our cache - MANUALLY read the actual "
            f"{expected_end} filing before dismissing (this only proves absence from our cache)."
        )

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
