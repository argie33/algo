"""Regression test for the 2026-08-17 fix: EnhancedQualityGrowthMetricsLoader.run() never
used its own watermark to skip already-current symbols, and never advanced it after a
success - so every invocation (including same-day retries after a partial failure/timeout)
unconditionally re-ran all 3 yfinance calls for the full ~4,900-symbol universe.

Live-measured 2026-08-17: ~2.9s/symbol -> ~4h for one full run of this loader alone, serially
blocking every downstream "metrics" pipeline loader (scores/buy_sell) queued behind it -
directly implicated in stock_scores/buy_sell staying stale for days despite repeated retries.

This test proves: (1) a symbol whose watermark already shows today is skipped without calling
fetch_incremental, and (2) a symbol that succeeds today has its watermark advanced so a later
same-day retry would see it as current.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _loader(watermarks: dict) -> EnhancedQualityGrowthMetricsLoader:
    loader = EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)
    loader._backfill_days = 0
    loader._watermark = MagicMock()
    loader._watermark.get_current_watermark.side_effect = lambda symbol: watermarks.get(symbol)
    loader.per_symbol_timeout_seconds = 5.0
    return loader


class TestSameDayResume:
    def test_symbol_already_current_today_is_skipped(self) -> None:
        today = datetime.now(EASTERN_TZ).date()
        loader = _loader({"DONE": today, "TODO": today - timedelta(days=1), "NEVER": None})

        fetch_calls = []

        def fake_fetch_incremental(symbol, since_date=None):
            fetch_calls.append(symbol)
            return [{"symbol": symbol, "gross_margin_trend": 1.5}]

        write_cur = MagicMock()

        def fake_db_context(mode, **kwargs):
            ctx = MagicMock()
            ctx.__enter__.return_value = write_cur
            ctx.__exit__.return_value = False
            return ctx

        with (
            patch.object(loader, "fetch_incremental", side_effect=fake_fetch_incremental),
            patch("loaders.load_enhanced_quality_growth_metrics.DatabaseContext", side_effect=fake_db_context),
            patch("loaders.load_enhanced_quality_growth_metrics.LoaderStatusManager", return_value=MagicMock()),
        ):
            stats = loader.run(["DONE", "TODO", "NEVER"], parallelism=1)

        # DONE's watermark already shows today - fetch_incremental (the 3 live yfinance calls)
        # must never be attempted for it.
        assert "DONE" not in fetch_calls
        assert "TODO" in fetch_calls
        assert "NEVER" in fetch_calls

        # All 3 still count as succeeded for this run's stats (DONE via the skip path).
        assert stats["symbols_succeeded"] == 3
        assert stats["symbols_failed"] == 0

    def test_successful_symbol_advances_watermark_to_today(self) -> None:
        loader = _loader({"AAA": None})

        def fake_fetch_incremental(symbol, since_date=None):
            return [{"symbol": symbol, "gross_margin_trend": 1.5}]

        write_cur = MagicMock()

        def fake_db_context(mode, **kwargs):
            ctx = MagicMock()
            ctx.__enter__.return_value = write_cur
            ctx.__exit__.return_value = False
            return ctx

        with (
            patch.object(loader, "fetch_incremental", side_effect=fake_fetch_incremental),
            patch("loaders.load_enhanced_quality_growth_metrics.DatabaseContext", side_effect=fake_db_context),
            patch("loaders.load_enhanced_quality_growth_metrics.LoaderStatusManager", return_value=MagicMock()),
        ):
            stats = loader.run(["AAA"], parallelism=1)

        assert stats["symbols_succeeded"] == 1
        loader._watermark.advance_watermark.assert_called_once()
        _, kwargs = loader._watermark.advance_watermark.call_args
        assert kwargs["symbol"] == "AAA"
        assert kwargs["new_watermark"] == datetime.now(EASTERN_TZ).date()
        assert kwargs["rows_loaded"] == 1
