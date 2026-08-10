"""Regression test for a CRITICAL safety bug: Phase 1 unconditionally cleared any active
halt flag whenever its own freshness check passed, regardless of which phase had actually
set it or why.

Live-reproduced 2026-08-10: manually set algo_runtime_state.halt_flag=True with an unrelated
reason ("LIVE STRESS TEST"), ran a full local orchestrator invocation. Phase 1's freshness
check passed and unconditionally called clear_halt_flag() - confirmed via
"[HALT_FLAG_CLEARED] Phase 1 verified data is fresh" in the log, with the halt wiped despite
having nothing to do with data freshness.

The dangerous concrete case: Phase 9's reconciliation-governance halt (phase9_reconciliation.py)
is set at the END of a run specifically to block Phase 8 from submitting real orders on the
*next* run with an unverified portfolio state (a real broker/DB reconciliation failure in
execution_mode=auto). Since Phase 1 runs before Phase 8/9 in that next run, its unconditional
clear erased the Phase 9 halt before Phase 9 (or anything else) ever got a chance to re-verify
the underlying reconciliation problem was actually resolved - Phase 8 would then trade with an
unverified portfolio state, exactly what the Phase 9 halt existed to prevent.

Fixed: set_halt_flag() now tags each halt with `triggered_by` (which phase set it).
Phase 1's success path only auto-clears a halt if no halt is active, or the active halt's
triggered_by is "phase1_data_freshness" (its own). Halts set by phase2_circuit_breaker or
phase9_reconciliation_governance are left in place - only that phase's own logic (or explicit
manual intervention) may resolve and clear them.

Live re-verified end-to-end after the fix: injected a phase9-tagged halt, ran a full local
orchestrator invocation, confirmed via log
"[PHASE 1] Data is fresh, but the active halt flag was set by 'phase9_reconciliation_governance'
... leaving it in place" that the halt survived, and Phase 7/8 correctly halted/refused to
trade as a result.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from algo.orchestration.orchestrator import Orchestrator


def _make_orchestrator(halt_triggered_by):
    """Real Orchestrator instance (bypassing __init__) with just enough state for
    phase_1_data_freshness() to run for real."""
    instance = Orchestrator.__new__(Orchestrator)
    instance.config = {}
    instance.run_date = None
    instance.dry_run = True
    instance.alerts = MagicMock()
    instance.verbose = False
    instance.phase_results = {}
    instance.execution_tracker = MagicMock()
    instance.halt_manager = MagicMock()
    instance.halt_manager.get_halt_triggered_by.return_value = halt_triggered_by
    return instance


def _run_phase1_with_status(instance, status, halted=False, error=None):
    fake_result = SimpleNamespace(status=status, halted=halted, error=error)
    with (
        patch("algo.orchestration.orchestrator.run_phase1", return_value=fake_result),
        patch.dict("os.environ", {"LOCAL_MODE": "true"}),
    ):
        return instance.phase_1_data_freshness()


class TestPhase1DoesNotClearUnrelatedHalts:
    def test_does_not_clear_halt_set_by_phase9_governance(self):
        instance = _make_orchestrator(halt_triggered_by="phase9_reconciliation_governance")
        _run_phase1_with_status(instance, "ok")
        instance.halt_manager.clear_halt_flag.assert_not_called()

    def test_does_not_clear_halt_set_by_phase2_circuit_breaker(self):
        instance = _make_orchestrator(halt_triggered_by="phase2_circuit_breaker")
        _run_phase1_with_status(instance, "ok")
        instance.halt_manager.clear_halt_flag.assert_not_called()

    def test_clears_halt_it_set_itself(self):
        instance = _make_orchestrator(halt_triggered_by="phase1_data_freshness")
        _run_phase1_with_status(instance, "ok")
        instance.halt_manager.clear_halt_flag.assert_called_once()

    def test_clears_when_no_halt_is_currently_active(self):
        instance = _make_orchestrator(halt_triggered_by=None)
        _run_phase1_with_status(instance, "ok")
        instance.halt_manager.clear_halt_flag.assert_called_once()

    def test_degraded_status_sets_halt_tagged_as_phase1(self):
        instance = _make_orchestrator(halt_triggered_by=None)
        instance.halt_manager.set_halt_flag.return_value = True
        _run_phase1_with_status(instance, "degraded", error="stale data")
        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase1_data_freshness"
