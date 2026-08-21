"""Regression test for the 2026-08-21 fix: _fetch_price_batch() used a flat calendar-day
date range (`date >= start_date AND date <= end_date`), which assumes ~5/7 of calendar days
are trading days. Live-confirmed 538 symbols with >=200 total price_daily rows (some with
years of history - e.g. EDN back to 2007, 4332 rows) trade on fewer than half their calendar
days, so they had under 200 rows inside ANY 400-day calendar window regardless of how the
window was sized. sma_200 (rolling(200) over the fetched close series) was permanently NaN
for these symbols, which cascades into trend_template_data.weinstein_stage being permanently
NULL (load_trend_analysis.py only assigns a stage when sma_200 is present) even though the
symbol has ample real history.

Fix: fetch each symbol's most recent _TRADING_DAYS_LOOKBACK rows via a LATERAL join + LIMIT,
not a calendar-day range - this guarantees a full trading-day lookback regardless of how
sparsely a symbol trades.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_technical_indicators import (
    OUTPUT_WINDOW_DAYS_TECH_INDICATORS,
    VectorizedTechnicalLoader,
)


class TestThinTickerLookbackUsesTradingDayCount:
    def test_fetch_uses_lateral_limit_not_calendar_range(self) -> None:
        loader = VectorizedTechnicalLoader()
        cur = MagicMock()
        cur.fetchall.return_value = []

        with patch("loaders.load_technical_indicators.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            loader._fetch_price_batch(["EDN", "FAMI"], date(2025, 7, 17), date(2026, 8, 20))

        executed_sql, params = cur.execute.call_args.args
        assert "LATERAL" in executed_sql
        assert "LIMIT %s" in executed_sql
        # Symbols list, end_date, and the trading-day lookback count - no start_date bound,
        # so a thin ticker's window isn't capped by calendar span.
        assert params == [["EDN", "FAMI"], date(2026, 8, 20), loader._TRADING_DAYS_LOOKBACK]

    def test_lookback_covers_roc_252d_across_the_full_output_window(self) -> None:
        # rolling(252) over N fetched rows is only valid for the LAST (N - 252 + 1) rows -
        # every row inside the OUTPUT_WINDOW (the rows actually written) needs a valid
        # roc_252d, not just the single most recent fetched row, or roc_252d/
        # minervini_trend_score regress to NULL for most of the output window even on
        # dense tickers (the exact bug the prior 300->400 calendar-day fix addressed).
        # A generous trading-day upper bound for the output window's calendar span.
        max_output_window_trading_days = OUTPUT_WINDOW_DAYS_TECH_INDICATORS
        valid_rows_at_end = VectorizedTechnicalLoader._TRADING_DAYS_LOOKBACK - 252 + 1
        assert valid_rows_at_end >= max_output_window_trading_days
