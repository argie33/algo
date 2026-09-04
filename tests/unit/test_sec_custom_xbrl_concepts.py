"""Tests for utils/external/sec_custom_xbrl_concepts.py - the explicit, hand-verified
fallback for capex tagged under a filer-specific custom XBRL extension taxonomy.

Fixture XML below mirrors the real structure confirmed live 2026-08-29 against DHT
Holdings' and Costamare's actual filed XBRL instance documents (accessions
0001140361-26-010407 and 0001140361-26-007868) - same context/fact shape, values kept
identical to the real filings for a meaningful regression test.
"""

from datetime import date
from unittest.mock import MagicMock

from utils.external.sec_custom_xbrl_concepts import (
    CUSTOM_CAPEX_CONCEPTS,
    CUSTOM_CAPEX_DIMENSIONED_CONCEPTS,
    CUSTOM_DEBT_CONCEPTS,
    CUSTOM_DEBT_LONGTERM_CONCEPTS,
    CUSTOM_DEBT_SHORTTERM_CONCEPTS,
    CUSTOM_DIVIDEND_CONCEPTS,
    CUSTOM_REVENUE_CONCEPTS,
    _extract_dimensioned_sum_from_xbrl_xml,
    _extract_duration_dimensioned_sum_from_xbrl_xml,
    _extract_instant_values_for_concepts,
    _fiscal_year_for_instant,
    extract_custom_capex_from_xbrl_xml,
    extract_custom_debt_longterm_from_xbrl_xml,
    extract_custom_debt_shortterm_from_xbrl_xml,
    extract_custom_dividends_from_xbrl_xml,
    extract_custom_revenue_from_xbrl_xml,
    fetch_custom_capex,
    fetch_custom_capex_dimensioned_sum,
    fetch_custom_debt,
    fetch_custom_debt_longterm,
    fetch_custom_debt_shortterm,
    fetch_custom_dividends,
    fetch_custom_revenue,
)

_DHT_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:dht="http://dhtankers.com/20251231">
  <context id="c20250101to20251231">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001331284</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c20240101to20241231">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001331284</identifier></entity>
    <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
  </context>
  <context id="c20250101to20251231_SegmentAxis_TankerMember">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001331284</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
    <segment>
      <xbrldi:explicitMember dimension="dht:SegmentAxis">dht:TankerMember</xbrldi:explicitMember>
    </segment>
  </context>
  <context id="c20251001to20251231">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001331284</identifier></entity>
    <period><startDate>2025-10-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <dht:InvestmentsInVessels contextRef="c20250101to20251231" unitRef="U002" decimals="-3">111125000</dht:InvestmentsInVessels>
  <dht:InvestmentsInVessels contextRef="c20240101to20241231" unitRef="U002" decimals="-3">6687000</dht:InvestmentsInVessels>
  <dht:InvestmentInVesselsUnderConstruction contextRef="c20250101to20251231" unitRef="U002" decimals="-3">2000000</dht:InvestmentInVesselsUnderConstruction>
  <dht:InvestmentsInVessels contextRef="c20250101to20251231_SegmentAxis_TankerMember" unitRef="U002" decimals="-3">999999999</dht:InvestmentsInVessels>
  <dht:InvestmentsInVessels contextRef="c20251001to20251231" unitRef="U002" decimals="-3">50000000</dht:InvestmentsInVessels>
  <dht:ProfitLossOnSaleOfVessels contextRef="c20250101to20251231" unitRef="U002" decimals="-3">-52943000</dht:ProfitLossOnSaleOfVessels>
</xbrl>
"""

_CMRE_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:cmre="http://costamare.com/20251231">
  <context id="c20250101to20251231">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001503584</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <cmre:PaymentsToAcquireVessels contextRef="c20250101to20251231" unitRef="U002" decimals="-3">68971000</cmre:PaymentsToAcquireVessels>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-02 against APA Corporation's actual
# filed FY2025 10-K reconstructed XBRL instance document (accession
# 0001841666-26-000015): context "c-1" (plain, no segment/scenario dimension) carries
# the real consolidated total revenue; "c-450"/"c-451"/"c-452" are the US/Egypt/North
# Sea segment-scoped facts that must NOT be summed into the consolidated figure.
_APA_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:apa="http://www.apachecorp.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001841666</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-1-prior">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001841666</identifier></entity>
    <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
  </context>
  <context id="c-450">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001841666</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">us-gaap:OperatingSegmentsMember</xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">apa:SegmentUnitedStatesMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-q4-2025">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001841666</identifier></entity>
    <period><startDate>2025-10-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments contextRef="c-1" unitRef="usd" decimals="-6">8951000000</apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments>
  <apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments contextRef="c-1-prior" unitRef="usd" decimals="-6">9739000000</apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments>
  <apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments contextRef="c-450" unitRef="usd" decimals="-6">5541000000</apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments>
  <apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments contextRef="c-q4-2025" unitRef="usd" decimals="-6">2200000000</apa:RevenuesAndRealizedGainsLossesOnDerivativeInstruments>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against CMS Energy's actual filed
# FY2025 10-K raw XBRL instance document (accession 0000811156-26-000004,
# cms-20251231_htm.xml): contexts "c-1"/"c-12"/"c-13" (plain, no segment/scenario
# dimension) carry the real FY2025/FY2024/FY2023 dividends-paid totals; "c-99" is a
# segment-dimensioned decoy and "c-q4" a Q4-only (92-day) decoy, neither of which may be
# counted.
_CMS_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:cms="http://www.cmsenergy.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000811156</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-12">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000811156</identifier></entity>
    <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
  </context>
  <context id="c-13">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000811156</identifier></entity>
    <period><startDate>2023-01-01</startDate><endDate>2023-12-31</endDate></period>
  </context>
  <context id="c-99">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000811156</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">cms:ElectricUtilityMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-q4">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000811156</identifier></entity>
    <period><startDate>2025-10-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <cms:PaymentsOfOrdinaryDividendsCommonAndPreferred contextRef="c-1" unitRef="usd" decimals="-6">663000000</cms:PaymentsOfOrdinaryDividendsCommonAndPreferred>
  <cms:PaymentsOfOrdinaryDividendsCommonAndPreferred contextRef="c-12" unitRef="usd" decimals="-6">626000000</cms:PaymentsOfOrdinaryDividendsCommonAndPreferred>
  <cms:PaymentsOfOrdinaryDividendsCommonAndPreferred contextRef="c-13" unitRef="usd" decimals="-6">579000000</cms:PaymentsOfOrdinaryDividendsCommonAndPreferred>
  <cms:PaymentsOfOrdinaryDividendsCommonAndPreferred contextRef="c-99" unitRef="usd" decimals="-6">400000000</cms:PaymentsOfOrdinaryDividendsCommonAndPreferred>
  <cms:PaymentsOfOrdinaryDividendsCommonAndPreferred contextRef="c-q4" unitRef="usd" decimals="-6">170000000</cms:PaymentsOfOrdinaryDividendsCommonAndPreferred>
</xbrl>
"""


