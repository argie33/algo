"""Regression test for the local-dev stale-RUNNING-loader reaper.

Bug: local dev has no equivalent of production's ECS-task-based
orchestrator._kill_long_running_loaders() (which makes real AWS ListTasks calls that always
fail locally with no credentials). A crashed loader process, a killed subprocess whose
parent's subprocess.run(timeout=...) failed to reap it, or a local_loader_scheduler.py
instance still running stale in-memory code from before a same-day timeout fix all leave
data_loader_status stuck at status=RUNNING forever - live-confirmed 2026-08-10 on
trend_template_data/earnings_calendar/quality_metrics/growth_metrics, each stuck RUNNING for
1.5-5.5+ hours with zero progress. A prior incident (buy_sell_daily_stuck_running_74_hours_
20260810) required a manual one-off fix and explicitly recommended, but never implemented,
an automatic version of this check.

reap_stale_running_loaders() closes that gap: mark any RUNNING row whose execution_started
is older than that loader's own timeout + 25% margin as FAILED via the same well-tested
LoaderStatusManager.mark_failed() path every other terminal-status transition uses.

NOTE 2026-08-16: this file previously tested a table_names/max_age_hours-scoped contract
(and mocked execution_started as a plain string) that predates the Session 106 refactor to
per-loader timeouts - both had silently drifted from the real implementation (which takes no
arguments and always requires a real datetime for execution_started, since real psycopg2
always returns one for a timestamp column). Rewritten to match current behavior.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from utils.loaders.status_manager import reap_stale_running_loaders


def test_reaps_stale_running_table_and_marks_failed():
    stale_started = datetime.now(timezone.utc) - timedelta(hours=10)

    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchall.return_value = [("earnings_calendar", stale_started)]

        with patch("loaders.loader_timeout_config.get_loader_timeout", return_value=3600):
            with patch("utils.loaders.status_manager.LoaderStatusManager") as mock_manager_cls:
                mock_manager = MagicMock()
                mock_manager_cls.return_value = mock_manager

                reaped = reap_stale_running_loaders()

    assert reaped == ["earnings_calendar"]
    mock_manager_cls.assert_called_once_with("earnings_calendar")
    mock_manager.mark_failed.assert_called_once()
    (kwargs,) = [mock_manager.mark_failed.call_args.kwargs]
    assert "REAPED" in kwargs["error_message"]


def test_no_stale_rows_reaps_nothing():
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchall.return_value = []

        with patch("utils.loaders.status_manager.LoaderStatusManager") as mock_manager_cls:
            reaped = reap_stale_running_loaders()

    assert reaped == []
    mock_manager_cls.assert_not_called()


def test_within_timeout_is_not_reaped():
    recent_started = datetime.now(timezone.utc) - timedelta(minutes=5)

    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchall.return_value = [("company_info_sec", recent_started)]

        with patch("loaders.loader_timeout_config.get_loader_timeout", return_value=3600):
            with patch("utils.loaders.status_manager.LoaderStatusManager") as mock_manager_cls:
                reaped = reap_stale_running_loaders()

    assert reaped == []
    mock_manager_cls.assert_not_called()
