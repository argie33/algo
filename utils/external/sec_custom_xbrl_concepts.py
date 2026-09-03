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
    # NextEra Energy Inc (CIK 0000753308, regulated electric utility) - verified live
    # 2026-09-03 (goal session: "missing SEC/XBRL data" sweep, capex_never_tagged_in_
    # recent_filings investigation) against the real filed FY2025 10-K raw XBRL instance
    # document (accession 0000753308-26-000015, nee-20251231_htm.xml), via this module's
    # own _extract_values_for_concepts function, not just the rendered R-file. Three real,
    # additive, dimension-free concepts on the consolidated cash flow statement:
    # nee:CapitalExpendituresOfFPL (FPL segment) $8,719,000,000 FY2025 / $7,992,000,000
    # FY2024 / $9,302,000,000 FY2023, nee:IndependentPowerInvestments (NEER segment)
    # $15,332,000,000 / $16,215,000,000 / $15,565,000,000, nee:OtherCapitalExpenditures
    # (small residual line) $2,000,000 / $123,000,000 / $61,000,000 - summed total capex
    # $24,053,000,000 FY2025 / $24,330,000,000 FY2024 / $24,928,000,000 FY2023 (plausible
    # vs. NextEra's real, publicly reported capital spending scale). Deliberately excludes
    # nee:CapitalExpendituresOfPublicUtility, which the extraction function correctly
    # returns empty for - that concept only appears in a LegalEntityAxis-dimensioned
    # context representing FPL's own standalone co-registrant statement within the same
    # filing (same $8,719M/$7,992M/$9,302M values as CapitalExpendituresOfFPL, a pure
    # duplicate under a different tag, not additional spend). NEE's companyfacts JSON has
    # zero entries under any PP&E-family/standard concept for any of these three - the
    # only path to this data is the raw instance document, same structural limitation as
    # every other symbol in this registry.
    "NEE": [
        ("nee", "CapitalExpendituresOfFPL"),
        ("nee", "IndependentPowerInvestments"),
        ("nee", "OtherCapitalExpenditures"),
    ],
    # Phillips 66 (CIK 0001534701, integrated refiner) - verified live 2026-09-03 (same
    # sweep) against the real filed FY2025 10-K raw XBRL instance document (accession
    # 0001534701-26-000006, psx-20251231_htm.xml) via this module's own
    # _extract_values_for_concepts function. Single concept covers PSX's whole capex line
    # ("Capital expenditures and investments" on the consolidated cash flow statement):
    # psx:CapitalExpendituresAndInvestments $4,466,000,000 FY2025 / $3,718,000,000 FY2024
    # / $4,310,000,000 FY2023 - plausible vs. Phillips 66's real, publicly reported capex
    # scale. PSX's companyfacts JSON has zero entries under any PP&E-family/standard
    # concept for any fiscal year.
    "PSX": [("psx", "CapitalExpendituresAndInvestments")],
    # ConocoPhillips (CIK 0001163165, integrated oil & gas major) - verified live
    # 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
    # no_recent_free_cash_flow_reported investigation, $309B market cap). COP's
    # companyfacts JSON has zero entries under any PP&E-family/standard capex concept
    # since FY2022 (its last "PaymentsToAcquireProductiveAssets" 10-K value was FY2022,
    # $10.159B). Real FY2023-2025 companion figure confirmed against the raw filed
    # FY2025 10-K XBRL instance document (accession 0001163165-26-000009,
    # cop-20251231_htm.xml): single concept covers COP's whole capex line ("Capital
    # expenditures and investments" on the consolidated cash flow statement, immediately
    # below Net Cash Provided by Operating Activities, plain non-dimensioned contexts):
    # cop:PaymentToAcquireProductiveAssetsAndInvestments $12,553,000,000 FY2025 /
    # $12,118,000,000 FY2024 / $11,248,000,000 FY2023 - plausible vs. COP's real,
    # publicly reported ~$11-13B/yr capex budget, growing consistent with no gap/reset
    # between years. Same "filer switched to its own extension concept, standard
    # companyfacts extraction structurally can't see it" pattern as PSX above.
    "COP": [("cop", "PaymentToAcquireProductiveAssetsAndInvestments")],
    # Alibaba Group Holding Ltd (CIK 0001577552, $278B market cap 20-F filer) - verified
    # live 2026-09-03 (same sweep) against the real filed FY2026 (fiscal year ended
    # 2026-03-31) 20-F raw XBRL instance document (accession 0001193125-26-231755,
    # baba-20260331_htm.xml). companyfacts JSON's only PP&E-family concept
    # (PaymentsToAcquireOtherPropertyPlantAndEquipment) stops after FY2020 (last real
    # value $3.483B, fiscal year ended 2020-03-31) - every fiscal year since is a genuine
    # unextracted-data gap, not a structural absence: baba:PaymentsToAcquireLandUseRights
    # PropertyAndEquipment (BABA's own combined "land use rights" - the standard PRC
    # equivalent of purchased land - plus PP&E concept) continues with real, plain
    # non-dimensioned contexts every fiscal year: CNY 32,087,000,000 FY2024 (fiscal year
    # ended 2024-03-31) / CNY 85,972,000,000 FY2025 / CNY 126,063,000,000 (USD
    # 18,275,000,000) FY2026 - a real, sharply accelerating capex ramp plausible against
    # Alibaba's own publicly reported AI/cloud-infrastructure buildout, not a placeholder.
    "BABA": [("baba", "PaymentsToAcquireLandUseRightsPropertyAndEquipment")],
    # Cigna Group (CIK 0001739940, $114.8B market cap health insurer) - verified live
    # 2026-09-03 (same sweep) against the real filed FY2025 10-K raw XBRL instance
    # document (accession 0001739940-26-000006, ci-20251231_htm.xml). companyfacts JSON
    # has zero us-gaap PP&E-family concept with any value since FY2022 - real capex
    # continues under ci:PaymentsForProceedsFromPropertyPlantAndEquipment, plain
    # non-dimensioned annual contexts, immediately adjacent to
    # PaymentsToAcquireOtherInvestments/PaymentsToAcquireBusinessesNetOfCashAcquired on
    # the investing-activities cash flow line: $1,212,000,000 FY2025 / $1,406,000,000
    # FY2024 / $1,573,000,000 FY2023 - plausible, full-sized figures for Cigna's real
    # capex scale (not a small residual the way PaymentsForProceedsFromProductiveAssets
    # turned out to be for COP above - no separate, larger PP&E-purchase concept exists
    # anywhere in Cigna's companyfacts to be the "real" primary line instead). Despite the
    # "...ProceedsFrom..." naming (usually a net-of-disposals pattern), this reads as
    # Cigna's own single combined cash-flow-statement PP&E line, the only one it reports.
    "CI": [("ci", "PaymentsForProceedsFromPropertyPlantAndEquipment")],
    # Diageo plc (CIK 0000835403, $50.7B market cap 20-F filer, fiscal year ends June 30) -
    # verified live 2026-09-03 (same sweep) against the real filed FY2026 20-F raw XBRL
    # instance document (deo-20260630_htm.xml). Real capex tagged under
    # deo:PurchaseOfPropertyPlantAndEquipmentAndComputerSoftware, plain non-dimensioned
    # annual contexts: GBP 1,197,000,000 FY2026 (period 2025-07-01 to 2026-06-30) /
    # 1,612,000,000 FY2025 / 1,510,000,000 FY2024 - plausible vs. Diageo's real,
    # publicly reported capex scale.
    "DEO": [("deo", "PurchaseOfPropertyPlantAndEquipmentAndComputerSoftware")],
    # Infosys Ltd (CIK 0001067491, $48.5B market cap 20-F filer, fiscal year ends March
    # 31) - verified live 2026-09-03 (same sweep) against the real filed FY2026 20-F raw
    # XBRL instance document (accession 0001193125-26-270520, infy-20260331_htm.xml).
    # Real capex tagged under infy:PurchaseOfPropertyPlantAndEquipmentAndIntangibles
    # ClassifiedAsInvestingActivities (USD-denominated fact), plain non-dimensioned
    # annual contexts: $306,000,000 FY2026 (period 2025-04-01 to 2026-03-31) /
    # $263,000,000 FY2025 / $266,000,000 FY2024 - plausible vs. Infosys's real,
    # publicly reported capex scale.
    "INFY": [("infy", "PurchaseOfPropertyPlantAndEquipmentAndIntangiblesClassifiedAsInvestingActivities")],
    # Equitable Holdings Inc (CIK 0001333986, $15.4B market cap life insurer) - verified
    # live 2026-09-03 (same sweep) against the real filed FY2025 10-K raw XBRL instance
    # document (accession 0001333986-26-000012, eqh-20251231_htm.xml). Real capex tagged
    # under eqh:InvestmentInCapitalizedSoftwareLeaseholdImprovementsAndEDPEquipment,
    # sitting directly in the investing-activities section of the cash flow statement
    # (between PaymentsForProceedsFromDerivativeInstrumentInvestingActivities and
    # PaymentsForProceedsFromOtherInvestingActivities - not an unrelated disclosure),
    # plain non-dimensioned annual contexts: $34,000,000 FY2025 / $153,000,000 FY2024 /
    # $117,000,000 FY2023.
    "EQH": [("eqh", "InvestmentInCapitalizedSoftwareLeaseholdImprovementsAndEDPEquipment")],
}


