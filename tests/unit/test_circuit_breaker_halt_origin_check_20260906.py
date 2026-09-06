"""Regression test for the circuit-breaker Lambda's halt-clear origin check (2026-09-06,
real-money-readiness dig): `_set_halt` used to write halt_flag directly to RDS/DynamoDB via
raw UPSERTs, unconditionally overwriting whatever halt state existed - including a halt set
by a completely different origin (Phase 9 governance, a manual operator halt). Any scheduled
run where this circuit breaker's own variance happened to look fine would silently clear ANY
active halt and send a "TRADING RESUMED" alert, regardless of why trading was actually
halted.

Fixed to delegate to HaltFlagManager.set_halt_flag()/clear_halt_flag() - the same
origin-aware primitive every other halt source in this codebase uses - so a clear is only
ever applied when the currently active halt belongs to this circuit breaker itself (or
nothing is halted).
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

MODULE_PATH = Path(__file__).resolve().parents[2] / "lambda" / "circuit-breaker" / "index.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("circuit_breaker_index_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_halt_true_always_sets_tagged_as_circuit_breaker_origin():
    module = _load_module()
    mock_manager = MagicMock()

    with patch.object(module, "_get_halt_flag_manager", return_value=mock_manager):
        result = module._set_halt(None, True, "variance breach", "10:00")

    mock_manager.set_halt_flag.assert_called_once_with(reason="variance breach", triggered_by="circuit_breaker")
    assert result is True


def test_halt_false_clears_when_active_halt_is_own_origin():
    module = _load_module()
    mock_manager = MagicMock()
    mock_manager.get_halt_triggered_by.return_value = "circuit_breaker"
    mock_manager.clear_halt_flag.return_value = True

    with patch.object(module, "_get_halt_flag_manager", return_value=mock_manager):
        result = module._set_halt(None, False, "variance recovered", "12:00")

    mock_manager.clear_halt_flag.assert_called_once_with(
        reason="variance recovered", allowed_triggers=frozenset({"circuit_breaker", None})
    )
    assert result is True


def test_halt_false_refuses_to_clear_a_different_origins_halt():
    """The core bug: a manual operator halt (or any other origin) must survive this circuit
    breaker's own variance recovering - clear_halt_flag's own origin check refuses, and this
    wrapper must propagate that refusal (return False), not silently treat it as cleared."""
    module = _load_module()
    mock_manager = MagicMock()
    mock_manager.get_halt_triggered_by.return_value = "manual_operator"
    mock_manager.clear_halt_flag.return_value = False

    with patch.object(module, "_get_halt_flag_manager", return_value=mock_manager):
        result = module._set_halt(None, False, "variance recovered", "12:00")

    mock_manager.clear_halt_flag.assert_called_once_with(
        reason="variance recovered", allowed_triggers=frozenset({"circuit_breaker", None})
    )
    assert result is False


def test_no_op_alerts_stub_never_raises():
    """HaltFlagManager's constructor requires an `alerts` object with send_position_alert -
    confirm the stub this module supplies is actually callable with arbitrary args (matching
    the escalation-alert call shape inside set_halt_flag) rather than crashing."""
    module = _load_module()
    stub = module._NoOpAlerts()
    stub.send_position_alert("HALT_ESCALATION", "HALT_REPEAT_2", "message", {"halt_count": 2})
