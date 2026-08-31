"""Coverage test for algo/orchestration/database_health_monitor.py - found 2026-08-31 via the
same objective coverage-analysis pass as commits 5b4ae35ce/8e3479e5d/d242f84aa to have zero
dedicated tests anywhere in the suite (8.72% coverage, purely incidental). Focuses on the two
most safety-critical, self-contained functions:

- verify_task_stopped(): called by Orchestrator._kill_long_running_loaders() after issuing
  ecs.stop_task() - its own docstring documents the bug it exists to prevent ("Prevents hung
  tasks consuming RDS connections by verifying termination... ECS stop_task is async and may
  fail silently"). A regression here could leave a killed loader's DB connection held forever
  while believing it was cleaned up.
- validate_required_tables(): a pre-flight safety gate run before phases execute.

health_check_diagnostics()/check_db_connectivity()/check_connection_pool_health() are lower-value
targets (mostly logging/diagnostics with less pure decision logic) - not covered here, left for
a future pass if this file's overall coverage is revisited.
"""

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.orchestration.database_health_monitor import DatabaseHealthMonitor


def _monitor():
    return DatabaseHealthMonitor(alerts=MagicMock())


def _ecs_response(last_status, desired_status="STOPPED"):
    return {"tasks": [{"lastStatus": last_status, "desiredStatus": desired_status}]}


class TestVerifyTaskStopped:
    def test_returns_true_immediately_when_already_stopped(self):
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.return_value = _ecs_response("STOPPED")

        result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily")

        assert result is True
        assert ecs.describe_tasks.call_count == 1

    def test_retries_while_still_transitioning_then_succeeds(self):
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.side_effect = [
            _ecs_response("RUNNING"),
            _ecs_response("DEPROVISIONING"),
            _ecs_response("STOPPED"),
        ]

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=3)

        assert result is True
        assert ecs.describe_tasks.call_count == 3

    def test_returns_false_after_exhausting_retries_still_running(self):
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.return_value = _ecs_response("RUNNING")

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=3)

        assert result is False
        assert ecs.describe_tasks.call_count == 3

    def test_returns_false_when_stop_not_acknowledged(self):
        """desiredStatus is NOT STOPPED (stop_task call itself may not have registered) -
        must not be treated as a transitional/retryable state indefinitely."""
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.return_value = _ecs_response("RUNNING", desired_status="RUNNING")

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=2)

        assert result is False

    def test_retries_when_task_not_found_in_response(self):
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.side_effect = [
            {"tasks": []},
            _ecs_response("STOPPED"),
        ]

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=3)

        assert result is True
        assert ecs.describe_tasks.call_count == 2

    def test_returns_false_when_task_never_found(self):
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.return_value = {"tasks": []}

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=2)

        assert result is False

    def test_raises_on_missing_status_fields_is_caught_and_retried(self):
        """A malformed ECS response (missing lastStatus/desiredStatus) raises ValueError
        internally - must be caught by the retry loop, not propagate and crash the caller."""
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.side_effect = [
            {"tasks": [{"lastStatus": None, "desiredStatus": None}]},
            _ecs_response("STOPPED"),
        ]

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=3)

        assert result is True

    def test_describe_tasks_exception_is_caught_and_retried(self):
        monitor = _monitor()
        ecs = MagicMock()
        ecs.describe_tasks.side_effect = [
            psycopg2.OperationalError("transient"),
            _ecs_response("STOPPED"),
        ]

        with patch("algo.orchestration.database_health_monitor.time.sleep"):
            result = monitor.verify_task_stopped(ecs, "cluster", "task-arn", "price_daily", max_retries=3)

        assert result is True


class TestValidateRequiredTables:
    def test_returns_true_when_all_tables_exist(self):
        monitor = _monitor()
        cur = MagicMock()
        cur.fetchone.return_value = (1,)

        result = monitor.validate_required_tables(cur)

        assert result is True

    def test_returns_false_when_a_table_is_missing(self):
        monitor = _monitor()
        cur = MagicMock()
        cur.fetchone.side_effect = [(1,), None, (1,), (1,), (1,), (1,)]

        result = monitor.validate_required_tables(cur)

        assert result is False

    def test_returns_false_on_database_error_for_a_table_check(self):
        monitor = _monitor()
        cur = MagicMock()
        cur.execute.side_effect = [
            None,
            psycopg2.DatabaseError("connection lost"),
            None,
            None,
            None,
            None,
        ]
        cur.fetchone.return_value = (1,)

        result = monitor.validate_required_tables(cur)

        assert result is False

    def test_returns_false_on_outer_database_error(self):
        monitor = _monitor()
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.DatabaseError("connection lost entirely")

        result = monitor.validate_required_tables(cur)

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
