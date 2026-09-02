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
        contexts = _context("c1", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-01-01", "2025-12-31")
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
                [
                    ("StatementGeographicalAxis", "UnitedStatesMember"),
                    ("StatementBusinessSegmentsAxis", "MedsSegmentMember"),
                ],
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
            [
                ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("StatementBusinessSegmentsAxis", "NorthAmericaSegmentMember"),
            ],
            "2025-01-01",
            "2025-12-31",
        ) + _multi_dim_context(
            "c2",
            [
                ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("StatementBusinessSegmentsAxis", "EuropeSegmentMember"),
            ],
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
            [
                ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("StatementBusinessSegmentsAxis", "MedsSegmentMember"),
            ],
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
        contexts = _context(
            "c1", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-01-01", "2025-12-31"
        ) + _context("c2", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-10-01", "2025-12-31")
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
        contexts = _context("c1", "StatementBusinessSegmentsAxis", "CloudSegmentMember", "2025-01-01", "2025-12-31")
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
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "ConsumerBankingSegmentMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "GlobalWealthAndInvestmentManagementSegmentMember"),
                ],
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

    def test_ifrs_segments_axis_recognized_for_20f_filers(self) -> None:
        """Real filer shape (verified live against BP's FY2025 20-F instance, CIK
        313807): IFRS/20-F filers tag segment revenue under ifrs-full:SegmentsAxis
        paired with SegmentConsolidationItemsAxis=OperatingSegmentsMember - the IFRS
        taxonomy's equivalent of us-gaap's StatementBusinessSegmentsAxis /
        ConsolidationItemsAxis=OperatingSegmentsMember pairing. Pre-fix, neither axis
        was recognized, so every IFRS 20-F filer with real segment data (BP, Shell,
        Sony, Toyota, Rio Tinto, BHP, Sanofi, Novartis, and more - 15+ symbols
        confirmed live) fell through to no_segment_dimension_contexts_in_xbrl_xml
        despite having real, correctly-dimensioned segment facts. Values match BP's
        real reported FY2025 segment revenue exactly: Gas & Low Carbon Energy
        $38.501B, Oil Production & Operations $1.651B, Customers & Products
        $148.740B."""
        contexts = (
            _multi_dim_context(
                "c1",
                [
                    ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("SegmentsAxis", "GasLowCarbonEnergyMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [
                    ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("SegmentsAxis", "OilProductionOperationsMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c3",
                [
                    ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("SegmentsAxis", "CustomersProductsMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
        )
        facts = """
        <ifrs-full:RevenueAndOperatingIncome contextRef="c1">38501000000</ifrs-full:RevenueAndOperatingIncome>
        <ifrs-full:RevenueAndOperatingIncome contextRef="c2">1651000000</ifrs-full:RevenueAndOperatingIncome>
        <ifrs-full:RevenueAndOperatingIncome contextRef="c3">148740000000</ifrs-full:RevenueAndOperatingIncome>
        """
        xml_content = self._xml(contexts, facts).replace(
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"',
            '<xbrl xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" '
            'xmlns="http://www.xbrl.org/2003/instance"',
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_type"] == "operating"
        assert result["segment_count"] == 3
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "GasLowCarbonEnergyMember": 38_501_000_000.0,
            "OilProductionOperationsMember": 1_651_000_000.0,
            "CustomersProductsMember": 148_740_000_000.0,
        }

    def test_ifrs_single_segments_axis_context_without_consolidation_pairing(self) -> None:
        """Real filer shape (verified live against Sanofi's FY2025 20-F instance):
        a plain single-dimension SegmentsAxis context (no SegmentConsolidationItemsAxis
        companion) must also be recognized directly - not every IFRS filer
        necessarily pairs the two axes. Sanofi reports exactly one operating segment
        (BiopharmaSegmentMember) - its single SegmentsAxis-only context's
        RevenueFromSaleOfGoods value ($43.626B) matches its own plain consolidated
        total exactly, confirming this is real single-segment reporting, not a
        parsing artifact."""
        contexts = _context("c1", "SegmentsAxis", "BiopharmaSegmentMember", "2025-01-01", "2025-12-31")
        facts = """
        <ifrs-full:RevenueFromSaleOfGoods contextRef="c1">43626000000</ifrs-full:RevenueFromSaleOfGoods>
        """
        xml_content = self._xml(contexts, facts).replace(
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"',
            '<xbrl xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" '
            'xmlns="http://www.xbrl.org/2003/instance"',
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 1
        assert result["segments"][0]["revenue"] == 43_626_000_000.0

    def test_ifrs_scenario_axis_actual_currency_stripped_as_boilerplate(self) -> None:
        """Real filer shape (verified live against SAP SE's FY2025 20-F instance, CIK
        1000184, accession 0001104659-26-020058): every real segment-total context
        carries a THIRD dimension beyond SegmentsAxis+SegmentConsolidationItemsAxis -
        sap:IfrsScenarioAxis=ActualCurrencyMember - so pre-fix these 3-dimension
        contexts failed the single-non-boilerplate-dimension check and SAP fell
        through to no_segment_revenue_in_xbrl_xml despite having real segment data.
        A parallel ConstantCurrencyMember context (using prior-year FX rates for the
        same fact) is deliberately included here too and must NOT be picked up -
        only ActualCurrencyMember is boilerplate-stripped, so the 2-dimension-after-
        stripping ConstantCurrency contexts stay excluded, avoiding a wrong-basis
        duplicate. Values match SAP's own reported FY2025 segment revenue exactly:
        Applications, Technology & Support EUR32.847B, Core Services EUR3.953B,
        summing to SAP's real consolidated Total revenue EUR36.800B."""
        contexts = (
            _multi_dim_context(
                "c1",
                [
                    ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("SegmentsAxis", "ApplicationsTechnologyAndSupportMember"),
                    ("IfrsScenarioAxis", "ActualCurrencyMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [
                    ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("SegmentsAxis", "CoreServicesMember"),
                    ("IfrsScenarioAxis", "ActualCurrencyMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c3",
                [
                    ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("SegmentsAxis", "ApplicationsTechnologyAndSupportMember"),
                    ("IfrsScenarioAxis", "ConstantCurrencyMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
        )
        facts = """
        <ifrs-full:Revenue contextRef="c1">32847000000</ifrs-full:Revenue>
        <ifrs-full:Revenue contextRef="c2">3953000000</ifrs-full:Revenue>
        <ifrs-full:Revenue contextRef="c3">33500000000</ifrs-full:Revenue>
        """
        xml_content = self._xml(contexts, facts).replace(
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"',
            '<xbrl xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" '
            'xmlns="http://www.xbrl.org/2003/instance"',
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 2
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "ApplicationsTechnologyAndSupportMember": 32_847_000_000.0,
            "CoreServicesMember": 3_953_000_000.0,
        }
        assert sum(revenues.values()) == 36_800_000_000.0

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
            [
                ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("StatementBusinessSegmentsAxis", "NEERSegmentMember"),
            ],
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

    def test_reportable_segment_aggregation_subtotal_excluded_from_concentration_math(self) -> None:
        """Real filer shape (verified live against Caterpillar's FY2025 10-K instance):
        the ASU 2023-07 segment-reporting taxonomy's standard "subtotal before All
        Other" member (us-gaap:ReportableSegmentAggregationBeforeOtherOperatingSegmentMember)
        is tagged on the SAME StatementBusinessSegmentsAxis as real segments, with a
        value equal to the sum of the real segments it aggregates - pre-fix, this was
        counted as a peer 6th "segment", roughly doubling the true total and
        corrupting HHI/largest_segment_revenue_pct for every filer that discloses
        under the new taxonomy."""
        contexts = (
            _multi_dim_context(
                "c1",
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "ConstructionIndustriesMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "ResourceIndustriesMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c3",
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "ReportableSegmentAggregationBeforeOtherOperatingSegmentMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
        )
        facts = """
        <us-gaap:Revenues contextRef="c1">25060000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">12474000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c3">37534000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "ConstructionIndustriesMember": 25_060_000_000.0,
            "ResourceIndustriesMember": 12_474_000_000.0,
        }
        assert result["segment_count"] == 2

    def test_gross_boilerplate_paired_value_overridden_by_disagreeing_plain_value(self) -> None:
        """Real filer shape (verified live against Caterpillar's FY2025 10-K instance):
        Power & Energy's ConsolidationItemsAxis=OperatingSegmentsMember-paired context
        tags $32.201B (gross, including intersegment sales - reconciles exactly against
        CAT's own IntersegmentEliminationMember fact of -$5.058B) while its plain
        (no ConsolidationItemsAxis dimension at all) context tags $27.143B (net, the
        figure CAT actually discloses as segment revenue). Pre-fix, "keep the first
        value seen" made this a coin flip on document order - real live run picked the
        wrong (gross) value, overstating this segment's revenue by ~19%."""
        contexts = _multi_dim_context(
            "c1",
            [
                ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("StatementBusinessSegmentsAxis", "PowerEnergyMember"),
            ],
            "2025-01-01",
            "2025-12-31",
        ) + _context("c2", "StatementBusinessSegmentsAxis", "PowerEnergyMember", "2025-01-01", "2025-12-31")
        facts = """
        <us-gaap:Revenues contextRef="c1">32201000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">27143000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"PowerEnergyMember": 27_143_000_000.0}

    def test_insurer_premiums_earned_net_revenue_concept(self) -> None:
        """Real filer shape (verified live against AIG's FY2025 10-K instance):
        insurers tag segment-level revenue as net earned premiums
        (us-gaap:PremiumsEarnedNet), not Revenues - pre-fix, AIG always reported
        data_unavailable despite real, correctly-dimensioned segment facts. Values
        match AIG's real reported FY2025 segment revenue: North America $8.626B,
        International $8.580B, Global Personal Travel Insurance $6.472B (summing to
        within 0.3% of AIG's real $23.751B consolidated revenue, an unallocated-
        corporate residual, same shape as NEE's)."""
        contexts = (
            _multi_dim_context(
                "c1",
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "NorthAmericaOperatingSegmentMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "InternationalOperatingSegmentMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c3",
                [
                    ("ConsolidationItemsAxis", "OperatingSegmentsMember"),
                    ("StatementBusinessSegmentsAxis", "GlobalPersonalTravelInsuranceSegmentMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
        )
        facts = """
        <us-gaap:PremiumsEarnedNet contextRef="c1">8626000000</us-gaap:PremiumsEarnedNet>
        <us-gaap:PremiumsEarnedNet contextRef="c2">8580000000</us-gaap:PremiumsEarnedNet>
        <us-gaap:PremiumsEarnedNet contextRef="c3">6472000000</us-gaap:PremiumsEarnedNet>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "NorthAmericaOperatingSegmentMember": 8_626_000_000.0,
            "InternationalOperatingSegmentMember": 8_580_000_000.0,
            "GlobalPersonalTravelInsuranceSegmentMember": 6_472_000_000.0,
        }

    def test_ifrs_plain_revenue_concept_recognized(self) -> None:
        """Real filer shape (verified live against SHEL/RIO/DEO/UL's FY2025 20-F
        instances, same-day follow-up to the SegmentsAxis fix above): the
        SegmentsAxis-recognition fix let the parser find these filers' segment-
        dimensioned contexts, but none tagged segment revenue under
        RevenueAndOperatingIncome/RevenueFromSaleOfGoods above, so they still fell
        through to no_segment_revenue_in_xbrl_xml. Pulled each filer's actual filed
        XBRL segment-note report (not companyfacts): SHEL's "Segment information"
        R93.htm, RIO's "Financial performance by segment" R100.htm ("Segmental
        revenue"), DEO's "Segmental information" R56.htm ("Sales"), and UL's
        "Segment information" R68.htm ("Turnover") all tag plain "ifrs-full:Revenue"
        - the taxonomy's generic top-line concept. Values match RIO's real reported
        FY2025 segment revenue exactly: Iron Ore $28.4B, Copper $15.2B (illustrative
        two-segment split summing to RIO's real $57.638B FY2025 group revenue)."""
        contexts = _multi_dim_context(
            "c1",
            [
                ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("SegmentsAxis", "IronOreMember"),
            ],
            "2025-01-01",
            "2025-12-31",
        ) + _multi_dim_context(
            "c2",
            [
                ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("SegmentsAxis", "CopperMember"),
            ],
            "2025-01-01",
            "2025-12-31",
        )
        facts = """
        <ifrs-full:Revenue contextRef="c1">28400000000</ifrs-full:Revenue>
        <ifrs-full:Revenue contextRef="c2">15200000000</ifrs-full:Revenue>
        """
        xml_content = self._xml(contexts, facts).replace(
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"',
            '<xbrl xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" '
            'xmlns="http://www.xbrl.org/2003/instance"',
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 2
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "IronOreMember": 28_400_000_000.0,
            "CopperMember": 15_200_000_000.0,
        }

    def test_ifrs_revenue_from_contracts_with_customers_plural_recognized(self) -> None:
        """Real filer shape (verified live against TTE/TotalEnergies' FY2025 20-F
        instance): TTE's "Business segment information" R51.htm tags segment
        revenue ("Revenues from sales") under "ifrs-full:RevenueFromContractsWith
        Customers" - note plural "Contracts", a genuinely distinct IFRS concept
        from us-gaap's already-covered singular "RevenueFromContractWithCustomer
        ExcludingAssessedTax" above, not a duplicate/typo. Values match TTE's real
        reported FY2025 Exploration & Production segment revenue scale."""
        contexts = _multi_dim_context(
            "c1",
            [
                ("SegmentConsolidationItemsAxis", "OperatingSegmentsMember"),
                ("SegmentsAxis", "ExplorationProductionMember"),
            ],
            "2025-01-01",
            "2025-12-31",
        )
        facts = """
        <ifrs-full:RevenueFromContractsWithCustomers contextRef="c1">17300000000</ifrs-full:RevenueFromContractsWithCustomers>
        """
        xml_content = self._xml(contexts, facts).replace(
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"',
            '<xbrl xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" '
            'xmlns="http://www.xbrl.org/2003/instance"',
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 1
        assert result["segments"][0]["revenue"] == 17_300_000_000.0

    def test_us_gaap_revenue_concepts_still_win_over_generic_ifrs_revenue(self) -> None:
        """The new generic 'Revenue'/'RevenueFromContractsWithCustomers' fallbacks
        must stay lowest-priority (last-tried) per this list's "first match wins"
        convention - a filer with both a more specific concept (e.g. Revenues) AND
        a coincidental unrelated 'Revenue'-named fact on the same segment contexts
        must resolve via the specific concept, not the generic one."""
        contexts = _context("c1", "StatementBusinessSegmentsAxis", "WidgetsSegmentMember", "2025-01-01", "2025-12-31")
        facts = """
        <us-gaap:Revenues contextRef="c1">9000000000</us-gaap:Revenues>
        <ifrs-full:Revenue contextRef="c1">1000000000</ifrs-full:Revenue>
        """
        xml_content = self._xml(contexts, facts).replace(
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"',
            '<xbrl xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" '
            'xmlns="http://www.xbrl.org/2003/instance"',
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segments"][0]["revenue"] == 9_000_000_000.0


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

    def test_cross_tab_reconciles_against_same_concept_anchor_not_a_broader_total(self) -> None:
        """Real bug found live against Progressive's (PGR) FY2025 10-K: segment
        revenue is tagged as PremiumsEarnedNet, cross-tabbed with
        ProductOrServiceAxis=UnderwritingOperationsMember. PGR ALSO tags a plain
        (non-dimensioned) Revenues fact for TOTAL company revenue - which includes
        ~6.9% of net investment income/realized gains that are never segment-
        allocated - alongside its own plain PremiumsEarnedNet fact that the 3
        segments sum to exactly. Reconciling against "Revenues" (the wrong,
        broader anchor) fails tolerance and wrongly reports data_unavailable;
        reconciling against the SAME concept that produced the segment candidates
        (PremiumsEarnedNet) succeeds, because it's the correct like-for-like
        comparison."""
        contexts = (
            _context("u1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _multi_dim_context(
                "c1",
                [
                    ("StatementBusinessSegmentsAxis", "AlphaMember"),
                    ("ProductOrServiceAxis", "UnderwritingOperationsMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [
                    ("StatementBusinessSegmentsAxis", "BetaMember"),
                    ("ProductOrServiceAxis", "UnderwritingOperationsMember"),
                ],
                "2025-01-01",
                "2025-12-31",
            )
            + _plain_context("premium_anchor", "2025-01-01", "2025-12-31")
            + _plain_context("revenue_anchor", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:PremiumsEarnedNet contextRef="c1">70000000</us-gaap:PremiumsEarnedNet>
        <us-gaap:PremiumsEarnedNet contextRef="c2">10000000</us-gaap:PremiumsEarnedNet>
        <us-gaap:PremiumsEarnedNet contextRef="premium_anchor">80000000</us-gaap:PremiumsEarnedNet>
        <us-gaap:Revenues contextRef="revenue_anchor">86000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["reason"] is None
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 70_000_000.0, "BetaMember": 10_000_000.0}


class TestFilerSpecificIncomeSegmentAxis:
    """Real gap found live against BBVA's FY2025 20-F: BBVA tags NONE of the three
    standard segment axes anywhere in its instance document, but its real per-segment
    income ("Note 6 Main margins and profit by operating segments") is tagged under
    its own filer-specific `IncomeByOperatingSegmentAxis` extension, with a
    `GrossProfit`-labeled concept as its segment revenue equivalent - confirmed live:
    Spain EUR10.027B, Mexico EUR15.198B, Turkey EUR5.213B FY2025, exactly matching
    BBVA's own reported segment table. `GrossProfit` is deliberately NOT trusted under
    the three standard axes (too generic/risky - see `_AXIS_SPECIFIC_EXTRA_REVENUE_CONCEPTS`
    docstring) - only under this specific, unambiguously-named axis.
    """

    def _xml(self, contexts: str, facts: str) -> str:
        return f"""<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:us-gaap="http://xbrl.us/us-gaap/2023-01-31"
      xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    {contexts}
    {facts}
</xbrl>
"""

    def test_gross_profit_trusted_under_filer_specific_income_segment_axis(self) -> None:
        contexts = _context("c1", "IncomeByOperatingSegmentAxis", "ES", "2025-01-01", "2025-12-31") + _context(
            "c2", "IncomeByOperatingSegmentAxis", "MX", "2025-01-01", "2025-12-31"
        )
        facts = """
        <ifrs-full:GrossProfit contextRef="c1">10027000000</ifrs-full:GrossProfit>
        <ifrs-full:GrossProfit contextRef="c2">15198000000</ifrs-full:GrossProfit>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 2
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"ES": 10_027_000_000.0, "MX": 15_198_000_000.0}

    def test_gross_profit_not_trusted_under_a_standard_axis(self) -> None:
        """The same risky concept must NOT be picked up under a standard axis - only
        the narrow, unambiguously-named filer-specific axis grants it trust. A filer
        tagging genuine COGS-based GrossProfit under StatementBusinessSegmentsAxis
        (a real, plausible scenario for a retailer/manufacturer) must NOT have it
        mistaken for segment revenue."""
        contexts = _context("c1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
        facts = """
        <us-gaap:GrossProfit contextRef="c1">5000000</us-gaap:GrossProfit>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_segment_revenue_in_xbrl_xml"


class TestCrossTabGrossProfitFallback:
    """GrossProfit is also tried by the cross-tab fallback (_extract_cross_tab_segment_revenue),
    a SEPARATE mechanism from TestFilerSpecificIncomeSegmentAxis above - safe here because
    every cross-tab candidate is reconciled against the filer's own plain consolidated total
    before being trusted, regardless of axis name. Real-world validation against Santander's
    FY2025 20-F: Santander cross-tabs a `GrossProfit`-labeled concept under the standard
    SegmentsAxis, but paired with SegmentItemsAxis=UnderlyingProfitItemsMember - that combination
    turns out to be a segment PROFIT reconciliation table (real total ~EUR62.4B), not the
    EUR58.4B "Total income" (revenue-equivalent) table - reconciliation against the real plain
    consolidated GrossProfit (EUR58.67B) correctly FAILS (off by ~6.3%, outside the 3% tolerance)
    and Santander correctly stays data_unavailable. These tests use synthetic data to verify
    both directions of that same reconciliation discipline.
    """

    def _xml(self, contexts: str, facts: str) -> str:
        return f"""<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:us-gaap="http://xbrl.us/us-gaap/2023-01-31"
      xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    {contexts}
    {facts}
</xbrl>
"""

    def test_cross_tab_gross_profit_used_when_it_reconciles(self) -> None:
        contexts = (
            _context("u1", "SegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _multi_dim_context(
                "c1",
                [("SegmentsAxis", "AlphaMember"), ("SegmentItemsAxis", "SomeBreakdownMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [("SegmentsAxis", "BetaMember"), ("SegmentItemsAxis", "SomeBreakdownMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _plain_context("anchor1", "2025-01-01", "2025-12-31")
        )
        facts = """
        <ifrs-full:GrossProfit contextRef="c1">60000000</ifrs-full:GrossProfit>
        <ifrs-full:GrossProfit contextRef="c2">40000000</ifrs-full:GrossProfit>
        <ifrs-full:GrossProfit contextRef="anchor1">100000000</ifrs-full:GrossProfit>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 60_000_000.0, "BetaMember": 40_000_000.0}

    def test_cross_tab_gross_profit_rejected_when_it_does_not_reconcile(self) -> None:
        """Mirrors the real Santander case: a cross-tabbed GrossProfit-labeled figure
        that represents something OTHER than segment revenue (e.g. a profit measure)
        fails reconciliation against the real consolidated GrossProfit and must be
        rejected, not silently reported as segment revenue."""
        contexts = (
            _context("u1", "SegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _multi_dim_context(
                "c1",
                [("SegmentsAxis", "AlphaMember"), ("SegmentItemsAxis", "UnderlyingProfitItemsMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _multi_dim_context(
                "c2",
                [("SegmentsAxis", "BetaMember"), ("SegmentItemsAxis", "UnderlyingProfitItemsMember")],
                "2025-01-01",
                "2025-12-31",
            )
            + _plain_context("anchor1", "2025-01-01", "2025-12-31")
        )
        facts = """
        <ifrs-full:GrossProfit contextRef="c1">37000000</ifrs-full:GrossProfit>
        <ifrs-full:GrossProfit contextRef="c2">25000000</ifrs-full:GrossProfit>
        <ifrs-full:GrossProfit contextRef="anchor1">58000000</ifrs-full:GrossProfit>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_segment_revenue_in_xbrl_xml"


class TestMultiAxisFallbackWhenFirstPriorityAxisHasNoRevenue:
    """Real gap found live against Bank of Montreal's FY2025 40-F: BOTH
    StatementBusinessSegmentsAxis AND SegmentsAxis are present in the same filing,
    but StatementBusinessSegmentsAxis (higher priority) is used ONLY for a
    Goodwill-by-segment footnote covering 2 of BMO's 5 real segments - the REAL,
    complete revenue breakdown (Canadian P&C $12.262B, US Banking $11.483B, Wealth
    Management $5.302B, Capital Markets $7.447B, Corporate Services -$220M FY2025)
    is tagged under the co-existing SegmentsAxis instead. The prior single-axis-
    then-give-up logic picked StatementBusinessSegmentsAxis, found zero revenue
    facts there, and reported data_unavailable without ever looking at SegmentsAxis
    - even though real, complete segment revenue was sitting right there under a
    different recognized axis in the same instance.
    """

    def _xml(self, contexts: str, facts: str) -> str:
        return f"""<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:us-gaap="http://xbrl.us/us-gaap/2023-01-31"
      xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    {contexts}
    {facts}
</xbrl>
"""

    def test_falls_through_to_second_axis_when_first_has_no_revenue(self) -> None:
        contexts = (
            # StatementBusinessSegmentsAxis: real axis, but only used for an
            # unrelated Goodwill footnote covering a partial subset of segments.
            _context("goodwill1", "StatementBusinessSegmentsAxis", "WealthManagementMember", "2025-01-01", "2025-12-31")
            + _context("goodwill2", "StatementBusinessSegmentsAxis", "CapitalMarketsMember", "2025-01-01", "2025-12-31")
            # SegmentsAxis: the REAL, complete revenue breakdown.
            + _context("r1", "SegmentsAxis", "CanadianBankingMember", "2025-01-01", "2025-12-31")
            + _context("r2", "SegmentsAxis", "UnitedStatesBankingMember", "2025-01-01", "2025-12-31")
            + _context("r3", "SegmentsAxis", "WealthManagementMember", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:Goodwill contextRef="goodwill1">500000000</us-gaap:Goodwill>
        <us-gaap:Goodwill contextRef="goodwill2">300000000</us-gaap:Goodwill>
        <us-gaap:Revenue contextRef="r1">60000000</us-gaap:Revenue>
        <us-gaap:Revenue contextRef="r2">40000000</us-gaap:Revenue>
        <us-gaap:Revenue contextRef="r3">20000000</us-gaap:Revenue>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["reason"] is None
        assert result["segment_count"] == 3
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {
            "CanadianBankingMember": 60_000_000.0,
            "UnitedStatesBankingMember": 40_000_000.0,
            "WealthManagementMember": 20_000_000.0,
        }

    def test_first_priority_axis_still_wins_when_it_has_real_revenue(self) -> None:
        """The overwhelmingly common case (a filer's real revenue IS under its
        first-priority axis) must resolve exactly as before - this fix only
        changes behavior when the first axis has zero revenue candidates."""
        contexts = _context(
            "c1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31"
        ) + _context("c2", "SegmentsAxis", "ShouldNotBeUsedMember", "2025-01-01", "2025-12-31")
        facts = """
        <us-gaap:Revenues contextRef="c1">100000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">999000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 100_000_000.0}


class TestComponentSumSegmentRevenueFallback:
    """Real gap found live against BOK Financial's, Ameris Bancorp's, and Arbor
    Realty Trust's FY2025 10-K instances - three genuinely different sub-industries
    (super-regional bank, community bank, mortgage REIT) all tag segment-level
    revenue as two SEPARATE standard us-gaap concepts (InterestIncomeExpenseNet +
    NoninterestIncome) rather than any single combined revenue-shaped concept -
    neither the primary single-concept path nor the cross-tab fallback (which only
    ever sums candidates for ONE concept at a time) can find this. Ameris Bancorp
    and Arbor Realty Trust both reconcile to within 0.01% of their real consolidated
    totals once summed; BOK Financial's real segment total is genuinely ~9.5% short
    (a "Corporate allocations" reconciling adjustment it doesn't tag as its own
    addable segment member) and correctly stays data_unavailable rather than
    reporting an incomplete total.
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

    def test_component_sum_used_when_only_two_separate_concepts_tagged(self) -> None:
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _context("c2", "StatementBusinessSegmentsAxis", "BetaMember", "2025-01-01", "2025-12-31")
            + _plain_context("anchor_nii", "2025-01-01", "2025-12-31")
            + _plain_context("anchor_noninterest", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:InterestIncomeExpenseNet contextRef="c1">60000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="c1">10000000</us-gaap:NoninterestIncome>
        <us-gaap:InterestIncomeExpenseNet contextRef="c2">40000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="c2">5000000</us-gaap:NoninterestIncome>
        <us-gaap:InterestIncomeExpenseNet contextRef="anchor_nii">100000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="anchor_noninterest">15000000</us-gaap:NoninterestIncome>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["reason"] is None
        assert result["segment_count"] == 2
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 70_000_000.0, "BetaMember": 45_000_000.0}

    def test_component_sum_treats_missing_secondary_concept_as_zero(self) -> None:
        """A segment can legitimately have no noninterest income at all - it must
        still be counted (at its NII value alone), not excluded outright the way a
        negative "Corporate and Eliminations" line is."""
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _context("c2", "StatementBusinessSegmentsAxis", "BetaMember", "2025-01-01", "2025-12-31")
            + _plain_context("anchor_nii", "2025-01-01", "2025-12-31")
            + _plain_context("anchor_noninterest", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:InterestIncomeExpenseNet contextRef="c1">60000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="c1">10000000</us-gaap:NoninterestIncome>
        <us-gaap:InterestIncomeExpenseNet contextRef="c2">30000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:InterestIncomeExpenseNet contextRef="anchor_nii">90000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="anchor_noninterest">10000000</us-gaap:NoninterestIncome>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 70_000_000.0, "BetaMember": 30_000_000.0}

    def test_component_sum_fails_closed_when_reconciliation_off(self) -> None:
        """Same shape as BOK Financial's real gap: the two components are tagged per
        segment, but the segment total is genuinely far short of the consolidated
        total (an unallocated corporate/reconciling piece not captured as its own
        segment member) - must stay honestly unavailable, not report a partial sum."""
        contexts = (
            _context("c1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31")
            + _context("c2", "StatementBusinessSegmentsAxis", "BetaMember", "2025-01-01", "2025-12-31")
            + _plain_context("anchor_nii", "2025-01-01", "2025-12-31")
            + _plain_context("anchor_noninterest", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:InterestIncomeExpenseNet contextRef="c1">60000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="c1">10000000</us-gaap:NoninterestIncome>
        <us-gaap:InterestIncomeExpenseNet contextRef="c2">30000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="c2">5000000</us-gaap:NoninterestIncome>
        <us-gaap:InterestIncomeExpenseNet contextRef="anchor_nii">200000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="anchor_noninterest">50000000</us-gaap:NoninterestIncome>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_segment_revenue_in_xbrl_xml"

    def test_component_sum_not_reached_when_primary_concept_already_matches(self) -> None:
        """If a filer tags a normal single revenue concept AND (redundantly, or for
        some unrelated cost-allocation footnote) also tags InterestIncomeExpenseNet/
        NoninterestIncome under the same axis, the primary path's match must win -
        the component-sum fallback is only reached when the primary scan finds
        nothing at all."""
        contexts = _context(
            "c1", "StatementBusinessSegmentsAxis", "AlphaMember", "2025-01-01", "2025-12-31"
        ) + _context("c2", "StatementBusinessSegmentsAxis", "BetaMember", "2025-01-01", "2025-12-31")
        facts = """
        <us-gaap:Revenues contextRef="c1">60000000</us-gaap:Revenues>
        <us-gaap:Revenues contextRef="c2">40000000</us-gaap:Revenues>
        <us-gaap:InterestIncomeExpenseNet contextRef="c1">999000000</us-gaap:InterestIncomeExpenseNet>
        <us-gaap:NoninterestIncome contextRef="c1">999000000</us-gaap:NoninterestIncome>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        revenues = {s["segment_id"]: s["revenue"] for s in result["segments"]}
        assert revenues == {"AlphaMember": 60_000_000.0, "BetaMember": 40_000_000.0}


class TestSingleReportableSegmentFallback:
    """Real gap found live: Gilead Sciences, Regeneron, United Airlines Holdings,
    and Realty Income all disclose exactly one reportable segment via the
    ASU 2023-07-mandated NumberOfReportableSegments/NumberOfOperatingSegments=1
    tag, but never (or only partially, for non-revenue line items) tag revenue
    under the segment axis at all - a single segment's revenue is trivially the
    consolidated total, so filers routinely skip re-tagging it. Both the primary
    and cross-tab paths correctly find nothing; this fallback uses the filer's
    own disclosed count + consolidated revenue instead of reporting
    data_unavailable for a real, common, non-buggy filing shape.
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

    def test_no_segment_axis_at_all_falls_back_to_consolidated_revenue(self) -> None:
        """Matches GILD/REGN/UAL's real shape: zero segment-dimensioned contexts
        anywhere in the filing (context_segment is empty), but a plain
        NumberOfReportableSegments=1 fact and a plain consolidated revenue fact
        both exist."""
        contexts = _plain_context("count1", "2025-01-01", "2025-12-31") + _plain_context(
            "rev1", "2025-01-01", "2025-12-31"
        )
        facts = """
        <us-gaap:NumberOfReportableSegments contextRef="count1">1</us-gaap:NumberOfReportableSegments>
        <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="rev1">29000000000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["reason"] is None
        assert result["segment_count"] == 1
        assert result["largest_segment_revenue_pct"] == 100.0
        assert result["revenue_concentration_hhi"] == 10000.0
        assert result["segments"][0]["revenue"] == 29_000_000_000.0

    def test_segment_axis_present_only_for_non_revenue_facts_falls_back(self) -> None:
        """Matches Realty Income's (O) real shape: a single-dimension segment
        context DOES exist (keeping context_segment non-empty and axis_to_use
        resolvable), but it's only ever used for expense-line facts, never
        revenue - so the primary path's candidate_facts search comes up empty
        and the cross-tab fallback also finds nothing to reconcile. Falls back
        to the disclosed segment count + consolidated revenue, using the real
        segment member name it found for other facts."""
        contexts = (
            _context("u1", "StatementBusinessSegmentsAxis", "ReportableSegmentMember", "2025-01-01", "2025-12-31")
            + _plain_context("count1", "2025-01-01", "2025-12-31")
            + _plain_context("rev1", "2025-01-01", "2025-12-31")
        )
        facts = """
        <us-gaap:GeneralAndAdministrativeExpense contextRef="u1">171000000</us-gaap:GeneralAndAdministrativeExpense>
        <us-gaap:NumberOfReportableSegments contextRef="count1">1</us-gaap:NumberOfReportableSegments>
        <us-gaap:Revenues contextRef="rev1">5749000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is True
        assert result["segment_count"] == 1
        assert result["segments"][0]["segment_id"] == "ReportableSegmentMember"
        assert result["segments"][0]["revenue"] == 5_749_000_000.0

    def test_multi_segment_count_does_not_trigger_fallback(self) -> None:
        """If the count concept says >1, this must NOT fabricate a single-segment
        result even when per-segment revenue extraction otherwise fails - that
        would be a real multi-segment gap, not this fallback's case to handle.
        Stays honest with data_unavailable."""
        contexts = _plain_context("count1", "2025-01-01", "2025-12-31") + _plain_context(
            "rev1", "2025-01-01", "2025-12-31"
        )
        facts = """
        <us-gaap:NumberOfReportableSegments contextRef="count1">3</us-gaap:NumberOfReportableSegments>
        <us-gaap:Revenues contextRef="rev1">29000000000</us-gaap:Revenues>
        """
        xml_content = self._xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_segment_dimension_contexts_in_xbrl_xml"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
