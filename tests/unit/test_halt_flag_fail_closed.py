"""Verifies HaltFlagManager fails closed (halts trading) when both its backing
stores are unavailable, and that LOCAL_MODE does not weaken this.

Replaces two always-skipped stubs in tests/test_session_282_integration.py
(TestHaltFlagFailClosedBehavior) that never actually exercised the code.
check_halt_flag() itself has no LOCAL_MODE branch at all (confirmed by reading
algo/orchestration/halt_flag_manager.py) - this test locks that invariant in
so a future edit can't reintroduce a LOCAL_MODE bypass without failing a test.
"""

import os
from unittest.mock import MagicMock, patch

from algo.orchestration.halt_flag_manager import HaltFlagManager


def _manager() -> HaltFlagManager:
    return HaltFlagManager(alerts=MagicMock(), log_phase_result=MagicMock())


def test_fails_closed_when_dynamodb_and_rds_both_unavailable():
    manager = _manager()
    with (
        patch.object(manager, "_check_halt_flag_dynamodb", return_value=None),
        patch.object(manager, "_check_halt_flag_rds", return_value=None),
    ):
        assert manager.check_halt_flag() is True


def test_fail_closed_not_bypassed_in_local_mode():
    manager = _manager()
    with (
        patch.dict(os.environ, {"LOCAL_MODE": "true"}),
        patch.object(manager, "_check_halt_flag_dynamodb", return_value=None),
        patch.object(manager, "_check_halt_flag_rds", return_value=None),
    ):
        assert manager.check_halt_flag() is True


def test_rds_fallback_used_when_dynamodb_unavailable():
    manager = _manager()
    with (
        patch.object(manager, "_check_halt_flag_dynamodb", return_value=None),
        patch.object(manager, "_check_halt_flag_rds", return_value=False),
    ):
        assert manager.check_halt_flag() is False


def test_active_halt_detected_via_dynamodb_returns_true():
    manager = _manager()
    with patch.object(manager, "_check_halt_flag_dynamodb", return_value=True):
        assert manager.check_halt_flag() is True


def test_dynamodb_not_halted_never_short_circuits_rds_cross_check():
    """SPLIT-BRAIN FIX (2026-09-05): set_halt_flag() writes to RDS only when DynamoDB's
    OWN write fails, so a halt set during a transient DynamoDB failure lands only in RDS.
    A halt recorded that way must not go invisible the moment DynamoDB itself recovers -
    check_halt_flag() must cross-check RDS even when DynamoDB is reachable and says False,
    not just when DynamoDB is unreachable entirely."""
    manager = _manager()
    with (
        patch.object(manager, "_check_halt_flag_dynamodb", return_value=False),
        patch.object(manager, "_check_halt_flag_rds", return_value=True),
    ):
        assert manager.check_halt_flag() is True


def test_dynamodb_not_halted_and_rds_not_halted_returns_false():
    manager = _manager()
    with (
        patch.object(manager, "_check_halt_flag_dynamodb", return_value=False),
        patch.object(manager, "_check_halt_flag_rds", return_value=False),
    ):
        assert manager.check_halt_flag() is False


def test_dynamodb_not_halted_rds_cross_check_error_fails_open_to_dynamodb_answer():
    """The RDS cross-check is defense-in-depth on top of an already-successful DynamoDB
    read, not the primary path - an error checking-the-checker must not itself force a
    halt, or a flaky RDS cross-check could halt trading with no real halt condition."""
    manager = _manager()
    with (
        patch.object(manager, "_check_halt_flag_dynamodb", return_value=False),
        patch.object(manager, "_check_halt_flag_rds", side_effect=RuntimeError("RDS down")),
    ):
        assert manager.check_halt_flag() is False


def test_dynamodb_halted_skips_rds_cross_check_entirely():
    """When DynamoDB itself says halted, that's already authoritative - no false-negative
    risk - so RDS must not be queried at all (avoids paying an extra read on the common
    Dynamo-halted path)."""
    manager = _manager()
    with (
        patch.object(manager, "_check_halt_flag_dynamodb", return_value=True),
        patch.object(manager, "_check_halt_flag_rds") as mock_rds,
    ):
        assert manager.check_halt_flag() is True
        mock_rds.assert_not_called()
