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


def test_skipped_phase_error_names_the_actual_halting_phase():
    """A phase skipped due to an EARLIER phase's halt must carry that phase's real reason in
    .error, not None/"unknown reason" - this is what downstream always_run phases (e.g. Phase 6)
    read when logging why they're running in degraded mode. Regression test for the bug where
    Phase 6 logged "Phase 5 halted: unknown reason" even though the actual halt was Phase 2's
    circuit breaker - Phase 5 itself never ran and never set an error, so downstream code
    got None with no way to see the real cause."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    executor.register_phases(
        [
            PhaseDefinition(
                2,
                "circuit_breakers",
                [],
                lambda executor, **kw: PhaseResult(
                    2, "circuit_breakers", "halted", {}, True, "Consecutive Losses Limit: 10 consecutive losses >= 5"
                ),
            ),
            PhaseDefinition(5, "exposure_policy", [], lambda executor, **kw: _ok_phase(5)),
        ]
    )

    executor.run()

    result_5 = executor.get_result(5)
    assert result_5.status == "skipped"
    assert result_5.halted
    assert "Phase 2" in result_5.error
    assert "Consecutive Losses Limit" in result_5.error


def test_global_halt_flag_skip_names_the_real_reason_not_unknown():
    """A phase skipped because the GLOBAL halt flag is active (e.g. manual operator kill
    switch, or a halt already active before this run started - NOT an earlier phase in this
    same run halting) must still carry a real reason in .error, not None. Regression test for
    the live-reproduced bug where this path built its PhaseResult with no `error` at all
    (halt_check_fn only returns a bool), so downstream degraded-mode logging (Phase 6) fell
    back to "unknown reason" - the exact symptom test_skipped_phase_error_names_the_actual_halting_phase
    already fixed for the cascade-skip path, but that fix didn't cover this separate path."""
    executor = OrchestratorPhaseExecutor(
        config={},
        halt_check_fn=lambda: True,
        halt_reason_fn=lambda: "Operator manual override: investigating anomaly",
    )
    executor.register_phases(
        [
            PhaseDefinition(5, "exposure_policy", [], lambda executor, **kw: _ok_phase(5)),
        ]
    )

    executor.run()

    result_5 = executor.get_result(5)
    assert result_5.status == "skipped"
    assert result_5.halted
    assert result_5.error is not None
    assert "unknown reason" not in result_5.error
    assert "Operator manual override: investigating anomaly" in result_5.error


def test_global_halt_flag_skip_without_reason_fn_still_non_null():
    """Same as above, but when the executor wasn't given a halt_reason_fn at all (defensive
    default) - must still produce a non-null, non-empty error, never bare None."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: True)
    executor.register_phases(
        [
            PhaseDefinition(5, "exposure_policy", [], lambda executor, **kw: _ok_phase(5)),
        ]
    )

    executor.run()

    result_5 = executor.get_result(5)
    assert result_5.error
    assert "halt flag is active" in result_5.error


def test_dependency_halted_stores_skipped_result_not_missing_or_critical_error() -> None:
    """A phase whose dependency HALTED (not crashed) must get a stored 'skipped' PhaseResult -
    not silently absent (downstream code must not treat it as 'never executed'), and not
    'error' either.

    BUG FOUND 2026-08-10: since every phase 3-9 is now always_run (fixed earlier the same
    session so risk-management phases run during a halt), the clean direct halt-flag-check
    path became unreachable for all of them - every halt now has to propagate through the
    dependency-check path instead, which used to treat "my dependency correctly halted" the
    same as a genuine crash: CRITICAL log + status="error". dashboard/panels/health.py renders
    phases_errored in red, so every routine halt cascade painted the dashboard as if something
    had broken. Fixed to detect a halted (not merely failed) dependency and report status=
    "skipped"/halted=True at info level instead - matching the vocabulary the direct halt-check
    path already used before always_run made it unreachable."""
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
    assert result_5.status == "skipped"
    assert result_5.halted
    assert "DEPENDENCY FAILED" in (result_5.error or "")


def test_halted_dependency_fix_covers_every_real_phase_not_just_one_pair() -> None:
    """The fix lives once in execute_phase()'s shared dependency-check fallback, not
    duplicated per phase - so it must protect every real dependency edge in
    phase_registry.py's actual topology (4->3, 5->4, 6->3, 7->5, 8->[5,7]), not just the
    Phase 7->8 pair that was live-reproduced. Mirrors the real registry: phase 3 halts, and
    phases 4 and 6 (two independent, unrelated dependents of 3) must both come back
    'skipped', not 'error' - proving the fix isn't hardcoded to one specific phase pair."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    executor.register_phases(
        [
            PhaseDefinition(3, "position_monitor", [], lambda executor, **kw: _halting_phase(3), always_run=True),
            PhaseDefinition(4, "reconciliation", [3], lambda executor, **kw: _ok_phase(4), always_run=True),
            PhaseDefinition(6, "exit_execution", [3], lambda executor, **kw: _ok_phase(6), always_run=True),
        ]
    )

    executor.run()

    for phase_num in (4, 6):
        result = executor.get_result(phase_num)
        assert result is not None
        assert result.status == "skipped", f"phase {phase_num} expected 'skipped', got {result.status!r}"
        assert result.halted


def test_dependency_genuinely_errored_still_stores_critical_error_result() -> None:
    """A phase whose dependency genuinely errored (not halted - e.g. an unhandled exception
    in the dependency's own logic) must still get the original CRITICAL 'error' treatment,
    not be softened to 'skipped' - only a halted dependency gets the gentler treatment."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)
    executor.register_phases(
        [
            PhaseDefinition(
                4,
                "reconciliation",
                [],
                lambda executor, **kw: PhaseResult(4, "reconciliation", "error", {}, False, "boom"),
                always_run=True,
            ),
            PhaseDefinition(5, "exposure_policy", [4], lambda executor, **kw: _ok_phase(5), always_run=True),
        ]
    )

    executor.run()

    result_5 = executor.get_result(5)
    assert result_5 is not None
    assert result_5.status == "error"
    assert "DEPENDENCY FAILED" in (result_5.error or "")