class TestExtractCustomCapexFromXbrlXml:
    def test_dht_sums_both_concepts_for_the_annual_context(self):
        result = extract_custom_capex_from_xbrl_xml(_DHT_XML, "DHT")
        # 111,125,000 (InvestmentsInVessels) + 2,000,000 (UnderConstruction) for FY2025
        assert result[2025] == 113_125_000.0
        assert result[2024] == 6_687_000.0

    def test_dht_excludes_dimensionally_scoped_segment_fact(self):
        result = extract_custom_capex_from_xbrl_xml(_DHT_XML, "DHT")
        # The 999,999,999 value is tagged under a segment-dimensioned context and must
        # never be summed into the consolidated total.
        assert result[2025] < 999_999_999.0

    def test_dht_excludes_non_annual_duration_context(self):
        result = extract_custom_capex_from_xbrl_xml(_DHT_XML, "DHT")
        # The 50,000,000 value is tagged under a Q4-only (92-day) context and must not
        # be counted into the full-year FY2025 bucket.
        assert result[2025] == 113_125_000.0

    def test_cmre_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_CMRE_XML, "CMRE")
        assert result[2025] == 68_971_000.0

    def test_unregistered_symbol_returns_empty_without_parsing(self):
        assert extract_custom_capex_from_xbrl_xml(_DHT_XML, "SOME_OTHER_SYMBOL") == {}

    def test_malformed_xml_does_not_match_wrong_symbol_data(self):
        # DHT's XML parsed for CMRE's concept name must find nothing (different tag names).
        assert extract_custom_capex_from_xbrl_xml(_DHT_XML, "CMRE") == {}


class TestFetchCustomCapex:
    def test_unregistered_symbol_never_calls_sec_client(self):
        sec_client = MagicMock()
        result = fetch_custom_capex("AAPL", sec_client)
        assert result == {}
        sec_client.symbol_to_cik.assert_not_called()

    def test_registered_symbol_fetches_latest_annual_filing_and_parses(self):
        sec_client = MagicMock()
        sec_client.symbol_to_cik.return_value = "0001331284"
        sec_client.get_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["8-K", "20-F", "20-F"],
                    "accessionNumber": ["0000000000-26-000001", "0001140361-26-010407", "0001140361-25-009685"],
                }
            }
        }
        sec_client.get_filing_xml.return_value = _DHT_XML

        result = fetch_custom_capex("DHT", sec_client)

        assert result[2025] == 113_125_000.0
        # Must pick the first ANNUAL form in the list (skipping the 8-K), not just the
        # first row overall.
        sec_client.get_filing_xml.assert_called_once_with("0001331284", "0001140361-26-010407", "20-F")

    def test_sec_client_failure_returns_empty_not_raise(self):
        sec_client = MagicMock()
        sec_client.symbol_to_cik.side_effect = RuntimeError("network error")
        assert fetch_custom_capex("DHT", sec_client) == {}

    def test_prefers_base_10k_over_a_10ka_amendment_that_sorts_first(self):
        """Live-reproduced 2026-08-29: EGY's most-recent-first filing list has a
        Part-III-only 10-K/A (near-empty XBRL instance) sorted before its real,
        substantive 10-K - a naive "first matching annual form" scan picks the
        amendment and finds nothing. Same bug class already fixed once in this repo for
        load_sec_segment_info.py's _find_latest_annual_filing (LAC/PDSB, 2026-08-29)."""
        sec_client = MagicMock()
        sec_client.symbol_to_cik.return_value = "0000894627"
        sec_client.get_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["10-K/A", "10-K", "10-K"],
                    "accessionNumber": ["0000894627-26-000017", "0000894627-26-000013", "0000894627-25-000009"],
                }
            }
        }
        sec_client.get_filing_xml.return_value = _EGY_XML

        result = fetch_custom_capex("EGY", sec_client)

        assert result[2025] == 252_856_000.0
        sec_client.get_filing_xml.assert_called_once_with("0000894627", "0000894627-26-000013", "10-K")

    def test_falls_back_to_amendment_when_no_base_form_filing_exists(self):
        sec_client = MagicMock()
        sec_client.symbol_to_cik.return_value = "0000894627"
        sec_client.get_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["10-K/A"],
                    "accessionNumber": ["0000894627-26-000017"],
                }
            }
        }
        sec_client.get_filing_xml.return_value = _EGY_XML

        result = fetch_custom_capex("EGY", sec_client)

        assert result[2025] == 252_856_000.0
        sec_client.get_filing_xml.assert_called_once_with("0000894627", "0000894627-26-000017", "10-K/A")


def test_custom_capex_concepts_registry_is_well_formed():
    """Every registered symbol must map to at least one (prefix, local_name) tuple - a
    guard against an accidental empty-list entry that would silently resolve to no data."""
    assert "DHT" in CUSTOM_CAPEX_CONCEPTS
    assert "CMRE" in CUSTOM_CAPEX_CONCEPTS
    assert "EGY" in CUSTOM_CAPEX_CONCEPTS
    assert "ANNA" in CUSTOM_CAPEX_CONCEPTS
    assert "EPSN" in CUSTOM_CAPEX_CONCEPTS
    for symbol, concepts in CUSTOM_CAPEX_CONCEPTS.items():
        assert concepts, f"{symbol} has an empty concept list"
        for prefix, local_name in concepts:
            assert prefix and local_name


class TestExtractCustomRevenueFromXbrlXml:
    def test_apa_returns_the_consolidated_total_not_the_segment_or_quarterly_facts(self):
        result = extract_custom_revenue_from_xbrl_xml(_APA_XML, "APA")
        assert result[2025] == 8_951_000_000.0
        assert result[2024] == 9_739_000_000.0

    def test_apa_excludes_dimensionally_scoped_segment_fact(self):
        result = extract_custom_revenue_from_xbrl_xml(_APA_XML, "APA")
        # The $5.541B US-segment value must never be summed into the consolidated total.
        assert result[2025] == 8_951_000_000.0

    def test_apa_excludes_non_annual_duration_context(self):
        result = extract_custom_revenue_from_xbrl_xml(_APA_XML, "APA")
        # The $2.2B Q4-only (92-day) value must not be counted into the FY2025 bucket.
        assert result[2025] == 8_951_000_000.0

    def test_unregistered_symbol_returns_empty_without_parsing(self):
        assert extract_custom_revenue_from_xbrl_xml(_APA_XML, "SOME_OTHER_SYMBOL") == {}

    def test_malformed_xml_does_not_match_wrong_symbol_data(self):
        assert extract_custom_revenue_from_xbrl_xml(_DHT_XML, "APA") == {}


class TestFetchCustomRevenue:
    def test_unregistered_symbol_never_calls_sec_client(self):
        sec_client = MagicMock()
        result = fetch_custom_revenue("AAPL", sec_client)
        assert result == {}
        sec_client.symbol_to_cik.assert_not_called()

    def test_registered_symbol_fetches_latest_annual_filing_and_parses(self):
        sec_client = MagicMock()
        sec_client.symbol_to_cik.return_value = "0001841666"
        sec_client.get_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-K", "10-K"],
                    "accessionNumber": ["0000000000-26-000001", "0001841666-26-000015", "0002040266-25-000007"],
                }
            }
        }
        sec_client.get_filing_xml.return_value = _APA_XML

        result = fetch_custom_revenue("APA", sec_client)

        assert result[2025] == 8_951_000_000.0
        sec_client.get_filing_xml.assert_called_once_with("0001841666", "0001841666-26-000015", "10-K")

    def test_sec_client_failure_returns_empty_not_raise(self):
        sec_client = MagicMock()
        sec_client.symbol_to_cik.side_effect = RuntimeError("network error")
        assert fetch_custom_revenue("APA", sec_client) == {}


