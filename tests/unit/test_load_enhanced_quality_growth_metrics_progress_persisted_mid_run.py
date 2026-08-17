"""Regression test for the 2026-08-17 fix: EnhancedQualityGrowthMetricsLoader.run() never
persisted mid-run progress.

Same bug class as the load_prices.py fix from the same day (see
tests/unit/test_load_prices_progress_persisted_mid_run.py): run() called mark_running() at the
start and mark_completed()/mark_failed() at the end, but nothing in between - the per-symbol
loop's real progress never reached data_loader_status. Live-confirmed: the dashboard's
growth_metrics/quality_metrics rows sat frozen at completion_pct=0/symbols_loaded=0 for over an
hour on a run whose own log lines showed it steadily working through symbols alphabetically,
indistinguishable from a hang.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader


def _loader() -> EnhancedQualityGrowthMetricsLoader:
    loader = EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)
    loader._backfill_days = 0
    loader._watermark = MagicMock()
    loader._watermark.get_current_watermark.return_value = None
    loader.per_symbol_timeout_seconds = 5.0
    return loader


class TestProgressPersistedMidRun:
    def test_progress_persisted_for_both_tables_after_run(self) -> None:
        loader = _loader()

        def fake_fetch_incremental(symbol, since_date=None):
            return [{"symbol": symbol, "gross_margin_trend": 1.5}]

        write_cur = MagicMock()

        def fake_db_context(mode, **kwargs):
            ctx = MagicMock()
            ctx.__enter__.return_value = write_cur
            ctx.__exit__.return_value = False
            return ctx

        status_managers: dict[str, MagicMock] = {}

        def fake_status_manager(table_name):
            status_managers.setdefault(table_name, MagicMock())
            return status_managers[table_name]

        with (
            patch.object(loader, "fetch_incremental", side_effect=fake_fetch_incremental),
            patch("loaders.load_enhanced_quality_growth_metrics.DatabaseContext", side_effect=fake_db_context),
            patch(
                "loaders.load_enhanced_quality_growth_metrics.LoaderStatusManager",
                side_effect=fake_status_manager,
            ),
        ):
            stats = loader.run(["AAA", "BBB", "CCC"], parallelism=1)

        assert stats["symbols_succeeded"] == 3

        # Progress must be persisted for BOTH shared status tables, not just marked
        # running/completed with nothing in between.
        for table in ("quality_metrics", "growth_metrics"):
            mgr = status_managers[table]
            mgr.update_progress.assert_called_once_with(
                symbols_loaded=3,
                symbol_count=3,
                completion_pct=100.0,
            )

    def test_status_manager_db_error_does_not_crash_the_load(self) -> None:
        """A monitoring-side DB hiccup on the progress update must not take down the load."""
        loader = _loader()

        import psycopg2

        def fake_fetch_incremental(symbol, since_date=None):
            return [{"symbol": symbol, "gross_margin_trend": 1.5}]

        write_cur = MagicMock()

        def fake_db_context(mode, **kwargs):
            ctx = MagicMock()
            ctx.__enter__.return_value = write_cur
            ctx.__exit__.return_value = False
            return ctx

        def fake_status_manager(table_name):
            mgr = MagicMock()
            mgr.update_progress.side_effect = psycopg2.OperationalError("connection lost")
            return mgr

        with (
            patch.object(loader, "fetch_incremental", side_effect=fake_fetch_incremental),
            patch("loaders.load_enhanced_quality_growth_metrics.DatabaseContext", side_effect=fake_db_context),
            patch(
                "loaders.load_enhanced_quality_growth_metrics.LoaderStatusManager",
                side_effect=fake_status_manager,
            ),
        ):
            stats = loader.run(["AAA"], parallelism=1)

        assert stats["symbols_succeeded"] == 1

    def test_progress_persisted_even_when_every_symbol_is_watermark_skipped(self) -> None:
        """A same-day retry where every symbol is already watermark-current must not skip
        the progress-persist block for the whole run - that's exactly the scenario an operator
        is watching the dashboard for."""
        loader = _loader()
        loader._watermark.get_current_watermark.return_value = datetime.now(timezone.utc).date()

        status_managers: dict[str, MagicMock] = {}

        def fake_status_manager(table_name):
            status_managers.setdefault(table_name, MagicMock())
            return status_managers[table_name]

        with (
            patch.object(loader, "fetch_incremental") as mock_fetch,
            patch(
                "loaders.load_enhanced_quality_growth_metrics.LoaderStatusManager",
                side_effect=fake_status_manager,
            ),
        ):
            stats = loader.run(["AAA", "BBB", "CCC"], parallelism=1)

        # None of these should have gone through actual fetch/write work.
        mock_fetch.assert_not_called()
        assert stats["symbols_succeeded"] == 3

        for table in ("quality_metrics", "growth_metrics"):
            status_managers[table].update_progress.assert_called_once_with(
                symbols_loaded=3,
                symbol_count=3,
                completion_pct=100.0,
            )
