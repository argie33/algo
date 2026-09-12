"""Currency-aware duration-fact extractor for custom XBRL extension concepts, extracted
out of sec_custom_xbrl_concepts.py (2026-09-12, file-size ratchet: that file is already at
its baseline, so a new capability must land in a new module, not grow it) rather than
alongside its non-currency sibling `_extract_values_for_concepts`.

Goal-session context ("SEC/XBRL missing data under 200" push): SU (Suncor Energy, CIK
0000311337) tags real, consolidated, non-dimensioned capex under a custom extension
concept (su:CashFlowsUsedForCapitalExpenditures) - live-confirmed against its real filed
FY2025 40-F (accession 0001104659-26-020411): CAD 5,856,000,000 FY2025 / CAD
6,483,000,000 FY2024, plain `Duration_..._2025` contexts with no SegmentAxis (the
filing's per-segment OilSands/E&P/Refining breakdowns use separate, clearly-dimensioned
contexts, correctly excluded). The existing `_extract_values_for_concepts` (used by every
current CUSTOM_CAPEX_CONCEPTS entry - DHT, CMRE, EGY, APA - all USD-only filers) has no
currency/unitRef check at all, so using it as-is for SU would treat the raw CAD figure as
USD - a real currency-scale bug, same class this codebase already caught and fixed once
for NXAT's KRW debt figures (see utils/external/sec_custom_xbrl_concepts.py's
CUSTOM_DEBT_LONGTERM_CONCEPTS module comment) and for DB/BIDU's income-dimensioned
figures (`_extract_single_concept_duration_dimensioned_sum`). This combines that same
proven currency-resolution logic (`_parse_unit_currencies` + MAJOR_CURRENCIES-gated FX
conversion via `_fx_rate_cache.get_usd_rate`) with `_extract_values_for_concepts`'s own
"exclude any dimensioned context, require a ~350-380 day annual duration" governance,
which neither existing extractor did on its own.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from utils.external.fx_rates import MAJOR_CURRENCIES
from utils.external.sec_custom_xbrl_concepts import _fetch_custom_concept, _local_name, _parse_unit_currencies
from utils.external.sec_custom_xbrl_concepts import _fx_rate_cache as _shared_fx_rate_cache


def _index_non_dimensioned_duration_contexts(root: ET.Element) -> dict[str, tuple[str, str]]:
    """{context id: (startDate, endDate)} for every context in `root` that is a plain
    duration (no <segment>/<scenario> dimensional qualifier) - the consolidated-total
    contexts a non-dimensioned figure like SU's capex is tagged against.
    """
    context_periods: dict[str, tuple[str, str]] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        if any(_local_name(child.tag) in ("segment", "scenario") for child in ctx.iter() if child is not ctx):
            continue  # Dimensionally-scoped context - not the consolidated total.
        period = next((c for c in ctx if _local_name(c.tag) == "period"), None)
        if period is None:
            continue
        start_el = next((c for c in period if _local_name(c.tag) == "startDate"), None)
        end_el = next((c for c in period if _local_name(c.tag) == "endDate"), None)
        if start_el is None or end_el is None or not start_el.text or not end_el.text:
            continue  # Instant context, not a duration one.
        context_periods[ctx_id] = (start_el.text.strip(), end_el.text.strip())
    return context_periods


def _extract_duration_values_for_concepts_with_currency(
    xml_content: str, concepts: list[tuple[str, str]] | None
) -> dict[int, float]:
    """Currency-aware counterpart of sec_custom_xbrl_concepts._extract_values_for_concepts
    - see this module's own docstring for why SU needs it. Returns {fiscal_year: value},
    always in USD.
    """
    if not concepts:
        return {}
    wanted_local_names = {local_name for _prefix, local_name in concepts}

    root = ET.fromstring(xml_content)
    unit_currencies = _parse_unit_currencies(root)
    context_periods = _index_non_dimensioned_duration_contexts(root)

    # {fiscal_year: {currency: value}} - a real USD fact always wins over a same-year
    # local-currency duplicate, same governance as the income-dimensioned case.
    candidates_by_year: dict[int, dict[str, float]] = {}
    # {fiscal_year: real period end date string} - see the FX lookup below for why this
    # must be the ACTUAL end date, not a synthesized "{fiscal_year}-12-31".
    period_end_by_year: dict[int, str] = {}
    seen_context_concepts: set[tuple[str, str, str | None]] = set()
    for el in root.iter():
        local_name = _local_name(el.tag)
        if local_name not in wanted_local_names:
            continue
        ctx_ref = el.get("contextRef")
        if ctx_ref not in context_periods:
            continue
        unit_ref = el.get("unitRef")
        # LIVE-CONFIRMED 2026-09-12 (SU/Suncor): the identical (contextRef, concept, unit)
        # fact can appear MORE THAN ONCE in a real filing's raw instance document with the
        # exact same value (once inline in the primary cash-flow statement, once again in
        # a footnote/reconciliation table reusing the same context) - summing every
        # occurrence silently doubled SU's real figure before this dedup was added, same
        # governance as _extract_instant_values_for_concepts's own dedup-by-(contextRef,
        # concept) set. Unit MUST be part of the key, not just (contextRef, concept) -
        # live-caught via NCTY, which dual-tags the SAME concept+context in BOTH CNY and
        # USD (see this registry's own comment) - keying on (contextRef, concept) alone
        # treated the second (USD) occurrence as a duplicate of the first (CNY) and
        # silently discarded the real USD fact, same currency-preference bug this whole
        # module exists to avoid.
        dedup_key = (ctx_ref, local_name, unit_ref)
        if dedup_key in seen_context_concepts:
            continue
        seen_context_concepts.add(dedup_key)
        start_str, end_str = context_periods[ctx_ref]
        try:
            start_date = date.fromisoformat(start_str)
            end_date = date.fromisoformat(end_str)
        except ValueError:
            continue
        duration_days = (end_date - start_date).days
        if not (350 <= duration_days <= 380):
            continue  # Not a full-year duration.
        if el.text is None:
            continue
        try:
            value = float(el.text.strip())
        except ValueError:
            continue
        currency = unit_currencies.get(unit_ref) if unit_ref else None
        if currency is None:
            continue  # Unresolvable unit - never guess a currency.
        fiscal_year = end_date.year
        # Sum multiple concepts (e.g. a long-term + current-portion pair) within the same
        # currency for the same year, mirroring _extract_values_for_concepts's summing
        # behavior - only meaningfully differs from it once a real multi-concept,
        # non-USD registry entry exists.
        by_currency = candidates_by_year.setdefault(fiscal_year, {})
        by_currency[currency] = by_currency.get(currency, 0.0) + value
        period_end_by_year[fiscal_year] = end_str

    values_by_year: dict[int, float] = {}
    for fiscal_year, by_currency in candidates_by_year.items():
        if "USD" in by_currency:
            values_by_year[fiscal_year] = by_currency["USD"]
            continue
        for currency, value in by_currency.items():
            if currency not in MAJOR_CURRENCIES:
                continue
            # FIXED 2026-09-12 (live-caught via PAYP, fiscal year ending March 31): this
            # used to synthesize "{fiscal_year}-12-31" as the FX lookup date, assuming
            # every filer's fiscal year ends on a calendar-year boundary - true for SU/
            # NCTY/JF/SQNS (this module's other registry entries, all Dec 31 FYE) but
            # WRONG in general. For a March-FYE filer, fiscal_year (= end_date.year) is
            # 2026 while the real period end is 2026-03-31 - looking up a rate for
            # 2026-12-31 asks for a genuinely FUTURE date relative to "today" during this
            # goal session (2026-09-11/12), which Frankfurter can never have published,
            # so the whole fiscal year's dividend silently vanished (fail-closed on a
            # lookup date that was never real in the first place, not a genuine "no rate
            # available"). Uses the real period end date now.
            fx_rate = _shared_fx_rate_cache.get_usd_rate(currency, period_end_by_year[fiscal_year])
            if fx_rate is None or fx_rate == 0:
                continue  # No real rate available - fail closed.
            values_by_year[fiscal_year] = value / fx_rate
            break

    return values_by_year


# SU (Suncor Energy Inc, CIK 0000311337) - see module docstring for the live evidence.
#
# JF (J and Friends Holdings Limited, CIK 0001716338) - live-verified against its real
# filed FY2025 20-F (accession 0001104659-26-048056): jf:PaymentsToAcquirePropertyEquipment
# AndSoftware = USD 5,000 FY2025, plain non-dimensioned context, already tagged in USD
# (Unit_Standard_USD) - registered here (not the plain CUSTOM_CAPEX_CONCEPTS registry)
# purely so one extractor/registry pair covers every symbol this DERA-scan sweep found,
# not because JF itself needs FX conversion.
#
# NCTY (The9 Limited, CIK 0001296774) - live-verified against its real filed FY2025 20-F
# (accession 0001104659-26-043910): ncty:PaymentsToAcquirePropertyEquipmentAndSoftware
# tagged in BOTH CNY and USD for FY2025 (CNY 1,446,000 / USD 207,000, identical context) -
# same dual-tagging shape already documented for BIDU elsewhere in this codebase - and
# CNY-only for FY2023 (CNY 2,112,000, no USD sibling that year). This extractor's
# prefer-real-USD-else-convert logic handles both cases without any special-casing.
#
# SQNS (Sequans Communications S.A., CIK 0001383395) - live-verified against its real
# filed FY2025 20-F (accession 0001383395-26-000082):
# sqns:PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssetsClassifiedAsInvestingActivities
# = USD 2,243,000 FY2025 / 3,316,000 FY2024 / 5,457,000 FY2023, plain non-dimensioned
# contexts, already tagged in USD - registered here (not CUSTOM_CAPEX_CONCEPTS) for the
# same one-registry-covers-the-sweep reason as JF above.
CUSTOM_CAPEX_CONCEPTS_CURRENCY_AWARE: dict[str, list[tuple[str, str]]] = {
    "SU": [("su", "CashFlowsUsedForCapitalExpenditures")],
    "JF": [("jf", "PaymentsToAcquirePropertyEquipmentAndSoftware")],
    "NCTY": [("ncty", "PaymentsToAcquirePropertyEquipmentAndSoftware")],
    "SQNS": [("sqns", "PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssetsClassifiedAsInvestingActivities")],
}


def extract_custom_capex_currency_aware_from_xbrl_xml(xml_content: str, symbol: str) -> dict[int, float]:
    """Parse a filing's raw XBRL instance document for `symbol`'s known currency-aware
    custom capex concept(s) (see CUSTOM_CAPEX_CONCEPTS_CURRENCY_AWARE), returning
    {fiscal_year: summed_value_in_usd}. Returns {} for any unregistered symbol.
    """
    return _extract_duration_values_for_concepts_with_currency(
        xml_content, CUSTOM_CAPEX_CONCEPTS_CURRENCY_AWARE.get(symbol)
    )


def fetch_custom_capex_currency_aware(symbol: str, sec_client: Any) -> dict[int, float]:
    """Fetch and parse `symbol`'s latest annual filing for its known
    CUSTOM_CAPEX_CONCEPTS_CURRENCY_AWARE concept(s). Returns {} if symbol isn't
    registered, the filing can't be found, or the XML can't be parsed.
    """
    return _fetch_custom_concept(
        symbol, sec_client, CUSTOM_CAPEX_CONCEPTS_CURRENCY_AWARE, extract_custom_capex_currency_aware_from_xbrl_xml
    )
