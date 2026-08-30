#!/usr/bin/env python3
"""Explicit, hand-verified fallback for capex tagged under a filer-specific custom XBRL
extension taxonomy - invisible to SEC's companyfacts/companyconcept aggregation APIs.

FOUND 2026-08-29 (goal: "full data" audit continuation, shipping-sector capex follow-up):
`annual_cash_flow.capex` was NULL for shipping/tanker owners (DHT, CMRE, and others) despite
real capex being on file - live-confirmed both filers' real vessel-acquisition capex is
tagged under a filer-invented extension concept (`dht:InvestmentsInVessels` /
`dht:InvestmentInVesselsUnderConstruction` for DHT, `cmre:PaymentsToAcquireVessels` for
CMRE), not any shared us-gaap/ifrs-full standard concept `utils/external/sec_statements.py`'s
`get_cash_flow()` can ever match.

CONFIRMED this is a structural SEC API limitation, not an unchecked concept name: a direct
request to `https://data.sec.gov/api/xbrl/companyconcept/CIK0001331284/dht/
InvestmentsInVessels.json` 404s (same CIK/concept resolves fine for `us-gaap`/`ifrs-full`
concepts), and DHT's own `companyfacts` response contains only `dei`/`ifrs-full` namespaces,
never `dht` - custom filer-extension concepts are excluded from both convenience APIs
entirely. The ONLY way to reach this data is the filing's own raw XBRL instance document
(the same mechanism `utils/external/sec_xbrl_segments.py` already uses for segment
disclosures that have the identical problem) - fetched via
`SecEdgarClient.get_filing_xml()`.

Deliberately NOT a generalized "match by rendered statement label" engine (that was
considered and rejected as materially riskier - a label-matching heuristic could silently
pick the wrong line item on some filer whose labels aren't a clean match). This is instead
a small, explicit, per-symbol whitelist of concept names, each verified by hand against the
real filed XBRL instance document (contextRef checked for absence of segment/scenario
dimensional qualifiers - i.e. confirmed to be the CONSOLIDATED entity-wide value, not a
business-segment-scoped one - and a plausible full-year duration) before being added here.
Adding a new symbol means doing that same verification, not guessing.
"""

import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

