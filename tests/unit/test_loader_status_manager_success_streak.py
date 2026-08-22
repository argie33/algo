"""Tests for LoaderStatusManager's success-streak tracking (migration 1163).

data_loader_status.execution_completed is stamped on every terminal outcome
(mark_completed, mark_failed, mark_timeout all set it), so it can't distinguish
"last time this loader finished successfully" from "last time it finished at all"
(including a failure). consecutive_failures/last_success_at close that gap:
mark_completed resets the streak and stamps success time; mark_failed/mark_timeout
increment the streak without touching last_success_at.
"""

from unittest.mock import MagicMock, patch

from utils.loaders.status_manager import LoaderStatusManager


def _make_manager() -> LoaderStatusManager:
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__.return_value = MagicMock()
        mock_db_ctx.return_value.__exit__.return_value = False
        return LoaderStatusManager(table_name="price_daily")


def test_mark_completed_resets_streak_and_stamps_success():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        # Mock fetchone() to return different values for different queries
        # First call: SELECT symbol_count, symbols_loaded, completion_pct (3 values)
        # Second call: SELECT for archive (7 values)
        # SAFETY CHECK FIX (2026-08-04): Use 99% completion (>= 98% minimum) so mark_completed succeeds
        # Previously 95.75% would trigger safety check and mark as FAILED instead
        mock_cur.fetchone.side_effect = [
            (5486, 5380, 99.0),  # symbol_count, symbols_loaded, completion_pct from safety check (>= 98%)
            (
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),  # archive SELECT: (exec_started, exec_completed, error_msg, row_count, completion_pct, symbols_loaded, symbol_count)
        ]
        mock_cur.rowcount = 1  # Verify rowcount check passes

        manager.mark_completed()

        # Find the UPDATE query among the execute() calls
        # (skipping the initial "SET lock_timeout" call)
        update_sql = None
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            if "UPDATE data_loader_status" in sql:
                update_sql = sql
                break

        assert update_sql is not None, "UPDATE query not found in execute calls"
        assert "last_success_at = NOW()" in update_sql
        assert "consecutive_failures = 0" in update_sql
        # Also verify new diagnostic fields are included
        assert "execution_duration_sec" in update_sql
        assert "http_status_code" in update_sql


def test_mark_completed_persists_symbols_failed():
    """Regression test for the 2026-08-03 fix (migration 1196): runner.py computes an
    accurate per-run symbols_failed count and passes it to mark_completed(), but it was
    only ever logger.warning()'d, never written to any column - a loader that partially
    fails every run (under max_fail_rate, so never FAILED/consecutive_failures) looked
    identical to a fully healthy one anywhere the dashboard/API reads this table."""
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.side_effect = [
            (5486, 5380, 99.0),
            (None, None, None, None, None, None, None),
        ]
        mock_cur.rowcount = 1

        manager.mark_completed(symbols_failed=12)

        update_call = None
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            if "UPDATE data_loader_status" in sql:
                update_call = call
                break

        assert update_call is not None, "UPDATE query not found in execute calls"
        assert "symbols_failed = %s" in update_call[0][0]
        assert 12 in update_call[0][1]


def test_mark_failed_increments_streak_without_touching_last_success(monkeypatch=None):
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1  # Verify rowcount check passes

        # First fetchone(): stale-report guard SELECT (execution_started, last_success_at).
        # Second fetchone(): archive SELECT (7 values). last_success_at=None means the guard
        # never suppresses, so the real UPDATE always runs in these tests.
        mock_cur.fetchone.side_effect = [
            (None, None),
            (None, None, None, None, None, None, None),
        ]

        manager.mark_failed("connection refused")

        # Find the UPDATE query among the execute() calls
        update_sql = None
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            if "UPDATE data_loader_status" in sql:
                update_sql = sql
                break

        assert update_sql is not None, "UPDATE query not found in execute calls"
        assert "consecutive_failures = consecutive_failures + 1" in update_sql
        assert "last_success_at" not in update_sql
        # Verify new diagnostic fields are included
        assert "http_status_code" in update_sql or "retry_count" in update_sql


def test_mark_failed_with_completion_pct_also_increments_streak():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1  # Verify rowcount check passes

        # First fetchone(): stale-report guard SELECT. Second: archive SELECT (7 values).
        mock_cur.fetchone.side_effect = [
            (None, None),
            (None, None, None, None, None, None, None),
        ]

        manager.mark_failed("timeout mid-batch", completion_pct=42.0)

        # Find the UPDATE query among the execute() calls
        update_sql = None
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            if "UPDATE data_loader_status" in sql:
                update_sql = sql
                break

        assert update_sql is not None, "UPDATE query not found in execute calls"
        assert "consecutive_failures = consecutive_failures + 1" in update_sql