# FOUND 2026-09-02 (goal: "SEC/XBRL missing data" audit, investigating the
# `no_revenue_reported` bucket): annual_income_statement.revenue was NULL for APA
# Corporation (CIK 1841666, a real, large oil & gas major with billions in real
# revenue) despite APA filing real, current 10-Ks every year - the SAME structural gap
# as CUSTOM_CAPEX_CONCEPTS above, just for the top-line revenue figure instead of
# capex: APA tags its consolidated total revenue under its own extension concept
# apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments (oil/gas sales revenue plus
# realized hedging gains/losses, APA's own presentation of its income-statement top
# line), invisible to sec_statements.py's get_income_statement() us-gaap-only concept
# list and to SEC's companyfacts/companyconcept APIs (same "custom extension concepts
# excluded from both convenience APIs entirely" limitation CUSTOM_CAPEX_CONCEPTS'
# module docstring already documents for DHT/CMRE). Live-verified against APA's real
# FY2025 10-K (accession 0001841666-26-000015) reconstructed XBRL instance document:
# context "c-1" (plain, no segment/scenario dimension, full FY2025 duration) carries
# apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments=8,951,000,000 - exactly the
# consolidated total that the segment-revenue fix (commit 9ca9feb75) already confirmed
# equals the sum of APA's US ($5.541B) + Egypt ($2.637B) + North Sea ($0.773B) segment
# revenues with 0% reconciliation error for FY2023-2025.
CUSTOM_REVENUE_CONCEPTS: dict[str, list[tuple[str, str]]] = {
    "APA": [("apa", "RevenuesAndRealizedGainsLossesOnDerivativeInstruments")],
}


