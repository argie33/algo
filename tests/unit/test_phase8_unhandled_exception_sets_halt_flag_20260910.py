"""Regression test for a real-money-readiness safety gap in Phase 8 (entry execution):
unlike Phase 6/9, _executor_phase_8() had NO try/except at all around run_phase8(). Phase 8 is
real order submission - a mid-loop exception that isn't one of run_phase8()'s own narrowly
caught types propagates straight to OrchestratorPhaseExecutor.execute_phase()'s generic
Exception handler, which marks this run's Phase 8 status="error" but never sets the shared
halt_manager flag (only an explicit PhaseResult(halted=True) does that, and none was ever
returned since the exception bypassed PhaseResult construction entirely). Some symbols may
already have been entered before the crash; the next scheduled run would have no signal that
entry execution failed catastrophically mid-run.

Fixed: _executor_phase_8() now wraps run_phase8() in try/except and calls set_halt_flag() on
any exception, mirroring Phase 6/9's halted-result pattern, then re-raises.
"""

from unittest.mock import MagicMock, patch

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


def _make_executor_stub():
    executor = MagicMock()
    executor.get_phase_data_required.return_value = {"halt_new_entries": False}
    return executor


class TestPhase8UnhandledExceptionSetsHaltFlag:
    def test_unhandled_exception_sets_halt_flag_then_reraises(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = True

        with patch(
            "algo.orchestration.orchestrator.run_phase8",
            side_effect=KeyError("malformed signal payload"),
        ):
            try:
                instance._executor_phase_8(executor=_make_executor_stub())
                raised = False
            except KeyError:
                raised = True

        assert raised, "the original exception must still propagate after setting the halt flag"
        instance.halt_manager.set_halt_flag.assert_called_once()
        _, kwargs = instance.halt_manager.set_halt_flag.call_args
        assert kwargs.get("triggered_by") == "phase8_entry_execution"

    def test_halt_flag_set_failure_is_logged_but_original_exception_still_raised(self):
        instance = _make_orchestrator()
        instance.halt_manager.set_halt_flag.return_value = False

        with patch(
            "algo.orchestration.orchestrator.run_phase8",
            side_effect=RuntimeError("unexpected broker client error"),
        ):
            try:
                instance._executor_phase_8(executor=_make_executor_stub())
                raised = False
            except RuntimeError:
                raised = True

        assert raised
        instance.halt_manager.set_halt_flag.assert_called_once()

    def test_normal_result_does_not_touch_halt_flag(self):
        instance = _make_orchestrator()
        from algo.orchestrator.phase_result import PhaseResult

        ok_result = PhaseResult(8, "entry_execution", "ok", {"entered": 1}, False, None)

        with patch("algo.orchestration.orchestrator.run_phase8", return_value=ok_result):
            result = instance._executor_phase_8(executor=_make_executor_stub())

        assert result.halted is False
        instance.halt_manager.set_halt_flag.assert_not_called()
