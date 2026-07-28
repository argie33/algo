"""Regression tests for utils/external/yfinance_analyst_ratings.py::fetch_analyst_sentiment().

Covers the recommendations_summary + analyst_price_targets combination that
analyst_sentiment_analysis needs: current-period count extraction, bullish/bearish/neutral
bucketing, upside/downside computation, and no-coverage symbols returning None (not an
error) - same conventions as fetch_analyst_actions's existing test coverage.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.external.yfinance_analyst_ratings import fetch_analyst_sentiment


def _mock_ticker(recommendations_summary=None, analyst_price_targets=None):
    ticker = MagicMock()
    ticker.recommendations_summary = recommendations_summary
    ticker.analyst_price_targets = analyst_price_targets
    return ticker


@pytest.fixture(autouse=True)
def _patch_circuit_breaker():
    with patch("utils.external.yfinance_analyst_ratings.get_circuit_breaker") as mock_get_cb:
        cb = MagicMock()
        mock_get_cb.return_value = cb
        yield cb


class TestFetchAnalystSentiment:
    def _summary_df(self, strong_buy=6, buy=23, hold=14, sell=2, strong_sell=2):
        return pd.DataFrame(
            {
                "period": ["0m", "-1m", "-2m", "-3m"],
                "strongBuy": [strong_buy, 6, 7, 7],
                "buy": [buy, 22, 23, 25],
                "hold": [hold, 16, 15, 14],
                "sell": [sell, 1, 1, 1],
                "strongSell": [strong_sell, 2, 2, 1],
            }
        )

    def test_maps_current_period_counts_and_target_price(self):
        ticker = _mock_ticker(
            recommendations_summary=self._summary_df(),
            analyst_price_targets={"current": 336.91, "high": 400.0, "low": 215.0, "mean": 318.8093, "median": 329.0},
        )
        with patch("yfinance.Ticker", return_value=ticker):
            result = fetch_analyst_sentiment("AAPL")

        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["bullish_count"] == 29  # strongBuy(6) + buy(23)
        assert result["bearish_count"] == 4  # sell(2) + strongSell(2)
        assert result["neutral_count"] == 14
        assert result["analyst_count"] == 47
        assert result["target_price"] == 318.8093
        assert result["current_price"] == 336.91
        assert result["upside_downside_percent"] == pytest.approx(-5.37, abs=0.01)

    def test_no_coverage_returns_none(self):
        ticker = _mock_ticker(recommendations_summary=pd.DataFrame())
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_analyst_sentiment("ZZZZ") is None

    def test_all_zero_counts_returns_none(self):
        ticker = _mock_ticker(
            recommendations_summary=self._summary_df(strong_buy=0, buy=0, hold=0, sell=0, strong_sell=0)
        )
        with patch("yfinance.Ticker", return_value=ticker):
            assert fetch_analyst_sentiment("AAPL") is None

    def test_missing_price_targets_still_returns_counts(self):
        ticker = _mock_ticker(recommendations_summary=self._summary_df(), analyst_price_targets=None)
        with patch("yfinance.Ticker", return_value=ticker):
            result = fetch_analyst_sentiment("AAPL")

        assert result is not None
        assert result["analyst_count"] == 47
        assert result["target_price"] is None
        assert result["upside_downside_percent"] is None