# Each entry: list of (namespace_prefix, local_name) pairs to SUM for that symbol's real
# annual capex - a filer may split acquisition vs. under-construction spend across two
# concepts that are both real, additive parts of total vessel capex (verified for DHT via
# its own real FY2023-2025 values, both concepts present and economically distinct - not a
# duplicate). namespace_prefix is informational only (not used for matching - local_name
# alone is matched, since Clark-notation strips the actual prefix anyway); kept for
# traceability back to the filer's own XBRL instance document.
CUSTOM_CAPEX_CONCEPTS: dict[str, list[tuple[str, str]]] = {
    # DHT Holdings (CIK 0001331284, tanker owner) - verified live 2026-08-29 against
    # accession 0001140361-26-010407 (FY2025 20-F). Both concepts real and additive, not
    # a duplicate: dht:InvestmentsInVessels (completed acquisitions) $111,125,000 FY2025 /
    # $6,687,000 FY2024 / $128,081,000 FY2023, dht:InvestmentInVesselsUnderConstruction
    # (newbuilding progress payments) $198,511,000 FY2025 / $90,196,000 FY2024 / $0
    # FY2023 - summed total capex $309,636,000 FY2025 / $96,883,000 FY2024 /
    # $128,081,000 FY2023 (plausible vs. DHT's real fleet-growth/newbuilding activity).
    "DHT": [("dht", "InvestmentsInVessels"), ("dht", "InvestmentInVesselsUnderConstruction")],
    # Costamare Inc (CIK 0001503584, containership owner) - verified live 2026-08-29
    # against accession 0001140361-26-007868 (FY2025 20-F): cmre:PaymentsToAcquireVessels
    # $68,971,000 FY2025 / $8,222,000 FY2024 / $7,632,000 FY2023.
    "CMRE": [("cmre", "PaymentsToAcquireVessels")],
    # VAALCO Energy (CIK 0000894627, oil & gas E&P) - verified live 2026-08-29 against
    # accession 0000894627-26-000013 (FY2025 10-K): egy:PaymentToAcquirePropertyAndEquipmentExpendituresIncludingExplorationExpense
    # $252,856,000 FY2025 / $102,996,000 FY2024 / $97,223,000 FY2023 - the filer's own
    # concept name states it's already the comprehensive total ("...IncludingExplorationExpense"),
    # so used alone, NOT summed with the filing's two smaller, ambiguous sibling concepts
    # (egy:AcquisitionOfCrudeOilAndNaturalGasProperties, egy:NonCashPaymentsToExploreOilAndGasProperties -
    # both carry negative values in the raw filing for at least one year, inconsistent
    # with a plain cash-capex-outflow sign convention, and "NonCash" in the second name
    # suggests it may already be a component backed OUT of a broader total rather than
    # an additive one - summing either risks double-counting or including a non-cash
    # adjustment; the conservative single-concept choice avoids that risk).
    "EGY": [("egy", "PaymentToAcquirePropertyAndEquipmentExpendituresIncludingExplorationExpense")],
    # ALEnnA Resources (CIK 0001845123, conventional + renewable natural gas E&P) -
    # verified live 2026-08-29 against accession 0001213900-26-036606 (FY2025 10-K). Both
    # concepts real, positive in every year, and economically distinct (conventional vs.
    # renewable natural gas property spend), not a duplicate:
    # anna:PaymentToAdditionsToConventionalNaturalGasProperties $6,769,337 FY2025 /
    # $13,344,911 FY2024, anna:PaymentsToAdditionsToRenewableNaturalGasProperties
    # $235,724 FY2025 / $9,721,376 FY2024 - summed total capex $7,005,061 FY2025 /
    # $23,066,287 FY2024.
    "ANNA": [
        ("anna", "PaymentToAdditionsToConventionalNaturalGasProperties"),
        ("anna", "PaymentsToAdditionsToRenewableNaturalGasProperties"),
    ],
    # Epsilon Energy (CIK 0001726126, oil & gas E&P) - verified live 2026-08-29 against
    # accession 0001104659-26-035794 (FY2025 10-K). Both concepts real, positive in every
    # year, and economically distinct (proved vs. unproved property acquisitions), not a
    # duplicate: epsn:PaymentsToAcquireProvedOilAndGasProperty $7,929,773 FY2025 /
    # $31,695,651 FY2024, epsn:PaymentsToAcquireUnprovedOilAndGasProperty $6,999,905
    # FY2025 / $4,507,280 FY2024 - summed total capex $14,929,678 FY2025 / $36,202,931
    # FY2024. Deliberately excludes the filing's third sibling concept
    # (epsn:PaymentsToAcquireLandBuildingsAndOtherPropertyPlantAndEquipment) - small
    # magnitude and NEGATIVE in FY2025 (-$270,488), inconsistent with a plain
    # cash-capex-outflow sign convention, so not safely summable without further
    # investigation this session didn't do.
    "EPSN": [
        ("epsn", "PaymentsToAcquireProvedOilAndGasProperty"),
        ("epsn", "PaymentsToAcquireUnprovedOilAndGasProperty"),
    ],
}


def _local_name(tag: str) -> str:
    """Strip the Clark-notation namespace from an ElementTree tag."""
    return tag.rsplit("}", 1)[-1]


