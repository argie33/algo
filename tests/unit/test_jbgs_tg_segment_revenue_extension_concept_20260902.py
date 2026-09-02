"""Regression test: JBG SMITH Properties' (JBGS) PropertyRevenue and Tredegar Corp's (TG)
NetSales extension concepts must be recognized as segment revenue - same filer-specific-
extension pattern as APA (test_apa_segment_revenue_extension_concept_20260902.py), found via
a systematic scan of the no_segment_revenue_in_xbrl_xml bucket following that fix.

Found live 2026-09-02: both filers tag segment-level revenue under their own extension
concepts, directly under StatementBusinessSegmentsAxis (paired only with the standard
ConsolidationItemsAxis boilerplate _index_segment_contexts already strips) - segment values
sum EXACTLY to each filer's own plain consolidated total for all 3 fiscal years on file
(JBGS FY2025 $433.180M; TG FY2025 $698.731M).
"""

from utils.external.sec_xbrl_segments import XBRLSegmentParser

_NS_XBRLI = "http://www.xbrl.org/2003/instance"
_NS_XBRLDI = "http://xbrl.org/2006/xbrldi"


def _context(ns_prefix: str, ctx_id: str, end: str, start: str, members: dict[str, str] | None = None) -> str:
    segment_xml = ""
    if members:
        member_tags = "".join(
            f'<xbrldi:explicitMember dimension="{ns_prefix}:{axis}">{ns_prefix}:{member}</xbrldi:explicitMember>'
            for axis, member in members.items()
        )
        segment_xml = f"<xbrli:segment>{member_tags}</xbrli:segment>"
    return f"""
    <xbrli:context id="{ctx_id}">
      <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>{segment_xml}</xbrli:entity>
      <xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period>
    </xbrli:context>
    """


def _fact(ns_prefix: str, concept: str, ctx_id: str, value: float) -> str:
    return f'<{ns_prefix}:{concept} contextRef="{ctx_id}" unitRef="usd" decimals="-6">{value}</{ns_prefix}:{concept}>'


def _build_xml(ns_prefix: str, ns_uri: str, concept: str, plain: float, seg_values: dict[str, float]) -> str:
    contexts = [_context(ns_prefix, "c_plain", "2025-12-31", "2025-01-01")]
    facts = [_fact(ns_prefix, concept, "c_plain", plain)]
    for i, (member, value) in enumerate(seg_values.items()):
        ctx_id = f"c_seg{i}"
        contexts.append(
            _context(
                ns_prefix,
                ctx_id,
                "2025-12-31",
                "2025-01-01",
                {"ConsolidationItemsAxis": "OperatingSegmentsMember", "StatementBusinessSegmentsAxis": member},
            )
        )
        facts.append(_fact(ns_prefix, concept, ctx_id, value))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="{_NS_XBRLI}" xmlns:xbrldi="{_NS_XBRLDI}" xmlns:{ns_prefix}="{ns_uri}">
{"".join(contexts)}
{"".join(facts)}
</xbrli:xbrl>
"""


class TestJbgsTgSegmentRevenueExtensionConcept:
    def test_jbgs_property_revenue_recognized_as_segment_revenue(self):
        xml_content = _build_xml(
            "jbgs",
            "http://www.jbgsmith.com/20251231",
            "PropertyRevenue",
            433180000.0,
            {"MultiFamilySegmentsMember": 205937000.0, "CommercialSegmentMember": 227243000.0},
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "JBGS")

        assert result["data_available"] is True
        assert result["segment_count"] == 2
        revenue_by_name = {s["name"]: s["revenue"] for s in result["segments"]}
        assert sum(revenue_by_name.values()) == 433180000.0

    def test_tg_net_sales_recognized_as_segment_revenue(self):
        xml_content = _build_xml(
            "tg",
            "http://www.tredegar.com/20251231",
            "NetSales",
            698731000.0,
            {"AluminumExtrusionsMember": 598975000.0, "PEFilmsMember": 99756000.0},
        )

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TG")

        assert result["data_available"] is True
        assert result["segment_count"] == 2
        revenue_by_name = {s["name"]: s["revenue"] for s in result["segments"]}
        assert sum(revenue_by_name.values()) == 698731000.0
