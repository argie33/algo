"""Unit tests for utils/external/sec_custom_xbrl_currency_duration.py - the currency-aware
duration-fact extractor added for SU (Suncor Energy), which tags real, consolidated capex
under a custom extension concept in CAD rather than USD. See that module's docstring for
the live evidence (real FY2025 40-F, accession 0001104659-26-020411).
"""

from unittest.mock import MagicMock, patch

from utils.external.sec_custom_xbrl_currency_duration import (
    CUSTOM_CAPEX_CONCEPTS_CURRENCY_AWARE,
    _extract_duration_values_for_concepts_with_currency,
    extract_custom_capex_currency_aware_from_xbrl_xml,
    fetch_custom_capex_currency_aware,
)

# Mirrors SU's real structure: a plain (non-dimensioned) consolidated context tagged in
# CAD, the identical fact repeated once more elsewhere in the document (live-confirmed
# shape - a footnote/reconciliation table reusing the same context), and a
# SegmentAxis-dimensioned sibling that must be excluded.
_SU_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:su="http://suncor.com/20251231">
  <unit id="U_CAD"><measure>iso4217:CAD</measure></unit>
  <context id="c2025">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000311337</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c2024">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000311337</identifier></entity>
    <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
  </context>
  <context id="c2025_OilSands">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000311337</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
    <segment>
      <xbrldi:explicitMember dimension="ifrs-full:SegmentsAxis">su:OilSandsSegmentMember</xbrldi:explicitMember>
    </segment>
  </context>
  <su:CashFlowsUsedForCapitalExpenditures contextRef="c2025" unitRef="U_CAD" decimals="-6">5856000000</su:CashFlowsUsedForCapitalExpenditures>
  <su:CashFlowsUsedForCapitalExpenditures contextRef="c2025" unitRef="U_CAD" decimals="-6">5856000000</su:CashFlowsUsedForCapitalExpenditures>
  <su:CashFlowsUsedForCapitalExpenditures contextRef="c2024" unitRef="U_CAD" decimals="-6">6483000000</su:CashFlowsUsedForCapitalExpenditures>
  <su:CashFlowsUsedForCapitalExpenditures contextRef="c2025_OilSands" unitRef="U_CAD" decimals="-6">3000000000</su:CashFlowsUsedForCapitalExpenditures>
</xbrl>
"""

# Mirrors NCTY's real structure: the SAME concept, SAME context, dual-tagged in BOTH a
# local currency (CNY) and USD - live-confirmed shape (same as BIDU elsewhere in this
# codebase). The USD fact must win, not get discarded as a "duplicate" of the CNY one.
_NCTY_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:ncty="http://the9.com/20251231">
  <unit id="U_CNY"><measure>iso4217:CNY</measure></unit>
  <unit id="U_USD"><measure>iso4217:USD</measure></unit>
  <context id="c2025">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001296774</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <ncty:PaymentsToAcquirePropertyEquipmentAndSoftware contextRef="c2025" unitRef="U_CNY" decimals="-3">1446000</ncty:PaymentsToAcquirePropertyEquipmentAndSoftware>
  <ncty:PaymentsToAcquirePropertyEquipmentAndSoftware contextRef="c2025" unitRef="U_USD" decimals="-3">207000</ncty:PaymentsToAcquirePropertyEquipmentAndSoftware>
</xbrl>
"""

# Mirrors PAYP's real structure: a March 31 fiscal-year-end filer (period 2025-04-01 to
# 2026-03-31 is labeled fiscal_year=2026 by this module's own end_date.year convention).
# Live-caught bug: the FX lookup used to synthesize "{fiscal_year}-12-31" (2026-12-31) as
# the rate date, which during this goal session (2026-09-11/12) is a genuinely FUTURE
# date with no published rate - silently dropping the whole fiscal year, not a real
# "no rate available" case.
_PAYP_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-01/ifrs-full">
  <unit id="U_JPY"><measure>iso4217:JPY</measure></unit>
  <context id="c-fy2026">
    <entity><identifier scheme="http://www.sec.gov/CIK">0002080845</identifier></entity>
    <period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period>
  </context>
  <ifrs-full:DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities contextRef="c-fy2026" unitRef="U_JPY" decimals="-6">311000000</ifrs-full:DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities>