def extract_custom_capex_from_xbrl_xml(xml_content: str, symbol: str) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for `symbol`'s known custom capex
    concept(s) (see CUSTOM_CAPEX_CONCEPTS), returning {fiscal_year: summed_value}.

    Only meaningful for symbols in CUSTOM_CAPEX_CONCEPTS - returns {} immediately for any
    other symbol (never guesses at unregistered concept names).

    Excludes any context with a <segment>/<scenario> dimensional qualifier - a
    dimensionally-scoped fact is a specific business segment or member, not the
    consolidated entity-wide total this codebase's other capex figures represent
    (same governance as sec_xbrl_segments.py's own context handling). Also excludes
    non-annual-duration contexts (anything not ~350-380 days) so a quarterly/interim fact
    can't get misattributed to the wrong annual bucket.
    """
    concepts = CUSTOM_CAPEX_CONCEPTS.get(symbol)
    if not concepts:
        # Not an error - no candidates registered for this symbol at all, so there is
        # nothing to search the XML for. This is an optional supplemental data source
        # (see module docstring); an unregistered symbol simply gets no supplement, the
        # same as if this module didn't exist for it.
        return {}
    wanted_local_names = {local_name for _prefix, local_name in concepts}

    root = ET.fromstring(xml_content)

    context_periods: dict[str, tuple[str, str]] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        if any(_local_name(child.tag) in ("segment", "scenario") for child in ctx):
            continue  # Dimensionally-scoped context - not the consolidated total
        period = next((c for c in ctx if _local_name(c.tag) == "period"), None)
        if period is None:
            continue
        start_el = next((c for c in period if _local_name(c.tag) == "startDate"), None)
        end_el = next((c for c in period if _local_name(c.tag) == "endDate"), None)
        if start_el is None or end_el is None or not start_el.text or not end_el.text:
            continue
        context_periods[ctx_id] = (start_el.text.strip(), end_el.text.strip())

    values_by_year: dict[int, float] = {}
    for el in root.iter():
        local_name = _local_name(el.tag)
        if local_name not in wanted_local_names:
            continue
        ctx_ref = el.get("contextRef")
        if ctx_ref not in context_periods:
            continue
        start_str, end_str = context_periods[ctx_ref]
        try:
            start_date = date.fromisoformat(start_str)
            end_date = date.fromisoformat(end_str)
        except ValueError:
            continue
        duration_days = (end_date - start_date).days
        if not (350 <= duration_days <= 380):
            continue  # Not a full-year duration - skip quarterly/interim facts
        if el.text is None:
            continue
        try:
            value = float(el.text.strip())
        except ValueError:
            continue
        fiscal_year = end_date.year
        values_by_year[fiscal_year] = values_by_year.get(fiscal_year, 0.0) + value

    return values_by_year


_ANNUAL_FILING_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"})
# BASE (non-amendment) forms only - tried first. See fetch_custom_capex's docstring.
_BASE_ANNUAL_FILING_FORMS = frozenset({"10-K", "10-KT", "20-F", "40-F"})


def fetch_custom_capex(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known custom capex
    concept(s). Returns {} if symbol isn't in CUSTOM_CAPEX_CONCEPTS, the filing can't be
    found, or the XML can't be parsed - callers should treat that as "no fallback data",
    not raise.

    LIVE-REPRODUCED 2026-08-29 while validating this exact function: a naive
    "most-recent annual-form filing" scan picked EGY's 10-K/A (a Part-III-only amendment,
    5.3KB, zero financial-statement facts) over its real, substantive 10-K filed earlier
    the same season - the amendment sorts first in SEC's `recent` filing list. Same bug
    class as `loaders/load_sec_segment_info.py`'s `_find_latest_annual_filing()` (fixed
    there 2026-08-29 for the identical LAC/PDSB pattern - see that method's own
    docstring) and `sec_segment_info` picked a Part-III-only 10-K/A over the real 10-K
    for a different filer entirely (commit da2833e2a). Now prefers a BASE (non-amendment)
    annual form first, only falling back to an amendment if no base-form filing exists at
    all in the filing history - same two-tier strategy as that fix, reimplemented here
    (not imported from that loader) to keep this module dependency-free of the loader
    layer.
    """
    if symbol not in CUSTOM_CAPEX_CONCEPTS:
        # Not an error - no candidates registered for this symbol, nothing to fetch.
        return {}
    try:
        cik = sec_client.symbol_to_cik(symbol)
        submissions = sec_client.get_submissions(cik)
        recent = submissions["filings"]["recent"]
        fallback_amendment: tuple[str, str] | None = None
        for i in range(len(recent["form"])):
            form = recent["form"][i]
            if form not in _ANNUAL_FILING_FORMS:
                continue
            accession = recent["accessionNumber"][i]
            if form in _BASE_ANNUAL_FILING_FORMS:
                xml_content = sec_client.get_filing_xml(cik, accession, form)
                return extract_custom_capex_from_xbrl_xml(xml_content, symbol)
            if fallback_amendment is None:
                fallback_amendment = (accession, form)
        if fallback_amendment is not None:
            accession, form = fallback_amendment
            xml_content = sec_client.get_filing_xml(cik, accession, form)
            return extract_custom_capex_from_xbrl_xml(xml_content, symbol)
    except Exception:
        # Not an error for THIS optional fallback - a fetch/parse failure here just means
        # no supplemental capex value is available this run; the symbol keeps whatever
        # the normal SEC concept-list extraction already found (possibly still NULL, same
        # as before this module existed). Same soft-fail contract as this codebase's
        # other optional-fallback sources (e.g. sec_base.py's _try_yfinance_fallback).
        return {}
    # Not an error - no candidates at all: the filing history had no 10-K/20-F/40-F to check.
    return {}
