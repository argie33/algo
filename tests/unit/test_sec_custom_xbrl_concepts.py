"""Tests for utils/external/sec_custom_xbrl_concepts.py - the explicit, hand-verified
fallback for capex tagged under a filer-specific custom XBRL extension taxonomy.

Fixture XML below mirrors the real structure confirmed live 2026-08-29 against DHT
Holdings' and Costamare's actual filed XBRL instance documents (accessions
0001140361-26-010407 and 0001140361-26-007868) - same context/fact shape, values kept
identical to the real filings for a meaningful regression test.
"""

from unittest.mock import MagicMock

from utils.external.sec_custom_xbrl_concepts import (
    CUSTOM_CAPEX_CONCEPTS,
    extract_custom_capex_from_xbrl_xml,
    fetch_custom_capex,
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


def test_custom_capex_concepts_registry_is_well_formed():
    """Every registered symbol must map to at least one (prefix, local_name) tuple - a
    guard against an accidental empty-list entry that would silently resolve to no data."""
    assert "DHT" in CUSTOM_CAPEX_CONCEPTS
    assert "CMRE" in CUSTOM_CAPEX_CONCEPTS
    for symbol, concepts in CUSTOM_CAPEX_CONCEPTS.items():
        assert concepts, f"{symbol} has an empty concept list"
        for prefix, local_name in concepts:
            assert prefix and local_name