def _local_name(tag: str) -> str:
    """Strip the Clark-notation namespace from an ElementTree tag."""
    return tag.rsplit("}", 1)[-1]


def _extract_values_for_concepts(xml_content: str, concepts: list[tuple[str, str]] | None) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for the given (namespace_prefix,
    local_name) concept(s), returning {fiscal_year: summed_value}. Shared core of
    extract_custom_capex_from_xbrl_xml and extract_custom_revenue_from_xbrl_xml - see
    either for the per-field registry it's called with.

    Excludes any context with a <segment>/<scenario> dimensional qualifier - a
    dimensionally-scoped fact is a specific business segment or member, not the
    consolidated entity-wide total this codebase's other figures represent (same
    governance as sec_xbrl_segments.py's own context handling - see the FIXED comment
    just below on why this scans the full context subtree, not just direct children).
    Also excludes non-annual-duration contexts (anything not ~350-380 days) so a
    quarterly/interim fact can't get misattributed to the wrong annual bucket.
    """
    if not concepts:
        # Not an error - no candidates registered for this symbol/field at all, so
        # there is nothing to search the XML for (never guesses at unregistered concept
        # names).
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
        # FIXED 2026-09-02 (found while adding CUSTOM_REVENUE_CONCEPTS/APA): this used
        # to check only ctx's DIRECT children for segment/scenario, which happened to
        # match the DHT/CMRE/EGY/ANNA/EPSN test fixtures (they model <segment> as a
        # sibling of <entity>) but not real XBRL - live-confirmed APA's actual filed
        # FY2025 10-K reconstructed instance document (accession 0001841666-26-000015)
        # nests <segment> INSIDE <entity> (<context><entity><identifier/><segment>...
        # </segment></entity><period>...</period></context>), the structure the XBRL
        # spec actually requires and sec_xbrl_segments.py's own context indexer already
        # handles correctly via ctx.iter() (see e.g. its _index_segment_contexts). The
        # direct-children-only check would have silently treated every real
        # dimensionally-scoped context as the consolidated total for any filer using
        # spec-correct nesting - now scans the full context subtree like that sibling
        # module does.
        if any(_local_name(child.tag) in ("segment", "scenario") for child in ctx.iter() if child is not ctx):
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


def _fiscal_year_for_instant(instant_date: date) -> int:
    """Resolve the fiscal year a balance-sheet instant fact belongs to, correcting for a
    52/53-week fiscal calendar whose year-end lands in early January (e.g. TXT/Textron's
    real period end "2026-01-03", which Textron itself labels fiscal 2025, not 2026).

    FOUND 2026-09-03 (adding TXT to CUSTOM_DEBT_CONCEPTS): plain `instant_date.year` -
    what this module used unconditionally before this fix - put TXT's real Jan-2026-dated
    debt facts in the DB's fiscal_year=2026 bucket, while every other TXT field (via the
    main `get_balance_sheet`/`_aggregate_concepts` pipeline, which trusts SEC's own `fy`
    metadata field on each fact rather than a bare date calculation - see
    `_aggregate_concepts`'s own "BUG FOUND 2026-09-01... 52/53-week-fiscal-year phantom-
    year" comment for the full mechanism) already lands in fiscal_year=2025 for the
    identical real period end. Raw XBRL instance documents (what this module parses)
    don't carry SEC's derived `fy` field at all - only the shared duration-fact extractor
    above and the main companyfacts-driven pipeline have access to it - so this uses the
    same "Jan 1-10 crossing window" heuristic that pipeline's own comment documents as the
    real-world shape of a 52/53-week fiscal year-end, not a guessed threshold: subtract one
    year for an instant landing in the first 10 days of January. A no-op for every symbol
    with a normal fiscal year end (AES/DE/BRK.A/BRK.B all end in November/December,
    outside this window) - safe to apply unconditionally, not gated per-symbol.
    """
    if instant_date.month == 1 and instant_date.day <= 10:
        return instant_date.year - 1
    return instant_date.year


def _extract_instant_values_for_concepts(xml_content: str, concepts: list[tuple[str, str]] | None) -> dict[int, float]:
    """Instant-fact counterpart of _extract_values_for_concepts above, for balance-sheet
    (point-in-time) custom concepts like AES's real debt tags - see CUSTOM_DEBT_LONGTERM_
    CONCEPTS/CUSTOM_DEBT_SHORTTERM_CONCEPTS's module comment for the live evidence.

    Same "exclude any dimensioned context" consolidated-total governance as
    _extract_values_for_concepts, just matched against <instant> instead of <startDate>/
    <endDate> - a balance-sheet fact has no duration to filter on.

    LIVE-CONFIRMED 2026-09-03 (AES/RecourseDebtNonCurrent, adding CUSTOM_DEBT_LONGTERM_
    CONCEPTS): the identical (contextRef, concept) fact can appear MORE THAN ONCE in a real
    filing's raw instance document with the exact same value (e.g. once inline in the
    primary balance-sheet statement's XBRL, once again in a footnote/schedule table that
    happens to reuse the same context) - summing every occurrence would silently double (or
    more) the real figure. Deduplicates by (contextRef, concept) before accumulating, same
    governance as the Berkshire dimensioned-sum extractor's members_seen_by_year set.
    """
    if not concepts:
        # Not an error - no candidates registered for this symbol/field at all, so there
        # is nothing to search the XML for (never guesses at unregistered concept names).
        return {}
    wanted_local_names = {local_name for _prefix, local_name in concepts}

    root = ET.fromstring(xml_content)

    context_instants: dict[str, str] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        if any(_local_name(child.tag) in ("segment", "scenario") for child in ctx.iter() if child is not ctx):
            continue  # Dimensionally-scoped context - not the consolidated total
        period = next((c for c in ctx if _local_name(c.tag) == "period"), None)
        if period is None:
            continue
        instant_el = next((c for c in period if _local_name(c.tag) == "instant"), None)
        if instant_el is None or not instant_el.text:
            continue  # Duration context, not an instant balance-sheet snapshot.
        context_instants[ctx_id] = instant_el.text.strip()

    values_by_year: dict[int, float] = {}
    seen_context_concepts: set[tuple[str, str]] = set()
    for el in root.iter():
        local_name = _local_name(el.tag)
        if local_name not in wanted_local_names:
            continue
        ctx_ref = el.get("contextRef")
        if ctx_ref not in context_instants:
            continue
        dedup_key = (ctx_ref, local_name)
        if dedup_key in seen_context_concepts:
            continue  # Same fact re-tagged elsewhere in the document - count it once.
        seen_context_concepts.add(dedup_key)
        try:
            instant_date = date.fromisoformat(context_instants[ctx_ref])
        except ValueError:
            continue
        if el.text is None:
            continue
        try:
            value = float(el.text.strip())
        except ValueError:
            continue
        fiscal_year = _fiscal_year_for_instant(instant_date)
        values_by_year[fiscal_year] = values_by_year.get(fiscal_year, 0.0) + value

    return values_by_year


def extract_custom_capex_from_xbrl_xml(xml_content: str, symbol: str) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for `symbol`'s known custom capex
    concept(s) (see CUSTOM_CAPEX_CONCEPTS), returning {fiscal_year: summed_value}.

    Only meaningful for symbols in CUSTOM_CAPEX_CONCEPTS - returns {} immediately for any
    other symbol (never guesses at unregistered concept names).
    """
    return _extract_values_for_concepts(xml_content, CUSTOM_CAPEX_CONCEPTS.get(symbol))