def test_custom_revenue_concepts_registry_is_well_formed():
    """Every registered symbol must map to at least one (prefix, local_name) tuple - a
    guard against an accidental empty-list entry that would silently resolve to no data."""
    assert "APA" in CUSTOM_REVENUE_CONCEPTS
    for symbol, concepts in CUSTOM_REVENUE_CONCEPTS.items():
        assert concepts, f"{symbol} has an empty concept list"
        for prefix, local_name in concepts:
            assert prefix and local_name


class TestExtractCustomDividendsFromXbrlXml:
    def test_cms_returns_the_consolidated_total_for_each_fiscal_year(self):
        result = extract_custom_dividends_from_xbrl_xml(_CMS_XML, "CMS")
        assert result[2025] == 663_000_000.0
        assert result[2024] == 626_000_000.0
        assert result[2023] == 579_000_000.0

    def test_cms_excludes_dimensionally_scoped_segment_fact(self):
        result = extract_custom_dividends_from_xbrl_xml(_CMS_XML, "CMS")
        # The $400M segment-scoped value must never be summed into or replace the real
        # $663M consolidated FY2025 total.
        assert result[2025] == 663_000_000.0

    def test_cms_excludes_non_annual_duration_context(self):
        result = extract_custom_dividends_from_xbrl_xml(_CMS_XML, "CMS")
        # The $170M Q4-only (92-day) value must not be counted into the FY2025 bucket.
        assert result[2025] == 663_000_000.0

    def test_unregistered_symbol_returns_empty_without_parsing(self):
        assert extract_custom_dividends_from_xbrl_xml(_CMS_XML, "SOME_OTHER_SYMBOL") == {}

    def test_malformed_xml_does_not_match_wrong_symbol_data(self):
        assert extract_custom_dividends_from_xbrl_xml(_APA_XML, "CMS") == {}


class TestFetchCustomDividends:
    def test_unregistered_symbol_never_calls_sec_client(self):
        sec_client = MagicMock()
        result = fetch_custom_dividends("AAPL", sec_client)
        assert result == {}
        sec_client.symbol_to_cik.assert_not_called()

    def test_registered_symbol_fetches_latest_annual_filing_and_parses(self):
        sec_client = MagicMock()
        sec_client.symbol_to_cik.return_value = "0000811156"
        sec_client.get_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-K", "10-K"],
                    "accessionNumber": ["0000000000-26-000001", "0000811156-26-000004", "0000811156-25-000036"],
                }
            }
        }
        sec_client.get_filing_xml.return_value = _CMS_XML

        result = fetch_custom_dividends("CMS", sec_client)

        assert result[2025] == 663_000_000.0
        sec_client.get_filing_xml.assert_called_once_with("0000811156", "0000811156-26-000004", "10-K")

    def test_sec_client_failure_returns_empty_not_raise(self):
        sec_client = MagicMock()
        sec_client.symbol_to_cik.side_effect = RuntimeError("network error")
        assert fetch_custom_dividends("CMS", sec_client) == {}


def test_custom_dividend_concepts_registry_is_well_formed():
    """Every registered symbol must map to at least one (prefix, local_name) tuple - a
    guard against an accidental empty-list entry that would silently resolve to no data."""
    assert "CMS" in CUSTOM_DIVIDEND_CONCEPTS
    for symbol, concepts in CUSTOM_DIVIDEND_CONCEPTS.items():
        assert concepts, f"{symbol} has an empty concept list"
        for prefix, local_name in concepts:
            assert prefix and local_name


_EGY_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:egy="http://vaalco.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000894627</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <egy:PaymentToAcquirePropertyAndEquipmentExpendituresIncludingExplorationExpense contextRef="c-1" unitRef="usd" decimals="-3">252856000</egy:PaymentToAcquirePropertyAndEquipmentExpendituresIncludingExplorationExpense>
  <egy:AcquisitionOfCrudeOilAndNaturalGasProperties contextRef="c-1" unitRef="usd" decimals="-3">-3034000</egy:AcquisitionOfCrudeOilAndNaturalGasProperties>
</xbrl>
"""

_ANNA_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:anna="http://aleanna.com/20251231">
  <context id="cref_2136440082">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001845123</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <anna:PaymentToAdditionsToConventionalNaturalGasProperties contextRef="cref_2136440082" unitRef="usd" decimals="0">6769337</anna:PaymentToAdditionsToConventionalNaturalGasProperties>
  <anna:PaymentsToAdditionsToRenewableNaturalGasProperties contextRef="cref_2136440082" unitRef="usd" decimals="0">235724</anna:PaymentsToAdditionsToRenewableNaturalGasProperties>
</xbrl>
"""

_EPSN_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:epsn="http://epsilonenergy.com/20251231">
  <context id="Duration_1_1_2025">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001726126</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <epsn:PaymentsToAcquireProvedOilAndGasProperty contextRef="Duration_1_1_2025" unitRef="usd" decimals="0">7929773</epsn:PaymentsToAcquireProvedOilAndGasProperty>
  <epsn:PaymentsToAcquireUnprovedOilAndGasProperty contextRef="Duration_1_1_2025" unitRef="usd" decimals="0">6999905</epsn:PaymentsToAcquireUnprovedOilAndGasProperty>
  <epsn:PaymentsToAcquireLandBuildingsAndOtherPropertyPlantAndEquipment contextRef="Duration_1_1_2025" unitRef="usd" decimals="0">-270488</epsn:PaymentsToAcquireLandBuildingsAndOtherPropertyPlantAndEquipment>
