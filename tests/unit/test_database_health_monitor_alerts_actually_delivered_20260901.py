"""Regression test: DatabaseHealthMonitor's CRITICAL conditions must actually call the
injected AlertManager (self.alerts), not just log.

self.alerts was injected by __init__ ("AlertManager instance for escalation") but was
never referenced anywhere in the class before this fix - every CRITICAL condition here
(stuck connections, missing required tables, ECS task-termination failure) only ever
reached a log line. Same "computed but never delivered" bug class already found and
fixed twice this session for position_sync.py/reconciliation.py (commit 6f70d1e27).
"""

from unittest.mock import MagicMock, patch

import psycopg2

from algo.orchestration.database_health_monitor import DatabaseHealthMonitor


def _monitor():
    alerts = MagicMock()
    return DatabaseHealthMonitor(alerts=alerts), alerts


def _ecs_response(last_status, desired_status="STOPPED"):
    return {"tasks": [{"lastStatus": last_status, "desiredStatus": desired_status}]}


class TestValidateRequiredTablesAlerts:
    def test_missing_table_calls_alerts_critical(self):
        monitor, alerts = _monitor()
        cur = MagicMock()
        cur.fetchone.side_effect = [(1,), None, (1,), (1,), (1,), (1,)]

        result = monitor.validate_required_tables(cur)

        assert result is False
        alerts.critical.assert_called_once()
        assert "trend_template_data" in alerts.critical.call_args.args[0]

    def test_all_tables_present_does_not_alert(self):
        monitor, alerts = _monitor()
        cur = MagicMock()
        cur.fetchone.return_value = (1,)

        result = monitor.validate_required_tables(cur)

        assert result is True
        alerts.critical.assert_not_called()


class TestVerifyTaskStoppedAlerts:
    def test_final_failure_calls_alerts_critical(self):
        monitor, alerts = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.return_value = _ecs_response("RUNNING")

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=2)

        assert result is False
        alerts.critical.assert_called_once()
        assert "price_daily" in alerts.critical.call_args.args[0]

    def test_eventual_success_does_not_alert(self):
        monitor, alerts = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.side_effect = [_ecs_response("RUNNING"), _ecs_response("STOPPED")]

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=3)

        assert result is True
        alerts.critical.assert_not_called()


class TestConnectionPoolHealthAlerts:
    def test_stuck_connections_calls_alerts_critical(self):
        monitor, alerts = _monitor()
        status = {"active_connections": 10, "max_connections": 100, "usage_pct": 10.0, "stuck_connections_count": 2}

        with (
            patch("algo.monitoring.get_pool_status", return_value=status),
            patch("algo.monitoring.check_stuck_connections"),
        ):
            monitor.check_connection_pool_health()

        alerts.critical.assert_called_once()
        assert "stuck connections" in alerts.critical.call_args.args[0]

    def test_no_stuck_connections_does_not_alert(self):
        monitor, alerts = _monitor()
        status = {"active_connections": 10, "max_connections": 100, "usage_pct": 10.0, "stuck_connections_count": 0}

        with patch("algo.monitoring.get_pool_status", return_value=status):
            monitor.check_connection_pool_health()

        alerts.critical.assert_not_called()

    def test_pool_status_error_does_not_raise(self):
        """Existing (KeyError, ValueError, AttributeError) fail-soft behavior must survive
        the new alert call being added inside the try block."""
        monitor, alerts = _monitor()

        with patch("algo.monitoring.get_pool_status", side_effect=KeyError("usage_pct")):
            monitor.check_connection_pool_health()  # must not raise

        alerts.critical.assert_not_called()
