"""Regression test: mark_running() must stamp last_updated, not just execution_started.

Bug (found 2026-08-10, live DB evidence): neither UPDATE branch in mark_running() touched
last_updated, leaving it frozen at whatever the previous run (or pipeline_health.py's own
business-date health-sweep) last wrote - stale from the very first second of a fresh run.
Combined with algo/monitoring/pipeline_health.py's _check_stuck_loaders() treating
last_updated as a liveness signal, this made growth_metrics/quality_metrics/
earnings_calendar/trend_template_data - all actively RUNNING and progressing - falsely
report "likely crashed" within minutes of a healthy run starting. See that module's
_check_stuck_loaders docstring for the full chain (three cooperating fixes, this is one).
"""

from unittest.mock import MagicMock, patch

from utils.loaders.status_manager import LoaderStatusManager


def _make_manager() -> LoaderStatusManager:
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__.return_value = MagicMock()
        mock_db_ctx.return_value.__exit__.return_value = False
        return LoaderStatusManager(table_name="growth_metrics")


def test_mark_running_without_symbol_count_stamps_last_updated():
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
        assert "last_updated = NOW()" in sql_text


def test_mark_running_with_symbol_count_stamps_last_updated():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.return_value = ("COMPLETED",)
        mock_cur.rowcount = 1

        manager.mark_running(symbol_count=100)

        update_call = mock_cur.execute.call_args_list[-1]
        sql_text = update_call[0][0]
        assert "last_updated = NOW()" in sql_text
