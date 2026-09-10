"""Regression test for a CRITICAL real-money-readiness safety gap in Phase 2 (circuit
breakers) and Phase 9 (reconciliation): the same crash-swallows-halt-flag bug class already
fixed for Phase 1 (see test_phase1_crash_sets_halt_flag_20260906.py) but never applied to
these two methods.

An unhandled exception inside run_phase2()/run_phase9() used to propagate straight past
phase_2_circuit_breakers()/phase_9_reconcile()'s own halt-flag logic (their `if result.halted`
branches, the ONLY places these methods called set_halt_flag()) and hit
phase_executor.py's generic Exception handler instead, which records
PhaseResult(status="error", halted=False) without ever touching the halt flag. Since phases
3-9 are all always_run=True, a Phase 2 or Phase 9 crash left the global halt flag exactly as
it was before the run - Phase 8 would check check_halt_flag(), see it unaffected by this
run's crash, and place real entry orders with circuit breakers (Phase 2) or portfolio
reconciliation (Phase 9) never actually verified this cycle.

Fixed: wrap each run_phaseN() call in try/except, mirroring Phase 1's pattern exactly -
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


class TestPhase2CrashSetsHaltFlag:
    def test_run_phase2_exception_sets_halt_flag_before_reraising(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        boom = RuntimeError("simulated psycopg2.OperationalError")

        with (
            patch("algo.orchestration.orchestrator.run_phase2", side_effect=boom),
            pytest.raises(RuntimeError),
        ):
            instance.phase_2_circuit_breakers()

        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase2_circuit_breaker"
        instance.halt_manager.clear_halt_flag.assert_not_called()

    def test_halt_flag_set_failure_after_phase2_crash_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False

        with (
            patch("algo.orchestration.orchestrator.run_phase2", side_effect=ValueError("boom")),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance.phase_2_circuit_breakers()


class TestPhase9CrashSetsHaltFlag:
    def test_run_phase9_exception_sets_halt_flag_before_reraising(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        boom = RuntimeError("simulated broker API failure")

        with (
            patch("algo.orchestration.orchestrator.run_phase9", side_effect=boom),
            pytest.raises(RuntimeError),
        ):
            instance.phase_9_reconcile()

        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase9_reconciliation_governance"

    def test_halt_flag_set_failure_after_phase9_crash_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False

        with (
            patch("algo.orchestration.orchestrator.run_phase9", side_effect=ValueError("boom")),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance.phase_9_reconcile()
