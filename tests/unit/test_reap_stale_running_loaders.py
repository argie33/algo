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
is older than max_age_hours as FAILED via the same well-tested LoaderStatusManager.mark_failed()
path every other terminal-status transition uses.
"""

from unittest.mock import MagicMock, patch

from utils.loaders.status_manager import reap_stale_running_loaders


def test_reaps_stale_running_table_and_marks_failed():
    stale_row = ("earnings_calendar", "2026-08-10 02:55:15")

    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchall.return_value = [stale_row]

        with patch("utils.loaders.status_manager.LoaderStatusManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager_cls.return_value = mock_manager

            reaped = reap_stale_running_loaders(max_age_hours=4.0)

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
            reaped = reap_stale_running_loaders(max_age_hours=4.0)

    assert reaped == []
    mock_manager_cls.assert_not_called()


def test_scopes_query_to_given_table_names_when_provided():
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchall.return_value = []

        reap_stale_running_loaders(table_names=["prices"], max_age_hours=4.0)

    sql_text, params = mock_cur.execute.call_args[0]
    assert "table_name = ANY(%s)" in sql_text
    assert params[0] == ["prices"]
