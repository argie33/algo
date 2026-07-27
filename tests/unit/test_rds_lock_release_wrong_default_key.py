"""Regression test: RDSLockManager.release() must default to the lock_key that was actually
acquired, not an unrelated hardcoded default.

release() used to default to lock_key="orchestrator-run-lock" - a completely different string
than whatever key acquire() was actually called with. Any caller that does
`lock_manager.acquire(lock_key="my-loader")` then later `lock_manager.release()` with no
argument would silently try to delete the row for "orchestrator-run-lock" instead of
"my-loader" - a 0-row DELETE, previously logged as a false "Released lock" success while the
real lock stayed held until its 600s TTL naturally expired. No current call site in this
codebase actually hits it (all pass lock_key explicitly to both calls), but it's a live footgun
in a safety-critical shared utility - reproduced live 2026-07-27 via a standalone acquire/
release script that left a real row stuck in loader_execution_locks.

Also covers the new 0-row-delete detection: release() must report failure (not a false
success) when the DELETE doesn't actually match a row.
"""

from unittest.mock import MagicMock, patch

from utils.db.rds_lock import RDSLockManager


def _manager_with_mock_db(cur_mock):
    with patch.object(RDSLockManager, "__init__", lambda self: None):
        manager = RDSLockManager()
    manager.lock_duration_seconds = 600
    manager.enable_auto_cleanup = True
    manager.lock_id = "test-lock-id"
    manager.acquired = True
    manager.is_available = True
    manager.lock_key = "orchestrator-run-lock"

    db_context = MagicMock()
    db_context.__enter__.return_value = cur_mock
    db_context.__exit__.return_value = False
    return manager, db_context


def test_release_with_no_argument_uses_the_key_that_was_actually_acquired():
    """release() called bare after acquire(lock_key="my-loader") must target "my-loader",
    not the unrelated hardcoded default "orchestrator-run-lock"."""
    cur = MagicMock()
    cur.rowcount = 1
    manager, db_context = _manager_with_mock_db(cur)
    manager.lock_key = "my-loader"  # what acquire(lock_key="my-loader") would have set

    with patch("utils.db.rds_lock.DatabaseContext", return_value=db_context):
        result = manager.release()

    assert result is True
    delete_call_args = cur.execute.call_args[0][1]
    assert delete_call_args[0] == "my-loader"


def test_release_reports_failure_when_delete_matches_zero_rows():
    """A 0-row DELETE means the lock was NOT actually released - must not report success."""
    cur = MagicMock()
    cur.rowcount = 0
    manager, db_context = _manager_with_mock_db(cur)
    manager.lock_key = "my-loader"

    with patch("utils.db.rds_lock.DatabaseContext", return_value=db_context):
        result = manager.release()

    assert result is False
    # acquired must still be cleared locally even on a failed release - this instance no
    # longer believes it holds the lock, regardless of whether the DB row was actually gone.
    assert manager.acquired is False


def test_release_explicit_lock_key_still_overrides_self_lock_key():
    """Explicit lock_key argument must still take priority over self.lock_key."""
    cur = MagicMock()
    cur.rowcount = 1
    manager, db_context = _manager_with_mock_db(cur)
    manager.lock_key = "some-other-key"

    with patch("utils.db.rds_lock.DatabaseContext", return_value=db_context):
        result = manager.release(lock_key="explicit-key")

    assert result is True
    delete_call_args = cur.execute.call_args[0][1]
    assert delete_call_args[0] == "explicit-key"
