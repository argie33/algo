"""Regression test (2026-09-06, same-day follow-up to commit 7108922a4): that commit
relaxed `_extract_single_segment_revenue` to no longer require an explicit
NumberOfReportableSegments/NumberOfOperatingSegments=1 tag before extracting a plain
consolidated revenue fact - correct for its intended call site (zero segment-dimensioned
contexts anywhere in the filing, e.g. Abeona Therapeutics).

But `XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml` has a SECOND call site for
this same function, reached when real segment-axis-dimensioned contexts DO exist but none
of the cross-tab/component-sum/alt-asset-manager/Ares-style reconciliation strategies
matched them to a consolidated anchor. At that call site the relaxed rule is wrong: the
filer is proven NOT single-segment, so grabbing an arbitrary plain (non-dimensioned) revenue
fact - typically the whole-company consolidated total tagged for an unrelated purpose - and
mislabeling it as if it were one specific segment's revenue is a confidently-wrong number,
violating this codebase's "an honest data_unavailable beats a silently wrong number"
governance principle. Live-caught via
tests/test_sec_xbrl_segments.py::TestCrossTabSegmentRevenueFallback::
test_cross_tab_fallback_fails_closed_when_no_candidate_reconciles going from PASS (before
7108922a4) to FAIL (after it) - the exact fixture returned segment "AlphaMember" with
revenue=$999,000,000 (the anchor's own value), when the real segment components (c1=$60M,
c2=$40M) don't reconcile against it at all.

Fix: `_extract_single_segment_revenue` grew a `require_explicit_count_tag` keyword,
`False` by default (preserving the new relaxed behavior for the legitimate zero-context
call site) but passed `True` from the deeper fallback-chain call site in
`extract_segment_revenue_from_xbrl_xml`, restoring the original strict requirement there.
"""

# Must import the "entry point" module first - sec_xbrl_segment_revenue_2 is imported BY
# sec_xbrl_segments (near the bottom of that file), so importing sec_xbrl_segment_revenue_2
# directly first triggers a circular partial-init failure (see
# test_single_segment_revenue_missing_count_tag_20260906.py's identical comment).
import utils.external.sec_xbrl_segments
from tests.test_sec_xbrl_segments import TestCrossTabSegmentRevenueFallback as _XmlHelperSource
from tests.test_sec_xbrl_segments import _context, _multi_dim_context, _plain_context
from utils.external.sec_xbrl_segment_revenue_2 import _extract_single_segment_revenue
from utils.external.sec_xbrl_segments import XBRLSegmentParser

_xml = _XmlHelperSource()._xml


class TestRequireExplicitCountTagKeyword:
    def test_no_count_tag_returns_none_when_required(self) -> None:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(
            _xml(
                """<context id="c1"><period><startDate>2025-01-01</startDate>
                <endDate>2025-12-31</endDate></period></context>""",
                '<us-gaap:Revenues contextRef="c1">999000000</us-gaap:Revenues>',
            )
        )

        # Default (relaxed) behavior still recovers a value.
        assert _extract_single_segment_revenue(root, "TEST") is not None
        # Strict behavior for the deeper-fallback call site must decline.
        assert _extract_single_segment_revenue(root, "TEST", require_explicit_count_tag=True) is None

    def test_explicit_count_of_one_still_works_when_required(self) -> None:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(
            _xml(
                """<context id="c1"><period><startDate>2025-01-01</startDate>
                <endDate>2025-12-31</endDate></period></context>""",
                """<us-gaap:NumberOfReportableSegments contextRef="c1">1</us-gaap:NumberOfReportableSegments>
                <us-gaap:Revenues contextRef="c1">999000000</us-gaap:Revenues>""",
            )
        )

        result = _extract_single_segment_revenue(root, "TEST", require_explicit_count_tag=True)
        assert result is not None
        assert result[1] == 999_000_000.0


class TestCrossTabFailClosedNotMislabeledAsSingleSegment:
    def test_unreconciled_cross_tab_does_not_fall_back_to_anchor_as_single_segment(self) -> None:
        """Exact regression shape: real segment-dimensioned contexts exist (AlphaMember
        split by US/NonUs) but their sum ($100M) doesn't reconcile with the plain anchor
        context's total ($999M) - must fail closed, not mislabel the anchor's $999M as
        AlphaMember's own revenue."""
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
        xml_content = _xml(contexts, facts)

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TEST")

        assert result["data_available"] is False
        assert result["reason"] == "no_segment_revenue_in_xbrl_xml"
        assert result["segments"] == []
