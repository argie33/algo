"""Regression test: APA Corporation's (apachecorp.com: namespace) own
RevenuesAndRealizedGainsLossesOnDerivativeInstruments extension concept must be
recognized as segment revenue, same filer-specific-extension pattern as the existing
GLW/AMH/BAC entries in _REVENUE_CONCEPT_LOCAL_NAMES.

Found live 2026-09-02 via loader.fetch_incremental("APA", ...): APA tags this concept
directly under StatementBusinessSegmentsAxis (paired only with the standard
ConsolidationItemsAxis=OperatingSegmentsMember boilerplate _index_segment_contexts already
strips) - segment values sum EXACTLY to APA's own plain consolidated total for all 3 fiscal
years on file (FY2025 $8.951B, FY2024 $9.739B, FY2023 $8.327B). Before this fix, APA fell
through to "no_segment_revenue_in_xbrl_xml" because the loader only recognized the standard
"Revenues" concept, which APA tags for a DIFFERENT, finer cross-tabbed breakdown (by product
and reserve type, correctly excluded by _index_segment_contexts' multi-axis filter) rather
than the real segment-level total.
"""

from utils.external.sec_xbrl_segments import XBRLSegmentParser

_NS_XBRLI = "http://www.xbrl.org/2003/instance"
_NS_XBRLDI = "http://xbrl.org/2006/xbrldi"
_NS_APA = "http://www.apachecorp.com/20251231"


def _context(ctx_id: str, end: str, start: str | None = None, members: dict[str, str] | None = None) -> str:
    period = (
        f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>"
        if start
        else (f"<xbrli:instant>{end}</xbrli:instant>")
    )
    segment_xml = ""
    if members:
        member_tags = "".join(
            f'<xbrldi:explicitMember dimension="apa:{axis}">apa:{member}</xbrldi:explicitMember>'
            for axis, member in members.items()
        )
        segment_xml = f"<xbrli:segment>{member_tags}</xbrli:segment>"
    return f"""
    <xbrli:context id="{ctx_id}">
      <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001841666</xbrli:identifier>{segment_xml}</xbrli:entity>
      <xbrli:period>{period}</xbrli:period>
    </xbrli:context>
    """


def _fact(concept: str, ctx_id: str, value: float) -> str:
    return f'<apa:{concept} contextRef="{ctx_id}" unitRef="usd" decimals="-6">{value}</apa:{concept}>'


def _build_apa_style_xml() -> str:
    contexts = "".join(
        [
            _context("c_plain", "2025-12-31", "2025-01-01"),
            _context(
                "c_us",
                "2025-12-31",
                "2025-01-01",
                {
                    "ConsolidationItemsAxis": "OperatingSegmentsMember",
                    "StatementBusinessSegmentsAxis": "SegmentUnitedStatesMember",
                },
            ),
            _context(
                "c_egypt",
                "2025-12-31",
                "2025-01-01",
                {
                    "ConsolidationItemsAxis": "OperatingSegmentsMember",
                    "StatementBusinessSegmentsAxis": "SegmentEgyptMember",
                },
            ),
            _context(
                "c_northsea",
                "2025-12-31",
                "2025-01-01",
                {
                    "ConsolidationItemsAxis": "OperatingSegmentsMember",
                    "StatementBusinessSegmentsAxis": "SegmentNorthSeaMember",
                },
            ),
        ]
    )
    facts = "".join(
        [
            _fact("RevenuesAndRealizedGainsLossesOnDerivativeInstruments", "c_plain", 8951000000.0),
            _fact("RevenuesAndRealizedGainsLossesOnDerivativeInstruments", "c_us", 5541000000.0),
            _fact("RevenuesAndRealizedGainsLossesOnDerivativeInstruments", "c_egypt", 2637000000.0),
            _fact("RevenuesAndRealizedGainsLossesOnDerivativeInstruments", "c_northsea", 773000000.0),
        ]
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="{_NS_XBRLI}" xmlns:xbrldi="{_NS_XBRLDI}" xmlns:apa="{_NS_APA}">
{contexts}
{facts}
</xbrli:xbrl>
"""


class TestApaSegmentRevenueExtensionConcept:
    def test_apa_extension_concept_recognized_as_segment_revenue(self):
        xml_content = _build_apa_style_xml()

        result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "APA")

        assert result["data_available"] is True
        assert result["segment_count"] == 3
        revenue_by_name = {s["name"]: s["revenue"] for s in result["segments"]}
        assert set(revenue_by_name) == {"Segment United States", "Segment Egypt", "Segment North Sea"}
        assert revenue_by_name["Segment United States"] == 5541000000.0
        assert revenue_by_name["Segment Egypt"] == 2637000000.0
        assert revenue_by_name["Segment North Sea"] == 773000000.0
        # Exact reconciliation against the plain consolidated total (8.951B).
        assert sum(revenue_by_name.values()) == 8951000000.0
