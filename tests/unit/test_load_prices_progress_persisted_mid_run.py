"""Regression test for the 2026-08-17 fix: PriceLoader never persisted mid-run progress.

`_monitor_and_enforce_timeouts()` is called once per batch and already computes a real
`processed/total_symbols` completion percentage for its own log line ("Progress: 3000/4925
symbols (61%)"), but that number was never written to `data_loader_status` - the loader only
calls `mark_running()` at the very start and `mark_completed()`/`mark_failed()` at the very end.
Live-confirmed: the dashboard's price_daily row sat frozen at completion_pct=0/symbols_loaded=0
for a multi-hour run that was genuinely 61% done per its own logs, because nothing in between
ever called `LoaderStatusManager.update_progress()`.
"""

from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader


def _make_loader() -> PriceLoader:
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    loader.batch_size = 500
    loader.fetcher = MagicMock()
    loader.fetcher.get_current_batch_size.return_value = 500
    loader._rate_limit_circuit_break_threshold = 999999
    return loader


class TestProgressPersistedMidRun:
    def test_batch_progress_is_persisted_to_status_manager(self) -> None:
        loader = _make_loader()

        with patch("loaders.load_prices.LoaderStatusManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr_cls.return_value = mock_mgr

            result = loader._monitor_and_enforce_timeouts(
                elapsed_sec=120.0,
                processed=3000,
                total_symbols=4925,
                batch_times=[10.0, 12.0],
                batches_count=10,
                task_timeout_sec=86400,
                emergency_mode_threshold=999999,
                completion_threshold_pct=0.95,
                emergency_mode_enabled=False,
                batch_elapsed=11.0,
                max_concurrent=1,
            )

        mock_mgr_cls.assert_called_once_with("price_daily")
        mock_mgr.update_progress.assert_called_once_with(
            symbols_loaded=3000,
            symbol_count=4925,
            completion_pct=3000 / 4925 * 100,
        )
        assert result["status"] == "continue"

    def test_status_manager_db_error_does_not_crash_the_load(self) -> None:
        """A monitoring-side DB hiccup must not take down the actual price load."""
        loader = _make_loader()

        import psycopg2

        with patch("loaders.load_prices.LoaderStatusManager") as mock_mgr_cls:
            mock_mgr_cls.return_value.update_progress.side_effect = psycopg2.OperationalError("connection lost")

            result = loader._monitor_and_enforce_timeouts(
                elapsed_sec=60.0,
                processed=500,
                total_symbols=4925,
                batch_times=[10.0],
                batches_count=10,
                task_timeout_sec=86400,
                emergency_mode_threshold=999999,
                completion_threshold_pct=0.95,
                emergency_mode_enabled=False,
                batch_elapsed=10.0,
                max_concurrent=1,
            )

        assert result["status"] == "continue"