def extract_custom_revenue_from_xbrl_xml(xml_content: str, symbol: str) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for `symbol`'s known custom revenue
    concept(s) (see CUSTOM_REVENUE_CONCEPTS), returning {fiscal_year: summed_value}.

    Only meaningful for symbols in CUSTOM_REVENUE_CONCEPTS - returns {} immediately for
    any other symbol (never guesses at unregistered concept names).
    """
    return _extract_values_for_concepts(xml_content, CUSTOM_REVENUE_CONCEPTS.get(symbol))


_ANNUAL_FILING_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"})
# BASE (non-amendment) forms only - tried first. See _fetch_custom_concept's docstring.
_BASE_ANNUAL_FILING_FORMS = frozenset({"10-K", "10-KT", "20-F", "40-F"})


def _fetch_custom_concept(
    symbol: str,
    sec_client: Any,
    registry: dict[str, Any],
    extractor: Any,
) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known custom concept(s)
    registered in `registry`, via `extractor(xml_content, symbol)`. Returns {} if symbol
    isn't in `registry`, the filing can't be found, or the XML can't be parsed - callers
    should treat that as "no fallback data", not raise. Shared core of fetch_custom_capex
    and fetch_custom_revenue.

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
    if symbol not in registry:
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
                return extractor(xml_content, symbol)  # type: ignore[no-any-return]
            if fallback_amendment is None:
                fallback_amendment = (accession, form)
        if fallback_amendment is not None:
            accession, form = fallback_amendment
            xml_content = sec_client.get_filing_xml(cik, accession, form)
            return extractor(xml_content, symbol)  # type: ignore[no-any-return]
    except Exception:
        # Not an error for THIS optional fallback - a fetch/parse failure here just means
        # no supplemental value is available this run; the symbol keeps whatever the
        # normal SEC concept-list extraction already found (possibly still NULL, same as
        # before this module existed). Same soft-fail contract as this codebase's other
        # optional-fallback sources (e.g. sec_base.py's _try_yfinance_fallback).
        return {}
    # Not an error - no candidates at all: the filing history had no 10-K/20-F/40-F to check.
    return {}


def fetch_custom_capex(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known custom capex
    concept(s). Returns {} if symbol isn't in CUSTOM_CAPEX_CONCEPTS, the filing can't be
    found, or the XML can't be parsed - callers should treat that as "no fallback data",
    not raise.
    """
    return _fetch_custom_concept(symbol, sec_client, CUSTOM_CAPEX_CONCEPTS, extract_custom_capex_from_xbrl_xml)


