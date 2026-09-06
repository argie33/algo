"""Regression test for the algo_orchestrator Lambda's risk-monitor dispatch.

UPDATED 2026-09-06: `mode: "stop_loss_guardian"` and `mode: "intraday_risk_monitor"` were
two separate dispatches (this file originally tested only the former in isolation). Both
are now consolidated into `algo/risk/unified_risk_monitor.py::check_unified_risk`, run on
one 5-minute schedule instead of the old separate stop-loss-guardian/intraday-risk-monitor
cadences (which absorbed 2 further separately-packaged Lambdas - circuit-breaker and
execution-monitor - not dispatched through this file). `stop_loss_guardian`/
`intraday_risk_monitor` are now deprecated aliases that forward to the same consolidated
check, kept for one deploy cycle so an in-flight EventBridge schedule using the old
payload shape during cutover doesn't hard-fail.

Confirms the dispatch (1) calls the shared consolidated check - not a reimplementation -
for the canonical mode AND both deprecated aliases, and (2) surfaces an unexpected failure
as a failed invocation rather than a fake 200.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "lambda" / "algo_orchestrator" / "lambda_function.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("algo_orchestrator_lambda_function_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", ["unified_risk_monitor", "stop_loss_guardian", "intraday_risk_monitor"])
def test_risk_monitor_modes_call_shared_unified_check_and_return_200(mode):
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    mock_config = MagicMock()

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", return_value=mock_config),
        patch("algo.risk.unified_risk_monitor.check_unified_risk") as mock_check,
    ):
        result = module.lambda_handler({"mode": mode}, None)

    mock_check.assert_called_once()
    assert mock_check.call_args.args[0] is mock_config
    assert result["statusCode"] == 200


@pytest.mark.parametrize("mode", ["unified_risk_monitor", "stop_loss_guardian", "intraday_risk_monitor"])
def test_risk_monitor_modes_do_not_run_full_orchestrator(mode):
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", return_value=MagicMock()),
        patch("algo.risk.unified_risk_monitor.check_unified_risk"),
        patch("algo.orchestration.Orchestrator") as mock_orchestrator_cls,
    ):
        module.lambda_handler({"mode": mode}, None)

    mock_orchestrator_cls.assert_not_called()


@pytest.mark.parametrize("mode", ["unified_risk_monitor", "stop_loss_guardian", "intraday_risk_monitor"])
def test_risk_monitor_modes_surface_unexpected_failure_as_500(mode):
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", side_effect=RuntimeError("config boom")),
    ):
        result = module.lambda_handler({"mode": mode}, None)

    assert result["statusCode"] == 500
