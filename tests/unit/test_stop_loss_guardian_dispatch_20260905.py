"""Regression test for the algo_orchestrator Lambda's `mode: "stop_loss_guardian"`
dispatch (2026-09-05, real-money-readiness audit): a tightly-scheduled EventBridge rule
can invoke the SAME orchestrator Lambda to run ONLY the stop-loss protection
verify/auto-repair check (phase9_reconciliation.py) between full 9-phase runs, without
touching order entry/exit logic or running any phase. Confirms the dispatch (1) calls
the shared verification function - not a reimplementation - and (2) surfaces an
unexpected failure as a failed invocation rather than a fake 200.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

MODULE_PATH = Path(__file__).resolve().parents[2] / "lambda" / "algo_orchestrator" / "lambda_function.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("algo_orchestrator_lambda_function_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stop_loss_guardian_mode_calls_shared_verification_step_and_returns_200():
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    mock_config = MagicMock()

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", return_value=mock_config),
        patch("algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step") as mock_verify,
    ):
        result = module.lambda_handler({"mode": "stop_loss_guardian"}, None)

    mock_verify.assert_called_once()
    assert mock_verify.call_args.args[1] is mock_config
    assert result["statusCode"] == 200


def test_stop_loss_guardian_mode_does_not_run_full_orchestrator():
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", return_value=MagicMock()),
        patch("algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step"),
        patch("algo.orchestration.Orchestrator") as mock_orchestrator_cls,
    ):
        module.lambda_handler({"mode": "stop_loss_guardian"}, None)

    mock_orchestrator_cls.assert_not_called()


def test_stop_loss_guardian_mode_surfaces_unexpected_failure_as_500():
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", side_effect=RuntimeError("config boom")),
    ):
        result = module.lambda_handler({"mode": "stop_loss_guardian"}, None)

    assert result["statusCode"] == 500
