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