</xbrl>
"""


class TestExtractCustomCapexAdditionalFilers:
    def test_egy_uses_only_the_comprehensive_concept_not_the_ambiguous_sibling(self):
        result = extract_custom_capex_from_xbrl_xml(_EGY_XML, "EGY")
        assert result[2025] == 252_856_000.0

    def test_anna_sums_conventional_and_renewable(self):
        result = extract_custom_capex_from_xbrl_xml(_ANNA_XML, "ANNA")
        assert result[2025] == 7_005_061.0

    def test_epsn_sums_proved_and_unproved_only(self):
        result = extract_custom_capex_from_xbrl_xml(_EPSN_XML, "EPSN")
        # Must NOT include the ambiguous/negative LandBuildings concept (-270,488).
        assert result[2025] == 14_929_678.0


# Mirrors the real structure confirmed live 2026-09-03 against NextEra Energy's actual
# filed FY2025 10-K raw XBRL instance document (accession 0000753308-26-000015): three
# real, additive, dimension-free concepts, plus the FPL co-registrant's own standalone
# statement re-tagging the same FPL figure under a distinct, LegalEntityAxis-dimensioned
# concept that must be excluded, not summed as if it were additional spend.
_NEE_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:nee="http://nexteraenergy.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000753308</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-2-fpl-entity">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000753308</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:LegalEntityAxis">nee:FloridaPowerAndLightCoMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <nee:CapitalExpendituresOfFPL contextRef="c-1" unitRef="usd" decimals="-6">8719000000</nee:CapitalExpendituresOfFPL>
  <nee:IndependentPowerInvestments contextRef="c-1" unitRef="usd" decimals="-6">15332000000</nee:IndependentPowerInvestments>
  <nee:OtherCapitalExpenditures contextRef="c-1" unitRef="usd" decimals="-6">2000000</nee:OtherCapitalExpenditures>
  <nee:CapitalExpendituresOfPublicUtility contextRef="c-2-fpl-entity" unitRef="usd" decimals="-6">8719000000</nee:CapitalExpendituresOfPublicUtility>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Phillips 66's actual filed
# FY2025 10-K raw XBRL instance document (accession 0001534701-26-000006): a single
# concept covers the entire "Capital expenditures and investments" cash-flow-statement
# line.
_PSX_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:psx="http://phillips66.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001534701</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <psx:CapitalExpendituresAndInvestments contextRef="c-1" unitRef="usd" decimals="-6">4466000000</psx:CapitalExpendituresAndInvestments>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against ConocoPhillips' actual
# filed FY2025 10-K raw XBRL instance document (accession 0001163165-26-000009): a single
# concept covers the entire "Capital expenditures and investments" cash-flow-statement
# line, plain non-dimensioned context, immediately after Net Cash Provided by Operating
# Activities.
_COP_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:cop="http://conocophillips.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001163165</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <cop:PaymentToAcquireProductiveAssetsAndInvestments contextRef="c-1" unitRef="usd" decimals="-6">12553000000</cop:PaymentToAcquireProductiveAssetsAndInvestments>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Alibaba's actual filed
# FY2026 (fiscal year ended 2026-03-31) 20-F raw XBRL instance document (accession
# 0001193125-26-231755): a plain non-dimensioned annual-duration context, USD-denominated
# fact alongside a parallel CNY one (only the USD fact used here, matching this module's
# "match by local name only" convention - both are real, not a duplicate/typo).
_BABA_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:baba="http://alibabagroup.com/20260331">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001577552</identifier></entity>
    <period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period>
  </context>
  <baba:PaymentsToAcquireLandUseRightsPropertyAndEquipment contextRef="c-1" unitRef="usd" decimals="-6">18275000000</baba:PaymentsToAcquireLandUseRightsPropertyAndEquipment>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Cigna's actual filed
# FY2025 10-K raw XBRL instance document (accession 0001739940-26-000006): a single
# concept covers Cigna's whole capex line, plain non-dimensioned context.
_CI_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:ci="http://cigna.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001739940</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <ci:PaymentsForProceedsFromPropertyPlantAndEquipment contextRef="c-1" unitRef="usd" decimals="-6">1212000000</ci:PaymentsForProceedsFromPropertyPlantAndEquipment>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Diageo's actual filed
# FY2026 20-F raw XBRL instance document (fiscal year ends June 30).
_DEO_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:deo="http://diageo.com/20260630">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000835403</identifier></entity>
    <period><startDate>2025-07-01</startDate><endDate>2026-06-30</endDate></period>
  </context>
  <deo:PurchaseOfPropertyPlantAndEquipmentAndComputerSoftware contextRef="c-1" unitRef="gbp" decimals="-6">1197000000</deo:PurchaseOfPropertyPlantAndEquipmentAndComputerSoftware>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Infosys's actual filed
# FY2026 20-F raw XBRL instance document (accession 0001193125-26-270520, fiscal year
# ends March 31).
_INFY_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:infy="http://infosys.com/20260331">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001067491</identifier></entity>
    <period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period>
  </context>
  <infy:PurchaseOfPropertyPlantAndEquipmentAndIntangiblesClassifiedAsInvestingActivities contextRef="c-1" unitRef="usd" decimals="-6">306000000</infy:PurchaseOfPropertyPlantAndEquipmentAndIntangiblesClassifiedAsInvestingActivities>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Equitable Holdings' actual
# filed FY2025 10-K raw XBRL instance document (accession 0001333986-26-000012).
_EQH_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:eqh="http://equitableholdings.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001333986</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <eqh:InvestmentInCapitalizedSoftwareLeaseholdImprovementsAndEDPEquipment contextRef="c-1" unitRef="usd" decimals="-6">34000000</eqh:InvestmentInCapitalizedSoftwareLeaseholdImprovementsAndEDPEquipment>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Viking Holdings' actual
# filed FY2025 10-K raw XBRL instance document (accession 0001745201-26-000007).
_VIK_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:vik="http://viking.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001745201</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <vik:InvestmentsInPropertyPlantAndEquipmentAndIntangibleAssets contextRef="c-1" unitRef="usd" decimals="-6">1026854000</vik:InvestmentsInPropertyPlantAndEquipmentAndIntangibleAssets>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Zurn Elkay's actual filed
# FY2025 10-K raw XBRL instance document (accession 0001628280-26-006372).
_ZWS_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:zws="http://zurnelkay.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001439288</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <zws:PaymentsToAcquirePropertyPlantAndEquipmentIncludingDiscontinuedOperations contextRef="c-1" unitRef="usd" decimals="-6">29900000</zws:PaymentsToAcquirePropertyPlantAndEquipmentIncludingDiscontinuedOperations>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Ensign Group's actual
# filed FY2025 10-K raw XBRL instance document (accession 0001125376-26-000007).
_ENSG_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:ensg="http://ensigngroup.net/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001125376</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <ensg:PaymentsToAcquirePropertyAndEquipment contextRef="c-1" unitRef="usd" decimals="-6">193557000</ensg:PaymentsToAcquirePropertyAndEquipment>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against B2Gold's actual filed
# FY2025 40-F raw XBRL instance document (accession 0001104659-26-026310): the
# consolidated (non-dimensioned) total plus a per-mine-dimensioned sibling context for
# the same concept, which must be excluded (StatementBusinessSegmentsAxis-scoped, not
# the consolidated figure).
_BTG_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:btg="http://b2gold.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001429937</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-2-fekola-mine">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0001429937</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">btg:FekolaMineMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <btg:PaymentsForCapitalExpenditures contextRef="c-1" unitRef="usd" decimals="-6">863069000</btg:PaymentsForCapitalExpenditures>
  <btg:PaymentsForCapitalExpenditures contextRef="c-2-fekola-mine" unitRef="usd" decimals="-6">312000000</btg:PaymentsForCapitalExpenditures>
</xbrl>
"""

