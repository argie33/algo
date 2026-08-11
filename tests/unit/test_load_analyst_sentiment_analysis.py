"""Regression tests for loaders/load_analyst_sentiment_analysis.py.

Covers fetch_incremental()'s daily-watermark gate (already have today's snapshot -> skip,
no coverage -> empty list not None) and that table/key config matches the live schema
(id SERIAL PK, real UNIQUE(symbol, date) constraint used as the upsert conflict target) -
same conventions as test_load_analyst_upgrade_downgrade.py.
"""

from datetime import date, datetime
from unittest.mock import patch

from loaders.load_analyst_sentiment_analysis import AnalystSentimentAnalysisLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _summary(symbol: str = "AAPL") -> dict:
    return {
        "symbol": symbol,
        "analyst_count": 47,
        "bullish_count": 29,
        "bearish_count": 4,
        "neutral_count": 14,
        "target_price": 318.81,
        "current_price": 336.91,
        "upside_downside_percent": -5.37,
    }


class TestFetchIncremental:
    def test_no_coverage_returns_data_unavailable_marker(self):
        loader = AnalystSentimentAnalysisLoader.__new__(AnalystSentimentAnalysisLoader)
        today = datetime.now(EASTERN_TZ).date()
        with patch("loaders.load_analyst_sentiment_analysis.fetch_analyst_sentiment", return_value=None):
            result = loader.fetch_incremental("ZZZZ", since=None)
        assert len(result) == 1
        assert result[0]["symbol"] == "ZZZZ"
        assert result[0]["date"] == today
        assert result[0]["data_unavailable"] is True
        assert result[0]["data_unavailable_reason"] == "no_analyst_coverage"

    def test_since_none_fetches_todays_snapshot(self):
        loader = AnalystSentimentAnalysisLoader.__new__(AnalystSentimentAnalysisLoader)
        today = datetime.now(EASTERN_TZ).date()
        with patch("loaders.load_analyst_sentiment_analysis.fetch_analyst_sentiment", return_value=_summary()):
            result = loader.fetch_incremental("AAPL", since=None)
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["date"] == today

    def test_already_have_today_skips_refetch(self):
        loader = AnalystSentimentAnalysisLoader.__new__(AnalystSentimentAnalysisLoader)
        today = datetime.now(EASTERN_TZ).date()
        with patch("loaders.load_analyst_sentiment_analysis.fetch_analyst_sentiment") as mock_fetch:
            result = loader.fetch_incremental("AAPL", since=today)
        assert result == []
        mock_fetch.assert_not_called()

    def test_stale_watermark_still_fetches(self):
        loader = AnalystSentimentAnalysisLoader.__new__(AnalystSentimentAnalysisLoader)
        yesterday = date(2020, 1, 1)
        with patch(
            "loaders.load_analyst_sentiment_analysis.fetch_analyst_sentiment", return_value=_summary()
        ) as mock_fetch:
            result = loader.fetch_incremental("AAPL", since=yesterday)
        mock_fetch.assert_called_once_with("AAPL")
        assert len(result) == 1

    def test_table_and_key_config_matches_live_schema(self):
        assert AnalystSentimentAnalysisLoader.table_name == "analyst_sentiment_analysis"
        assert AnalystSentimentAnalysisLoader.primary_key == ("symbol", "date")
