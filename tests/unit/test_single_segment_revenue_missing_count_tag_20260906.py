"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep):
_extract_single_segment_revenue required an explicit plain NumberOfReportableSegments/
NumberOfOperatingSegments=1 tag before ever attempting to find a consolidated revenue fact -
but this function is only called (see XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml)
after the caller has already confirmed ZERO segment-axis-dimensioned contexts exist anywhere in
the filing, which alone is sufficient evidence of a single reportable segment (a real
multi-segment filer must tag some dimensional fact for its ASC 280 segment footnote). Many
filers never tag the redundant count concept at all despite genuinely having one segment -
live-confirmed via SEC's own companyconcept API: Abeona Therapeutics (CIK 0000318306) tags
NumberOfReportableSegments=1 in its 10-Qs but NOT in its FY2025 10-K (the annual filing this
loader actually processes), despite that same 10-K having real, positive revenue ($5.82M) and
zero segment-dimensioned contexts anywhere - was falling through to the generic
"no_segment_dimension_contexts_in_xbrl_xml" ("Missing SEC/XBRL data") instead of correctly
extracting its trivial single-segment revenue.
"""

import xml.etree.ElementTree as ET

# Must import the "entry point" module first - sec_xbrl_segment_revenue_2 is imported BY
# sec_xbrl_segments (near the bottom of that file, after everything these fallbacks need is
# already defined), so importing sec_xbrl_segment_revenue_2 directly first would trigger a
# circular partial-init failure the same way a fresh interpreter session hitting this module
# via any other entry point never does.
import utils.external.sec_xbrl_segments
from utils.external.sec_xbrl_segment_revenue_2 import _extract_single_segment_revenue

_NS = 'xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:xbrli="http://www.xbrl.org/2003/instance"'


def _xbrl(body: str) -> ET.Element:
    return ET.fromstring(f"<xbrl {_NS}>{body}</xbrl>")


class TestSingleSegmentRevenueMissingCountTag:
    def test_no_count_tag_still_extracts_revenue_when_no_dimensional_contexts(self) -> None:
        # ABEO-shaped: real consolidated revenue, no NumberOfReportableSegments tag anywhere,
        # no dimensional (explicitMember) contexts at all.
        root = _xbrl(
            """
            <xbrli:context id="FY2025">
                <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
            </xbrli:context>
            <us-gaap:Revenues contextRef="FY2025">5820000</us-gaap:Revenues>
            """
        )

        result = _extract_single_segment_revenue(root, "ABEO")

        assert result is not None
        concept, revenue, end_date, duration_days = result
        assert concept == "Revenues"
        assert revenue == 5_820_000.0
        assert end_date == "2025-12-31"
        assert duration_days == 364

    def test_explicit_count_of_one_still_works(self) -> None:
        # Pre-existing behavior must be unchanged when the count tag IS present and says 1.
        root = _xbrl(
            """
            <xbrli:context id="FY2025">
                <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
            </xbrli:context>
            <us-gaap:NumberOfReportableSegments contextRef="FY2025">1</us-gaap:NumberOfReportableSegments>
            <us-gaap:Revenues contextRef="FY2025">5820000</us-gaap:Revenues>
            """
        )

        result = _extract_single_segment_revenue(root, "ACET")

        assert result is not None
        assert result[1] == 5_820_000.0

    def test_explicit_count_greater_than_one_still_returns_none(self) -> None:
        # Must NOT guess through a genuine multi-segment signal even with zero dimensional
        # contexts captured by this minimal fixture - a real count tag saying >1 stays
        # authoritative.
        root = _xbrl(
            """
            <xbrli:context id="FY2025">
                <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
            </xbrli:context>
            <us-gaap:NumberOfReportableSegments contextRef="FY2025">3</us-gaap:NumberOfReportableSegments>
            <us-gaap:Revenues contextRef="FY2025">5820000</us-gaap:Revenues>
            """
        )

        result = _extract_single_segment_revenue(root, "MULTISEG")

        assert result is None

    def test_no_count_tag_and_no_revenue_concept_still_returns_none(self) -> None:
        root = _xbrl(
            """
            <xbrli:context id="FY2025">
                <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
            </xbrli:context>
            """
        )

        result = _extract_single_segment_revenue(root, "NOREV")

        assert result is None

    def test_no_count_tag_picks_latest_period_among_multiple_revenue_facts(self) -> None:
        # Two fiscal years of plain (non-dimensioned) Revenues facts, no count tag at all -
        # must pick the latest period, not an arbitrary one.
        root = _xbrl(
            """
            <xbrli:context id="FY2024">
                <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period>
            </xbrli:context>
            <xbrli:context id="FY2025">
                <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
            </xbrli:context>
            <us-gaap:Revenues contextRef="FY2024">4246000</us-gaap:Revenues>
            <us-gaap:Revenues contextRef="FY2025">5820000</us-gaap:Revenues>
            """
        )

        result = _extract_single_segment_revenue(root, "ABEO")

        assert result is not None
        assert result[1] == 5_820_000.0
        assert result[2] == "2025-12-31"
