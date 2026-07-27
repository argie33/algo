"""Regression test for the 2026-07-27 fix: OptimalLoader.run()'s lock-acquisition block
wrapped its whole body (including the retry-exhausted `raise LockAcquisitionError(...)`)
in a single `except Exception as _lock_err: raise LockAcquisitionError(reason=str(_lock_err))`.
Since LockAcquisitionError is itself an Exception, the generic handler caught its own
already-raised error and wrapped it a second time.

Live-reproduced 2026-07-27: a real Phase 7 run halted with the message
"Failed to acquire lock for signal_quality_scores: Failed to acquire lock for
signal_quality_scores: Lock acquisition timeout after retries" - the reason text
duplicated verbatim, obscuring the actual failure for anyone reading the halt log.

Fixed by adding an `except LockAcquisitionError: raise` before the generic handler so a
well-formed LockAcquisitionError propagates unchanged instead of being re-wrapped.
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


class TestLockAcquisitionErrorNotDoubleWrapped:
    def test_run_lock_timeout_message_mentions_table_once(self):
        loader = _TestLoader.__new__(_TestLoader)
        loader.table_name = "signal_quality_scores"

        with (
            patch("utils.db.local_file_lock.get_lock_manager", return_value=_make_contended_lock_manager()),
            patch("time.sleep"),
        ):
            try:
                loader.run(symbols=["AAPL"], parallelism=1)
                raise AssertionError("expected LockAcquisitionError")
            except LockAcquisitionError as e:
                message = str(e)

        assert message.count("Failed to acquire lock for signal_quality_scores") == 1, message
        assert message == "Failed to acquire lock for signal_quality_scores: Lock acquisition timeout after retries"
