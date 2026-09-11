"""Regression test for a CRITICAL real-money-readiness safety gap in Phase 4 (reconciliation)
and Phase 5 (exposure policy): the same crash-swallows-halt-flag bug class already fixed for
Phases 1/2/3/6/9 (see test_phase1_crash_sets_halt_flag_20260906.py,
test_phase2_phase9_crash_sets_halt_flag_20260907.py, test_phase3_halted_sets_halt_flag_20260910.py)
but never applied to _executor_phase_4()/phase_5_exposure_policy() until this adversarial
re-audit found it.

An unhandled exception raised BEFORE run_phase4()/run_phase5() ever returns a PhaseResult
(e.g. validate_phase_config() raising ConfigValidationError on a missing execution_mode key,
a realistic failure mode) used to propagate straight past each method's own `if result.halted`
branch - the ONLY place either method called set_halt_flag() - and hit phase_executor.py's
generic Exception handler instead, which records PhaseResult(status="error", halted=False)
without ever touching the shared halt flag. Since Phase 4/5 are always_run=True and Phase 8
only ever consults self.halt_manager's shared flag (not either phase's own result object - no
caller anywhere reads a stored Phase 4 result, and Phase 7's Phase-5-result fallback is a
separate, only partially-overlapping safety net), a Phase 4 or Phase 5 crash left the global
halt flag untouched and Phase 8 could submit real entry orders in the same run despite
broker-vs-DB reconciliation (Phase 4) or exposure/regime constraints (Phase 5) never having
actually been verified this cycle.

Fixed: wrap each run_phaseN() call in try/except, mirroring Phase 1/2/9's pattern exactly -
set_halt_flag(triggered_by=...) before re-raising, and fail hard via RuntimeError
(GOVERNANCE VIOLATION) if the halt flag itself can't be set.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestration.orchestrator import Orchestrator


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


class TestPhase4CrashSetsHaltFlag:
    def test_run_phase4_exception_sets_halt_flag_before_reraising(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        boom = RuntimeError("simulated ConfigValidationError")

        with (
            patch("algo.orchestration.orchestrator.run_phase4", side_effect=boom),
            pytest.raises(RuntimeError),
        ):
            instance._executor_phase_4()

        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase4_reconciliation"

    def test_halt_flag_set_failure_after_phase4_crash_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False

        with (
            patch("algo.orchestration.orchestrator.run_phase4", side_effect=ValueError("boom")),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance._executor_phase_4()


class TestPhase5CrashSetsHaltFlag:
    def test_run_phase5_exception_sets_halt_flag_before_reraising(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        boom = RuntimeError("simulated ConfigValidationError")

        with (
            patch("algo.orchestration.orchestrator.run_phase5", side_effect=boom),
            pytest.raises(RuntimeError),
        ):
            instance.phase_5_exposure_policy()

        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase5_exposure_policy"

    def test_halt_flag_set_failure_after_phase5_crash_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False

        with (
            patch("algo.orchestration.orchestrator.run_phase5", side_effect=ValueError("boom")),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance.phase_5_exposure_policy()