def test_mark_timeout_increments_streak_without_touching_last_success():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1  # Verify rowcount check passes

        # First fetchone(): stale-report guard SELECT. Second: archive SELECT (7 values).
        mock_cur.fetchone.side_effect = [
            (None, None),
            (None, None, None, None, None, None, None),
        ]

        manager.mark_timeout(runtime_seconds=120.5)

        # Find the UPDATE query among the execute() calls
        update_sql = None
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            if "UPDATE data_loader_status" in sql:
                update_sql = sql
                break

        assert update_sql is not None, "UPDATE query not found in execute calls"
        assert "consecutive_failures = consecutive_failures + 1" in update_sql
        assert "last_success_at" not in update_sql
        # Verify new diagnostic fields are included
        assert "execution_duration_sec" in update_sql
        assert "http_status_code" in update_sql


def test_mark_failed_suppresses_stale_report_after_newer_success():
    """Regression test (2026-08-17): a hung/orphaned run's late failure report must not
    clobber a newer run's already-recorded success. Live-reproduced: sector_ranking/
    industry_ranking/sector_performance/trend_template_data all genuinely completed, then
    a stale reap of an older overlapping run's RUNNING row overwrote status back to FAILED
    with a stale error_message - the dashboard reported FAILED for tables that had actually
    succeeded. Guard: if last_success_at is newer than execution_started, skip the write.

    UPDATED 2026-08-17 (later): suppressing the wrong FAILED write isn't enough on its own -
    live-confirmed growth_metrics/quality_metrics/value_metrics stuck showing RUNNING at 0%
    indefinitely because the guard used to just `return` with no correction, leaving the row
    exactly as a stale mark_running() left it even though last_success_at proved a newer run
    had already completed. The guard must now self-heal the row back to COMPLETED (pulling
    real stats from history) instead of leaving it in a self-contradictory RUNNING state."""
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        from datetime import datetime

        execution_started = datetime(2026, 8, 16, 13, 25, 12)
        last_success_at = datetime(2026, 8, 16, 18, 10, 5)  # newer than execution_started
        history_completion_pct = 98.5
        history_symbols_loaded = 4850
        history_symbol_count = 4922
        history_execution_started = datetime(2026, 8, 16, 18, 9, 40)
        mock_cur.fetchone.side_effect = [
            (execution_started, last_success_at),  # guard's own SELECT FOR UPDATE
            (history_completion_pct, history_symbols_loaded, history_symbol_count, history_execution_started),
        ]

        manager.mark_failed("[REAPED] Stuck in RUNNING since 2026-08-16 13:25:12")

        # No FAILED write should have been issued - the stale report must be suppressed.
        update_calls = [
            call[0][0] for call in mock_cur.execute.call_args_list if "UPDATE data_loader_status" in call[0][0]
        ]
        assert len(update_calls) == 1, f"Expected exactly one self-healing UPDATE, got: {update_calls}"
        assert "status = %s" in update_calls[0]
        healing_call = mock_cur.execute.call_args_list[-1]
        assert healing_call[0][1][0] == "COMPLETED"


def test_mark_failed_does_not_suppress_same_run_self_conflict():
    """Regression test (2026-08-22): a run's OWN internal mark_completed() (e.g.
    OptimalLoader.run() stamping last_success_at at the end of its per-symbol write loop)
    must not cause a LATER failure from the SAME run (e.g. a post_run() audit hook raising
    moments afterward) to be suppressed as "stale". execution_started never changed - no
    other run's mark_running() has superseded this one - so last_success_at being newer
    than it just reflects this run's own earlier success marker.

    Live-confirmed: stock_scores' post_run audit_upstream_coverage() raised twice in a row
    on 2026-08-21 ("value_metrics only 94.7% complete"), yet data_loader_status.stock_scores
    read status=COMPLETED, error_message=NULL both times because the pre-fix guard couldn't
    tell this case apart from test_mark_failed_suppresses_stale_report_after_newer_success's
    genuinely-different-later-run case above.
    """
    manager = _make_manager()
    from datetime import datetime

    same_execution_started = datetime(2026, 8, 21, 23, 58, 18)
    own_run_last_success = datetime(2026, 8, 21, 23, 58, 52)  # this run's own mark_completed()

    # mark_running() first, so the manager captures its own execution_started baseline.
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1
        mock_cur.fetchone.side_effect = [(None,), (same_execution_started,)]
        manager.mark_running()
    assert manager._own_execution_started == same_execution_started

    # Now the same instance reports a failure (e.g. a post_run() hook raising) - the row's
    # execution_started is unchanged (no newer mark_running() happened), but last_success_at
    # is newer because THIS run's own internal mark_completed() already stamped it.
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1
        mock_cur.fetchone.side_effect = [
            (same_execution_started, own_run_last_success),  # guard's own SELECT FOR UPDATE
            (None, None, None, None, None, None, None),  # archive SELECT
        ]

        manager.mark_failed("post_run failed: value_metrics only 94.7% complete")

        update_calls = [
            call[0][0] for call in mock_cur.execute.call_args_list if "UPDATE data_loader_status" in call[0][0]
        ]
        assert len(update_calls) == 1, f"Expected the real FAILED UPDATE to proceed, got: {update_calls}"
        failed_call = mock_cur.execute.call_args_list[
            [i for i, c in enumerate(mock_cur.execute.call_args_list) if "UPDATE data_loader_status" in c[0][0]][0]
        ]
        assert failed_call[0][1][0] == "FAILED"