# Mirrors the real structure confirmed live 2026-09-03 against Lyft's actual filed
# FY2025 10-K raw XBRL instance document (accession 0001628280-26-006960).
_LYFT_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:lyft="http://lyft.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001759509</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <lyft:PaymentsToAcquirePropertyAndEquipmentAndScooterFleet contextRef="c-1" unitRef="usd" decimals="-6">52822000</lyft:PaymentsToAcquirePropertyAndEquipmentAndScooterFleet>
</xbrl>
"""


class TestExtractCustomCapexUtilityAndRefinerFilers:
    def test_nee_sums_the_three_additive_concepts(self):
        result = extract_custom_capex_from_xbrl_xml(_NEE_XML, "NEE")
        # 8,719,000,000 (FPL) + 15,332,000,000 (NEER) + 2,000,000 (Other)
        assert result[2025] == 24_053_000_000.0

    def test_nee_excludes_the_fpl_co_registrant_duplicate_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_NEE_XML, "NEE")
        # CapitalExpendituresOfPublicUtility re-tags the same $8,719M FPL figure under a
        # LegalEntityAxis-dimensioned context (FPL's own standalone statement within the
        # same filing) - summing it in would double-count FPL's capex.
        assert result[2025] == 24_053_000_000.0

    def test_psx_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_PSX_XML, "PSX")
        assert result[2025] == 4_466_000_000.0

    def test_cop_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_COP_XML, "COP")
        assert result[2025] == 12_553_000_000.0

    def test_baba_fiscal_year_matches_march_period_end_not_start(self):
        result = extract_custom_capex_from_xbrl_xml(_BABA_XML, "BABA")
        # Fiscal year ended 2026-03-31 must bucket as FY2026 (end_date.year), matching
        # this codebase's own annual_cash_flow.fiscal_year convention for BABA - not
        # FY2025 (the year the period started in).
        assert result[2026] == 18_275_000_000.0

    def test_ci_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_CI_XML, "CI")
        assert result[2025] == 1_212_000_000.0

    def test_deo_fiscal_year_matches_june_period_end(self):
        result = extract_custom_capex_from_xbrl_xml(_DEO_XML, "DEO")
        # Fiscal year ended 2026-06-30 must bucket as FY2026 (end_date.year).
        assert result[2026] == 1_197_000_000.0

    def test_infy_fiscal_year_matches_march_period_end(self):
        result = extract_custom_capex_from_xbrl_xml(_INFY_XML, "INFY")
        assert result[2026] == 306_000_000.0

    def test_eqh_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_EQH_XML, "EQH")
        assert result[2025] == 34_000_000.0

    def test_vik_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_VIK_XML, "VIK")
        assert result[2025] == 1_026_854_000.0

    def test_zws_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_ZWS_XML, "ZWS")
        assert result[2025] == 29_900_000.0

    def test_ensg_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_ENSG_XML, "ENSG")
        assert result[2025] == 193_557_000.0

    def test_btg_excludes_per_mine_dimensioned_duplicates(self):
        result = extract_custom_capex_from_xbrl_xml(_BTG_XML, "BTG")
        # Must use only the consolidated (non-dimensioned) total, not double-count
        # against the per-mine-dimensioned sibling contexts for the same concept.
        assert result[2025] == 863_069_000.0

    def test_lyft_returns_its_own_concept(self):
        result = extract_custom_capex_from_xbrl_xml(_LYFT_XML, "LYFT")
        assert result[2025] == 52_822_000.0


# Mirrors the real structure confirmed live 2026-09-03 against Berkshire Hathaway's actual
# filed FY2025 10-K raw XBRL instance document (accession 0001193125-26-083899,
# brka-20251231_htm.xml): the two entity-level segment totals (exactly one explicitMember
# each, both required to be summed), a multi-dimensioned sub-entity/sub-bond breakdown fact
# under the identical concept name that must be excluded (2 explicitMembers), and a
# non-USD currency-risk-footnote fact under the same concept name using an unrelated
# CurrencyAxis dimension that must also be excluded.
_BRK_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:us-gaap="http://fasb.org/us-gaap/2025"
      xmlns:srt="http://fasb.org/srt/2025"
      xmlns:dei="http://xbrl.sec.gov/dei/2025"
      xmlns:brka="http://berkshirehathaway.com/20251231">
  <context id="C_insurance_2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">brka:InsuranceAndOtherMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <context id="C_insurance_2024">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">brka:InsuranceAndOtherMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2024-12-31</instant></period>
  </context>
  <context id="C_rue_2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">brka:RailroadUtilitiesAndEnergyMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <context id="C_subentity_2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidatedEntitiesAxis">srt:SubsidiariesMember</xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">brka:RailroadUtilitiesAndEnergyMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <context id="C_currency_footnote_2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:CurrencyAxis">currency:EUR</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <us-gaap:DebtAndCapitalLeaseObligations contextRef="C_insurance_2025" unitRef="U_USD" decimals="-6">45763000000</us-gaap:DebtAndCapitalLeaseObligations>
  <us-gaap:DebtAndCapitalLeaseObligations contextRef="C_insurance_2024" unitRef="U_USD" decimals="-6">44885000000</us-gaap:DebtAndCapitalLeaseObligations>
  <us-gaap:DebtAndCapitalLeaseObligations contextRef="C_rue_2025" unitRef="U_USD" decimals="-6">83318000000</us-gaap:DebtAndCapitalLeaseObligations>
  <us-gaap:DebtAndCapitalLeaseObligations contextRef="C_subentity_2025" unitRef="U_USD" decimals="-6">14914000000</us-gaap:DebtAndCapitalLeaseObligations>
  <us-gaap:DebtAndCapitalLeaseObligations contextRef="C_currency_footnote_2025" unitRef="U_EUR" decimals="-6">6850000000</us-gaap:DebtAndCapitalLeaseObligations>
</xbrl>
"""


class TestExtractDimensionedSumFromXbrlXml:
    def test_brk_sums_the_two_segment_totals_for_2025(self) -> None:
        result = _extract_dimensioned_sum_from_xbrl_xml(_BRK_XML, "BRK.B")
        # 45,763,000,000 (Insurance and Other) + 83,318,000,000 (Railroad, Utilities and Energy)
        assert result[2025] == 129_081_000_000.0

    def test_brk_2024_missing_one_segment_is_not_returned(self) -> None:
        # The fixture only has an Insurance-and-Other fact for 2024 (no Railroad/
        # Utilities/Energy comparative-year fact) - mirrors a real filer dropping one
        # segment's tag for an older comparative year. Must NOT be returned as a
        # (silently understated) total rather than the real combined figure.
        result = _extract_dimensioned_sum_from_xbrl_xml(_BRK_XML, "BRK.B")
        assert 2024 not in result

    def test_brk_excludes_multi_dimensioned_sub_entity_fact(self) -> None:
        result = _extract_dimensioned_sum_from_xbrl_xml(_BRK_XML, "BRK.B")
        # The $14,914,000,000 sub-entity breakdown fact (2 explicitMembers: Subsidiaries +
        # RailroadUtilitiesAndEnergy) is a component OF the $83,318M segment total, not
        # additional debt - summing it in would double-count.
        assert result[2025] == 129_081_000_000.0

    def test_brk_excludes_non_usd_currency_footnote_fact(self) -> None:
        result = _extract_dimensioned_sum_from_xbrl_xml(_BRK_XML, "BRK.B")
        # The EUR 6,850,000,000 currency-risk-footnote fact uses an unrelated CurrencyAxis
        # dimension (not one of our target ProductOrServiceAxis members) and must be
        # excluded regardless of unit.
        assert result[2025] == 129_081_000_000.0

    def test_unregistered_symbol_returns_empty_without_parsing(self) -> None:
        assert _extract_dimensioned_sum_from_xbrl_xml(_BRK_XML, "SOME_OTHER_SYMBOL") == {}

    def test_brk_a_shares_the_same_registration_as_brk_b(self) -> None:
        result = _extract_dimensioned_sum_from_xbrl_xml(_BRK_XML, "BRK.A")
        assert result[2025] == 129_081_000_000.0


