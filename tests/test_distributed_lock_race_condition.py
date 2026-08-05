#!/usr/bin/env python3
"""Test that verifies the LOCAL_MODE concurrency race condition is fixed.

Session 281 Critical Fix: Two LOCAL_MODE users can no longer both acquire
the orchestrator lock simultaneously. This test verifies that distributed
locking (DynamoDB, with an RDS fallback added in Session 290 - see
utils/db/rds_lock.py) is enforced for the orchestrator, even in LOCAL_MODE.
A purely local file lock must never be used for this.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from utils.db.dynamo_lock import DynamoDBLockManager


def test_get_lock_manager_always_returns_dynamodb():
    """Verify get_lock_manager() ALWAYS returns DynamoDBLockManager (not FileLockManager), when LOCAL_MODE=false.

    In LOCAL_MODE=true, falls back to RDSLockManager (which is still a distributed lock, not file-based).
    """
    from utils.db.local_file_lock import get_lock_manager

    # Temporarily unset LOCAL_MODE so DynamoDB is tried (production behavior)
    original_local_mode = os.environ.get("LOCAL_MODE")
    try:
        os.environ.pop("LOCAL_MODE", None)

        with patch('utils.db.dynamo_lock.DynamoDBLockManager') as mock_dynamodb:
            # Mock DynamoDBLockManager to bypass actual AWS calls
            mock_lock_manager = MagicMock()
            mock_lock_manager.is_available = True
            mock_lock_manager.acquire.return_value = True  # Test acquire succeeds
            mock_dynamodb.return_value = mock_lock_manager

            result = get_lock_manager()

            # Verify it's the DynamoDB manager, not FileLockManager
            assert result is mock_lock_manager
            assert isinstance(result, MagicMock)  # Our mock
    finally:
        # Restore LOCAL_MODE
        if original_local_mode is not None:
            os.environ["LOCAL_MODE"] = original_local_mode


def test_get_lock_manager_falls_back_to_rds_if_dynamodb_unavailable():
    """Verify get_lock_manager() falls back to RDSLockManager if DynamoDB init fails (Session 290).

    RDS is a shared, centralized backend (the same production DB every instance connects
    to, using atomic INSERT ... ON CONFLICT locking), so this fallback preserves the
    Session 281 safety guarantee - it is NOT a regression to the original bug (two
    LOCAL_MODE processes racing on a purely local, per-machine file lock). Only a true
    "both backends down" case should fail fast - see the test below.
    """
    from utils.db.local_file_lock import get_lock_manager

    original_local_mode = os.environ.get("LOCAL_MODE")
    try:
        os.environ["LOCAL_MODE"] = "false"  # Test production fallback behavior, not LOCAL_MODE

        with patch('utils.db.dynamo_lock.DynamoDBLockManager') as mock_dynamodb, \
             patch('utils.db.rds_lock.RDSLockManager') as mock_rds:
            mock_dynamodb.side_effect = RuntimeError("DynamoDB table not found")
            mock_rds_manager = MagicMock()
            mock_rds_manager.is_available = True
            mock_rds.return_value = mock_rds_manager

            result = get_lock_manager()

            assert result is mock_rds_manager
    finally:
        if original_local_mode is not None:
            os.environ["LOCAL_MODE"] = original_local_mode
        else:
            os.environ.pop("LOCAL_MODE", None)


def test_get_lock_manager_fails_fast_if_both_dynamodb_and_rds_unavailable():
    """Verify get_lock_manager() raises RuntimeError only when BOTH backends fail (Session 290)."""
    from utils.db.local_file_lock import get_lock_manager

    original_local_mode = os.environ.get("LOCAL_MODE")
    try:
        os.environ["LOCAL_MODE"] = "false"  # Test production fallback behavior, not LOCAL_MODE

        with patch('utils.db.dynamo_lock.DynamoDBLockManager') as mock_dynamodb, \
             patch('utils.db.rds_lock.RDSLockManager') as mock_rds:
            mock_dynamodb.side_effect = RuntimeError("DynamoDB table not found")
            mock_rds.side_effect = RuntimeError("RDS connection refused")

            with pytest.raises(RuntimeError, match="Both DynamoDB and RDS lock managers unavailable"):
                get_lock_manager()
    finally:
        if original_local_mode is not None:
            os.environ["LOCAL_MODE"] = original_local_mode
        else:
            os.environ.pop("LOCAL_MODE", None)


def test_local_mode_env_var_ignored_for_orchestrator():
    """Verify LOCAL_MODE env var does NOT make get_lock_manager() fall back to FileLockManager.

    Session 281 Fix: LOCAL_MODE only controls orchestrator invocation method (direct vs Lambda).
    It does NOT affect distributed locking requirements.
    """
    from utils.db.local_file_lock import get_lock_manager

    # Set LOCAL_MODE. FIX (2026-07-27): must restore the ORIGINAL value in finally, not
    # unconditionally `del` - .env.local sets LOCAL_MODE=true for local dev, so an
    # unconditional delete here permanently erased it for every test running later in
    # the same pytest session/process (env vars are process-global). Confirmed live:
    # running the full suite raised an uncaught RuntimeError from
    # Orchestrator._check_loader_health's "CRITICAL HALT: All critical loaders are
    # stale/missing" escalation in a test that only passes in LOCAL_MODE (where that
    # escalation logs a warning instead of raising) - passed every time in isolation,
    # only failed when this test ran first in the same process and wiped the env var.
    original_local_mode = os.environ.get("LOCAL_MODE")
    os.environ["LOCAL_MODE"] = "1"

    try:
        with patch('utils.db.dynamo_lock.DynamoDBLockManager') as mock_dynamodb:
            mock_lock_manager = MagicMock()
            mock_dynamodb.return_value = mock_lock_manager

            result = get_lock_manager()

            # Should still use DynamoDB, not file-based locks
            assert result is mock_lock_manager
            mock_dynamodb.assert_called_once()
    finally:
        if original_local_mode is not None:
            os.environ["LOCAL_MODE"] = original_local_mode
        else:
            os.environ.pop("LOCAL_MODE", None)


def test_orchestrator_fails_fast_if_lock_manager_unavailable():
    """Verify Orchestrator.__init__ will fail if lock manager initialization fails.

    This ensures the orchestrator never runs without distributed locking.
    """
    from algo.orchestration.orchestrator import Orchestrator

    # Mock config
    mock_config = MagicMock()
    mock_config.get.return_value = "paper"  # execution_mode

    with patch('utils.db.local_file_lock.get_lock_manager') as mock_get_lock:
        mock_get_lock.side_effect = RuntimeError("DynamoDB unavailable")

        with pytest.raises(RuntimeError):
            Orchestrator(config=mock_config)


def test_loader_fail_fast_on_ddb_error():
    """Verify loaders fail-fast when DynamoDB unavailable (Session 282).

    Session 282 removed FileLockManager fallback because it has Windows race condition
    (non-atomic file creation). Better to fail-fast and trigger infrastructure retry
    than silently degrade to unsafe locking.

    This test verifies optimal_loader.py properly raises LockAcquisitionError when
    DynamoDB locking unavailable.
    """
    import inspect

    from utils import optimal_loader

    # Check that optimal_loader module fails-fast on DynamoDB errors
    source = inspect.getsource(optimal_loader)
    assert "RuntimeError as ddb_err" in source  # Catches RuntimeError from get_lock_manager()
    assert "LockAcquisitionError" in source  # Raises LockAcquisitionError (fail-fast)
    assert "Cannot proceed without distributed locking" in source  # Clear error message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
