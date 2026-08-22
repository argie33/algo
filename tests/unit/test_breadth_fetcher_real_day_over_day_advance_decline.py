#!/usr/bin/env python3
"""Regression test (2026-08-20, goal: finance-accuracy audit): BreadthFetcher.fetch()'s
advance_decline_ratio used to be COUNT(price_above_sma50=true)/COUNT(price_above_sma50=false)
from trend_template_data - "% of stocks above their 50-day moving average" (a trend-
participation metric, already separately and correctly captured by MarketExposure's breadth
factor - now algo/risk/market_exposure.py's merged BREADTH factor, formerly the standalone
breadth_50dma_factor.py in a pre-2026-08-20 architecture since removed), mislabeled as an
advance/decline ratio.

Live-confirmed the mislabeling before this fix: market_health_daily.advance_decline_ratio sat
in a narrow 0.91-1.41 band for 3+ weeks straight (2026-07-31 through 2026-08-20) - not how a
real day-to-day advance/decline ratio behaves, since "% above a slow-moving 50-day average"
barely changes day to day. This meant load_market_status_daily.py's breadth_momentum_10d
("% of the last 10 days with advance_decline_ratio > 1.0") trivially pinned at 100% for days
at a time during any sustained uptrend, and MarketExposure's A/D line factor (which reads
this same column) was really just re-scoring the breadth factor's signal a second time under
a different factor name in the market exposure composite.

Fixed to compute a genuine day-over-day A/D: each symbol's close vs. its own immediately-prior
available close (LAG), summed per date - live-verified against the real DB (2026-08-10 to
2026-08-19): the real ratio swung from 0.532 to 1.405 across that window, including 3 net-
decliner days, vs. the old metric's near-static 1.09-1.41 band over the same period.

These tests mock the DB layer (same convention as
tests/test_market_health_fetchers_comprehensive.py) and assert on the executed SQL text, since
that's what actually distinguishes the two metrics - a regression back to price_above_sma50/
trend_template_data would still return `(date, advances, declines)`-shaped rows and pass every
row-shape-only test in that file without this guard.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.market_health_fetchers import BreadthFetcher


class TestBreadthFetcherUsesRealDayOverDayAdvanceDecline:
    def test_query_does_not_read_trend_template_data_or_price_above_sma50(self) -> None:
        """Guard against regressing back to the trend-participation proxy this fix replaced -
        that data is the breadth factor's signal, not advance/decline's."""
        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [(date(2026, 8, 19), 100, 50)],  # advance/decline query
                [(date(2026, 8, 19), 8, 3)],  # new highs/lows query
            ]
            mock_db.return_value.__enter__.return_value = mock_cursor

            fetcher.fetch(date(2026, 8, 19), date(2026, 8, 19))

        ad_sql = mock_cursor.execute.call_args_list[0].args[0]
        assert "trend_template_data" not in ad_sql
        assert "price_above_sma50" not in ad_sql

    def test_query_computes_day_over_day_close_comparison_from_price_daily(self) -> None:
        """The replacement must be a genuine day-over-day close-vs-prior-close comparison
        (LAG over price_daily), not another proxy."""
        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [(date(2026, 8, 19), 100, 50)],
                [(date(2026, 8, 19), 8, 3)],
            ]
            mock_db.return_value.__enter__.return_value = mock_cursor

            fetcher.fetch(date(2026, 8, 19), date(2026, 8, 19))

        ad_sql = mock_cursor.execute.call_args_list[0].args[0]
        assert "price_daily" in ad_sql
        assert "LAG(close)" in ad_sql
        assert "close > prev_close" in ad_sql
        assert "close < prev_close" in ad_sql

    def test_lookback_window_extends_before_start_for_lag_continuity(self) -> None:
        """The inner window must reach back before `start` (so the first requested date has a
        real prior close to compare against), while the final result is still scoped to
        [start, end] only - live-confirmed via the params passed to the first execute() call."""
        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [(date(2026, 8, 19), 100, 50)],
                [(date(2026, 8, 19), 8, 3)],
            ]
            mock_db.return_value.__enter__.return_value = mock_cursor

            start = date(2026, 8, 19)
            fetcher.fetch(start, start)

        ad_params = mock_cursor.execute.call_args_list[0].args[1]
        lookback_start, end_param, result_start = ad_params
        assert lookback_start < start, "inner window must look back before `start` for LAG continuity"
        assert result_start == start, "outer WHERE must still scope the final result to the real `start`"
        assert end_param == start
