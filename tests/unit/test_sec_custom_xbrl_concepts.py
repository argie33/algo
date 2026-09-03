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
    CUSTOM_DEBT_CONCEPTS,
    CUSTOM_REVENUE_CONCEPTS,
    _extract_dimensioned_sum_from_xbrl_xml,
    extract_custom_capex_from_xbrl_xml,
    extract_custom_revenue_from_xbrl_xml,
    fetch_custom_capex,
    fetch_custom_debt,
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
