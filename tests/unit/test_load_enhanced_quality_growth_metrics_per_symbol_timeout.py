"""Regression test for the 2026-08-16 per-symbol timeout fix to
EnhancedQualityGrowthMetricsLoader.run().

Live-reproduced 2026-08-16: growth_metrics/quality_metrics went completely silent (zero log
output at any level) after a normal per-symbol commit, and stayed silent for 4+ hours until
local_loader_scheduler's external "0%% stall for >1800s" subprocess watchdog force-killed it.
Before this fix, run()'s per-symbol loop had no bound of its own - only the individual
yfinance sub-calls inside fetch_incremental() were capped at 20s each, so a stall anywhere
else (a DB read, a lock wait, anything) blocked every symbol queued behind it indefinitely,
with no per-symbol diagnostic logged. This test proves a stuck symbol is abandoned after
per_symbol_timeout_seconds and the loop keeps moving through the rest of the batch.
"""

import time
from unittest.mock import MagicMock, patch

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader


def _loader(timeout_seconds: float) -> EnhancedQualityGrowthMetricsLoader:
    loader = EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)
    loader._backfill_days = 0
    loader._watermark = MagicMock()
    loader._watermark.get_current_watermark.return_value = None
    loader.per_symbol_timeout_seconds = timeout_seconds
    return loader


class TestPerSymbolTimeout:
    def test_stalled_symbol_is_abandoned_and_loop_continues(self):
        loader = _loader(timeout_seconds=0.2)

        def fake_fetch_incremental(symbol, since_date=None):
            if symbol == "STUCK":
                # Simulate the live 4+ hour silent hang - far longer than the test's 0.2s
                # per-symbol timeout, but the test itself must not actually wait that long.
                time.sleep(5)
                return [{"symbol": symbol, "gross_margin_trend": 1.5}]
            return [{"symbol": symbol, "gross_margin_trend": 1.5}]

        write_cur = MagicMock()

        def fake_db_context(mode, **kwargs):
            ctx = MagicMock()
            ctx.__enter__.return_value = write_cur
            ctx.__exit__.return_value = False
            return ctx

        status_managers: dict[str, MagicMock] = {}

        def fake_status_manager(table_name):
            mgr = MagicMock()
            status_managers[table_name] = mgr
            return mgr

        with (
            patch.object(loader, "fetch_incremental", side_effect=fake_fetch_incremental),
            patch("loaders.load_enhanced_quality_growth_metrics.DatabaseContext", side_effect=fake_db_context),
            patch("loaders.load_enhanced_quality_growth_metrics.LoaderStatusManager", side_effect=fake_status_manager),
        ):
            start = time.monotonic()
            stats = loader.run(["BEFORE", "STUCK", "AFTER"], parallelism=1)
            elapsed = time.monotonic() - start

        # The whole run must complete quickly (bounded by the 0.2s per-symbol timeout), not
        # block for the full 5s the STUCK symbol's fetch actually takes.
        assert elapsed < 4.0

        # BEFORE and AFTER both succeed - the stalled symbol must not block symbols after it.
        assert stats["symbols_succeeded"] == 2
        assert stats["symbols_failed"] == 1
