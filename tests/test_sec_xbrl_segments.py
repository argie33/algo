#!/usr/bin/env python3
"""Tests for SEC XBRL segment disclosure parser."""

import pytest

from utils.external.sec_xbrl_segments import XBRLSegmentParser


class TestParseCompanyFacts:
    """parse_companyfacts() can only ever recover segment COUNT, never per-segment
    revenue - SEC's companyfacts API strips XBRL dimensional (segment) context from
    every fact it returns (confirmed against real SEC companyfacts responses: each
    fact is {val, fy, fp, accn, form, filed, frame, ...} with no segment/contextRef
    field at all). These fixtures mirror that real shape - no fabricated 'segment'
    key on facts.
    """

    def test_segment_count_found_still_reports_unavailable(self) -> None:
        facts_response = {
            "cik": "0000789019",
            "entityName": "Microsoft Corp",
            "facts": {
                "us-gaap": {
                    "NumberOfReportableSegments": {
                        "units": {
                            "Segment": [
                                {"val": 3, "fy": 2025, "fp": "FY", "accn": "0000950170-25-100235"},
                            ]
                        }
                    },
                }
            },
        }

        result = XBRLSegmentParser.parse_companyfacts(facts_response, "MSFT")

        assert result["segment_count"] == 3
        assert result["data_available"] is False
        assert result["reason"] == "companyfacts_api_never_exposes_per_segment_revenue"
        assert result["segments"] == []
        assert result["largest_segment_revenue_pct"] is None

    def test_no_segment_count_concept_present(self) -> None:
        facts_response = {
            "cik": "0000123456",
            "entityName": "Test Corp",
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [{"val": 100, "fy": 2023, "fp": "FY"}]}},
                }
            },
        }

        result = XBRLSegmentParser.parse_companyfacts(facts_response, "TEST")

        assert result["segment_count"] is None
        assert result["data_available"] is False
        assert result["reason"] == "no_segment_count_facts_in_companyfacts"

    def test_no_facts(self) -> None:
        facts_response = {"cik": "0000123456", "entityName": "Test Corp"}

        result = XBRLSegmentParser.parse_companyfacts(facts_response, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_us_gaap_facts"


class TestHerfindahlIndex:
    def test_compute_herfindahl_index(self) -> None:
        # Duopoly (50-50): HHI = 0.5^2 + 0.5^2 = 0.5 * 10000 = 5000
        hhi = XBRLSegmentParser._compute_herfindahl_index([50.0, 50.0], 100.0)
        assert hhi == pytest.approx(5000, 1)

        # Monopoly: HHI = 1^2 = 10000
        hhi = XBRLSegmentParser._compute_herfindahl_index([100.0], 100.0)
        assert hhi == pytest.approx(10000, 1)

        # Competitive (4-way): HHI = 4 * (0.25^2) = 2500
        hhi = XBRLSegmentParser._compute_herfindahl_index([25.0, 25.0, 25.0, 25.0], 100.0)
        assert hhi == pytest.approx(2500, 1)


def _context(ctx_id: str, axis_local: str, member_local: str, start: str, end: str) -> str:
    return f"""
    <context id="{ctx_id}">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000789019</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:{axis_local}">aapl:{member_local}</xbrldi:explicitMember>
            </segment>
        </entity>
        <period>
            <startDate>{start}</startDate>
            <endDate>{end}</endDate>
        </period>
    </context>
    """


def _multi_dim_context(ctx_id: str, dims: list[tuple[str, str]], start: str, end: str) -> str:
    members = "\n".join(
        f'<xbrldi:explicitMember dimension="us-gaap:{axis}">aapl:{member}</xbrldi:explicitMember>'
        for axis, member in dims
    )
    return f"""
    <context id="{ctx_id}">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000789019</identifier>
            <segment>
                {members}
            </segment>
        </entity>
        <period>
            <startDate>{start}</startDate>
            <endDate>{end}</endDate>
        </period>
    </context>
    """


def _instant_context(ctx_id: str, axis_local: str, member_local: str, instant: str) -> str:
    return f"""
    <context id="{ctx_id}">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000789019</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:{axis_local}">aapl:{member_local}</xbrldi:explicitMember>
            </segment>
        </entity>
        <period>
            <instant>{instant}</instant>
        </period>
    </context>
    """


class TestExtractSegmentRevenueFromXbrlXml:
    """extract_segment_revenue_from_xbrl_xml() reads the real XBRL dimensional
    model (context -> explicitMember -> segment axis/member), matching how SEC
    filers actually tag segment revenue - verified against a real filing
    (Microsoft's FY2025 10-K instance): this exact shape (three fiscal years of
    RevenueFromContractWithCustomerExcludingAssessedTax facts dimensioned on
    StatementBusinessSegmentsAxis) reproduced the company's real reported
    segment revenue exactly.
    """

    def _xml(self, contexts: str, facts: str) -> str:
        return f"""<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:us-gaap="http://xbrl.us/us-gaap/2023-01-31"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    {contexts}
    {facts}
</xbrl>
"""

    def test_picks_latest_fiscal_year_business_segments(self) -> None:
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2023-07-01", "2024-06-30")
            + _context("c2", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2024-07-01", "2025-06-30")
            + _context("c3", "StatementBusinessSegmentsAxis", "DevicesSegmentMember", "2023-07-01", "2024-06-30")
            + _context("c4", "StatementBusinessSegmentsAxis", "DevicesSegmentMember", "2024-07-01", "2025-06-30")
        )
        facts = """
        <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="c1">80000000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
        <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="c2">100000000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
        <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="c3">30000000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
        <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="c4">20000000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_type"] == "operating"
        assert result["segment_count"] == 2
        # Only the 2024-07-01..2025-06-30 period should be used (100M + 20M), not
        # the prior comparative year (80M + 30M) - proves stale-year facts don't
        # leak into the total.
        total = 100_000_000 + 20_000_000
        assert result["largest_segment_revenue_pct"] == pytest.approx(100_000_000 / total * 100, abs=0.01)
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"CloudSegmentMember": 100_000_000.0, "DevicesSegmentMember": 20_000_000.0}

    def test_falls_back_to_geographic_axis_when_no_business_segments(self) -> None:
        contexts = _context(
            "g1", "StatementGeographicalAxis", "UnitedStatesMember", "2024-01-01", "2024-12-31"
        ) + _context("g2", "StatementGeographicalAxis", "InternationalMember", "2024-01-01", "2024-12-31")
        facts = """
        <us-gaap:Revenues contextRef="g1">60000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="g2">40000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_type"] == "geographic"
        assert result["segment_count"] == 2

    def test_negative_eliminations_segment_excluded_from_concentration_math(self) -> None:
        """A "Corporate and Eliminations" reconciling line (negative revenue, tagged
        under the same axis so segment totals foot to the consolidated total) is not a
        real reportable operating segment. Pre-fix, including it in total_revenue could
        push the total below a real segment's own revenue, producing an impossible
        largest_segment_revenue_pct > 100%."""
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "WidgetsSegmentMember", "2024-01-01", "2024-12-31")
            + _context("c2", "StatementBusinessSegmentsAxis", "GadgetsSegmentMember", "2024-01-01", "2024-12-31")
            + _context(
                "c3", "StatementBusinessSegmentsAxis", "CorporateAndEliminationsMember", "2024-01-01", "2024-12-31"
            )
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">200000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">50000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c3">-60000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 2
        segment_ids = {s["segment_id"] for s in result["segments"]}
        assert "CorporateAndEliminationsMember" not in segment_ids
        assert result["largest_segment_revenue_pct"] <= 100.0
        total = 200_000_000 + 50_000_000
        assert result["largest_segment_revenue_pct"] == pytest.approx(200_000_000 / total * 100, abs=0.01)

    def test_no_segment_dimensioned_contexts(self) -> None:
        xml_content = """<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://xbrl.us/us-gaap/2023-01-31">
    <context id="c1">
        <entity><identifier scheme="http://www.sec.gov/CIK">0000789019</identifier></entity>
        <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
    </context>
    <us-gaap:Revenues contextRef="c1">100000000</us-gaap:Revenues>
</xbrl>
"""
        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_segment_dimension_contexts_in_xbrl_xml"

    def test_malformed_xml(self) -> None:
        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml("<not><valid", "TEST")

        assert result["data_available"] is False
        assert "xml_parse_error" in result["reason"]

    def test_operating_income_and_assets_populated_when_disclosed(self) -> None:
        """Real filer shape (verified live against Amazon's FY2025 10-K instance):
        OperatingIncomeLoss is a duration concept matching revenue's period exactly,
        Assets is an instant (balance-sheet) concept as of the period end date. A
        segment operating LOSS (negative value) must still be kept, not treated like
        a revenue elimination line."""
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "NorthAmericaSegmentMember", "2025-01-01", "2025-12-31")
            + _context("c2", "StatementBusinessSegmentsAxis", "InternationalSegmentMember", "2025-01-01", "2025-12-31")
            + _instant_context("c3", "StatementBusinessSegmentsAxis", "NorthAmericaSegmentMember", "2025-12-31")
            + _instant_context("c4", "StatementBusinessSegmentsAxis", "InternationalSegmentMember", "2025-12-31")
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">400000000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">150000000000</us-gaap:Revenues>
        <us-gaap:OperatingIncomeLoss contextRef="c1">29619000000</us-gaap:OperatingIncomeLoss>
        <us-gaap:OperatingIncomeLoss contextRef="c2">-2656000000</us-gaap:OperatingIncomeLoss>
        <us-gaap:Assets contextRef="c3">235652000000</us-gaap:Assets>
        <us-gaap:Assets contextRef="c4">81984000000</us-gaap:Assets>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        by_id = {s["segment_id"]: s for s in result["segments"]}
        assert by_id["NorthAmericaSegmentMember"]["operating_income"] == 29619000000.0
        assert by_id["NorthAmericaSegmentMember"]["assets"] == 235652000000.0
        # Legitimate operating loss - must not be dropped like a revenue elimination.
        assert by_id["InternationalSegmentMember"]["operating_income"] == -2656000000.0
        assert by_id["InternationalSegmentMember"]["assets"] == 81984000000.0

    def test_operating_income_and_assets_none_when_not_disclosed(self) -> None:
        """Real filer shape (verified live against MSFT/AAPL FY2025 10-K instances):
        many filers tag OperatingIncomeLoss per segment but never Assets - honest
        None, not a fabricated 0, distinguishes "not disclosed" from "disclosed as
        zero"."""
        contexts = _context(
            "c1", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-01-01", "2025-12-31"
        )
        facts = """<us-gaap:Revenues contextRef="c1">100000000</us-gaap:Revenues>"""
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        segment = result["segments"][0]
        assert segment["operating_income"] is None
        assert segment["assets"] is None

    def test_cross_tabbed_subsegment_context_not_summed_into_segment_total(self) -> None:
        """Real bug found live against JNJ's FY2025 10-K: Innovative Medicine revenue
        is tagged once for the segment total, then AGAIN broken out by geography
        (US/Non-US) and AGAIN by therapeutic sub-segment (Oncology, Immunology, ...),
        every one of those extra contexts still carrying
        StatementBusinessSegmentsAxis=InnovativeMedicineMember. Pre-fix, all of those
        finer-grained contexts collapsed onto the same member key as the plain segment
        total and got summed together, inflating revenue several times over (real
        finding: parser reported $421B for a segment whose real revenue was $60B)."""
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "MedsSegmentMember", "2025-01-01", "2025-12-31")
            + _multi_dim_context(
                "c2",
                [("StatementGeographicalAxis", "UnitedStatesMember"), ("StatementBusinessSegmentsAxis", "MedsSegmentMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c3",
                [("StatementBusinessSegmentsAxis", "MedsSegmentMember"), ("SubsegmentsAxis", "OncologyMember")],
                "2025-01-01",
                "2025-12-31",
            )
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">60000000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">35000000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c3">20000000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        # Only the plain single-dimension context (c1) should count - the
        # geography- and sub-segment-cross-tabbed breakdowns (c2, c3) must be
        # excluded, not summed in.
        assert revenues == {"MedsSegmentMember": 60_000_000_000.0}

    def test_consolidation_items_operating_segments_marker_still_counted(self) -> None:
        """Real filer shape (verified live against Coca-Cola's FY2025 10-K): segment
        revenue is ONLY ever tagged as (ConsolidationItemsAxis=OperatingSegmentsMember,
        StatementBusinessSegmentsAxis=<segment>), never as a plain single-dimension
        context - unlike JNJ's stray cross-tab breakdowns above, this companion
        dimension is a standard us-gaap marker for "this is a real reportable-segment
        figure" (as opposed to ConsolidationItemsAxis=MaterialReconcilingItemsMember,
        the corporate/eliminations line), not a further breakdown of the segment."""
        contexts = _multi_dim_context(
            "c1",
            [("ConsolidationItemsAxis", "OperatingSegmentsMember"), ("StatementBusinessSegmentsAxis", "NorthAmericaSegmentMember")],
            "2025-01-01",
            "2025-12-31",
        ) + _multi_dim_context(
            "c2",
            [("ConsolidationItemsAxis", "OperatingSegmentsMember"), ("StatementBusinessSegmentsAxis", "EuropeSegmentMember")],
            "2025-01-01",
            "2025-12-31",
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">19586000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">11513000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"NorthAmericaSegmentMember": 19_586_000_000.0, "EuropeSegmentMember": 11_513_000_000.0}

    def test_duplicate_context_same_segment_not_double_counted(self) -> None:
        """Real bug found live against JNJ's FY2025 10-K: the same segment's revenue
        is tagged via TWO different qualifying contexts for the same period - a plain
        single-axis context AND a ConsolidationItemsAxis=OperatingSegmentsMember-paired
        one - both carrying the identical value. Pre-fix, both contexts' facts were
        summed, exactly doubling every segment's revenue (real finding: $60.4B became
        $120.8B after fixing the cross-tab bug above, because this duplicate-tagging
        case was still being summed)."""
        contexts = _context(
            "c1", "StatementBusinessSegmentsAxis", "MedsSegmentMember", "2025-01-01", "2025-12-31"
        ) + _multi_dim_context(
            "c2",
            [("ConsolidationItemsAxis", "OperatingSegmentsMember"), ("StatementBusinessSegmentsAxis", "MedsSegmentMember")],
            "2025-01-01",
            "2025-12-31",
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">60000000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">60000000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"MedsSegmentMember": 60_000_000_000.0}

    def test_operating_income_from_wrong_duration_period_not_matched(self) -> None:
        """A quarterly OperatingIncomeLoss fact sharing the annual revenue fact's
        end date (e.g. Q4 ending on the same fiscal year-end) must not leak in next
        to an annual revenue total - they measure different-length periods."""
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-01-01", "2025-12-31")
            + _context("c2", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-10-01", "2025-12-31")
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">400000000</us-gaap:Revenues>
        <us-gaap:OperatingIncomeLoss contextRef="c2">50000000</us-gaap:OperatingIncomeLoss>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segments"][0]["operating_income"] is None

    def test_bank_holding_company_revenues_net_of_interest_expense(self) -> None:
        """Real filer shape (verified live against JPMorgan Chase's FY2025 10-K
        instance): banks don't tag plain Revenues/RevenueFromContractWithCustomer* at
        the per-segment level - they use RevenuesNetOfInterestExpense instead
        (NoninterestIncome + InterestIncomeExpenseNet, standard bank-holding-company
        income-statement framing). Pre-fix, this concept wasn't in
        _REVENUE_CONCEPT_LOCAL_NAMES at all, so JPM (and presumably other bank/
        financial filers) always reported data_unavailable despite having real,
        correctly-dimensioned segment revenue facts in the XML. Values below match
        JPM's real reported FY2025 segment revenue exactly: Consumer & Community
        Banking $76.029B, Commercial & Investment Bank $78.454B, Asset & Wealth
        Management $24.073B."""
        contexts = (
            _context(
                "c1", "StatementBusinessSegmentsAxis", "ConsumerCommunityBankingMember", "2025-01-01", "2025-12-31"
            )
            + _context(
                "c2", "StatementBusinessSegmentsAxis", "CommercialAndInvestmentBankMember", "2025-01-01", "2025-12-31"
            )
            + _context(
                "c3",
                "StatementBusinessSegmentsAxis",
                "AssetandWealthManagementSegmentMember",
                "2025-01-01",
                "2025-12-31",
            )
        )
        facts = """
        <us-gaap:RevenuesNetOfInterestExpense contextRef="c1">76029000000</us-gaap:RevenuesNetOfInterestExpense>
        <us-gaap:RevenuesNetOfInterestExpense contextRef="c2">78454000000</us-gaap:RevenuesNetOfInterestExpense>
        <us-gaap:RevenuesNetOfInterestExpense contextRef="c3">24073000000</us-gaap:RevenuesNetOfInterestExpense>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 3
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "ConsumerCommunityBankingMember": 76_029_000_000.0,
            "CommercialAndInvestmentBankMember": 78_454_000_000.0,
            "AssetandWealthManagementSegmentMember": 24_073_000_000.0,
        }

    def test_plain_revenues_still_preferred_over_bank_concept_when_both_present(self) -> None:
        """RevenuesNetOfInterestExpense is last in the preference order - a filer
        that tags the normal Revenues concept must not have it overridden by a
        stray/irrelevant RevenuesNetOfInterestExpense fact."""
        contexts = _context(
            "c1", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-01-01", "2025-12-31"
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">100000000</us-gaap:Revenues>
        <us-gaap:RevenuesNetOfInterestExpense contextRef="c1">999999999</us-gaap:RevenuesNetOfInterestExpense>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["segments"][0]["revenue"] == 100_000_000.0

    def test_custom_extension_concept_matched_by_local_name_regardless_of_namespace(self) -> None:
        """Real filer shape (verified live against Bank of America's FY2025 10-K
        instance): BAC tags segment revenue under a company-specific extension
        concept (bac:RevenuesNetOfInterestExpenseFullTaxEquivalentBasis, not the
        standard us-gaap:RevenuesNetOfInterestExpense JPMorgan uses) - pre-fix, this
        wasn't in _REVENUE_CONCEPT_LOCAL_NAMES, so BAC always reported
        data_unavailable despite real, correctly-dimensioned segment facts. Matching
        is by local name only (namespace-agnostic), so a custom bac: extension works
        the same as a standard us-gaap: concept. Values match BAC's real reported
        FY2025 segment revenue exactly: Consumer Banking $43.673B, GWIM $24.883B,
        Global Banking $24.108B, Global Markets $24.096B, Corporate/Eliminations
        -$3.054B (excluded by the existing negative-value filter) - summing to
        BAC's real $113.706B consolidated revenue."""
        contexts = (
            _multi_dim_context(
                "c1",
                [("ConsolidationItemsAxis", "OperatingSegmentsMember"), ("StatementBusinessSegmentsAxis", "ConsumerBankingSegmentMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [("ConsolidationItemsAxis", "OperatingSegmentsMember"), ("StatementBusinessSegmentsAxis", "GlobalWealthAndInvestmentManagementSegmentMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c3",
                [("ConsolidationItemsAxis", "CorporateReconcilingItemsAndEliminationsMember")],
                "2025-01-01",
                "2025-12-31",
            )
        )
        facts = """
        <bac:RevenuesNetOfInterestExpenseFullTaxEquivalentBasis contextRef="c1">43673000000</bac:RevenuesNetOfInterestExpenseFullTaxEquivalentBasis>
        <bac:RevenuesNetOfInterestExpenseFullTaxEquivalentBasis contextRef="c2">24883000000</bac:RevenuesNetOfInterestExpenseFullTaxEquivalentBasis>
        <bac:RevenuesNetOfInterestExpenseFullTaxEquivalentBasis contextRef="c3">-3054000000</bac:RevenuesNetOfInterestExpenseFullTaxEquivalentBasis>
        """
        xml_content = self._xml(contexts, facts).replace(
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"',
            '<xbrl xmlns:bac="http://www.bankofamerica.com/20251231" xmlns="http://www.xbrl.org/2003/instance"',
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "ConsumerBankingSegmentMember": 43_673_000_000.0,
            "GlobalWealthAndInvestmentManagementSegmentMember": 24_883_000_000.0,
        }

    def test_legal_entity_axis_stripped_when_matching_segment_member(self) -> None:
        """Real filer shape (verified live against NextEra Energy's FY2025 10-K
        instance): combined parent+subsidiary co-registrant filings tag the
        subsidiary's facts with dei:LegalEntityAxis IN ADDITION TO the segment axis
        - NEE's Florida Power & Light segment context carries both
        StatementBusinessSegmentsAxis=FloridaPowerLightCompanyMember AND
        LegalEntityAxis=FloridaPowerLightCompanyMember (identical member on both).
        Pre-fix, this looked like a 2-dimension (cross-tabbed) context and was
        excluded entirely, same failure shape as JNJ's real sub-breakdown case -
        except here the second dimension is entity identity, not a further
        breakdown, so it must be stripped rather than treated as disqualifying.
        Values match NEE's real reported FY2025 segment revenue: FPL $18.262B,
        NEER $8.760B."""
        contexts = _multi_dim_context(
            "c1",
            [
                ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("StatementBusinessSegmentsAxis", "FloridaPowerLightCompanyMember"),
                ("LegalEntityAxis", "FloridaPowerLightCompanyMember"),
            ],
            "2025-01-01",
            "2025-12-31",
        ) + _multi_dim_context(
            "c2",
            [("ConsolidationItemsAxis", "OperatingSegmentsMember"), ("StatementBusinessSegmentsAxis", "NEERSegmentMember")],
            "2025-01-01",
            "2025-12-31",
        )
        facts = """
        <us-gaap:RegulatedAndUnregulatedOperatingRevenue contextRef="c1">18262000000</us-gaap:RegulatedAndUnregulatedOperatingRevenue>
        <us-gaap:RegulatedAndUnregulatedOperatingRevenue contextRef="c2">8760000000</us-gaap:RegulatedAndUnregulatedOperatingRevenue>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "FloridaPowerLightCompanyMember": 18_262_000_000.0,
            "NEERSegmentMember": 8_760_000_000.0,
        }

    def test_legal_entity_axis_not_stripped_when_member_differs_from_segment(self) -> None:
        """Guard against over-stripping: a LegalEntityAxis dimension whose member
        does NOT match the segment axis member in the same context is a genuine
        further breakdown (e.g. a different co-registrant reporting within the same
        segment) and must still disqualify the context as a cross-tab, exactly like
        any other unrecognized second dimension."""
        contexts = _multi_dim_context(
            "c1",
            [
                ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("StatementBusinessSegmentsAxis", "FloridaPowerLightCompanyMember"),
                ("LegalEntityAxis", "SomeOtherSubsidiaryMember"),
            ],
            "2025-01-01",
            "2025-12-31",
        )
        facts = """
        <us-gaap:RegulatedAndUnregulatedOperatingRevenue contextRef="c1">18262000000</us-gaap:RegulatedAndUnregulatedOperatingRevenue>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False


def _plain_context(ctx_id: str, start: str, end: str) -> str:
    """A non-dimensioned context - the consolidated (not segment-level) figure."""
    return f"""
    <context id="{ctx_id}">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000034088</identifier>
        </entity>
        <period>
            <startDate>{start}</startDate>
            <endDate>{end}</endDate>
        </period>
    </context>
    """


class TestCrossTabSegmentRevenueFallback:
    """Real bug found live against Exxon Mobil's FY2023-2025 10-K instances (CIK
    34088): XOM tags EVERY segment revenue fact with an additional axis alongside
    the segment axis (geography, product type) - no plain single-dimension segment-
    total context exists anywhere in the filing for any revenue concept, so the
    primary extraction path (single-dimension-or-OperatingSegmentsMember-paired
    contexts only) always found zero facts and reported data_unavailable, even
    though real segment revenue is fully present in the XML.
    """

    def _xml(self, contexts: str, facts: str) -> str:
        return f"""<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:us-gaap="http://xbrl.us/us-gaap/2023-01-31"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    {contexts}
    {facts}
</xbrl>
"""

    def test_reconciled_cross_tab_sum_used_when_no_single_dimension_context(self) -> None:
        """Matches XOM's real shape: a structural single-dimension context exists
        (used only for an unrelated concept, e.g. an impairment footnote - keeps
        _index_segment_contexts non-empty so axis_to_use resolves), but every
        revenue fact is cross-tabbed with a geography axis. Summing revenue across
        both geography members per segment reproduces the plain consolidated
        revenue fact for the identical period, so the fallback must be trusted."""
        contexts = (
            _context("u1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _multi_dim_context(
                "c1",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "US")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "NonUsMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c3",
                [("StatementBusinessSegmentsAxis", "BetaMember"), ("StatementGeographicalAxis", "US")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c4",
                [("StatementBusinessSegmentsAxis", "BetaMember"), ("StatementGeographicalAxis", "NonUsMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _plain_context("anchor1", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:ImpairmentOfLongLivedAssetsHeldForUse contextRef="u1">1000000</us-gaap:ImpairmentOfLongLivedAssetsHeldForUse>
        <us-gaap:Revenues contextRef="c1">60000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">40000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c3">30000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c4">20000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="anchor1">150000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["reason"] is None
        assert result["segment_count"] == 2
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 100_000_000.0, "BetaMember": 50_000_000.0}

    def test_cross_tab_fallback_excludes_intersegment_elimination_from_sum(self) -> None:
        """The same shape as above, but each segment ALSO tags a large
        ConsolidationItemsAxis=IntersegmentEliminationMember-paired fact (confirmed
        live: XOM tags real "intersegment sales elimination" facts this way,
        alongside the same geography axis used for real revenue breakdown facts).
        This is a reconciling adjustment, not part of the segment's own reportable
        revenue - summing it in would corrupt the total and desync it from the
        consolidated anchor, so the reconciliation must reject any candidate that
        includes it and instead find the clean geography-only breakdown."""
        contexts = (
            _context("u1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _multi_dim_context(
                "c1",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "US")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "NonUsMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "e1",
                [
                    ("StatementBusinessSegmentsAxis", "AlphaMember"),
                    ("ConsolidationItemsAxis", "IntersegmentEliminationMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _plain_context("anchor1", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">60000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">40000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="e1">-999999999</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="anchor1">100000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 100_000_000.0}

    def test_cross_tab_fallback_picks_axis_combo_that_reconciles_over_one_that_doesnt(self) -> None:
        """A filer can tag more than one complete-looking breakdown of the same
        segment revenue (confirmed live: XOM ALSO tags a plain geography-only total
        that is NOT the real reportable total - gross of intersegment sales rather
        than net, overstating by ~36%). Picking the wrong one silently produces a
        plausible but wrong number - exactly the JNJ/KO double-counting bug class
        this parser already had to fix twice. The candidate whose grand total
        actually reconciles against the consolidated anchor must be preferred over
        one that doesn't, regardless of which was encountered first."""
        contexts = (
            _context("u1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            # Wrong combo: ProductAxis breakdown that does NOT sum to the real total.
            + _multi_dim_context(
                "w1",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("ProductOrServiceAxis", "GrossSalesMember")],
                "2025-01-01",
                "2025-12-31",
            )
            # Correct combo: geography breakdown that DOES sum to the real total.
            + _multi_dim_context(
                "c1",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "US")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "NonUsMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _plain_context("anchor1", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:Revenues contextRef="w1">999000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c1">60000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">40000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="anchor1">100000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 100_000_000.0}

    def test_cross_tab_fallback_fails_closed_when_no_candidate_reconciles(self) -> None:
        """If no candidate axis-combo's grand total is within tolerance of the
        consolidated anchor, this must report data_unavailable rather than guess -
        per GOVERNANCE's fail-fast principle, an honest "we don't know" beats a
        silently wrong number."""
        contexts = (
            _context("u1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _multi_dim_context(
                "c1",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "US")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [("StatementBusinessSegmentsAxis", "AlphaMember"), ("StatementGeographicalAxis", "NonUsMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _plain_context("anchor1", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">60000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">40000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="anchor1">999000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_segment_revenue_in_xbrl_xml"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
