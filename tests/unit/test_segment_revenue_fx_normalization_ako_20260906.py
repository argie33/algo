"""Regression test for the 2026-09-06 fix (goal session: "SEC/XBRL missing data to zero"
sweep, segment-sum-to-consolidated FX gap): segment revenue/operating_income/assets were
never currency-normalized, unlike annual_income_statement.revenue - live-confirmed against
AKO.A's (Embotelladora Andina, CIK 0000925261) real FY2025 20-F: Brazil segment revenue was
stored as $976,907,746,000 (raw CLP treated as USD, ~900x too large) before this fix.
"""

from unittest.mock import patch

from utils.external.sec_xbrl_segments import XBRLSegmentParser

_NS_XBRLI = "http://www.xbrl.org/2003/instance"
_NS_XBRLDI = "http://xbrl.org/2006/xbrldi"
_NS_GAAP = "http://fasb.org/us-gaap/2025"


def _context(ctx_id: str, end: str, start: str, member: str | None) -> str:
    segment_xml = ""
    if member:
        segment_xml = (
            "<xbrli:segment>"
            f'<xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">{member}'
            "</xbrldi:explicitMember></xbrli:segment>"
        )
    return f"""
    <xbrli:context id="{ctx_id}">
      <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000925261</xbrli:identifier>{segment_xml}</xbrli:entity>
      <xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period>
    </xbrli:context>
    """


def _build_xml(unit_id: str, measure: str) -> str:
    contexts = "".join(
        [
            _context("c_chile", "2025-12-31", "2025-01-01", "ChileOperationMember"),
            _context("c_brazil", "2025-12-31", "2025-01-01", "BrazilOperationMember"),
        ]
    )
    facts = "".join(
        [
            f'<us-gaap:Revenues contextRef="c_chile" unitRef="{unit_id}" decimals="-3">1319136024000.0</us-gaap:Revenues>',
            f'<us-gaap:Revenues contextRef="c_brazil" unitRef="{unit_id}" decimals="-3">976907746000.0</us-gaap:Revenues>',
        ]
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="{_NS_XBRLI}" xmlns:xbrldi="{_NS_XBRLDI}" xmlns:us-gaap="{_NS_GAAP}">
  <xbrli:unit id="{unit_id}"><xbrli:measure>{measure}</xbrli:measure></xbrli:unit>
{contexts}
{facts}
</xbrli:xbrl>
"""


class TestSegmentRevenueFxNormalization:
    def test_clp_segment_revenue_converted_via_major_currency_rate(self):
        xml_content = _build_xml("clp", "iso4217:CLP")

        with patch(
            "utils.external.sec_xbrl_segments._fx_rate_cache.get_usd_rate",
            return_value=900.0,
        ) as mock_rate:
            result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "AKO.A")

        mock_rate.assert_called_with("CLP", "2025-12-31")
        assert result["data_available"] is True
        revenue_by_name = {s["name"]: s["revenue"] for s in result["segments"]}
        assert revenue_by_name["Chile Operation"] == 1319136024000.0 / 900.0
        assert revenue_by_name["Brazil Operation"] == 976907746000.0 / 900.0
        # Not the raw, un-normalized magnitude - the whole point of the fix.
        assert revenue_by_name["Brazil Operation"] < 2_000_000_000

    def test_non_major_currency_rejected_not_stored_raw(self):
        xml_content = _build_xml("ars", "iso4217:ARS")

        with patch("utils.external.sec_xbrl_segments._fx_rate_cache.get_usd_rate") as mock_rate:
            result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TESTARS")

        mock_rate.assert_not_called()
        # Both candidate facts get rejected (ARS isn't a MAJOR_CURRENCIES member - too
        # volatile, per fx_rates.py's own deliberate exclusion) - falls through to no
        # usable segment revenue rather than storing a wildly-wrong converted value.
        assert result["data_available"] is False

    def test_usd_segment_revenue_unaffected(self):
        xml_content = _build_xml("usd", "iso4217:USD")

        with patch("utils.external.sec_xbrl_segments._fx_rate_cache.get_usd_rate") as mock_rate:
            result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TESTUSD")

        mock_rate.assert_not_called()
        revenue_by_name = {s["name"]: s["revenue"] for s in result["segments"]}
        assert revenue_by_name["Brazil Operation"] == 976907746000.0

    def test_fx_lookup_failure_rejects_rather_than_stores_raw(self):
        xml_content = _build_xml("clp", "iso4217:CLP")

        with patch(
            "utils.external.sec_xbrl_segments._fx_rate_cache.get_usd_rate",
            return_value=None,
        ):
            result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, "TESTNORATE")

        assert result["data_available"] is False
