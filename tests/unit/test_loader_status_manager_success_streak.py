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

        # Mock the fetchone for throughput calculation
        mock_cur.fetchone.return_value = (None,)  # symbols_loaded

        manager.mark_completed()

        sql = mock_cur.execute.call_args_list[0][0][0]  # First execute call
        assert "last_success_at = NOW()" in sql
        assert "consecutive_failures = 0" in sql
        # Also verify new diagnostic fields are included
        assert "execution_duration_sec" in sql
        assert "http_status_code" in sql


def test_mark_failed_increments_streak_without_touching_last_success(monkeypatch=None):
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        manager.mark_failed("connection refused")

        sql = mock_cur.execute.call_args_list[0][0][0]  # First execute call
        assert "consecutive_failures = consecutive_failures + 1" in sql
        assert "last_success_at" not in sql
        # Verify new diagnostic fields are included
        assert "http_status_code" in sql or "retry_count" in sql


def test_mark_failed_with_completion_pct_also_increments_streak():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        manager.mark_failed("timeout mid-batch", completion_pct=42.0)

        sql = mock_cur.execute.call_args_list[0][0][0]  # First execute call
        assert "consecutive_failures = consecutive_failures + 1" in sql


def test_mark_timeout_increments_streak_without_touching_last_success():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        manager.mark_timeout(runtime_seconds=120.5)

        sql = mock_cur.execute.call_args_list[0][0][0]  # First execute call
        assert "consecutive_failures = consecutive_failures + 1" in sql
        assert "last_success_at" not in sql
        # Verify new diagnostic fields are included
        assert "execution_duration_sec" in sql
        assert "http_status_code" in sql
