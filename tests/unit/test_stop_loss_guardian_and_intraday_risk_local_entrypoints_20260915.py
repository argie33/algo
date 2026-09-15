"""Tests for scripts/run_stop_loss_guardian.py and scripts/run_intraday_risk_monitor.py -
the local (no-AWS) equivalents of the AWS Scheduler->Lambda `mode: "stop_loss_guardian"` /
`mode: "intraday_risk_monitor"` dispatches in lambda/algo_orchestrator/lambda_function.py.

Added 2026-09-15 (goal: "keeps failing halting", user confirmed local-only deployment - no
AWS account in use). Neither underlying check function needed new logic - both already exist
and are exercised by their own dedicated test files (test_stop_loss_guardian_dispatch_20260905.py,
test_intraday_risk_monitor_20260906.py). These tests only cover the thin new entrypoints: that
main() calls the right function with the right arguments, and that a genuine failure exits
nonzero (Task Scheduler's LastTaskResult, the only local surface an operator would ever check
for a silently-broken 15-min safety check to show up in).
"""

from unittest.mock import MagicMock, patch


class TestRunStopLossGuardian:
    def test_calls_guardian_step_with_sync_positions_first_true(self) -> None:
        """sync_positions_first=True is required for the standalone dispatch path - it has
        no preceding full-reconciliation step (unlike the main orchestrator flow), so it
        must sync positions itself first to avoid false "missing stop leg" alarms on a
        position that already closed since the last full orchestrator run."""
        fake_config = MagicMock()
        with (
            patch("algo.infrastructure.config.get_config", return_value=fake_config),
            patch("algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step") as step,
        ):
            from scripts.run_stop_loss_guardian import main

            assert main() == 0
            step.assert_called_once()
            args, kwargs = step.call_args
            assert args[1] is fake_config
            assert kwargs.get("sync_positions_first") is True

    def test_guardian_exception_exits_nonzero(self) -> None:
        with (
            patch("algo.infrastructure.config.get_config", return_value=MagicMock()),
            patch(
                "algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step",
                side_effect=RuntimeError("boom"),
            ),
        ):
            from scripts.run_stop_loss_guardian import main

            assert main() == 1


class TestRunIntradayRiskMonitor:
    def test_calls_check_intraday_risk_with_config(self) -> None:
        fake_config = MagicMock()
        with (
            patch("algo.infrastructure.config.get_config", return_value=fake_config),
            patch("algo.risk.intraday_risk_monitor.check_intraday_risk", return_value={"breached": False}) as check,
        ):
            from scripts.run_intraday_risk_monitor import main

            assert main() == 0
            check.assert_called_once_with(fake_config)

    def test_monitor_exception_exits_nonzero(self) -> None:
        with (
            patch("algo.infrastructure.config.get_config", return_value=MagicMock()),
            patch("algo.risk.intraday_risk_monitor.check_intraday_risk", side_effect=RuntimeError("boom")),
        ):
            from scripts.run_intraday_risk_monitor import main

            assert main() == 1
