"""Regression test for a CRITICAL real-money-readiness safety gap: an unhandled exception
inside Phase 1's own run_phase1() call used to propagate straight past all of
phase_1_data_freshness()'s halt-flag logic - "degraded" set the flag, "halted" set the flag,
"ok" cleared it, but a raw exception (e.g. psycopg2.OperationalError, or any bug inside
phase1_data_freshness.py/phase1_price_freshness.py/phase1_table_freshness.py) hit none of
those branches. It propagated up to phase_executor.py's generic Exception handler, which
records PhaseResult(status="error", halted=False) - never calling set_halt_flag() anywhere.

Since phases 3/4/5/6/7/8/9 are all always_run=True and Phase 5's exposure constraints don't
depend on Phase 1's result, a Phase 1 crash left the global halt flag completely untouched:
Phase 8 would check check_halt_flag(), see it False, and place real entry orders on data
Phase 1 never actually validated as fresh.

Fixed: wrap the run_phase1() call in try/except. On any exception, call
set_halt_flag(triggered_by="phase1_data_freshness") before re-raising, mirroring the existing
degraded/halted branches' own pattern (including failing hard via RuntimeError if the halt
flag itself can't be set - a halt-flag failure must never be silently swallowed).
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


class TestPhase1CrashSetsHaltFlag:
    def test_run_phase1_exception_sets_halt_flag_before_reraising(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        boom = RuntimeError("simulated psycopg2.OperationalError")

        with (
            patch("algo.orchestration.orchestrator.run_phase1", side_effect=boom),
            patch.dict("os.environ", {"LOCAL_MODE": "true"}),
            pytest.raises(RuntimeError),
        ):
            instance.phase_1_data_freshness()

        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase1_data_freshness"
        # clear_halt_flag must never be reached on a crash - only the halted/degraded-style
        # set_halt_flag path applies.
        instance.halt_manager.clear_halt_flag.assert_not_called()

    def test_halt_flag_set_failure_after_crash_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False

        with (
            patch("algo.orchestration.orchestrator.run_phase1", side_effect=ValueError("boom")),
            patch.dict("os.environ", {"LOCAL_MODE": "true"}),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance.phase_1_data_freshness()
