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
        mock_cur.fetchone.side_effect = [
            (5486, 5253, 95.75),  # symbol_count, symbols_loaded, completion_pct from safety check
            (None, None, None, None, None, None, None),  # archive SELECT: (exec_started, exec_completed, error_msg, row_count, completion_pct, symbols_loaded, symbol_count)
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


def test_mark_failed_increments_streak_without_touching_last_success(monkeypatch=None):
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.rowcount = 1  # Verify rowcount check passes

        # Mock fetchone() for archive SELECT (7 values)
        mock_cur.fetchone.return_value = (None, None, None, None, None, None, None)

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

        # Mock fetchone() for archive SELECT (7 values)
        mock_cur.fetchone.return_value = (None, None, None, None, None, None, None)

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

        # Mock fetchone() for archive SELECT (7 values)
        mock_cur.fetchone.return_value = (None, None, None, None, None, None, None)

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
