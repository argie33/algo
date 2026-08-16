"""Regression/behavior tests for SecEdgarStatementLoader's yfinance fallback.

Added 2026-08-16 alongside utils/external/yfinance_financials.py: SEC EDGAR is the
primary/preferred source for financial statements, but ~500-650 symbols (out of ~4,922,
confirmed live) have no SEC XBRL data at all (cik_not_found / REIT-trust-SPV special
entities). Previously these stayed permanently data_unavailable even when the company's
real financials are obtainable from yfinance. _try_yfinance_fallback() is the single
choke point every "SEC has nothing" path in fetch_incremental() now routes through - see
loaders/helpers/sec_base.py's docstring on it and utils/external/yfinance_financials.py's
module docstring for the full governance rationale (fallback only, never a competing
source, every row explicitly tagged data_source so it's never indistinguishable from a
real SEC-audited figure - same discipline as
tests/unit/test_company_info_sec_no_yfinance_pollution.py enforces elsewhere).
"""

from datetime import date
from unittest.mock import patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.statement_type = statement_type
    loader.period = period
    loader.table_name = "annual_income_statement" if period == "annual" else "quarterly_income_statement"
    return loader


class TestYfinanceFallbackRecoversData:
    def test_recovers_rows_and_tags_data_source(self) -> None:
        loader = _make_loader()
        fake_rows = [
            {"symbol": "TEST", "fiscal_year": 2025, "revenues": 1000.0, "net_income_loss": 100.0},
            {"symbol": "TEST", "fiscal_year": 2024, "revenues": 900.0, "net_income_loss": 90.0},
        ]
        with patch(
            "utils.external.yfinance_financials.fetch_financial_statement",
            return_value=fake_rows,
        ):
            result = loader._try_yfinance_fallback("TEST", since=None, sec_reason="cik_not_found")

        assert len(result) == 2
        assert all(r["data_source"] == "yfinance" for r in result)
        assert {r["fiscal_year"] for r in result} == {2025, 2024}

    def test_respects_incremental_since_filter(self) -> None:
        loader = _make_loader()
        fake_rows = [
            {"symbol": "TEST", "fiscal_year": 2025, "revenues": 1000.0},
            {"symbol": "TEST", "fiscal_year": 2020, "revenues": 500.0},
        ]
        with patch(
            "utils.external.yfinance_financials.fetch_financial_statement",
            return_value=fake_rows,
        ):
            result = loader._try_yfinance_fallback("TEST", since=date(2022, 12, 31), sec_reason="cik_not_found")

        assert len(result) == 1
        assert result[0]["fiscal_year"] == 2025


class TestYfinanceFallbackFallsThroughToMarker:
    def test_returns_standard_marker_when_yfinance_has_nothing(self) -> None:
        loader = _make_loader()
        with patch(
            "utils.external.yfinance_financials.fetch_financial_statement",
            return_value=None,
        ):
            result = loader._try_yfinance_fallback("TEST", since=None, sec_reason="cik_not_found")

        assert len(result) == 1
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "cik_not_found"
        assert "data_source" not in result[0]

    def test_returns_standard_marker_when_yfinance_fetch_raises(self) -> None:
        loader = _make_loader()
        with patch(
            "utils.external.yfinance_financials.fetch_financial_statement",
            side_effect=RuntimeError("yfinance shared IP ban active"),
        ):
            result = loader._try_yfinance_fallback(
                "TEST", since=None, sec_reason="no_annual_income_data_in_sec_edgar_reit_or_special_entity"
            )

        assert len(result) == 1
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "no_annual_income_data_in_sec_edgar_reit_or_special_entity"

    def test_all_rows_filtered_by_since_falls_through_to_marker(self) -> None:
        loader = _make_loader()
        fake_rows = [{"symbol": "TEST", "fiscal_year": 2020, "revenues": 500.0}]
        with patch(
            "utils.external.yfinance_financials.fetch_financial_statement",
            return_value=fake_rows,
        ):
            result = loader._try_yfinance_fallback("TEST", since=date(2024, 12, 31), sec_reason="cik_not_found")

        assert len(result) == 1
        assert result[0]["data_unavailable"] is True