</xbrl>
"""


class TestExtractCustomCapexCurrencyAwareFromXbrlXml:
    def test_converts_cad_to_usd_via_the_fx_rate_cache(self):
        with patch(
            "utils.external.sec_custom_xbrl_currency_duration._shared_fx_rate_cache.get_usd_rate",
            return_value=1.37,
        ):
            result = extract_custom_capex_currency_aware_from_xbrl_xml(_SU_XML, "SU")
        assert result[2025] == 5_856_000_000 / 1.37
        assert result[2024] == 6_483_000_000 / 1.37

    def test_duplicate_context_concept_occurrence_is_deduplicated_not_summed(self):
        """The fact appears twice in the raw document for FY2025 with the identical
        value - must count once, not double."""
        with patch(
            "utils.external.sec_custom_xbrl_currency_duration._shared_fx_rate_cache.get_usd_rate",
            return_value=1.0,
        ):
            result = extract_custom_capex_currency_aware_from_xbrl_xml(_SU_XML, "SU")
        assert result[2025] == 5_856_000_000.0

    def test_dimensioned_segment_context_is_excluded(self):
        """The OilSands segment-level breakdown must never be mistaken for (or summed
        into) the consolidated total."""
        with patch(
            "utils.external.sec_custom_xbrl_currency_duration._shared_fx_rate_cache.get_usd_rate",
            return_value=1.0,
        ):
            result = extract_custom_capex_currency_aware_from_xbrl_xml(_SU_XML, "SU")
        assert result[2025] == 5_856_000_000.0  # not 8_856_000_000 (5.856bn + 3bn segment)

    def test_unregistered_symbol_returns_empty(self):
        assert extract_custom_capex_currency_aware_from_xbrl_xml(_SU_XML, "SOME_OTHER_SYMBOL") == {}

    def test_no_fx_rate_available_skips_the_year_rather_than_guessing(self):
        with patch(
            "utils.external.sec_custom_xbrl_currency_duration._shared_fx_rate_cache.get_usd_rate",
            return_value=None,
        ):
            result = extract_custom_capex_currency_aware_from_xbrl_xml(_SU_XML, "SU")
        assert result == {}


class TestExtractCustomCapexCurrencyAwareDualTaggedSameContext:
    """NCTY (The9 Limited) dual-tags the same concept+context in both CNY and USD -
    live-caught bug: keying the duplicate-fact dedup on (contextRef, concept) alone
    treated the second (USD) occurrence as a duplicate of the first (CNY) and silently
    discarded the real USD fact. Unit must be part of the dedup key.
    """

    def test_real_usd_fact_wins_over_same_context_local_currency_fact(self):
        with patch(
            "utils.external.sec_custom_xbrl_currency_duration._shared_fx_rate_cache.get_usd_rate",
            return_value=1.0,  # Would be wrong if CNY were (mis)selected - proves USD won
        ):
            result = extract_custom_capex_currency_aware_from_xbrl_xml(_NCTY_XML, "NCTY")
        assert result[2025] == 207_000.0


class TestExtractDurationValuesForConceptsWithCurrencyNonCalendarFiscalYear:
    """PAYP (fiscal year ends March 31, not Dec 31) - live-caught bug: the FX lookup date
    used to be synthesized as "{fiscal_year}-12-31" (a real end_date.year-based label),
    which is wrong for any non-calendar-fiscal-year filer - correct lookup date is the
    real period end date.
    """

    def test_fx_lookup_uses_the_real_period_end_date_not_a_synthesized_dec_31(self):
        with patch(
            "utils.external.sec_custom_xbrl_currency_duration._shared_fx_rate_cache.get_usd_rate",
            return_value=150.0,
        ) as mock_get_rate:
            result = _extract_duration_values_for_concepts_with_currency(
                _PAYP_XML,
                [("ifrs-full", "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities")],
            )
        mock_get_rate.assert_called_once_with("JPY", "2026-03-31")
        assert result[2026] == 311_000_000 / 150.0


class TestFetchCustomCapexCurrencyAware:
    def test_unregistered_symbol_never_fetches(self):
        sec_client = MagicMock()
        assert fetch_custom_capex_currency_aware("SOME_OTHER_SYMBOL", sec_client) == {}
        sec_client.symbol_to_cik.assert_not_called()


def test_custom_capex_concepts_currency_aware_registry_is_well_formed():
    for symbol, concepts in CUSTOM_CAPEX_CONCEPTS_CURRENCY_AWARE.items():
        assert isinstance(symbol, str) and symbol
        assert concepts
        for prefix, local_name in concepts:
            assert isinstance(prefix, str) and prefix
            assert isinstance(local_name, str) and local_name
