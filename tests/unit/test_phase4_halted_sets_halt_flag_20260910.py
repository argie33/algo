"""Regression test for a real-money-readiness safety gap in Phase 4 (reconciliation):
result.halted=True (set by phase4_reconciliation.py's run() on broker-unavailable,
ValueError, DatabaseError, or any unexpected exception during DB-vs-broker position
reconciliation) never reached the shared halt flag - the same gap already found and fixed
for Phases 1/2/3/6/9.

_executor_phase_4() only ever returned that PhaseResult straight to
OrchestratorPhaseExecutor.execute_phase(). Phase 4 is always_run=True and downstream
phases 5-9 only ever consult self.halt_manager's shared flag, not Phase 4's own result -
without this fix, Phase 8 could still submit brand-new entry orders in the same run
despite Phase 4 detecting real broker-vs-DB position drift.

Fixed: _executor_phase_4() now calls set_halt_flag() when result.halted is True, mirroring
Phase 3/6/9's identical pattern, and fails hard via RuntimeError (GOVERNANCE VIOLATION) if
the halt flag itself can't be set.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestration.orchestrator import Orchestrator
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


class TestPhase4HaltedSetsHaltFlag:
    def test_phase4_halted_result_sets_halt_flag(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        halted_result = PhaseResult(
            4,
            "reconciliation",
            "error",
            {"success": False, "reason": "db error"},
            True,
            "reconciliation crashed",
        )

        with patch("algo.orchestration.orchestrator.run_phase4", return_value=halted_result):
            result = instance._executor_phase_4()

        assert result.halted is True
        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase4_reconciliation"

    def test_halt_flag_set_failure_after_phase4_halted_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False
        halted_result = PhaseResult(
            4,
            "reconciliation",
            "error",
            {"success": False, "reason": "db error"},
            True,
            "reconciliation crashed",
        )

        with (
            patch("algo.orchestration.orchestrator.run_phase4", return_value=halted_result),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance._executor_phase_4()

    def test_phase4_ok_result_does_not_touch_halt_flag(self):
        instance = _make_orchestrator()
        ok_result = PhaseResult(
            4,
            "reconciliation",
            "ok",
            {"success": True},
            False,
            None,
        )

        with patch("algo.orchestration.orchestrator.run_phase4", return_value=ok_result):
            result = instance._executor_phase_4()

        assert result.halted is False
        instance.halt_manager.set_halt_flag.assert_not_called()
