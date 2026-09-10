"""Regression test for a real-money-readiness safety gap in Phase 3 (position monitor):
result.halted=True (set by phase3_position_monitor.py on a position-monitor crash, both the
paper-mode and live-mode branches) never reached the shared halt flag.

Phase 6 already treats Phase 3's own result as informational-only and continues (documented
"always_run" behavior), and Phase 5/7/8 never look at Phase 3's result at all - they only check
self.halt_manager's shared flag via check_halt_flag(). Without routing Phase 3's halted status
through set_halt_flag(), Phase 8 could still submit brand-new entry orders in the same run
despite Phase 3 believing position monitoring - and therefore trading - should be halted.

Fixed: phase_3_position_monitor() now calls set_halt_flag() when result.halted is True,
mirroring Phase 1/2/9's identical pattern, and fails hard via RuntimeError (GOVERNANCE
VIOLATION) if the halt flag itself can't be set.
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


class TestPhase3HaltedSetsHaltFlag:
    def test_phase3_halted_result_sets_halt_flag(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True
        halted_result = PhaseResult(
            3, "position_monitor", "halted", {"recommendations": []}, True, "position monitor crashed"
        )

        with patch("algo.orchestration.orchestrator.run_phase3", return_value=halted_result):
            ok = instance.phase_3_position_monitor()

        assert ok is False
        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase3_position_monitor"

    def test_halt_flag_set_failure_after_phase3_halted_raises_governance_violation(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False
        halted_result = PhaseResult(
            3, "position_monitor", "halted", {"recommendations": []}, True, "position monitor crashed"
        )

        with (
            patch("algo.orchestration.orchestrator.run_phase3", return_value=halted_result),
            pytest.raises(RuntimeError, match="GOVERNANCE VIOLATION"),
        ):
            instance.phase_3_position_monitor()

    def test_phase3_ok_result_does_not_touch_halt_flag(self):
        instance = _make_orchestrator()
        ok_result = PhaseResult(3, "position_monitor", "ok", {"recommendations": []}, False, None)

        with patch("algo.orchestration.orchestrator.run_phase3", return_value=ok_result):
            ok = instance.phase_3_position_monitor()

        assert ok is True
        instance.halt_manager.set_halt_flag.assert_not_called()