def fetch_custom_revenue(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known custom revenue
    concept(s). Returns {} if symbol isn't in CUSTOM_REVENUE_CONCEPTS, the filing can't
    be found, or the XML can't be parsed - callers should treat that as "no fallback
    data", not raise.
    """
    return _fetch_custom_concept(symbol, sec_client, CUSTOM_REVENUE_CONCEPTS, extract_custom_revenue_from_xbrl_xml)


# FOUND 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, total_debt_not_
# itemized investigation): BRK.A/BRK.B (Berkshire Hathaway, CIK 0001067983) have real, huge
# ($45.8B + $83.3B = ~$129B FY2025) debt on file, but long_term_debt/short_term_debt were
# NULL for every fiscal year - Berkshire's consolidated balance sheet has no single "total
# debt" line at all (by design: it presents assets/liabilities split into two entity-level
# columns, "Insurance and Other" and "Railroad, Utilities and Energy", not one consolidated
# column). Real value on file: both segments tag "us-gaap:DebtAndCapitalLeaseObligations",
# labeled "Notes payable and other borrowings" in the rendered statement - live-confirmed
# against Berkshire's own real FY2025 10-K (accession 0001193125-26-083899,
# brka-20251231_htm.xml) reconstructed XBRL instance document: Insurance and Other
# $45,763,000,000 FY2025/$44,885,000,000 FY2024, Railroad Utilities and Energy
# $83,318,000,000 FY2025/$79,877,000,000 FY2024 - both real, additive (distinct entity-level
# totals, not a duplicate), summed total matches Berkshire's real, publicly reported ~$129B
# debt scale. NOT the same shape as CUSTOM_CAPEX_CONCEPTS/CUSTOM_REVENUE_CONCEPTS above
# (a concept never exposed via companyfacts at all): this concept name IS a standard
# us-gaap concept and IS present in companyfacts, but only under a NON-USD unit
# (EUR/GBP/JPY, an unrelated currency-risk footnote disclosure using this same concept name)
# - the USD, entity-level facts are structurally dropped by companyfacts because there is no
# single non-dimensioned USD fact for this concept/period (only two same-period,
# axis-dimensioned USD facts), and companyfacts's aggregation appears to require a
# non-dimensioned representative to surface a unit at all. So this still needs the raw
# instance document like the concepts above, just via SUM-BY-DIMENSION-MEMBER instead of the
# "exclude every dimensioned context" rule _extract_values_for_concepts uses for capex/
# revenue - Berkshire's own debt footnote also tags DOZENS of sub-entity/individual-bond
# breakdowns under this exact same concept name (dimensioned by
# srt:ConsolidatedEntitiesAxis/dei:LegalEntityAxis/srt:CurrencyAxis members ON TOP OF the
# ProductOrServiceAxis segment member) that are components OF the two segment totals, not
# additional debt - live-confirmed by context inspection that only the 4 real contexts
# needed here (2 segments x FY2025/FY2024) have EXACTLY ONE dimension member total; every
# sub-entity breakdown fact has 2 or 3. _extract_dimensioned_sum_from_xbrl_xml's "exactly one
# explicitMember, and it's in the target set" filter is what correctly isolates the 4 real
# segment-total facts from the dozens of sub-entity duplicates - do not loosen that filter
# without re-verifying against the raw instance document, a double-count here would badly
# overstate one of the most widely-held stocks' total_debt.
CUSTOM_DEBT_CONCEPTS: dict[str, tuple[str, frozenset[str]]] = {
    "BRK.A": (
        "DebtAndCapitalLeaseObligations",
        frozenset({"InsuranceAndOtherMember", "RailroadUtilitiesAndEnergyMember"}),
    ),
    "BRK.B": (
        "DebtAndCapitalLeaseObligations",
        frozenset({"InsuranceAndOtherMember", "RailroadUtilitiesAndEnergyMember"}),
    ),
    # Textron Inc (CIK 0000217346) - verified live 2026-09-03 against its real filed
    # FY2025 10-K raw XBRL instance document (accession 0000217346-26-000006,
    # txt-20260103_htm.xml): same "no single consolidated total" shape as Berkshire above
    # - Textron presents its balance sheet split into "Manufacturing group" and "Finance
    # group" segments, each tagging the full (current+noncurrent combined) us-gaap:
    # LongTermDebt concept separately: Manufacturing $3,539,000,000 FY2025/$3,247,000,000
    # FY2024, Finance $339,000,000/$341,000,000 - combined ~$3.878B/$3.588B, plausible
    # against Textron's real, publicly known ~$3.6-3.9B debt scale. Confirmed absent from
    # companyfacts under this concept for this CIK (structural API limitation, not an
    # unchecked concept name). Textron's real fiscal year end lands in early January
    # (period end "2026-01-03" for what Textron itself calls fiscal 2025) - see
    # _fiscal_year_for_instant's docstring for why this needed a dedicated Jan-crossing
    # fix before being safe to add, not just a registry entry.
    "TXT": ("LongTermDebt", frozenset({"ManufacturingGroupMember", "FinanceGroupMember"})),
}


def _extract_dimensioned_sum_from_xbrl_xml(xml_content: str, symbol: str) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for `symbol`'s known
    CUSTOM_DEBT_CONCEPTS-registered concept, summing only the facts tagged in a context
    dimensioned by EXACTLY ONE explicitMember drawn from the registered member set (e.g.
    Berkshire's two entity-level segments) - returns {fiscal_year: summed_value}.

    This is the inverse filter of _extract_values_for_concepts above (which EXCLUDES every
    dimensioned context to find a single consolidated total): here there is no consolidated,
    non-dimensioned total at all, only N segment-level totals that must be summed, while
    still excluding every MORE-dimensioned sub-entity/sub-bond breakdown fact tagged under
    the identical concept name in the same document (see CUSTOM_DEBT_CONCEPTS's module
    comment for the live evidence this distinction matters). "Exactly one member, and it's
    in the target set" is what makes that distinction safely - a context with 2+ dimensions
    is always a narrower sub-breakdown of one of the N segment totals, never itself a
    segment total, in every real case checked so far.

    Only meaningful for symbols in CUSTOM_DEBT_CONCEPTS - returns {} immediately otherwise
    (never guesses at unregistered concept/member names). A fiscal year is only returned once
    ALL registered members were found for it, so a filer dropping one segment's tag in a
    future filing understates nothing silently - it just stops returning that year at all.
    """
    spec = CUSTOM_DEBT_CONCEPTS.get(symbol)
    if not spec:
        # Not an error - no candidates registered for this symbol at all, so there is
        # nothing to search the XML for (never guesses at unregistered concept/member
        # names).
        return {}
    concept_local_name, member_local_names = spec

    root = ET.fromstring(xml_content)

    context_members: dict[str, tuple[str, str]] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        period = next((c for c in ctx if _local_name(c.tag) == "period"), None)
        if period is None:
            continue
        instant_el = next((c for c in period if _local_name(c.tag) == "instant"), None)
        if instant_el is None or not instant_el.text:
            continue  # Duration context, not an instant balance-sheet snapshot - not usable here.
        members = [
            el.text.strip().rsplit(":", 1)[-1]
            for el in ctx.iter()
            if _local_name(el.tag) == "explicitMember" and el.text
        ]
        if len(members) != 1 or members[0] not in member_local_names:
            continue  # Not one of our target segment totals - see module comment above.
        context_members[ctx_id] = (instant_el.text.strip(), members[0])

    values_by_year: dict[int, float] = {}
    members_seen_by_year: dict[int, set[str]] = {}
    for el in root.iter():
        if _local_name(el.tag) != concept_local_name:
            continue
        ctx_ref = el.get("contextRef")
        if ctx_ref not in context_members:
            continue
        instant_str, member = context_members[ctx_ref]
        try:
            instant_date = date.fromisoformat(instant_str)
        except ValueError:
            continue
        if el.text is None:
            continue
        try:
            value = float(el.text.strip())
        except ValueError:
            continue
        fiscal_year = _fiscal_year_for_instant(instant_date)
        seen = members_seen_by_year.setdefault(fiscal_year, set())
        if member in seen:
            continue  # Duplicate fact for a member/year already summed - never double-count.
        seen.add(member)
        values_by_year[fiscal_year] = values_by_year.get(fiscal_year, 0.0) + value

    return {
        year: total for year, total in values_by_year.items() if members_seen_by_year[year] == set(member_local_names)
    }


def fetch_custom_debt(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known CUSTOM_DEBT_CONCEPTS
    dimensioned-sum concept. Returns {} if symbol isn't registered, the filing can't be
    found, or the XML can't be parsed - callers should treat that as "no fallback data",
    not raise.
    """
    return _fetch_custom_concept(symbol, sec_client, CUSTOM_DEBT_CONCEPTS, _extract_dimensioned_sum_from_xbrl_xml)


# FOUND 2026-09-03 (same sweep, "no debt" cross-check follow-up): AES Corporation (CIK
# 0000874761, independent power producer) tags its entire real debt load (~$29.9B FY2025)
# under filer-specific custom extension concepts split by recourse status - real, current,
# additive figures, live-confirmed against AES's own real FY2025 10-K raw XBRL instance
# document (accession 0000874761-26-000063, aes-20251231_htm.xml): noncurrent
# aes:RecourseDebtNonCurrent $5,105,000,000 + aes:NonRecourseDebtNonCurrent
# $21,681,000,000 = $26,786,000,000 FY2025 ($4,805,000,000 + $20,626,000,000 =
# $25,431,000,000 FY2024); current aes:RecourseDebtCurrent $879,000,000 +
# aes:NonRecourseDebtCurrent $2,232,000,000 = $3,111,000,000 FY2025 - both plausible
# against AES's real, publicly known ~$28-30B debt scale (AES structures most of its
# generation-project debt as non-recourse to the parent, hence the recourse/non-recourse
# split instead of a plain LongTermDebt tag). No standard us-gaap concept anywhere in AES's
# companyfacts covers this - same structural "custom filer-extension concept, invisible to
# companyfacts" limitation as CUSTOM_CAPEX_CONCEPTS's DHT/CMRE, not the Berkshire dimensioned-
# sum case above (these are plain, non-dimensioned facts - just filer-namespaced instead of
# a standard concept name). Split into separate long-term/short-term registries (unlike
# CUSTOM_DEBT_CONCEPTS's single combined figure for Berkshire) since AES's source data
# genuinely has a current/noncurrent split to preserve, same distinction as senior_notes/
# senior_notes_current elsewhere in this codebase.
CUSTOM_DEBT_LONGTERM_CONCEPTS: dict[str, list[tuple[str, str]]] = {
    "AES": [("aes", "RecourseDebtNonCurrent"), ("aes", "NonRecourseDebtNonCurrent")],
    # Deere & Company (CIK 0000315189) - verified live 2026-09-03 against its real filed
    # FY2025 10-K raw XBRL instance document (accession 0001104659-25-122321,
    # de-20251102x10k_htm.xml): de:LongTermDebtAndFinanceLeasesNoncurrent
    # $43,544,000,000 FY2025 / $43,229,000,000 FY2024, tagged "Long-term borrowings" on
    # the face of the consolidated balance sheet - a filer-specific extension concept
    # (DE's own standard LongTermDebtNoncurrent concept, already mapped in
    # sec_statements.py, stopped after FY2021 with no us-gaap/ifrs successor - same
    # structural companyfacts-invisibility as AES above, confirmed absent from DE's real
    # companyfacts JSON). Each fact appears twice in the raw document with the identical
    # value (once inline, once in a footnote table) - the shared dedup-by-(contextRef,
    # concept) logic in _extract_instant_values_for_concepts already handles this
    # correctly, same as it does for AES.
    "DE": [("de", "LongTermDebtAndFinanceLeasesNoncurrent")],
}
CUSTOM_DEBT_SHORTTERM_CONCEPTS: dict[str, list[tuple[str, str]]] = {
    "AES": [("aes", "RecourseDebtCurrent"), ("aes", "NonRecourseDebtCurrent")],
}


def extract_custom_debt_longterm_from_xbrl_xml(xml_content: str, symbol: str) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for `symbol`'s known noncurrent custom
    debt concept(s) (see CUSTOM_DEBT_LONGTERM_CONCEPTS), returning
    {fiscal_year: summed_value}. Returns {} for any unregistered symbol.
    """
    return _extract_instant_values_for_concepts(xml_content, CUSTOM_DEBT_LONGTERM_CONCEPTS.get(symbol))


def extract_custom_debt_shortterm_from_xbrl_xml(xml_content: str, symbol: str) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for `symbol`'s known current custom debt
    concept(s) (see CUSTOM_DEBT_SHORTTERM_CONCEPTS), returning {fiscal_year: summed_value}.
    Returns {} for any unregistered symbol.
    """
    return _extract_instant_values_for_concepts(xml_content, CUSTOM_DEBT_SHORTTERM_CONCEPTS.get(symbol))


def fetch_custom_debt_longterm(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known CUSTOM_DEBT_LONGTERM_
    CONCEPTS. Returns {} if symbol isn't registered, the filing can't be found, or the XML
    can't be parsed - callers should treat that as "no fallback data", not raise.
    """
    return _fetch_custom_concept(
        symbol, sec_client, CUSTOM_DEBT_LONGTERM_CONCEPTS, extract_custom_debt_longterm_from_xbrl_xml
    )


def fetch_custom_debt_shortterm(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known CUSTOM_DEBT_SHORTTERM_
    CONCEPTS. Returns {} if symbol isn't registered, the filing can't be found, or the XML
    can't be parsed - callers should treat that as "no fallback data", not raise.
    """
    return _fetch_custom_concept(
        symbol, sec_client, CUSTOM_DEBT_SHORTTERM_CONCEPTS, extract_custom_debt_shortterm_from_xbrl_xml
    )
