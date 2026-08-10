"""Regression test for a second --force-refresh bug in scripts/run_loader.py (found 2026-08-10,
same investigation as test_run_loader_force_refresh_respects_loader_status.py).

Bug: before marking loaders RUNNING, --force-refresh opened its own raw psycopg2 connection
hardcoded to "dbname=stocks user=stocks host=localhost" - ignoring DB_HOST/DB_USER/DB_PASSWORD/
DB_NAME entirely, so it silently misconnected (or failed to authenticate) outside this exact
local setup - and hand-rolled `UPDATE data_loader_status SET status='RUNNING', execution_started
=NOW()` without clearing execution_completed/symbols_loaded/completion_pct/error_message. That
reintroduced, via this second bypass path, the exact stale-progress bug that
LoaderStatusManager.mark_running() was fixed for in commit a58ecc5b5: a loader started via
--force-refresh would show execution_started newer than a leftover execution_completed from
its prior run, misleading proactive-wait/health checks. Live-reproduced 2026-08-10 on
market_health_daily/market_sentiment/earnings_calendar/market_exposure_daily/stock_scores.

Fixed: reuse the canonical, tested LoaderStatusManager.mark_running() for each output table
instead of a parallel raw-SQL implementation.
"""

import sys
from unittest.mock import MagicMock, patch

import scripts.run_loader as run_loader_module


def _run_main_with_force_refresh(loader_arg="technical"):
    argv = ["run_loader.py", loader_arg, "--force-refresh"]
    with patch.object(sys, "argv", argv):
        return run_loader_module.main()


class TestForceRefreshRunningUsesStatusManager:
    def test_marks_running_via_status_manager_not_raw_sql(self):
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED"}

        with (
            patch.object(run_loader_module, "get_loader_class_for_file", return_value=MagicMock()),
            patch.object(run_loader_module, "run_loader_generic", return_value={"symbols_processed": 100}),
            patch.object(run_loader_module, "update_watermarks_to_today"),
            patch("utils.loaders.status_manager.LoaderStatusManager", return_value=mock_status_mgr) as mock_cls,
            patch("psycopg2.connect") as mock_connect,
        ):
            exit_code = _run_main_with_force_refresh("technical")

        assert exit_code == 0
        mock_status_mgr.mark_running.assert_called()
        mock_connect.assert_not_called()
        assert mock_cls.call_count >= 1

    def test_status_manager_failure_for_one_table_does_not_abort_run(self):
        """A DB hiccup marking one table RUNNING must be logged and swallowed, not crash
        the whole --force-refresh invocation before the loader even runs."""
        mock_status_mgr = MagicMock()
        mock_status_mgr.mark_running.side_effect = RuntimeError("db unavailable")
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED"}

        with (
            patch.object(run_loader_module, "get_loader_class_for_file", return_value=MagicMock()),
            patch.object(run_loader_module, "run_loader_generic", return_value={"symbols_processed": 100}),
            patch.object(run_loader_module, "update_watermarks_to_today"),
            patch("utils.loaders.status_manager.LoaderStatusManager", return_value=mock_status_mgr),
        ):
            exit_code = _run_main_with_force_refresh("technical")

        assert exit_code == 0
