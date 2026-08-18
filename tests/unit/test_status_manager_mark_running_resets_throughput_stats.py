"""Regression test: mark_running() must reset execution_duration_sec/symbols_per_second/
http_status_code/rate_limit_quota to NULL.

Bug (found 2026-08-18, live DB evidence): same bug class as
test_status_manager_mark_running_resets_completion_pct.py, one tier deeper - these four
"prior run's final stats" columns were never reset by either UPDATE branch. Live-reproduced
on current_reports_8k: a fresh RUNNING row, 48.68% through and genuinely healthy, still
carried symbols_per_second=409462.40 (and a stale execution_duration_sec) from whatever run
last completed. dashboard/panels/health.py renders that cell unconditionally whenever
duration > 0, with no status==RUNNING gate, so the operator dashboard showed a physically
impossible throughput for an actively-running loader.
"""

from unittest.mock import MagicMock, patch

from utils.loaders.status_manager import LoaderStatusManager


def _make_manager() -> LoaderStatusManager:
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__.return_value = MagicMock()
        mock_db_ctx.return_value.__exit__.return_value = False
        return LoaderStatusManager(table_name="current_reports_8k")


def test_mark_running_without_symbol_count_resets_throughput_stats():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.return_value = ("COMPLETED",)
        mock_cur.rowcount = 1

        manager.mark_running()

        update_call = mock_cur.execute.call_args_list[-1]
        sql_text = update_call[0][0]
        assert "execution_duration_sec = NULL" in sql_text
        assert "symbols_per_second = NULL" in sql_text
        assert "http_status_code = NULL" in sql_text
        assert "rate_limit_quota = NULL" in sql_text


def test_mark_running_with_symbol_count_resets_throughput_stats():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.return_value = ("COMPLETED",)
        mock_cur.rowcount = 1

        manager.mark_running(symbol_count=4930)

        update_call = mock_cur.execute.call_args_list[-1]
        sql_text = update_call[0][0]
        assert "execution_duration_sec = NULL" in sql_text
        assert "symbols_per_second = NULL" in sql_text
        assert "http_status_code = NULL" in sql_text
        assert "rate_limit_quota = NULL" in sql_text
