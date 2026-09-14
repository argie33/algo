"""Regression test for a CRITICAL real-money-readiness safety gap in Phase 3 (position
monitor): the same crash-swallows-halt-flag bug class already fixed for Phases 1/2/4/5/6/9
(see test_phase1_crash_sets_halt_flag_20260906.py,
test_phase2_phase9_crash_sets_halt_flag_20260907.py,
test_phase4_phase5_crash_sets_halt_flag_20260910.py) but never actually applied to
phase_3_position_monitor() - despite phase_5_exposure_policy()'s own copy of this exact
comment already (incorrectly) claiming "same bug class as Phase 1/2/3/4/6/9's identical
fixes this session".

An unhandled exception raised inside run_phase3() used to propagate straight past
phase_3_position_monitor()'s own `if result.halted` branch - the ONLY place it called
set_halt_flag() - and hit phase_executor.py's generic Exception handler instead, which
records PhaseResult(status="error", halted=False) without ever touching the shared halt
flag. Since Phase 3 is always_run=True and Phase 5/7/8 only ever consult
self.halt_manager's shared flag (not Phase 3's own result object), a Phase 3 crash left
the global halt flag untouched and Phase 8 could submit real entry orders in the same run
despite position monitoring having crashed entirely.

Fixed: wrap run_phase3() in try/except, mirroring Phase 1/2/4/5/6/9's pattern exactly -
set_halt_flag(triggered_by="phase3_position_monitor") before re-raising, and fail hard via
RuntimeError (GOVERNANCE VIOLATION) if the halt flag itself can't be set.
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


class TestPhase3CrashSetsHaltFlag:
    def test_run_phase3_exception_sets_halt_flag_before_reraising(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        boom = RuntimeError("simulated position-monitor crash")

        with (
            patch("algo.orchestration.orchestrator.run_phase3", side_effect=boom),
            pytest.raises(RuntimeError),
        ):
            instance.phase_3_position_monitor()

        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase3_position_monitor"

    def test_halt_flag_set_failure_after_phase3_crash_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False

        with (
            patch("algo.orchestration.orchestrator.run_phase3", side_effect=ValueError("boom")),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance.phase_3_position_monitor()

    def test_original_exception_is_the_cause_of_the_governance_violation(self):
        """The re-raised RuntimeError must chain the original crash (`from e`), not hide it -
        matches the sibling phases' pattern so the real root cause stays visible in logs."""
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False
        original = ValueError("original crash detail")

        with patch("algo.orchestration.orchestrator.run_phase3", side_effect=original):
            try:
                instance.phase_3_position_monitor()
                raise AssertionError("expected RuntimeError")
            except RuntimeError as governance_err:
                assert governance_err.__cause__ is original
