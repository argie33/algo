#!/usr/bin/env python3
"""Regression test for the 2026-08-10 fix: PriceFetcher.fetch_incremental() and
fetch_batch_incremental() computed `end_date` as "today" for any call that wasn't
strictly *during* market hours (`market_open_time <= now_et < market_close_time`),
so a pre-market call (e.g. 8:21 AM ET) fell through untouched with end_date=today, even
though today has no data at all yet (market hasn't opened).

Live-reproduced: a Monday 8:21 AM ET run computed a fetch window covering only Sunday
and pre-market Monday (no data possible on either day). yfinance returned "possibly
delisted; no price data found" for essentially the entire universe (1572 symbols in one
run) - not a real API/data problem, just an impossible date range being requested. The
"start >= end" MORNING_CONTEXT fallback had the same problem one level down: a flat
`timedelta(days=1)` can itself land on a weekend/holiday.

Fixed to reuse the same trading-day-anchored pattern already applied elsewhere in this
codebase (Phase 1 freshness, Phase 7 buy-signal lookback, Phase 8 stale-signal circuit
breaker, sector_industry_daily) via MarketCalendar.get_previous_trading_day(): anything
before market close must ask about the previous TRADING day, not a flat "yesterday" or
"today only if we happen to be mid-session right now".
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from loaders.price_fetcher import PriceFetcher


def _fake_utcnow(et_year, et_month, et_day, et_hour, et_minute=0):
    """A UTC datetime that lands on the given ET wall-clock time (ET = UTC-4 in August)."""
    return datetime(et_year, et_month, et_day, et_hour + 4, et_minute, tzinfo=timezone.utc)


class TestFetchIncrementalPreMarketWeekendGap:
    def test_monday_premarket_fetches_through_friday_not_sunday(self):
        """The core bug: Monday 8:21 AM ET (pre-market), watermark is well in the past
        (`since` far behind) - end_date must resolve to the previous Friday, not Sunday
        (flat -1 day) and not "today" (the old bug)."""
        fetcher = PriceFetcher()
        captured = {}

        def _capture(symbol, start, end, max_retries=5):
            captured["start"], captured["end"] = start, end
            return []

        with (
            patch("loaders.price_fetcher.datetime") as mock_dt,
            patch.object(fetcher, "_try_fetch", side_effect=_capture),
        ):
            mock_dt.now.return_value = _fake_utcnow(2026, 8, 10, 8, 21)  # Monday pre-market
            fetcher.fetch_incremental("TEST", since=date(2026, 8, 1), is_eod_pipeline=False)

        assert captured["end"] == date(2026, 8, 7), (
            f"Expected end_date to land on the previous Friday (2026-08-07), got {captured['end']}"
        )

    def test_monday_premarket_morning_context_fallback_lands_on_thursday_not_saturday(self):
        """When the watermark is already at/past the resolved end_date, the MORNING_CONTEXT
        fallback must also land on a real trading day, not a flat calendar -1 day."""
        fetcher = PriceFetcher()
        captured = {}

        def _capture(symbol, start, end, max_retries=5):
            captured["start"], captured["end"] = start, end
            return []

        with (
            patch("loaders.price_fetcher.datetime") as mock_dt,
            patch.object(fetcher, "_try_fetch", side_effect=_capture),
        ):
            mock_dt.now.return_value = _fake_utcnow(2026, 8, 10, 8, 21)  # Monday pre-market
            # Watermark already at/after the resolved end_date (2026-08-07) forces the fallback.
            fetcher.fetch_incremental("TEST", since=date(2026, 8, 10), is_eod_pipeline=False)

        assert captured["end"] == date(2026, 8, 7)
        assert captured["start"] == date(2026, 8, 6), (
            f"Expected fallback start to land on Thursday 2026-08-06, got {captured['start']}"
        )

    def test_during_market_hours_still_fetches_through_yesterday(self):
        """Sanity check: the existing during-market-hours behavior must be unaffected."""
        fetcher = PriceFetcher()
        captured = {}

        def _capture(symbol, start, end, max_retries=5):
            captured["start"], captured["end"] = start, end
            return []

        with (
            patch("loaders.price_fetcher.datetime") as mock_dt,
            patch.object(fetcher, "_try_fetch", side_effect=_capture),
        ):
            mock_dt.now.return_value = _fake_utcnow(2026, 8, 11, 11, 0)  # Tuesday, market open
            fetcher.fetch_incremental("TEST", since=date(2026, 8, 1), is_eod_pipeline=False)

        assert captured["end"] == date(2026, 8, 10), (
            f"Expected end_date to be Monday's close (2026-08-10) during Tuesday market hours, got {captured['end']}"
        )

    def test_eod_pipeline_still_fetches_today_unconditionally(self):
        """Sanity check: EOD pipeline runs (after close) must still target today, unaffected
        by this fix (which only touches the not-is_eod_pipeline branch)."""
        fetcher = PriceFetcher()
        captured = {}

        def _capture(symbol, start, end, max_retries=5):
            captured["start"], captured["end"] = start, end
            return []

        with (
            patch("loaders.price_fetcher.datetime") as mock_dt,
            patch.object(fetcher, "_try_fetch", side_effect=_capture),
        ):
            mock_dt.now.return_value = _fake_utcnow(2026, 8, 10, 17, 0)  # Monday, after close
            fetcher.fetch_incremental("TEST", since=date(2026, 8, 1), is_eod_pipeline=True)

        assert captured["end"] == date(2026, 8, 10)


class TestFetchBatchIncrementalPreMarketWeekendGap:
    def test_monday_premarket_batch_fetches_through_friday_not_sunday(self):
        fetcher = PriceFetcher()
        captured = {}

        def _capture(symbols, start, end, batch_size, attempt):
            captured["start"], captured["end"] = start, end
            return {s: [] for s in symbols}

        with (
            patch("loaders.price_fetcher.datetime") as mock_dt,
            patch.object(fetcher, "_fetch_with_fallback", side_effect=_capture),
        ):
            mock_dt.now.return_value = _fake_utcnow(2026, 8, 10, 8, 21)  # Monday pre-market
            fetcher.fetch_batch_incremental(["TEST"], since=date(2026, 8, 1), is_eod_pipeline=False)

        assert captured["end"] == date(2026, 8, 7), (
            f"Expected batch end_date to land on the previous Friday (2026-08-07), got {captured['end']}"
        )

    def test_monday_premarket_batch_morning_context_fallback_lands_on_thursday(self):
        fetcher = PriceFetcher()
        captured = {}

        def _capture(symbols, start, end, batch_size, attempt):
            captured["start"], captured["end"] = start, end
            return {s: [] for s in symbols}

        with (
            patch("loaders.price_fetcher.datetime") as mock_dt,
            patch.object(fetcher, "_fetch_with_fallback", side_effect=_capture),
        ):
            mock_dt.now.return_value = _fake_utcnow(2026, 8, 10, 8, 21)  # Monday pre-market
            fetcher.fetch_batch_incremental(["TEST"], since=date(2026, 8, 10), is_eod_pipeline=False)

        assert captured["end"] == date(2026, 8, 7)
        assert captured["start"] == date(2026, 8, 6), (
            f"Expected batch fallback start to land on Thursday 2026-08-06, got {captured['start']}"
        )
