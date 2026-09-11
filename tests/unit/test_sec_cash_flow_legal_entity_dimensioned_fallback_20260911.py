"""Tests for sec_cash_flow.py's _fill_operating_cash_flow_from_legal_entity_dimensioned_
instance_document() - goal session 2026-09-11, "under 300" push. See
utils/external/sec_xbrl_instance_document.py's module docstring for the mechanism this
recovers (a combined REIT + operating-partnership UPREIT filer, e.g. SKT/Tanger, whose
operating cash flow is tagged exclusively under a dei:LegalEntityAxis dimension that SEC's
companyfacts API drops entirely).
"""

from unittest.mock import MagicMock

from utils.external.sec_cash_flow import (
    _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document,
)

_INSTANCE_XML = """<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:skt="http://example.com/skt">
  <xbrli:context id="c-8">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier>
      <xbrli:segment><xbrldi:explicitMember dimension="dei:LegalEntityAxis">skt:TangerIncMember</xbrldi:explicitMember></xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="c-9">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier>
      <xbrli:segment><xbrldi:explicitMember dimension="dei:LegalEntityAxis">skt:TangerIncMember</xbrldi:explicitMember></xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="c-8" unitRef="usd">295369000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="c-9" unitRef="usd">260678000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
</xbrli:xbrl>"""


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.symbol_to_cik.return_value = "0000899715"
    client.get_submissions.return_value = {
        "name": "TANGER INC.",
        "filings": {
            "recent": {
                "form": ["10-Q", "10-K", "10-Q"],
                "accessionNumber": ["0001-a", "0001628280-26-012252", "0001-c"],
            }
        },
    }
    client.get_filing_xml.return_value = _INSTANCE_XML
    return client


class TestFillOperatingCashFlowFromLegalEntityDimensionedInstanceDocument:
    def test_fills_missing_years_from_instance_document(self) -> None:
        rows = [
            {"fiscal_year": 2025, "net_cash_provided_by_used_in_operating_activities": None},
            {"fiscal_year": 2024, "net_cash_provided_by_used_in_operating_activities": None},
        ]
        client = _mock_client()
        _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_cash_provided_by_used_in_operating_activities"] == 295369000.0
        assert rows[1]["net_cash_provided_by_used_in_operating_activities"] == 260678000.0

    def test_never_overwrites_a_real_existing_value(self) -> None:
        rows = [
            {"fiscal_year": 2025, "net_cash_provided_by_used_in_operating_activities": 999.0},
            {"fiscal_year": 2024, "net_cash_provided_by_used_in_operating_activities": None},
        ]
        client = _mock_client()
        _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_cash_provided_by_used_in_operating_activities"] == 999.0
        assert rows[1]["net_cash_provided_by_used_in_operating_activities"] == 260678000.0

    def test_skips_entirely_when_nothing_is_missing(self) -> None:
        rows = [{"fiscal_year": 2025, "net_cash_provided_by_used_in_operating_activities": 999.0}]
        client = _mock_client()
        _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        client.symbol_to_cik.assert_not_called()

    def test_leaves_years_the_instance_document_has_no_match_for_untouched(self) -> None:
        rows = [{"fiscal_year": 2019, "net_cash_provided_by_used_in_operating_activities": None}]
        client = _mock_client()
        _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_cash_provided_by_used_in_operating_activities"] is None

    def test_no_crash_when_cik_resolution_fails(self) -> None:
        rows = [{"fiscal_year": 2025, "net_cash_provided_by_used_in_operating_activities": None}]
        client = MagicMock()
        client.symbol_to_cik.side_effect = ValueError("not found")
        _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document(rows, client, "NOPE")
        assert rows[0]["net_cash_provided_by_used_in_operating_activities"] is None

    def test_no_crash_when_no_10k_in_recent_filings(self) -> None:
        rows = [{"fiscal_year": 2025, "net_cash_provided_by_used_in_operating_activities": None}]
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000899715"
        client.get_submissions.return_value = {
            "name": "TANGER INC.",
            "filings": {"recent": {"form": ["10-Q"], "accessionNumber": ["0001-a"]}},
        }
        _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_cash_provided_by_used_in_operating_activities"] is None
        client.get_filing_xml.assert_not_called()

    def test_no_crash_when_instance_document_fetch_fails(self) -> None:
        rows = [{"fiscal_year": 2025, "net_cash_provided_by_used_in_operating_activities": None}]
        client = _mock_client()
        client.get_filing_xml.side_effect = FileNotFoundError("404")
        _fill_operating_cash_flow_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_cash_provided_by_used_in_operating_activities"] is None
