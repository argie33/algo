"""Tests for sec_income_statement_fallbacks.py's _fill_net_income_eps_from_legal_entity_
dimensioned_instance_document() - goal session 2026-09-11, "under 200" push. Extends
sec_cash_flow.py's UPREIT LegalEntityAxis instance-document fallback (see
test_sec_cash_flow_legal_entity_dimensioned_fallback_20260911.py) from operating cash flow
to net_income/EPS - live-confirmed via SKT (Tanger Inc): companyfacts has real NetIncomeLoss/
EarningsPerShareDiluted/EarningsPerShareBasic facts but only quarterly/YTD durations, never a
full fiscal year, despite 10-Ks filed every year.
"""

from unittest.mock import MagicMock

from utils.external.sec_income_statement_fallbacks import (
    _fill_net_income_eps_from_legal_entity_dimensioned_instance_document,
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
  <us-gaap:NetIncomeLoss contextRef="c-8" unitRef="usd">114776000</us-gaap:NetIncomeLoss>
  <us-gaap:NetIncomeLoss contextRef="c-9" unitRef="usd">98595000</us-gaap:NetIncomeLoss>
  <us-gaap:EarningsPerShareDiluted contextRef="c-8" unitRef="usdPerShare">0.99</us-gaap:EarningsPerShareDiluted>
  <us-gaap:EarningsPerShareDiluted contextRef="c-9" unitRef="usdPerShare">0.88</us-gaap:EarningsPerShareDiluted>
  <us-gaap:EarningsPerShareBasic contextRef="c-8" unitRef="usdPerShare">1.01</us-gaap:EarningsPerShareBasic>
  <us-gaap:EarningsPerShareBasic contextRef="c-9" unitRef="usdPerShare">0.89</us-gaap:EarningsPerShareBasic>
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


class TestFillNetIncomeEpsFromLegalEntityDimensionedInstanceDocument:
    def test_fills_net_income_and_eps_for_missing_years(self) -> None:
        rows = [
            {
                "fiscal_year": 2025,
                "net_income_loss": None,
                "earnings_per_share_diluted": None,
                "earnings_per_share_basic": None,
            },
            {
                "fiscal_year": 2024,
                "net_income_loss": None,
                "earnings_per_share_diluted": None,
                "earnings_per_share_basic": None,
            },
        ]
        client = _mock_client()
        _fill_net_income_eps_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_income_loss"] == 114776000.0
        assert rows[0]["earnings_per_share_diluted"] == 0.99
        assert rows[0]["earnings_per_share_basic"] == 1.01
        assert rows[1]["net_income_loss"] == 98595000.0
        assert rows[1]["earnings_per_share_diluted"] == 0.88
        assert rows[1]["earnings_per_share_basic"] == 0.89

    def test_never_overwrites_a_real_existing_value(self) -> None:
        rows = [{"fiscal_year": 2025, "net_income_loss": 5.0, "earnings_per_share_diluted": None}]
        client = _mock_client()
        _fill_net_income_eps_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_income_loss"] == 5.0
        assert rows[0]["earnings_per_share_diluted"] == 0.99

    def test_skips_entirely_when_nothing_is_missing(self) -> None:
        rows = [
            {
                "fiscal_year": 2025,
                "net_income_loss": 5.0,
                "earnings_per_share_diluted": 1.0,
                "earnings_per_share_basic": 1.0,
            }
        ]
        client = _mock_client()
        _fill_net_income_eps_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        client.symbol_to_cik.assert_not_called()

    def test_no_crash_when_cik_resolution_fails(self) -> None:
        rows = [{"fiscal_year": 2025, "net_income_loss": None}]
        client = MagicMock()
        client.symbol_to_cik.side_effect = ValueError("not found")
        _fill_net_income_eps_from_legal_entity_dimensioned_instance_document(rows, client, "NOPE")
        assert rows[0]["net_income_loss"] is None

    def test_no_crash_when_no_10k_in_recent_filings(self) -> None:
        rows = [{"fiscal_year": 2025, "net_income_loss": None}]
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000899715"
        client.get_submissions.return_value = {
            "name": "TANGER INC.",
            "filings": {"recent": {"form": ["10-Q"], "accessionNumber": ["0001-a"]}},
        }
        _fill_net_income_eps_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_income_loss"] is None
        client.get_filing_xml.assert_not_called()

    def test_no_crash_when_instance_document_fetch_fails(self) -> None:
        rows = [{"fiscal_year": 2025, "net_income_loss": None}]
        client = _mock_client()
        client.get_filing_xml.side_effect = FileNotFoundError("404")
        _fill_net_income_eps_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_income_loss"] is None

    def test_profit_loss_fills_when_net_income_loss_concept_absent(self) -> None:
        xml = """<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:skt="http://example.com/skt">
  <xbrli:context id="c-8">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier>
      <xbrli:segment><xbrldi:explicitMember dimension="dei:LegalEntityAxis">skt:TangerIncMember</xbrldi:explicitMember></xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <us-gaap:ProfitLoss contextRef="c-8" unitRef="usd">119501000</us-gaap:ProfitLoss>
</xbrli:xbrl>"""
        rows = [{"fiscal_year": 2025, "net_income_loss": None}]
        client = _mock_client()
        client.get_filing_xml.return_value = xml
        _fill_net_income_eps_from_legal_entity_dimensioned_instance_document(rows, client, "SKT")
        assert rows[0]["net_income_loss"] == 119501000.0
