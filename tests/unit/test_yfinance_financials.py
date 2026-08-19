"""Regression tests for utils/external/yfinance_financials.py.

Covers fetch_financial_statement()'s DataFrame-to-row-dict conversion: field mapping to
the same snake_cased XBRL-concept vocabulary sec_statements.py already produces, sign
normalization for fields yfinance reports as signed outflows/contra-items (capex,
dividends, depreciation - see the module's _ABS_MAGNITUDE_FIELDS comment for the live
WRB case that motivated this), NaN/empty handling, and rate-limit errors correctly
reported to the shared circuit breaker.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.external.yfinance_financials import fetch_financial_statement


def _mock_ticker_with_df(attr: str, df):
    mock_ticker = MagicMock()
    setattr(mock_ticker, attr, df)
    return mock_ticker


def _mock_ticker_with_df_and_currency(attr: str, df, currency: str):
    mock_ticker = MagicMock()
    setattr(mock_ticker, attr, df)
    mock_ticker.info = {"financialCurrency": currency}
    return mock_ticker


@pytest.fixture(autouse=True)
def _patch_circuit_breaker():
    with patch("utils.external.yfinance_financials.get_circuit_breaker") as mock_get_cb:
        cb = MagicMock()
        mock_get_cb.return_value = cb
        yield cb


class TestFetchFinancialStatementIncome:
    def test_maps_real_rows_to_sec_concept_vocabulary(self, _patch_circuit_breaker):
        df = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): {
                    "Total Revenue": 1000.0,
                    "Net Income": 100.0,
                    "Basic EPS": 1.5,
                },
                pd.Timestamp("2024-12-31"): {
                    "Total Revenue": 900.0,
                    "Net Income": 90.0,
                    "Basic EPS": 1.4,
                },
            }
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("income_stmt", df)):
            rows = fetch_financial_statement("TEST", "income", "annual")

        assert rows is not None
        assert len(rows) == 2
        row_2025 = next(r for r in rows if r["fiscal_year"] == 2025)
        assert row_2025["symbol"] == "TEST"
        assert row_2025["revenues"] == 1000.0
        assert row_2025["net_income_loss"] == 100.0
        assert row_2025["earnings_per_share_basic"] == 1.5
        assert "fiscal_period" not in row_2025

    def test_depreciation_sign_normalized_to_positive_magnitude(self, _patch_circuit_breaker):
        """Live-confirmed 2026-08-16: WRB's 'Reconciled Depreciation' goes negative for
        some fiscal years while every other checked symbol (AAPL/MSFT/JNJ) stays positive.
        SEC-sourced depreciation_expense is 100% positive in the real DB, so a negative
        yfinance value must be normalized, not passed through - otherwise it would
        subtract from EBITDA instead of adding back."""
        df = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): {"Reconciled Depreciation": -48126000.0},
            }
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("income_stmt", df)):
            rows = fetch_financial_statement("WRB", "income", "annual")

        assert rows is not None
        assert rows[0]["depreciation"] == 48126000.0

    def test_nan_values_omitted_not_zero_filled(self, _patch_circuit_breaker):
        df = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): {"Total Revenue": 1000.0, "Net Income": float("nan")},
            }
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("income_stmt", df)):
            rows = fetch_financial_statement("TEST", "income", "annual")

        assert rows is not None
        assert "net_income_loss" not in rows[0]
        assert rows[0]["revenues"] == 1000.0

    def test_empty_dataframe_returns_none_not_error(self, _patch_circuit_breaker):
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("income_stmt", pd.DataFrame())):
            assert fetch_financial_statement("ZZZZ", "income", "annual") is None

        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("income_stmt", None)):
            assert fetch_financial_statement("ZZZZ", "income", "annual") is None

    def test_quarterly_period_sets_fiscal_period(self, _patch_circuit_breaker):
        df = pd.DataFrame(
            {
                pd.Timestamp("2025-06-30"): {"Total Revenue": 500.0},
            }
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("quarterly_income_stmt", df)):
            rows = fetch_financial_statement("TEST", "income", "quarterly")

        assert rows is not None
        assert rows[0]["fiscal_period"] == "Q2"


class TestFetchFinancialStatementCashflow:
    def test_capex_and_dividends_sign_normalized(self, _patch_circuit_breaker):
        df = pd.DataFrame(
            {
                pd.Timestamp("2025-09-30"): {
                    "Capital Expenditure": -12715000000.0,
                    "Cash Dividends Paid": -15421000000.0,
                    "Operating Cash Flow": 20000000000.0,
                },
            }
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("cashflow", df)):
            rows = fetch_financial_statement("TEST", "cashflow", "annual")

        assert rows is not None
        assert rows[0]["payments_to_acquire_property_plant_and_equipment"] == 12715000000.0
        assert rows[0]["payments_of_dividends"] == 15421000000.0
        assert rows[0]["net_cash_provided_by_used_in_operating_activities"] == 20000000000.0


class TestFetchFinancialStatementCurrencyConversion:
    """FIXED 2026-08-19: yfinance reports statements in the filer's own reporting
    currency (Ticker.info["financialCurrency"]), not necessarily USD - live-confirmed via
    GGAL (ARS) landing a -1.6 TRILLION operating_cash_flow in the real DB, and SKM/KT
    (KRW) jumping ~1,300x between their (correctly converted) sec_audited row and their
    yfinance row for the very next fiscal year. This fed directly into the DCF's
    intrinsic-value math since shares_out/price stay USD-denominated regardless."""

    def test_usd_currency_left_unconverted(self, _patch_circuit_breaker):
        df = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Revenue": 1000.0}})
        ticker = _mock_ticker_with_df_and_currency("income_stmt", df, "USD")
        with patch("yfinance.Ticker", return_value=ticker):
            rows = fetch_financial_statement("TEST", "income", "annual")

        assert rows is not None
        assert rows[0]["revenues"] == 1000.0

    def test_unknown_currency_left_unconverted(self, _patch_circuit_breaker):
        """.info missing/failing must not nuke otherwise-valid data for the (common) case
        where the symbol genuinely reports in USD - fail open on unknown, not closed."""
        df = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Revenue": 1000.0}})
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df("income_stmt", df)):
            rows = fetch_financial_statement("TEST", "income", "annual")

        assert rows is not None
        assert rows[0]["revenues"] == 1000.0

    def test_major_currency_converted_to_usd(self, _patch_circuit_breaker):
        df = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): {
                    "Total Revenue": 1300.0,
                    "Basic Average Shares": 500.0,
                },
            }
        )
        ticker = _mock_ticker_with_df_and_currency("income_stmt", df, "KRW")
        with (
            patch("yfinance.Ticker", return_value=ticker),
            patch(
                "utils.external.yfinance_financials._fx_rate_cache.get_usd_rate",
                return_value=13.0,
            ),
        ):
            rows = fetch_financial_statement("TEST", "income", "annual")

        assert rows is not None
        # Monetary field divided by the FX rate ...
        assert rows[0]["revenues"] == pytest.approx(100.0)
        # ... but a share COUNT must never be divided by an FX rate.
        assert rows[0]["weighted_average_number_of_shares_outstanding_basic"] == 500.0

    def test_non_major_currency_rejected_entirely(self, _patch_circuit_breaker):
        """ARS (Argentine peso, the real GGAL case) isn't in MAJOR_CURRENCIES - fail
        closed and reject the whole fetch rather than store raw ARS as if it were USD."""
        df = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Revenue": 1_000_000_000.0}})
        ticker = _mock_ticker_with_df_and_currency("income_stmt", df, "ARS")
        with patch("yfinance.Ticker", return_value=ticker):
            rows = fetch_financial_statement("GGAL", "income", "annual")

        assert rows is None

    def test_missing_fx_rate_skips_period_not_whole_symbol(self, _patch_circuit_breaker):
        df = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): {"Total Revenue": 1300.0},
                pd.Timestamp("2024-12-31"): {"Total Revenue": 1200.0},
            }
        )
        ticker = _mock_ticker_with_df_and_currency("income_stmt", df, "KRW")
        with (
            patch("yfinance.Ticker", return_value=ticker),
            patch(
                "utils.external.yfinance_financials._fx_rate_cache.get_usd_rate",
                side_effect=lambda currency, date_str: None if date_str == "2025-12-31" else 13.0,
            ),
        ):
            rows = fetch_financial_statement("TEST", "income", "annual")

        assert rows is not None
        assert len(rows) == 1
        assert rows[0]["fiscal_year"] == 2024


class TestFetchFinancialStatementErrors:
    def test_unsupported_combo_raises_value_error(self, _patch_circuit_breaker):
        with pytest.raises(ValueError):
            fetch_financial_statement("TEST", "income", "ttm")

    def test_rate_limit_error_reported_to_circuit_breaker(self, _patch_circuit_breaker):
        with patch("yfinance.Ticker", side_effect=RuntimeError("429 Too Many Requests")):
            with pytest.raises(RuntimeError):
                fetch_financial_statement("TEST", "income", "annual")

        _patch_circuit_breaker.report_rate_limit_error.assert_called_once()

    def test_non_rate_limit_error_not_reported_to_circuit_breaker(self, _patch_circuit_breaker):
        with patch("yfinance.Ticker", side_effect=RuntimeError("connection reset")):
            with pytest.raises(RuntimeError):
                fetch_financial_statement("TEST", "income", "annual")

        _patch_circuit_breaker.report_rate_limit_error.assert_not_called()
