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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
