"""Regression test for the 2026-07-28 fix: OptimalLoader.load_global() had no success-path
status transition at all.

load_global() (used by 7 loaders: institutional_holdings_13f, load_market_constituents,
load_sector_industry_daily, load_algo_metrics_daily, load_market_status_daily,
load_aaii_sentiment, load_naaim - anything invoked via `run_loader(..., global_mode=True)`)
called `self._infrastructure.update_loader_status("RUNNING")` once at the top, but every one
of its 4 return points (the two data_unavailable-marker shapes, the empty-list case, and the
real success case) returned without ever transitioning status away from RUNNING. "FAILED" is
only reached via an exception path elsewhere - success was structurally unreachable.

This was historically masked by pipeline_health.py's log_health_check() age-based sweep,
which silently relabeled any RUNNING row HEALTHY based on the target table's row age - the
exact bug fixed earlier the same session (see
test_monitoring_health_system.py::test_log_health_check_preserves_running_status_not_just_consecutive_failures).
That fix makes THIS gap visible instead: preserving RUNNING (correct for a genuinely crashed
loader) also means a successfully-completed global_mode loader now sits at RUNNING forever
and eventually trips _check_stuck_loaders()'s 15-minute heartbeat-staleness alert as a false
"crashed" positive.

Fixed by calling update_loader_status("COMPLETED") at all 4 return points.
"""

from unittest.mock import MagicMock, patch

from utils.optimal_loader import OptimalLoader


def _make_loader(table_name="test_global_table"):
    loader = OptimalLoader.__new__(OptimalLoader)
    loader.table_name = table_name
    loader.watermark_field = "date"
    loader._execution_start_time = None
    loader._infrastructure = MagicMock()
    loader._status_manager = MagicMock()
    loader._bulk_insert_mgr = MagicMock()
    loader._stats = MagicMock()
    return loader


def _run_load_global(loader, fetch_global_return):
    lock_manager = MagicMock()
    lock_manager.acquire.return_value = True
    lock_manager.cleanup_expired_locks.return_value = 0

    read_cur = MagicMock()
    read_cur.fetchone.return_value = (None,)  # MAX(watermark_field) -> no prior watermark

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur
        ctx.__exit__.return_value = False
        return ctx

    loader.fetch_global = MagicMock(return_value=fetch_global_return)
    loader.transform = MagicMock(side_effect=lambda rows: rows)
    loader._bulk_insert_mgr.bulk_insert.return_value = len(fetch_global_return) if isinstance(fetch_global_return, list) else 0
    loader._log_execution_history = MagicMock()

    conn_manager = MagicMock()

    with patch("utils.db.local_file_lock.get_lock_manager", return_value=lock_manager), \
         patch("utils.optimal_loader.DatabaseContext", side_effect=fake_db_context), \
         patch("utils.db.pooled_connection_manager.PooledConnectionManager", return_value=conn_manager), \
         patch("utils.db.pooled_context_var.set_pooled_connection"):
        return loader.load_global()


class TestLoadGlobalCompletionStatus:
    def test_successful_load_marks_completed(self):
        loader = _make_loader()
        rows = [{"symbol": "AAPL", "date": "2026-07-28"}]

        result = _run_load_global(loader, rows)

        assert result == 1
        loader._status_manager.mark_completed.assert_called()
        loader._status_manager.mark_running.assert_called()

    def test_empty_result_still_marks_completed_not_left_running(self):
        loader = _make_loader()

        result = _run_load_global(loader, [])

        assert result == 0
        loader._status_manager.mark_completed.assert_called()

    def test_data_unavailable_marker_dict_still_marks_completed(self):
        loader = _make_loader()

        result = _run_load_global(loader, {"data_unavailable": True, "reason": "no_source_available"})

        assert result == 0
        loader._status_manager.mark_completed.assert_called()

    def test_list_wrapped_data_unavailable_marker_still_marks_completed(self):
        loader = _make_loader()

        result = _run_load_global(loader, [{"data_unavailable": True, "reason": "no_source_available"}])

        assert result == 0
        loader._status_manager.mark_completed.assert_called()

    def test_successful_load_passes_current_run_counts_to_mark_completed(self):
        # CRITICAL FIX 2026-08-03: load_global() used to call mark_completed() with no
        # arguments, so its safety check re-read symbol_count/symbols_loaded straight from
        # whatever the DB row already held (e.g. symbol_count=0 left over from the initial
        # _ensure_status_row() insert, since load_global() never calls
        # mark_running(symbol_count=...) / update_progress() to keep it in sync). Live-
        # confirmed on stock_symbols: a real, successful, 5555-row MarketConstituentsLoader
        # run was marked FAILED at "0.00% complete (3183/0)". Fixed by passing this run's own
        # verified insert count instead of relying on a stale DB re-read.
        loader = _make_loader()
        rows = [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "GOOGL"}]

        result = _run_load_global(loader, rows)

        assert result == 3
        # execution_duration_sec (added separately, real elapsed time) is intentionally not
        # pinned to a value here - just confirm the current-run counts this test targets.
        loader._status_manager.mark_completed.assert_called_once()
        call_kwargs = loader._status_manager.mark_completed.call_args.kwargs
        assert call_kwargs["current_run_symbols_loaded"] == 3
        assert call_kwargs["current_run_symbol_count"] == 3


class TestEarlyReturnBranchesPassExplicitZeroCounts:
    """BUG FOUND 2026-08-10 (same class as the 2026-08-03 fix above, and
    derive_aggregate_prices' 2026-08-10 fix): the 3 early-return branches
    (data_unavailable dict marker, list-wrapped marker, empty list) called
    mark_completed() with no current_run_* overrides, so a genuinely-empty run today
    would silently inherit symbol_count/symbols_loaded from whatever a PAST run last
    wrote to this row - misrepresenting today's real "0 rows, nothing to do" outcome.
    """

    def test_empty_result_passes_explicit_zero_counts(self):
        loader = _make_loader()

        _run_load_global(loader, [])

        loader._status_manager.mark_completed.assert_called_once()
        call_kwargs = loader._status_manager.mark_completed.call_args.kwargs
        assert call_kwargs["current_run_symbols_loaded"] == 0
        assert call_kwargs["current_run_symbol_count"] == 0
        assert call_kwargs["min_completion_pct"] == 0.0

    def test_data_unavailable_marker_passes_explicit_zero_counts(self):
        loader = _make_loader()

        _run_load_global(loader, {"data_unavailable": True, "reason": "no_source_available"})

        loader._status_manager.mark_completed.assert_called_once()
        call_kwargs = loader._status_manager.mark_completed.call_args.kwargs
        assert call_kwargs["current_run_symbols_loaded"] == 0
        assert call_kwargs["current_run_symbol_count"] == 0
        assert call_kwargs["min_completion_pct"] == 0.0

    def test_list_wrapped_marker_passes_explicit_zero_counts(self):
        loader = _make_loader()

        _run_load_global(loader, [{"data_unavailable": True, "reason": "no_source_available"}])

        loader._status_manager.mark_completed.assert_called_once()
        call_kwargs = loader._status_manager.mark_completed.call_args.kwargs
        assert call_kwargs["current_run_symbols_loaded"] == 0
        assert call_kwargs["current_run_symbol_count"] == 0
        assert call_kwargs["min_completion_pct"] == 0.0
