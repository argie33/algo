"""Regression test: StalenessChecker must cover market_sentiment/stock_symbols/
signal_quality_scores.

Live-caught (goal session 2026-09-13, staleness-coverage re-audit follow-up to the naaim/
19-table batch): these three real, actively-loaded tables had zero staleness entry at all -
market_sentiment is a sibling of market_health_daily/market_exposure_daily/capital_routing_daily/
sector_rotation_signal (all four already covered, this one was missed); stock_symbols is a
sibling of etf_symbols (already covered); signal_quality_scores is "Required by Phase 1 data
freshness check as tier-2 gate for filtering" per its own loader docstring, so a false
"never checked" gap here was especially load-bearing.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _cursor_with_latest_date(latest_date_str: str) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        sql = cursor._last_sql
        if "MAX(" in sql:
            return (1, latest_date_str)
        return (0,)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessMarketSentimentStockSymbolsSignalQualityScores:
    def test_market_sentiment_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        rows = [r for r in results if r.target_table == "market_sentiment" and "age_days" in r.details]
        assert len(rows) == 1
        assert rows[0].severity == "info"

    def test_stock_symbols_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        rows = [r for r in results if r.target_table == "stock_symbols" and "age_days" in r.details]
        assert len(rows) == 1
        assert rows[0].severity == "info"

    def test_signal_quality_scores_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        rows = [r for r in results if r.target_table == "signal_quality_scores" and "age_days" in r.details]
        assert len(rows) == 1
        assert rows[0].severity == "info"