class TestFetchCustomDebt:
    def test_unregistered_symbol_never_calls_sec_client(self) -> None:
        sec_client = MagicMock()
        result = fetch_custom_debt("AAPL", sec_client)
        assert result == {}
        sec_client.symbol_to_cik.assert_not_called()

    def test_registered_symbol_fetches_latest_annual_filing_and_parses(self) -> None:
        sec_client = MagicMock()
        sec_client.symbol_to_cik.return_value = "0001067983"
        sec_client.get_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-K", "10-K"],
                    "accessionNumber": ["0000000000-26-000001", "0001193125-26-083899", "0001193125-25-000009"],
                }
            }
        }
        sec_client.get_filing_xml.return_value = _BRK_XML

        result = fetch_custom_debt("BRK.B", sec_client)

        assert result[2025] == 129_081_000_000.0
        sec_client.get_filing_xml.assert_called_once_with("0001067983", "0001193125-26-083899", "10-K")

    def test_sec_client_failure_returns_empty_not_raise(self) -> None:
        sec_client = MagicMock()
        sec_client.symbol_to_cik.side_effect = RuntimeError("network error")
        assert fetch_custom_debt("BRK.B", sec_client) == {}


def test_custom_debt_concepts_registry_is_well_formed() -> None:
    assert "BRK.A" in CUSTOM_DEBT_CONCEPTS
    assert "BRK.B" in CUSTOM_DEBT_CONCEPTS
    for symbol, (concept_local_name, member_local_names) in CUSTOM_DEBT_CONCEPTS.items():
        assert concept_local_name, f"{symbol} has an empty concept name"
        assert member_local_names, f"{symbol} has an empty member set"


# Mirrors the real structure confirmed live 2026-09-03 against AES Corporation's actual
# filed FY2025 10-K raw XBRL instance document (accession 0000874761-26-000063,
# aes-20251231_htm.xml): plain, non-dimensioned instant contexts for the current and prior
# fiscal year, a duplicate-tagged fact (the identical (contextRef, concept) pair appearing
# twice with the same value - a real, harmless authoring pattern that must be deduplicated
# rather than summed twice), and a dimensioned decoy context (fair-value disclosure) under
# the same concept name that must be excluded.
_AES_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:us-gaap="http://fasb.org/us-gaap/2025"
      xmlns:aes="http://aes.com/20251231">
  <context id="c-3">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000874761</identifier></entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <context id="c-5">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000874761</identifier></entity>
    <period><instant>2024-12-31</instant></period>
  </context>
  <context id="c-332">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000874761</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:FairValueByMeasurementBasisAxis">us-gaap:CarryingReportedAmountFairValueDisclosureMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <aes:RecourseDebtNonCurrent contextRef="c-3" unitRef="usd" decimals="-6">5105000000</aes:RecourseDebtNonCurrent>
  <aes:RecourseDebtNonCurrent contextRef="c-3" unitRef="usd" decimals="-6">5105000000</aes:RecourseDebtNonCurrent>
  <aes:RecourseDebtNonCurrent contextRef="c-5" unitRef="usd" decimals="-6">4805000000</aes:RecourseDebtNonCurrent>
  <aes:NonRecourseDebtNonCurrent contextRef="c-3" unitRef="usd" decimals="-6">21681000000</aes:NonRecourseDebtNonCurrent>
  <aes:NonRecourseDebtNonCurrent contextRef="c-5" unitRef="usd" decimals="-6">20626000000</aes:NonRecourseDebtNonCurrent>
  <aes:NonRecourseDebtNonCurrent contextRef="c-332" unitRef="usd" decimals="-6">99999999999</aes:NonRecourseDebtNonCurrent>
  <aes:RecourseDebtCurrent contextRef="c-3" unitRef="usd" decimals="-6">879000000</aes:RecourseDebtCurrent>
  <aes:RecourseDebtCurrent contextRef="c-5" unitRef="usd" decimals="-6">899000000</aes:RecourseDebtCurrent>
  <aes:NonRecourseDebtCurrent contextRef="c-3" unitRef="usd" decimals="-6">2232000000</aes:NonRecourseDebtCurrent>
  <aes:NonRecourseDebtCurrent contextRef="c-5" unitRef="usd" decimals="-6">2688000000</aes:NonRecourseDebtCurrent>
</xbrl>
"""


class TestExtractInstantValuesForConcepts:
    def test_aes_sums_recourse_and_nonrecourse_noncurrent_debt(self) -> None:
        result = extract_custom_debt_longterm_from_xbrl_xml(_AES_XML, "AES")
        # 5,105,000,000 (Recourse) + 21,681,000,000 (Non-recourse)
        assert result[2025] == 26_786_000_000.0
        assert result[2024] == 25_431_000_000.0

    def test_aes_deduplicates_a_fact_tagged_twice_with_the_same_contextref(self) -> None:
        # RecourseDebtNonCurrent/c-3 appears twice in the fixture (same value both times,
        # mirroring the real filing) - must be counted once, not doubled.
        result = extract_custom_debt_longterm_from_xbrl_xml(_AES_XML, "AES")
        assert result[2025] == 26_786_000_000.0

    def test_aes_excludes_dimensioned_fair_value_decoy_fact(self) -> None:
        result = extract_custom_debt_longterm_from_xbrl_xml(_AES_XML, "AES")
        # The absurd 99,999,999,999 fair-value-disclosure decoy (dimensioned context) must
        # never be summed into the real consolidated total.
        assert result[2025] == 26_786_000_000.0

    def test_aes_sums_recourse_and_nonrecourse_current_debt(self) -> None:
        result = extract_custom_debt_shortterm_from_xbrl_xml(_AES_XML, "AES")
        # 879,000,000 (Recourse) + 2,232,000,000 (Non-recourse)
        assert result[2025] == 3_111_000_000.0
        assert result[2024] == 3_587_000_000.0

    def test_unregistered_symbol_returns_empty_without_parsing(self) -> None:
        assert extract_custom_debt_longterm_from_xbrl_xml(_AES_XML, "SOME_OTHER_SYMBOL") == {}
        assert extract_custom_debt_shortterm_from_xbrl_xml(_AES_XML, "SOME_OTHER_SYMBOL") == {}

    def test_none_concepts_returns_empty(self) -> None:
        assert _extract_instant_values_for_concepts(_AES_XML, None) == {}


class TestFetchCustomDebtLongtermShortterm:
    def test_unregistered_symbol_never_calls_sec_client(self) -> None:
        sec_client = MagicMock()
        assert fetch_custom_debt_longterm("AAPL", sec_client) == {}
        assert fetch_custom_debt_shortterm("AAPL", sec_client) == {}
        sec_client.symbol_to_cik.assert_not_called()

    def test_registered_symbol_fetches_latest_annual_filing_and_parses(self) -> None:
        sec_client = MagicMock()
        sec_client.symbol_to_cik.return_value = "0000874761"
        sec_client.get_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-K", "10-K"],
                    "accessionNumber": ["0000000000-26-000001", "0000874761-26-000063", "0000874761-25-000009"],
                }
            }
        }
        sec_client.get_filing_xml.return_value = _AES_XML

        result = fetch_custom_debt_longterm("AES", sec_client)

        assert result[2025] == 26_786_000_000.0
        sec_client.get_filing_xml.assert_called_once_with("0000874761", "0000874761-26-000063", "10-K")

    def test_sec_client_failure_returns_empty_not_raise(self) -> None:
        sec_client = MagicMock()
        sec_client.symbol_to_cik.side_effect = RuntimeError("network error")
        assert fetch_custom_debt_longterm("AES", sec_client) == {}
        assert fetch_custom_debt_shortterm("AES", sec_client) == {}


def test_custom_debt_longterm_shortterm_registries_are_well_formed() -> None:
    assert "AES" in CUSTOM_DEBT_LONGTERM_CONCEPTS
    assert "AES" in CUSTOM_DEBT_SHORTTERM_CONCEPTS
    assert "DE" in CUSTOM_DEBT_LONGTERM_CONCEPTS
    for symbol, concepts in CUSTOM_DEBT_LONGTERM_CONCEPTS.items():
        assert concepts, f"{symbol} has an empty concept list"
        for prefix, local_name in concepts:
            assert prefix and local_name
    for symbol, concepts in CUSTOM_DEBT_SHORTTERM_CONCEPTS.items():
        assert concepts, f"{symbol} has an empty concept list"
        for prefix, local_name in concepts:
            assert prefix and local_name


# Mirrors the real structure confirmed live 2026-09-03 against Deere & Company's actual
# filed FY2025 10-K raw XBRL instance document (accession 0001104659-25-122321,
# de-20251102x10k_htm.xml): a plain, non-dimensioned instant concept, duplicate-tagged
# (identical value appears twice under the same contextRef, same as AES) - both years'
# facts must be recovered and deduplicated correctly.
_DE_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:de="http://deere.com/20251102">
  <context id="c-2025">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000315189</identifier></entity>
    <period><instant>2025-11-02</instant></period>
  </context>
  <context id="c-2024">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000315189</identifier></entity>
    <period><instant>2024-10-27</instant></period>
  </context>
  <de:LongTermDebtAndFinanceLeasesNoncurrent contextRef="c-2025" unitRef="usd" decimals="-6">43544000000</de:LongTermDebtAndFinanceLeasesNoncurrent>
  <de:LongTermDebtAndFinanceLeasesNoncurrent contextRef="c-2025" unitRef="usd" decimals="-6">43544000000</de:LongTermDebtAndFinanceLeasesNoncurrent>
  <de:LongTermDebtAndFinanceLeasesNoncurrent contextRef="c-2024" unitRef="usd" decimals="-6">43229000000</de:LongTermDebtAndFinanceLeasesNoncurrent>
</xbrl>
"""


