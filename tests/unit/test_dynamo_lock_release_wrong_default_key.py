"""Regression test: DynamoDBLockManager.release() must default to the lock_key that was
actually acquired, not an unrelated hardcoded default.

Identical bug class to tests/unit/test_rds_lock_release_wrong_default_key.py (RDSLockManager
is documented as having "the same interface" as this class) - release() used to default to
lock_key="orchestrator-run-lock" regardless of what acquire() was actually called with, and
acquire() never even recorded the key it used. A caller doing
`lock_manager.acquire(lock_key="my-loader")` then a bare `.release()` would target a
completely different DynamoDB item - its ConditionExpression fails (wrong/missing lock_id),
silently treated as "already released" (line ~180), while the real "my-loader" lock item stays
held until its TTL expires. DynamoDBLockManager is the production-preferred lock backend (tried
before the RDS fallback in real AWS Lambda), making this the more production-relevant instance
of the two.
"""

from unittest.mock import MagicMock, patch

from utils.db.dynamo_lock import DynamoDBLockManager


def _manager_with_mock_table(acquired_keys=()):
    with patch.object(DynamoDBLockManager, "__init__", lambda self: None):
        manager = DynamoDBLockManager()
    manager.lock_duration_seconds = 600
    manager.enable_auto_cleanup = True
    manager.lock_id = "test-lock-id"
    manager.acquired = True
    manager.is_available = True
    manager.lock_key = "orchestrator-run-lock"
    manager.table = MagicMock()
    # Per-key acquired tracking (2026-08-22 fix) - must include whatever key(s) a test
    # expects release() to treat as already-acquired, or release() correctly no-ops instead.
    manager._acquired_keys = set(acquired_keys)
    return manager


def test_acquire_records_the_lock_key_it_was_called_with():
    manager = _manager_with_mock_table()
    manager.table.update_item.return_value = {}

    manager.acquire(lock_key="my-loader", timeout_seconds=1)

    assert manager.lock_key == "my-loader"


def test_release_with_no_argument_uses_the_key_that_was_actually_acquired():
    """release() called bare after acquire(lock_key="my-loader") must target "my-loader",
    not the unrelated hardcoded default "orchestrator-run-lock"."""
    manager = _manager_with_mock_table(acquired_keys={"my-loader"})
    manager.lock_key = "my-loader"  # what acquire(lock_key="my-loader") would have set

    manager.release()

    delete_call_kwargs = manager.table.delete_item.call_args.kwargs
    assert delete_call_kwargs["Key"] == {"lock_key": "my-loader"}


def test_release_explicit_lock_key_still_overrides_self_lock_key():
    manager = _manager_with_mock_table(acquired_keys={"explicit-key"})
    manager.lock_key = "some-other-key"

    manager.release(lock_key="explicit-key")

    delete_call_kwargs = manager.table.delete_item.call_args.kwargs
    assert delete_call_kwargs["Key"] == {"lock_key": "explicit-key"}


def test_release_does_not_clobber_other_held_locks():
    """The exact bug this session found live: one manager instance holding multiple keys -
    releasing one must not make release() treat the OTHERS as already-released too."""
    manager = _manager_with_mock_table(acquired_keys={"key-a", "key-b", "key-c"})

    manager.release(lock_key="key-a")

    assert "key-a" not in manager._acquired_keys
    assert manager._acquired_keys == {"key-b", "key-c"}
    # A second release for a still-held key must actually attempt the delete, not no-op.
    manager.release(lock_key="key-b")
    delete_call_kwargs = manager.table.delete_item.call_args.kwargs
    assert delete_call_kwargs["Key"] == {"lock_key": "key-b"}
    assert manager._acquired_keys == {"key-c"}