def test_mark_failed_tolerates_millisecond_level_execution_started_drift():
    """Regression test (2026-08-22, same-day follow-up): the first same-run-self-conflict fix
    above used EXACT equality between the row's execution_started and
    self._own_execution_started, which still incorrectly suppressed on a real, live-reproduced
    stock_scores run - confirmed via full call-stack tracing that mark_running() was called
    exactly ONCE (same PID, same LoaderStatusManager id()), yet the value captured via its own
    `RETURNING execution_started` differed from what a later SELECT on the same row read back,
    by roughly 11ms (root cause not fully isolated - not worth chasing further, since two
    GENUINELY different mark_running() calls for the same loader are always at least minutes
    apart in practice). Must now tolerate small timing drift and still recognize this as the
    same run."""
    manager = _make_manager()
    from datetime import datetime, timedelta

    own_execution_started = datetime(2026, 8, 22, 9, 4, 0, 151270)
    # What a later SELECT on the same row actually reads back - 11.5ms earlier, same run.
    row_execution_started = own_execution_started - timedelta(milliseconds=11)
    own_run_last_success = own_execution_started + timedelta(seconds=76)

    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1
        mock_cur.fetchone.side_effect = [(None,), (own_execution_started,)]
        manager.mark_running()
    assert manager._own_execution_started == own_execution_started

    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1
        mock_cur.fetchone.side_effect = [
            (row_execution_started, own_run_last_success),  # guard's own SELECT FOR UPDATE
            (None, None, None, None, None, None, None),  # archive SELECT
        ]

        manager.mark_failed("post_run failed: value_metrics only 94.7% complete")

        update_calls = [
            call[0][0] for call in mock_cur.execute.call_args_list if "UPDATE data_loader_status" in call[0][0]
        ]
        assert len(update_calls) == 1, f"Expected the real FAILED UPDATE to proceed, got: {update_calls}"
        failed_call = mock_cur.execute.call_args_list[
            [i for i, c in enumerate(mock_cur.execute.call_args_list) if "UPDATE data_loader_status" in c[0][0]][0]
        ]
        assert failed_call[0][1][0] == "FAILED"


def test_mark_failed_still_suppresses_genuinely_later_run_beyond_tolerance():
    """The tolerance window must not become overly permissive: a mark_running() call minutes
    later (a genuinely different, later scheduled run - not a sub-second timing artifact) must
    still be recognized as superseding this instance, even though this instance did call
    mark_running() itself at some point."""
    manager = _make_manager()
    from datetime import datetime, timedelta

    own_execution_started = datetime(2026, 8, 22, 9, 0, 0)
    # A genuinely different, later run's execution_started - many minutes later.
    later_execution_started = own_execution_started + timedelta(minutes=15)
    later_run_success = later_execution_started + timedelta(seconds=30)

    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1
        mock_cur.fetchone.side_effect = [(None,), (own_execution_started,)]
        manager.mark_running()

    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.side_effect = [
            (later_execution_started, later_run_success),  # guard's own SELECT FOR UPDATE
            (99.0, 5000, 5050, later_execution_started),  # archive/history SELECT for self-heal
        ]

        manager.mark_failed("this instance's own report, but a newer run has since started")

        update_calls = [
            call[0][0] for call in mock_cur.execute.call_args_list if "UPDATE data_loader_status" in call[0][0]
        ]
        assert len(update_calls) == 1, f"Expected exactly one self-healing UPDATE, got: {update_calls}"
        healing_call = mock_cur.execute.call_args_list[-1]
        assert healing_call[0][1][0] == "COMPLETED"


def test_mark_timeout_suppresses_stale_report_after_newer_success():
    """Same guard as mark_failed, for the mark_timeout() sibling path. See the self-heal
    note on test_mark_failed_suppresses_stale_report_after_newer_success above."""
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        from datetime import datetime

        execution_started = datetime(2026, 8, 16, 20, 0, 0)
        last_success_at = datetime(2026, 8, 16, 20, 30, 0)  # newer than execution_started
        mock_cur.fetchone.side_effect = [
            (execution_started, last_success_at),  # guard's own SELECT FOR UPDATE
            None,  # no history row - self-heal falls back to a status-only correction
        ]

        manager.mark_timeout(runtime_seconds=1800.0)

        update_calls = [
            call[0][0] for call in mock_cur.execute.call_args_list if "UPDATE data_loader_status" in call[0][0]
        ]
        assert len(update_calls) == 1, f"Expected exactly one self-healing UPDATE, got: {update_calls}"
        healing_call = mock_cur.execute.call_args_list[-1]
        assert healing_call[0][1][0] == "COMPLETED"
