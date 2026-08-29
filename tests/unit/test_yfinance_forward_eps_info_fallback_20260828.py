"""Regression tests for utils/external/yfinance_analyst_ratings.py::fetch_forward_eps().

Goal session (2026-08-28, "Forward P/E - analyst estimates unavailable" audit): the primary
Ticker.earnings_estimate ('+1y' row) source is empty on Yahoo's side for a real, non-trivial
slice of well-covered symbols (live-confirmed: BN, FOX, L, HEI-A, BF-A, LLYVA - dual-class/
tracking-stock/foreign-ADR names, several $10B+ market caps) even though Ticker.info carries
a real 'forwardEps' for the same symbol. fetch_forward_eps() now falls back to Ticker.info
when the primary earningsTrend path is empty.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.external.yfinance_analyst_ratings import fetch_forward_eps


def _mock_ticker(earnings_estimate=None, info=None):
    ticker = MagicMock()
    ticker.earnings_estimate = earnings_estimate
    ticker.info = info if info is not None else {}
    return ticker


def _estimate_df(avg_plus_1y=9.53127):
    return pd.DataFrame({"avg": {"0q": 1.97656, "+1q": 2.90859, "0y": 8.81249, "+1y": avg_plus_1y}})


@pytest.fixture(autouse=True)
def _patch_circuit_breaker():
    with patch("utils.external.yfinance_analyst_ratings.get_circuit_breaker") as mock_get_cb:
        cb = MagicMock()
        mock_get_cb.return_value = cb
        yield cb


class TestFetchForwardEps:
    def test_uses_earnings_trend_when_available(self):
        ticker = _mock_ticker(earnings_estimate=_estimate_df(9.53127), info={"forwardEps": 999.0})
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_forward_eps("AAPL") == pytest.approx(9.53127)

    def test_falls_back_to_info_when_earnings_trend_empty(self):
        ticker = _mock_ticker(earnings_estimate=pd.DataFrame(), info={"forwardEps": 5.87})
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_forward_eps("BN") == pytest.approx(5.87)

    def test_falls_back_to_info_when_plus_1y_row_missing(self):
        df = pd.DataFrame({"avg": {"0q": 1.0, "+1q": 1.1, "0y": 4.0}})  # no '+1y' row
        ticker = _mock_ticker(earnings_estimate=df, info={"forwardEps": 4.31})
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_forward_eps("HEI-A") == pytest.approx(4.31)

    def test_info_fallback_negative_value_still_returned(self):
        # Negative forward EPS is a real (if unprofitable) estimate - load_value_quality_
        # growth_metrics.py's forward_pe block is responsible for the negative-earnings
        # distinction (forward_pe_reason='negative_forward_eps'), not this fetch layer.
        ticker = _mock_ticker(earnings_estimate=pd.DataFrame(), info={"forwardEps": -2.93})
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_forward_eps("YQ") == pytest.approx(-2.93)

    def test_no_coverage_anywhere_returns_none(self):
        ticker = _mock_ticker(earnings_estimate=pd.DataFrame(), info={})
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_forward_eps("ZZZZ") is None

    def test_info_missing_forward_eps_key_returns_none(self):
        ticker = _mock_ticker(earnings_estimate=pd.DataFrame(), info={"shortName": "Zzzz Corp"})
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_forward_eps("ZZZZ") is None

    def test_info_non_dict_returns_none(self):
        ticker = _mock_ticker(earnings_estimate=pd.DataFrame(), info=None)
        ticker.info = None
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_forward_eps("ZZZZ") is None
