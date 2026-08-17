"""Regression test: Orchestrator._handle_concurrency_lock() must record a halted execution
log on both failure branches (lock held by another instance, lock backend unavailable),
mirroring the existing market-hours-guard early-exit pattern, instead of returning silently
with no row in algo_orchestrator_runs."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.orchestration.orchestrator import Orchestrator


def _fake_self():
    self = object.__new__(Orchestrator)
    self.run_id = "test-run"
    self.run_date = date(2026, 7, 28)
    self.dry_run = False
    self.execution_tracker = MagicMock()
    self._cleanup_stale_orchestrator_run_locks = MagicMock()
    self._install_shutdown_handler = MagicMock()
    self._save_orchestrator_run_status = MagicMock()
    return self


class TestOrchestratorLockContentionRecordsExecutionLog:
    def test_lock_held_by_another_instance_is_recorded(self):
        fake_self = _fake_self()
        fake_self._acquire_run_lock = MagicMock(return_value=False)
        fake_self.lock_manager = MagicMock(is_available=True)

        result = Orchestrator._handle_concurrency_lock(fake_self)

        assert result is not None
        assert result["success"] is False
        assert result["halted"] is True
        fake_self.execution_tracker.save_execution_log.assert_called_once()
        status, reason = fake_self.execution_tracker.save_execution_log.call_args[0]
        assert status == "halted"
        assert "lock" in reason.lower()
        fake_self._save_orchestrator_run_status.assert_called_once_with("halted", reason)

    def test_lock_backend_unavailable_is_recorded(self):
        fake_self = _fake_self()
        fake_self._acquire_run_lock = MagicMock(return_value=False)
        fake_self.lock_manager = MagicMock(is_available=False)

        result = Orchestrator._handle_concurrency_lock(fake_self)

        assert result is not None
        assert result["success"] is False
        assert result["halted"] is True
        fake_self.execution_tracker.save_execution_log.assert_called_once()
        status, reason = fake_self.execution_tracker.save_execution_log.call_args[0]
        assert status == "halted"
        fake_self._save_orchestrator_run_status.assert_called_once_with("halted", reason)

    def test_execution_log_write_failure_does_not_mask_lock_result(self):
        """If save_execution_log itself fails (e.g. DB unreachable), the lock-contention
        result must still be returned - never swallowed by a secondary failure."""
        fake_self = _fake_self()
        fake_self._acquire_run_lock = MagicMock(return_value=False)
        fake_self.lock_manager = MagicMock(is_available=True)
        fake_self.execution_tracker.save_execution_log.side_effect = Exception("DB unreachable")

        result = Orchestrator._handle_concurrency_lock(fake_self)

        assert result is not None
        assert result["success"] is False

    def test_successful_lock_acquisition_does_not_log(self):
        fake_self = _fake_self()
        fake_self._acquire_run_lock = MagicMock(return_value=True)
        fake_self.lock_manager = MagicMock(is_available=True)

        result = Orchestrator._handle_concurrency_lock(fake_self)

        assert result is None
        fake_self.execution_tracker.save_execution_log.assert_not_called()
        fake_self._save_orchestrator_run_status.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
