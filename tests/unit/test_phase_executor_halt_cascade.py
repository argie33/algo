"""Verifies OrchestratorPhaseExecutor's halt-cascade behavior.

Replaces the always-skipped stubs in tests/test_session_282_integration.py
(test_phase_failures_halt_subsequent_phases, test_phase_6_always_runs_on_halt,
test_phase_9_always_runs, test_phases_execute_in_sequence) - those called
pytest.skip() unconditionally and never actually exercised the executor. This
is the exact mechanism a 2026-07-21 audit session flagged as looking like a
possible bypass ("some stages halted yet some completed afterwards") - it
turned out to be intentional (Phase 3/6/9 always_run for risk management) but
was previously unverified by any real test.
"""

from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_result import PhaseResult


def _halting_phase(phase_num: int) -> PhaseResult:
    return PhaseResult(phase_num, f"phase_{phase_num}", "halted", {}, True, "simulated halt")


def _ok_phase(phase_num: int) -> PhaseResult:
    return PhaseResult(phase_num, f"phase_{phase_num}", "ok", {"ran": True}, False, None)


def test_non_always_run_phase_skipped_after_earlier_halt():
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    executor.register_phases(
        [
            PhaseDefinition(1, "one", [], lambda executor, **kw: _halting_phase(1)),
            PhaseDefinition(2, "two", [], lambda executor, **kw: _ok_phase(2)),
        ]
    )

    summary = executor.run()

    assert summary["results"][1].halted
    result_2 = summary["results"][2]
    assert result_2.status == "skipped"
    assert result_2.halted
    assert result_2.data.get("reason") == "phase skipped - no data available"


def test_always_run_phase_executes_after_earlier_halt():
    """Phase 6 (exits) / Phase 9 (reconciliation) must still run when an earlier phase halts."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    executed_always_run = []

    def always_run_fn(executor, **kw):
        executed_always_run.append(True)
        return _ok_phase(9)

    executor.register_phases(
        [
            PhaseDefinition(1, "one", [], lambda executor, **kw: _halting_phase(1)),
            PhaseDefinition(9, "always", [], always_run_fn, always_run=True),
        ]
    )

    summary = executor.run()

    assert executed_always_run == [True]
    assert summary["results"][9].status == "ok"


def test_entry_phase_still_gated_after_halt_not_bypassed():
    """A halt must NOT let a downstream entry-style phase (skip_if_halted=True, always_run=False) execute."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    entry_executed = []

    def entry_fn(executor, **kw):
        entry_executed.append(True)
        return _ok_phase(8)

    executor.register_phases(
        [
            PhaseDefinition(2, "circuit_breakers", [], lambda executor, **kw: _halting_phase(2)),
            PhaseDefinition(8, "entry_execution", [], entry_fn, skip_if_halted=True, always_run=False),
        ]
    )

    summary = executor.run()

    assert entry_executed == [], "entry phase must not execute once an earlier phase halted"
    assert summary["results"][8].status == "skipped"
    assert summary["results"][8].halted


def test_success_count_only_reflects_ok_phases():
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    executor.register_phases(
        [
            PhaseDefinition(1, "one", [], lambda executor, **kw: _ok_phase(1)),
            PhaseDefinition(2, "two", [], lambda executor, **kw: _halting_phase(2)),
            PhaseDefinition(9, "always", [], lambda executor, **kw: _ok_phase(9), always_run=True),
        ]
    )

    summary = executor.run()

    assert summary["phases_executed"] == 2  # phase 1 and phase 9, not phase 2
    assert summary["error_phase"] == 2
    assert summary["success"] is False


def test_dependency_failure_stores_error_result_not_missing():
    """A phase whose dependency failed must get a stored 'error' PhaseResult, not be silently absent
    (silent absence would make downstream code treat it as 'never executed' instead of 'failed')."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    executor.register_phases(
        [
            PhaseDefinition(4, "reconciliation", [], lambda executor, **kw: _halting_phase(4), always_run=True),
            PhaseDefinition(5, "exposure_policy", [4], lambda executor, **kw: _ok_phase(5), always_run=True),
        ]
    )

    executor.run()

    result_5 = executor.get_result(5)
    assert result_5 is not None
    assert result_5.status == "error"
    assert "DEPENDENCY FAILED" in (result_5.error or "")