class TestExtractCustomDebtDeere:
    def test_de_recovers_both_years(self) -> None:
        result = extract_custom_debt_longterm_from_xbrl_xml(_DE_XML, "DE")
        assert result[2025] == 43_544_000_000.0
        assert result[2024] == 43_229_000_000.0

    def test_de_deduplicates_the_twice_tagged_2025_fact(self) -> None:
        # The 2025 fact appears twice under contextRef="c-2025" with the identical value -
        # must be counted once, not doubled to 87,088,000,000.
        result = extract_custom_debt_longterm_from_xbrl_xml(_DE_XML, "DE")
        assert result[2025] == 43_544_000_000.0


class TestFiscalYearForInstant:
    """FOUND 2026-09-03 (adding TXT to CUSTOM_DEBT_CONCEPTS): TXT's real fiscal year end
    lands in early January (52/53-week fiscal calendar) - see _fiscal_year_for_instant's
    own docstring for the live evidence this needed a dedicated fix, not a guessed
    threshold."""

    def test_early_january_instant_is_the_prior_calendar_year(self) -> None:
        assert _fiscal_year_for_instant(date(2026, 1, 3)) == 2025
        assert _fiscal_year_for_instant(date(2026, 1, 1)) == 2025
        assert _fiscal_year_for_instant(date(2026, 1, 10)) == 2025

    def test_normal_fiscal_year_end_is_unaffected(self) -> None:
        # AES (December), DE (early November), BRK (December) - all safely outside the
        # Jan 1-10 crossing window, must be a no-op.
        assert _fiscal_year_for_instant(date(2025, 12, 31)) == 2025
        assert _fiscal_year_for_instant(date(2025, 11, 2)) == 2025
        assert _fiscal_year_for_instant(date(2026, 1, 11)) == 2026


# Mirrors the real structure confirmed live 2026-09-03 against Textron Inc's actual filed
# FY2025 10-K raw XBRL instance document (accession 0000217346-26-000006,
# txt-20260103_htm.xml): same dimensioned-sum shape as Berkshire (single concept, two
# entity-segment members, sum them), PLUS a real period end in the Jan 1-10 crossing
# window (2026-01-03, Textron's own "fiscal 2025") - the Finance group fact is also
# duplicate-tagged, same as AES/DE.
_TXT_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:us-gaap="http://fasb.org/us-gaap/2025"
      xmlns:srt="http://fasb.org/srt/2025"
      xmlns:txt="http://textron.com/20260103">
  <context id="c-21">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000217346</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidatedEntitiesAxis">txt:ManufacturingGroupMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2026-01-03</instant></period>
  </context>
  <context id="c-22">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000217346</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidatedEntitiesAxis">txt:ManufacturingGroupMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2024-12-28</instant></period>
  </context>
  <context id="c-23">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000217346</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidatedEntitiesAxis">txt:FinanceGroupMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2026-01-03</instant></period>
  </context>
  <context id="c-24">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000217346</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidatedEntitiesAxis">txt:FinanceGroupMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><instant>2024-12-28</instant></period>
  </context>
  <us-gaap:LongTermDebt contextRef="c-21" unitRef="usd" decimals="-6">3539000000</us-gaap:LongTermDebt>
  <us-gaap:LongTermDebt contextRef="c-22" unitRef="usd" decimals="-6">3247000000</us-gaap:LongTermDebt>
  <us-gaap:LongTermDebt contextRef="c-23" unitRef="usd" decimals="-6">339000000</us-gaap:LongTermDebt>
  <us-gaap:LongTermDebt contextRef="c-23" unitRef="usd" decimals="-6">339000000</us-gaap:LongTermDebt>
  <us-gaap:LongTermDebt contextRef="c-24" unitRef="usd" decimals="-6">341000000</us-gaap:LongTermDebt>
