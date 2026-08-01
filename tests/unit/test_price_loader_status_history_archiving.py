"""Regression test for the 2026-07-27 fix: PriceLoader._update_loader_status() (loaders/
load_prices.py) writes data_loader_status directly via its own finalize path instead of
going through utils/loaders/status_manager.py's StatusManager or utils/optimal_loader.py's
_update_final_status - both of which archive to data_loader_status_history for the
dashboard's failure-pattern analysis (dashboard/freshness_enhancements.py's
enrich_health_item_with_failure_pattern). Because PriceLoader overrides its own finalize
method entirely, the earlier archival fix applied to OptimalLoader's base-class writer never
reached price_daily - confirmed live: 0 rows in data_loader_status_history for price_daily
despite dozens of runs/day, for the one loader Phase 1's staleness check reads directly.

Fixed by adding the same SAVEPOINT-wrapped archive INSERT + 100-row retention DELETE used
by utils/optimal_loader.py and utils/loader_infrastructure.py.
"""

from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader


def _make_loader():
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    loader.interval = "1d"
    loader._stats = {"symbols_total": 10, "symbols_processed": 10, "start_time": 1_700_000_000.0}
    return loader


class TestPriceLoaderStatusHistoryArchiving:
    def test_update_loader_status_archives_to_history(self):
        loader = _make_loader()
        cur = MagicMock()
        # First SELECT: COUNT(*), MAX(date) from price_daily
        # Second SELECT: COUNT(DISTINCT symbol) from latest date
        # Third SELECT (in archive): execution_started, execution_completed, error_message, row_count, completion_pct, symbols_loaded, symbol_count
        cur.fetchone.side_effect = [(500, "2026-07-31"), (10,), (None, None, None, 500, 100.0, 10, 10)]
        cur.rowcount = 1  # Status manager checks rowcount

        with (
            patch("loaders.load_prices.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
            patch("loaders.load_prices._invalidate_phase1_cache"),
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur
            loader._update_loader_status()

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert any("SAVEPOINT archive_price_daily_history" in sql for sql in executed)
        assert any("INSERT INTO data_loader_status_history" in sql for sql in executed)
        assert any("DELETE FROM data_loader_status_history" in sql for sql in executed)
        assert any("RELEASE SAVEPOINT archive_price_daily_history" in sql for sql in executed)
        # the real status UPSERT (issued before the archive block) must still have happened
        assert any("INSERT INTO data_loader_status " in sql for sql in executed)

    def test_archive_failure_rolls_back_savepoint_without_raising(self):
        loader = _make_loader()
        cur = MagicMock()
        # First SELECT: COUNT(*), MAX(date) from price_daily
        # Second SELECT: COUNT(DISTINCT symbol) from latest date
        # Third SELECT (in archive): execution_started, execution_completed, error_message, row_count, completion_pct, symbols_loaded, symbol_count
        cur.fetchone.side_effect = [(500, "2026-07-31"), (10,), (None, None, None, 500, 100.0, 10, 10)]
        cur.rowcount = 1  # Status manager checks rowcount

        def _execute(sql, *args, **kwargs):
            if "INSERT INTO data_loader_status_history" in sql:
                raise Exception("boom")

        with (
            patch("loaders.load_prices.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
            patch("loaders.load_prices._invalidate_phase1_cache"),
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur
            cur.execute.side_effect = _execute
            loader._update_loader_status()  # must not raise

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert any("ROLLBACK TO SAVEPOINT archive_price_daily_history" in sql for sql in executed)
        # the real status UPSERT (issued before the archive block) must still have happened
        assert any("INSERT INTO data_loader_status " in sql for sql in executed)
