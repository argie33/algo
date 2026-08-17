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
    succeeded. Guard: if last_success_at is newer than execution_started, skip the write."""
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        from datetime import datetime

        execution_started = datetime(2026, 8, 16, 13, 25, 12)
        last_success_at = datetime(2026, 8, 16, 18, 10, 5)  # newer than execution_started
        mock_cur.fetchone.return_value = (execution_started, last_success_at)

        manager.mark_failed("[REAPED] Stuck in RUNNING since 2026-08-16 13:25:12")

        # No UPDATE should have been issued - the stale report must be suppressed entirely.
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            assert "UPDATE data_loader_status" not in sql, f"Stale FAILED report was not suppressed: {sql}"


def test_mark_timeout_suppresses_stale_report_after_newer_success():
    """Same guard as mark_failed, for the mark_timeout() sibling path."""
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        from datetime import datetime

        execution_started = datetime(2026, 8, 16, 20, 0, 0)
        last_success_at = datetime(2026, 8, 16, 20, 30, 0)  # newer than execution_started
        mock_cur.fetchone.return_value = (execution_started, last_success_at)

        manager.mark_timeout(runtime_seconds=1800.0)

        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            assert "UPDATE data_loader_status" not in sql, f"Stale TIMEOUT report was not suppressed: {sql}"
