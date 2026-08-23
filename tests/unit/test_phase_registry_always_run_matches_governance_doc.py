"""Regression test: steering/GOVERNANCE.md's "Key Principle" claims about which phases carry
always_run=True must match algo/orchestrator/phase_registry.py's actual current values.

Found stale 2026-08-23 (goal session, steering-doc accuracy audit): the doc claimed "only
phases 3, 6, 8, 9" are always_run=True, but phases 4, 5, and 7 were switched to always_run=True
at some point after that claim was written - phase_executor.py's own comment ("BUG FOUND
2026-08-10: since every phase from 3-9 is now always_run...") confirms this and explicitly
states the skip_if_halted mechanism the doc separately described for phases 4/5/7 is now dead/
unreachable code. Fixed the doc; this test exists so a future change to always_run values gets
caught here instead of silently re-staling the doc again.
"""

from algo.orchestrator.phase_registry import PhaseRegistry

_PHASES_BY_NUM = {p.phase_num: p for p in PhaseRegistry.PHASES}

ALWAYS_RUN_PHASES = {3, 4, 5, 6, 7, 8, 9}
GATED_PHASES = {1, 2}


def test_phases_3_through_9_are_always_run() -> None:
    for phase_num in ALWAYS_RUN_PHASES:
        phase = _PHASES_BY_NUM[phase_num]
        assert phase.always_run is True, (
            f"Phase {phase_num} always_run={phase.always_run} - steering/GOVERNANCE.md's Key "
            f"Principle section needs updating if this changed intentionally"
        )


def test_phases_1_and_2_are_not_always_run() -> None:
    for phase_num in GATED_PHASES:
        phase = _PHASES_BY_NUM[phase_num]
        assert phase.always_run is False, (
            f"Phase {phase_num} always_run={phase.always_run} - if phases 1/2 also became "
            f"always_run, the halt-gating mechanism itself may need re-examining, not just docs"
        )
