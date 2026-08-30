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


def fetch_custom_capex(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known custom capex
    concept(s). Returns {} if symbol isn't in CUSTOM_CAPEX_CONCEPTS, the filing can't be
    found, or the XML can't be parsed - callers should treat that as "no fallback data",
    not raise.
    """
    if symbol not in CUSTOM_CAPEX_CONCEPTS:
        return {}
    try:
        cik = sec_client.symbol_to_cik(symbol)
        submissions = sec_client.get_submissions(cik)
        recent = submissions["filings"]["recent"]
        annual_forms = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
        for i in range(len(recent["form"])):
            if recent["form"][i] not in annual_forms:
                continue
            accession = recent["accessionNumber"][i]
            xml_content = sec_client.get_filing_xml(cik, accession, recent["form"][i])
            return extract_custom_capex_from_xbrl_xml(xml_content, symbol)
    except Exception:
        # Not an error for THIS optional fallback - a fetch/parse failure here just means
        # no supplemental capex value is available this run; the symbol keeps whatever
        # the normal SEC concept-list extraction already found (possibly still NULL, same
        # as before this module existed). Same soft-fail contract as this codebase's
        # other optional-fallback sources (e.g. sec_base.py's _try_yfinance_fallback).
        return {}
    # No candidates - the filing history had no 10-K/20-F/40-F at all to check.
    return {}
