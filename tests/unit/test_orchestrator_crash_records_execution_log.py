"""Regression test: Orchestrator.run() had no except clause, only a bare try/finally.
phase_executor.py deliberately re-raises RuntimeError for phase governance violations
(e.g. phase6_exit_execution.py's "Phase 3 crashed, open positions unevaluated" / "Alpaca
credentials required" checks) to crash the whole orchestrator rather than silently
continue - by design, not a bug in phase_executor.py itself. But save_execution_log() is
only ever called from _save_early_exit_log() (preflight halts) and _final_report()
(normal completion), both of which require run()'s try block to return normally. Neither
run() itself, nor its callers (lambda_function.py's `except Exception` handler,
run_local_orchestrator.py's `except Exception` handler which only prints a traceback), nor
Python's default handler ever wrote anything to orchestrator_execution_log for such a
crash - the run vanished from the one table the dashboard/API/health checks query,
indistinguishable from "never ran" instead of a visible halted/error record. This is the
"exit execution halted, not sure why" blind spot the table exists to prevent, one level up
from any individual phase.

Fixed by wrapping run()'s body in try/except/finally: the except records the crash via
execution_tracker.save_execution_log("error", ...) and then re-raises unchanged - the
crash must still propagate exactly as before, only the audit-trail gap is closed.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.orchestration.orchestrator import Orchestrator


def _fake_self():
    self = object.__new__(Orchestrator)
    self.run_id = "test-run"
    self.run_date = date(2026, 7, 28)
    self.dry_run = True
    self.config = {"execution_mode": "paper", "alpaca_paper_trading": True}
    self.execution_tracker = MagicMock()
    self.run_start = 0.0
    self._handle_concurrency_lock = MagicMock(return_value=None)
    self._release_run_lock = MagicMock()
    self._restore_shutdown_handler = MagicMock()
    return self


class TestOrchestratorCrashRecordsExecutionLog:
    def test_phase_execution_crash_is_recorded_before_reraising(self):
        fake_self = _fake_self()
        fake_self._run_preflight_checks = MagicMock(return_value=None)
        fake_self._wait_for_loaders_before_execution = MagicMock()
        crash = RuntimeError("[PHASE 6 CRITICAL] Alpaca credentials required")
        fake_self._execute_phases = MagicMock(side_effect=crash)

        with pytest.raises(RuntimeError, match="Alpaca credentials required"):
            Orchestrator.run(fake_self)

        fake_self.execution_tracker.save_execution_log.assert_called_once()
        status, reason = fake_self.execution_tracker.save_execution_log.call_args[0]
        assert status == "error"
        assert "Alpaca credentials required" in reason
        fake_self._release_run_lock.assert_called_once()
        fake_self._restore_shutdown_handler.assert_called_once()

    def test_preflight_crash_is_also_recorded(self):
        fake_self = _fake_self()
        crash = ValueError("preflight blew up")
        fake_self._run_preflight_checks = MagicMock(side_effect=crash)

        with pytest.raises(ValueError, match="preflight blew up"):
            Orchestrator.run(fake_self)

        fake_self.execution_tracker.save_execution_log.assert_called_once()
        status, _reason = fake_self.execution_tracker.save_execution_log.call_args[0]
        assert status == "error"

    def test_execution_log_write_failure_does_not_mask_original_crash(self):
        """If save_execution_log itself fails (e.g. DB unreachable during the crash), the
        original exception must still propagate - never swallowed by a secondary failure."""
        fake_self = _fake_self()
        fake_self._run_preflight_checks = MagicMock(return_value=None)
        fake_self._wait_for_loaders_before_execution = MagicMock()
        original = RuntimeError("original phase crash")
        fake_self._execute_phases = MagicMock(side_effect=original)
        fake_self.execution_tracker.save_execution_log.side_effect = Exception("DB unreachable")

        with pytest.raises(RuntimeError, match="original phase crash"):
            Orchestrator.run(fake_self)

    def test_normal_completion_does_not_call_save_execution_log_from_except_path(self):
        """Sanity check: a clean run must not double-log via the new except branch - only
        _final_report()'s own existing save_execution_log call should fire."""
        fake_self = _fake_self()
        fake_self._run_preflight_checks = MagicMock(return_value=None)
        fake_self._wait_for_loaders_before_execution = MagicMock()
        fake_self._execute_phases = MagicMock(return_value={"success": True})
        fake_self._handle_executor_result = MagicMock(return_value=None)
        fake_self._emit_performance_metrics = MagicMock()
        fake_self._final_report = MagicMock(return_value={"success": True})

        result = Orchestrator.run(fake_self)

        assert result == {"success": True}
        fake_self.execution_tracker.save_execution_log.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