</xbrl>
"""


class TestExtractCustomDebtTextron:
    def test_txt_sums_manufacturing_and_finance_group_with_jan_crossing_correction(self) -> None:
        result = _extract_dimensioned_sum_from_xbrl_xml(_TXT_XML, "TXT")
        # 3,539,000,000 (Manufacturing) + 339,000,000 (Finance), bucketed as fiscal 2025
        # despite the raw instant date being 2026-01-03 (Jan-crossing correction).
        assert result[2025] == 3_878_000_000.0
        assert result[2024] == 3_588_000_000.0
        assert 2026 not in result

    def test_txt_deduplicates_the_twice_tagged_finance_group_fact(self) -> None:
        result = _extract_dimensioned_sum_from_xbrl_xml(_TXT_XML, "TXT")
        assert result[2025] == 3_878_000_000.0

    def test_custom_debt_concepts_registry_includes_txt(self) -> None:
        assert "TXT" in CUSTOM_DEBT_CONCEPTS
        concept_local_name, member_local_names = CUSTOM_DEBT_CONCEPTS["TXT"]
        assert concept_local_name and member_local_names


# Mirrors the real structure confirmed live 2026-09-03 against New Jersey Resources'
# actual filed FY2025 10-K raw XBRL instance document (accession 0000356309-25-000093,
# fiscal year ends September 30): the standard PaymentsToAcquirePropertyPlantAndEquipment
# concept split across 3 PropertyPlantAndEquipmentByTypeAxis members, no consolidated
# total anywhere. Includes a 4th member (a hypothetical 2-dimension sub-breakdown fact)
# to verify the multi-dimension exclusion the same way TestExtractDimensionedSumFromXbrlXml
# does for Berkshire's instant-fact case.
_NJR_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:us-gaap="http://fasb.org/us-gaap/2025"
      xmlns:njr="http://njresources.com/20250930">
  <context id="c-utility-fy2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000356309</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:PropertyPlantAndEquipmentByTypeAxis">njr:UtilityPlantMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2024-10-01</startDate><endDate>2025-09-30</endDate></period>
  </context>
  <context id="c-solar-fy2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000356309</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:PropertyPlantAndEquipmentByTypeAxis">njr:SolarEquipmentMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2024-10-01</startDate><endDate>2025-09-30</endDate></period>
  </context>
  <context id="c-storage-fy2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000356309</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:PropertyPlantAndEquipmentByTypeAxis">njr:StorageAndTransportationAndOtherMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2024-10-01</startDate><endDate>2025-09-30</endDate></period>
  </context>
  <context id="c-utility-fy2024-only">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000356309</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:PropertyPlantAndEquipmentByTypeAxis">njr:UtilityPlantMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2023-10-01</startDate><endDate>2024-09-30</endDate></period>
  </context>
  <context id="c-multi-dimension-fy2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000356309</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:PropertyPlantAndEquipmentByTypeAxis">njr:UtilityPlantMember</xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">njr:NaturalGasDistributionMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2024-10-01</startDate><endDate>2025-09-30</endDate></period>
  </context>
  <us-gaap:PaymentsToAcquirePropertyPlantAndEquipment contextRef="c-utility-fy2025" unitRef="usd" decimals="-3">391906000</us-gaap:PaymentsToAcquirePropertyPlantAndEquipment>
  <us-gaap:PaymentsToAcquirePropertyPlantAndEquipment contextRef="c-solar-fy2025" unitRef="usd" decimals="-3">238185000</us-gaap:PaymentsToAcquirePropertyPlantAndEquipment>
  <us-gaap:PaymentsToAcquirePropertyPlantAndEquipment contextRef="c-storage-fy2025" unitRef="usd" decimals="-3">29957000</us-gaap:PaymentsToAcquirePropertyPlantAndEquipment>
  <us-gaap:PaymentsToAcquirePropertyPlantAndEquipment contextRef="c-utility-fy2024-only" unitRef="usd" decimals="-3">372019000</us-gaap:PaymentsToAcquirePropertyPlantAndEquipment>
  <us-gaap:PaymentsToAcquirePropertyPlantAndEquipment contextRef="c-multi-dimension-fy2025" unitRef="usd" decimals="-3">150000000</us-gaap:PaymentsToAcquirePropertyPlantAndEquipment>
</xbrl>
"""


class TestExtractDurationDimensionedSumFromXbrlXml:
    def test_njr_sums_all_three_registered_members(self) -> None:
        result = _extract_duration_dimensioned_sum_from_xbrl_xml(_NJR_XML, "NJR")
        # 391,906,000 (Utility) + 238,185,000 (Solar) + 29,957,000 (Storage/Other)
        assert result[2025] == 660_048_000.0

    def test_njr_2024_missing_two_members_is_not_returned(self) -> None:
        # The fixture only has a UtilityPlant fact for FY2024 (no Solar/Storage
        # comparative-year facts) - must NOT be returned as a silently understated total.
        result = _extract_duration_dimensioned_sum_from_xbrl_xml(_NJR_XML, "NJR")
        assert 2024 not in result

    def test_njr_excludes_multi_dimensioned_sub_breakdown_fact(self) -> None:
        result = _extract_duration_dimensioned_sum_from_xbrl_xml(_NJR_XML, "NJR")
        # The 150,000,000 fact carries 2 explicitMembers (type axis + a hypothetical
        # segment axis) - not a plain single-member type total, must be excluded.
        assert result[2025] == 660_048_000.0

    def test_unregistered_symbol_returns_empty_without_parsing(self) -> None:
        assert _extract_duration_dimensioned_sum_from_xbrl_xml(_NJR_XML, "SOME_OTHER_SYMBOL") == {}

    def test_custom_capex_dimensioned_concepts_registry_includes_njr(self) -> None:
        assert "NJR" in CUSTOM_CAPEX_DIMENSIONED_CONCEPTS
        concept_local_name, member_local_names = CUSTOM_CAPEX_DIMENSIONED_CONCEPTS["NJR"]
        assert concept_local_name and member_local_names


class TestFetchCustomCapexDimensionedSum:
    def test_unregistered_symbol_never_calls_sec_client(self) -> None:
        sec_client = MagicMock()
        result = fetch_custom_capex_dimensioned_sum("AAPL", sec_client)
        assert result == {}
        sec_client.symbol_to_cik.assert_not_called()


# Mirrors the real structure confirmed live 2026-09-03 against McEwen Inc's actual filed
# FY2025 10-K raw XBRL instance document (accession 0001104659-26-028705): a
# single-target-member registration, where the target member (OperatingSegmentsMember)
# appears BOTH alone (the filer's own pre-summed consolidated total, the one we want) and
# paired with a second, unregistered region member (a component of that total, which must
# be excluded since it carries 2 explicitMembers, not exactly 1).
_MUX_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:mux="http://mcewenmining.com/20251231">
  <context id="c-us-fy2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000314203</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">us-gaap:OperatingSegmentsMember</xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">mux:UnitedStatesReportableSegmentMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-canada-fy2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000314203</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">us-gaap:OperatingSegmentsMember</xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">mux:CanadaReportableSegmentMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-total-fy2025">
    <entity>
      <identifier scheme="http://www.sec.gov/CIK">0000314203</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">us-gaap:OperatingSegmentsMember</xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <mux:PaymentsToAcquirePropertyPlantAndEquipmentAndAcquireMiningAssets contextRef="c-us-fy2025" unitRef="usd" decimals="-3">11306000</mux:PaymentsToAcquirePropertyPlantAndEquipmentAndAcquireMiningAssets>
  <mux:PaymentsToAcquirePropertyPlantAndEquipmentAndAcquireMiningAssets contextRef="c-canada-fy2025" unitRef="usd" decimals="-3">36581000</mux:PaymentsToAcquirePropertyPlantAndEquipmentAndAcquireMiningAssets>
  <mux:PaymentsToAcquirePropertyPlantAndEquipmentAndAcquireMiningAssets contextRef="c-total-fy2025" unitRef="usd" decimals="-3">48087000</mux:PaymentsToAcquirePropertyPlantAndEquipmentAndAcquireMiningAssets>
</xbrl>
"""


class TestExtractDurationDimensionedSumSingleMemberSubtotal:
    def test_mux_picks_the_single_member_subtotal_not_the_regional_components(self) -> None:
        result = _extract_duration_dimensioned_sum_from_xbrl_xml(_MUX_XML, "MUX")
        # Must return the filer's own pre-summed total (c-total-fy2025's 48,087,000), NOT
        # the 2-dimension regional components (11,306,000 / 36,581,000, which sum to a
        # DIFFERENT, deliberately-distinct 47,887,000 in this fixture) - a bug that summed
        # the 2-dimension contexts instead of picking the single-dimension one would fail
        # this exact assertion.
        assert result[2025] == 48_087_000.0

    def test_custom_capex_dimensioned_concepts_registry_includes_mux(self) -> None:
        assert "MUX" in CUSTOM_CAPEX_DIMENSIONED_CONCEPTS
