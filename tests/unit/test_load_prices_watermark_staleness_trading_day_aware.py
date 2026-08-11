"""Regression test for the 2026-08-11 fix: PriceLoader._load_batch()'s SESSION 297
staleness "deadlock breaker" used raw calendar-day math on the MIN watermark across
potentially thousands of symbols. A perfectly healthy Friday watermark on a Monday run is
3 calendar days old but only 1 trading day old - with `> 2` calendar days as the
threshold, this fired on every single Monday/post-holiday run, forcing an unnecessary
7-day re-fetch for prices (the heaviest-workload loader, 5000+ symbols) even though
nothing was actually stuck. Same bug class as phase8_signal_age_calendar_vs_trading_day
and 6 other same-day instances - this project's date math must be trading-day-aware.

Fixed to count actual trading days elapsed via MarketCalendar, same pattern already used
in position_sizer.py's VIX-staleness check.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader


def _make_loader(run_date):
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    loader.interval = "1d"
    loader.chunk_size = 10_000
    loader._backfill_days = 0
    loader._router = MagicMock()
    loader._run_date_context = run_date
    loader._stats = {
        "symbols_failed": 0,
        "symbols_processed": 0,
        "symbols_skipped_by_watermark": 0,
        "rows_fetched": 0,
        "rows_quality_dropped": 0,
        "rows_inserted": 0,
        "source_distribution": {},
    }
    loader.transform = lambda rows: rows
    loader._validate_row = lambda row: True
    loader.watermark_from_rows = lambda rows: max(r["date"] for r in rows)
    loader._bulk_insert_mgr = MagicMock()
    loader._bulk_insert_mgr.bulk_insert.return_value = 1
    loader._watermark = MagicMock()
    loader._is_eod_pipeline = False
    return loader


def _row(symbol, d):
    return {"symbol": symbol, "date": d, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100}


def _fake_db_context(max_dates_by_symbol):
    def factory(mode, **kwargs):
        ctx = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = list(max_dates_by_symbol.items())
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    return factory


class TestWatermarkStalenessTradingDayAware:
    def test_friday_watermark_on_monday_run_not_treated_as_stale_deadlock(self):
        """2026-08-07 is a Friday, 2026-08-10 is the following Monday (confirmed trading
        day per this session's own orchestrator logs) - a completely healthy 1-trading-day
        gap that must NOT trigger the >2-day deadlock-breaker, even though it's 3 calendar
        days."""
        run_date = date(2026, 8, 10)  # Monday
        watermark = date(2026, 8, 7)  # preceding Friday
        loader = _make_loader(run_date)
        loader._watermark.get_watermarks_bulk.return_value = {"AAPL": watermark}

        captured = {}

        def fake_fetch(symbols, since, **kwargs):
            captured["since"] = since
            return {"AAPL": [dict(_row("AAPL", run_date))]}

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        with patch(
            "loaders.load_prices.DatabaseContext",
            side_effect=_fake_db_context({"AAPL": watermark}),
        ):
            loader._load_batch(["AAPL"])

        assert captured["since"] == watermark, (
            f"a healthy weekend-only gap must not be widened to today-7, got since={captured['since']}"
        )

    def test_genuinely_stale_watermark_still_triggers_deadlock_breaker(self):
        """A watermark that's actually multiple TRADING days old (not just a weekend span)
        must still trigger the deadlock-breaker - this fix must not swallow real staleness,
        only the calendar-vs-trading-day false positive."""
        run_date = date(2026, 8, 10)  # Monday
        watermark = date(2026, 8, 3)  # the Monday before - a full stale trading week
        loader = _make_loader(run_date)
        loader._watermark.get_watermarks_bulk.return_value = {"AAPL": watermark}

        captured = {}

        def fake_fetch(symbols, since, **kwargs):
            captured["since"] = since
            return {"AAPL": [dict(_row("AAPL", run_date))]}

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        with patch(
            "loaders.load_prices.DatabaseContext",
            side_effect=_fake_db_context({"AAPL": watermark}),
        ):
            loader._load_batch(["AAPL"])

        assert captured["since"] == run_date - __import__("datetime").timedelta(days=7), (
            f"a genuinely multi-trading-day-stale watermark must still force the 7-day-back "
            f"re-fetch, got since={captured['since']}"
        )
