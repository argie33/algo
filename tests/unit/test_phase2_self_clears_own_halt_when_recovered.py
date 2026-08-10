"""Regression test: Phase 2 circuit breaker must self-clear its own halt once it re-evaluates
as healthy, since halt_flag_cleared_by_unrelated_phase_fix_20260810 stopped Phase 1 from
blindly clearing halts it didn't set.

Before that fix, Phase 2 only ever called set_halt_flag() (never cleared it) - the only thing
that ever unstuck a phase2_circuit_breaker halt was Phase 1's blanket clear on its next
successful freshness check, which was itself the bug (it also wiped Phase 9's much more
dangerous governance halt). Fixing that without giving Phase 2 its own clear path would have
left every circuit-breaker trip stuck until manual intervention forever, even after a
completely healthy re-evaluation - a real operational regression for something as routine as
a transient drawdown dip that recovers.

Phase 2 is safe to self-clear (unlike Phase 9 - see that phase's own comment): it re-evaluates
live, current data every run and runs before Phase 8 in the same run, so a "clear" here
reflects this run's own fresh assessment, not stale reassurance carried across a run boundary.
It must only ever clear a halt it recognizes as its own.

Live-verified end-to-end: injected a phase2_circuit_breaker-tagged halt via direct SQL, ran a
full local orchestrator invocation. Confirmed via log "[PHASE 2] Circuit breaker checks now
clear - clearing the halt flag it previously set." / "[HALT_FLAG_CLEARED] Phase 2 circuit
breaker checks are clear" and a direct DB re-query (halt_flag=False afterward).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from algo.orchestration.orchestrator import Orchestrator


def _make_orchestrator(halt_triggered_by):
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


def _run_phase2_with_result(instance, halted, error=None):
    fake_result = SimpleNamespace(halted=halted, error=error)
    with patch("algo.orchestration.orchestrator.run_phase2", return_value=fake_result):
        return instance.phase_2_circuit_breakers()


class TestPhase2SelfClearsOwnHalt:
    def test_clears_its_own_halt_when_now_healthy(self):
        instance = _make_orchestrator(halt_triggered_by="phase2_circuit_breaker")
        _run_phase2_with_result(instance, halted=False)
        instance.halt_manager.clear_halt_flag.assert_called_once()

    def test_does_not_clear_a_phase1_halt(self):
        instance = _make_orchestrator(halt_triggered_by="phase1_data_freshness")
        _run_phase2_with_result(instance, halted=False)
        instance.halt_manager.clear_halt_flag.assert_not_called()

    def test_does_not_clear_a_phase9_halt(self):
        instance = _make_orchestrator(halt_triggered_by="phase9_reconciliation_governance")
        _run_phase2_with_result(instance, halted=False)
        instance.halt_manager.clear_halt_flag.assert_not_called()

    def test_does_not_clear_a_manual_operator_halt(self):
        instance = _make_orchestrator(halt_triggered_by="manual_operator")
        _run_phase2_with_result(instance, halted=False)
        instance.halt_manager.clear_halt_flag.assert_not_called()

    def test_still_sets_halt_tagged_as_its_own_when_it_fires(self):
        instance = _make_orchestrator(halt_triggered_by=None)
        _run_phase2_with_result(instance, halted=True, error="drawdown breach")
        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase2_circuit_breaker"
