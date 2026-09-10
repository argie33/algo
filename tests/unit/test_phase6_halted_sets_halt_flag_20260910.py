"""Regression test for a real-money-readiness safety gap in Phase 6 (exit execution):
result.halted=True (set by phase6_exit_execution.py's run_phase6 on a DatabaseError or any
unexpected exception during exit/stop evaluation) never reached the shared halt flag.

_executor_phase_6() only ever returned that PhaseResult straight to
OrchestratorPhaseExecutor.execute_phase(), which logs it at CRITICAL but never calls
self.halt_manager.set_halt_flag(). Phase 8 only consults Phase 5's exposure_constraints
(unrelated to Phase 6), so it had no way of knowing exit execution had catastrophically
failed - it could still submit brand-new entry orders in the same run while existing
positions were left with unverified/unmanaged exits.

Fixed: _executor_phase_6() now calls set_halt_flag() when result.halted is True, mirroring
Phase 3/9's identical pattern, and fails hard via RuntimeError (GOVERNANCE VIOLATION) if the
halt flag itself can't be set.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestration.orchestrator import Orchestrator
from algo.orchestrator.phase_data_contract import MissingPhaseDataError
from algo.orchestrator.phase_result import PhaseResult


def _make_orchestrator():
    instance = Orchestrator.__new__(Orchestrator)
    instance.config = {}
    instance.run_date = None
    instance.dry_run = True
    instance.alerts = MagicMock()
    instance.verbose = False
    instance.phase_results = {}
    instance.execution_tracker = MagicMock()
    instance.halt_manager = MagicMock()
    return instance


def _make_executor_stub():
    executor = MagicMock()
    executor.get_result.return_value = None
    executor.get_phase_data_required.side_effect = MissingPhaseDataError("no data for test")
    return executor


class TestPhase6HaltedSetsHaltFlag:
    def test_phase6_halted_result_sets_halt_flag(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        halted_result = PhaseResult(
            6,
            "exit_execution",
            "halted",
            {"status": "halted", "reason": "db error", "exits_executed": 0},
            True,
            "exit execution crashed",
        )

        with patch("algo.orchestration.orchestrator.run_phase6", return_value=halted_result):
            result = instance._executor_phase_6(executor=_make_executor_stub())

        assert result.halted is True
        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase6_exit_execution"

    def test_halt_flag_set_failure_after_phase6_halted_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False
        halted_result = PhaseResult(
            6,
            "exit_execution",
            "halted",
            {"status": "halted", "reason": "db error", "exits_executed": 0},
            True,
            "exit execution crashed",
        )

        with (
            patch("algo.orchestration.orchestrator.run_phase6", return_value=halted_result),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance._executor_phase_6(executor=_make_executor_stub())

    def test_phase6_ok_result_does_not_touch_halt_flag(self):
        instance = _make_orchestrator()
        ok_result = PhaseResult(
            6,
            "exit_execution",
            "ok",
            {"status": "ok", "exits_executed": 2},
            False,
            None,
        )

        with patch("algo.orchestration.orchestrator.run_phase6", return_value=ok_result):
            result = instance._executor_phase_6(executor=_make_executor_stub())

        assert result.halted is False
        instance.halt_manager.set_halt_flag.assert_not_called()
