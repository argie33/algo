#!/usr/bin/env python3
"""Test that verifies the LOCAL_MODE concurrency race condition is fixed.

Session 281 Critical Fix: Two LOCAL_MODE users can no longer both acquire
the orchestrator lock simultaneously. This test verifies that distributed
locking (DynamoDB) is enforced for the orchestrator, even in LOCAL_MODE.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from utils.db.dynamo_lock import DynamoDBLockManager


def test_get_lock_manager_always_returns_dynamodb():
    """Verify get_lock_manager() ALWAYS returns DynamoDBLockManager, never FileLockManager."""
    from utils.db.local_file_lock import get_lock_manager

    with patch('utils.db.dynamo_lock.DynamoDBLockManager') as mock_dynamodb:
        # Mock DynamoDBLockManager to bypass actual AWS calls
        mock_lock_manager = MagicMock()
        mock_dynamodb.return_value = mock_lock_manager

        result = get_lock_manager()

        # Verify it's the DynamoDB manager, not FileLockManager
        assert result is mock_lock_manager
        assert isinstance(result, MagicMock)  # Our mock


def test_get_lock_manager_fails_fast_if_dynamodb_unavailable():
    """Verify get_lock_manager() raises RuntimeError if DynamoDB initialization fails."""
    from utils.db.local_file_lock import get_lock_manager

    with patch('utils.db.dynamo_lock.DynamoDBLockManager') as mock_dynamodb:
        # Simulate DynamoDB initialization failure
        mock_dynamodb.side_effect = RuntimeError("DynamoDB table not found")

        with pytest.raises(RuntimeError, match="DynamoDB lock manager unavailable"):
            get_lock_manager()


def test_local_mode_env_var_ignored_for_orchestrator():
    """Verify LOCAL_MODE env var does NOT make get_lock_manager() fall back to FileLockManager.

    Session 281 Fix: LOCAL_MODE only controls orchestrator invocation method (direct vs Lambda).
    It does NOT affect distributed locking requirements.
    """
    from utils.db.local_file_lock import get_lock_manager

    # Set LOCAL_MODE
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
        del os.environ["LOCAL_MODE"]


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


def test_loader_fallback_pattern_exists():
    """Verify loaders can degrade gracefully to FileLockManager if DynamoDB unavailable.

    Loaders are idempotent (multiple runs = same result), so they can use weaker locking.
    This test verifies the fallback code pattern exists in optimal_loader.py.
    """
    # Just verify that optimal_loader.py has been updated with fallback handling
    import inspect
    from utils import optimal_loader

    # Check that optimal_loader module has the DynamoDB fallback pattern
    source = inspect.getsource(optimal_loader)
    assert "RuntimeError as ddb_err" in source  # Expects RuntimeError from get_lock_manager()
    assert "FileLockManager" in source  # Has fallback to FileLockManager
    assert "Falling back to file-based locking" in source  # Has logging message for fallback


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
