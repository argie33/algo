"""Regression test for the algo_orchestrator Lambda's risk-monitor dispatch.

REVERTED 2026-09-07 (real-money-readiness pre-live audit): a 2026-09-06 consolidation
commit made `stop_loss_guardian` and `intraday_risk_monitor` deprecated aliases that
forwarded to a since-removed consolidated risk check which, unlike either mode's own
original behavior, could automatically HALT trading and automatically FLATTEN/reduce
real positions on a confirmed portfolio-variance or beta/concentration breach. That
forwarding shipped with NO new terraform sign-off: `enable_stop_loss_guardian = true`
in terraform/prod.tfvars was approved on 2026-09-06 for the OLD, narrow stop-loss
verify/repair-only behavior (self-healing only, never a halt or a flatten) - months
before that consolidated check existed. Each mode must run ONLY its own original,
already-approved, narrower check - never any action-taking consolidated one.
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


def test_stop_loss_guardian_mode_calls_narrow_repair_check_not_unified_risk():
    """CRITICAL: must never reach an automated halt/flatten ladder - this mode is only
    ever approved for the self-healing stop-loss verify/repair step."""
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    mock_config = MagicMock()

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", return_value=mock_config),
        patch("algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step") as mock_repair,
    ):
        result = module.lambda_handler({"mode": "stop_loss_guardian"}, None)

    mock_repair.assert_called_once()
    assert mock_repair.call_args.args[1] is mock_config
    assert result["statusCode"] == 200


def test_intraday_risk_monitor_mode_calls_alert_only_check_not_unified_risk():
    """CRITICAL: must never reach an automated halt/flatten ladder - this mode is only
    ever approved for the alert-only intraday beta/concentration re-check."""
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    mock_config = MagicMock()

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", return_value=mock_config),
        patch("algo.risk.intraday_risk_monitor.check_intraday_risk") as mock_intraday,
    ):
        result = module.lambda_handler({"mode": "intraday_risk_monitor"}, None)

    mock_intraday.assert_called_once_with(mock_config)
    assert result["statusCode"] == 200


@pytest.mark.parametrize("mode", ["stop_loss_guardian", "intraday_risk_monitor"])
def test_risk_monitor_modes_do_not_run_full_orchestrator(mode):
    module = _load_module()
    os.environ["APCA_API_KEY_ID"] = "test-key"
    os.environ["APCA_API_SECRET_KEY"] = "test-secret"

    with (
        patch.object(module, "_load_alpaca_credentials_from_secrets"),
        patch("algo.infrastructure.get_config", return_value=MagicMock()),
        patch("algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step"),
        patch("algo.risk.intraday_risk_monitor.check_intraday_risk"),
        patch("algo.orchestration.Orchestrator") as mock_orchestrator_cls,
    ):
        module.lambda_handler({"mode": mode}, None)

    mock_orchestrator_cls.assert_not_called()


@pytest.mark.parametrize("mode", ["stop_loss_guardian", "intraday_risk_monitor"])
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
