"""Regression test for the 2026-08-16 fix: OptimalLoader.run()'s generic
`except Exception as e:` handler unconditionally called `self._status_manager.mark_failed()`
on the primary table_name - including when `e` is a LockAcquisitionError.

A LockAcquisitionError means THIS instance never started any work: it means another,
legitimately-running instance already holds the lock. Live-confirmed on company_info_sec: a
second/duplicate invocation exhausted its ~1min LOCAL_MODE lock-retry budget, raised
LockAcquisitionError, and the old handler then called mark_failed() on the SHARED
table_name - stomping FAILED over the still-actively-running first instance's real status
(which kept working and completed normally minutes later, unaware its status had been
overwritten). The lock mechanism itself worked exactly as designed; only the status write on
the losing side was wrong.

Fixed by excluding LockAcquisitionError from the mark_failed() branch - the losing instance
now just re-raises without touching data_loader_status for a table it was correctly refused.
"""

from unittest.mock import MagicMock, patch

from algo.exceptions import LockAcquisitionError
from utils.optimal_loader import OptimalLoader


class _TestLoader(OptimalLoader):
    table_name = "signal_quality_scores"  # any real SAFE_TABLES entry


def _make_contended_lock_manager():
    lock_manager = MagicMock()
    lock_manager.is_available = True
    lock_manager.acquire.return_value = False  # always contended, never acquires
    lock_manager.cleanup_expired_locks.return_value = 0
    return lock_manager


class TestLockContentionDoesNotMarkFailed:
    def test_lock_contention_does_not_call_mark_failed(self):
        loader = _TestLoader.__new__(_TestLoader)
        loader.table_name = "signal_quality_scores"
        loader._status_manager = MagicMock()

        with (
            patch("utils.db.local_file_lock.get_lock_manager", return_value=_make_contended_lock_manager()),
            patch("time.sleep"),
        ):
            try:
                loader.run(symbols=["AAPL"], parallelism=1)
                raise AssertionError("expected LockAcquisitionError")
            except LockAcquisitionError:
                pass

        loader._status_manager.mark_failed.assert_not_called()

    def test_guard_condition_is_scoped_to_lock_acquisition_error_only(self):
        """The except-block guard added by this fix must check `isinstance(e,
        LockAcquisitionError)` specifically, not e.g. a bare string/type-name match that
        could accidentally swallow unrelated exceptions and silently skip marking a real
        crash as FAILED. A full run() integration test for the "genuine crash" side is
        already covered indirectly by the many existing OptimalLoader crash-path tests
        (e.g. test_optimal_loader_lock_error_not_double_wrapped.py's sibling suite) - this
        just pins the isinstance() check itself against source drift."""
        import inspect

        source = inspect.getsource(OptimalLoader.run)
        assert "isinstance(e, LockAcquisitionError)" in source
