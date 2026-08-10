"""Regression test for the 2026-08-04 fix: OptimalLoader.run() left the live
data_loader_status row stuck at RUNNING forever whenever _run_serial/_run_parallel raised
a plain (non-SLA-timeout) exception - only the mark_timeout() path (SLA exceeded) and the
"Upstream data incomplete" early-return path ever called self._status_manager.mark_failed().

Live-confirmed on dividend_data: a run that started 2026-08-02 11:43 crashed without ever
writing a completion/failure record to either data_loader_status or
data_loader_status_history, leaving status=RUNNING with a 2-day-stale execution_started and
no trace of what happened - completely invisible to scripts/monitor_data_staleness.py.

Fixed by having the outer except-block call self._status_manager.mark_failed() whenever no
more specific status (TIMEOUT, "Upstream data incomplete") was already written for this run,
tracked via a status_already_finalized flag so the fix doesn't clobber those more specific
statuses or a genuinely successful completion that later hit an unrelated error (e.g. metrics
publishing) after _update_final_status() had already written the real terminal status.
"""

from unittest.mock import MagicMock, patch

from utils.optimal_loader import OptimalLoader


def _make_loader(table_name="dividend_data"):
    loader = OptimalLoader.__new__(OptimalLoader)
    loader.table_name = table_name
    loader._status_manager = MagicMock()
    loader._infrastructure = MagicMock()
    loader._infrastructure.should_reduce_parallelism.return_value = (1, False)
    loader._stats = MagicMock()
    loader._stats.__setitem__ = MagicMock()
    loader._stats.to_dict.return_value = {}
    return loader


def _run_with_crash(loader, run_serial_side_effect, sla_timeout_seconds=999999):
    lock_manager = MagicMock()
    lock_manager.acquire.return_value = True
    lock_manager.is_available = True
    lock_manager.cleanup_expired_locks.return_value = 0

    conn_manager = MagicMock()

    with (
        patch("utils.db.local_file_lock.get_lock_manager", return_value=lock_manager),
        patch("loaders.config.get_loader_sla_timeout", return_value=sla_timeout_seconds),
        patch("utils.db.pooled_connection_manager.PooledConnectionManager", return_value=conn_manager),
        patch("utils.db.pooled_context_var.set_pooled_connection"),
        patch.object(loader, "_run_serial", side_effect=run_serial_side_effect),
    ):
        try:
            loader.run(symbols=["AAPL"], parallelism=1)
            return None
        except Exception as e:
            return e


class TestCrashDuringRunMarksFailed:
    def test_plain_exception_calls_mark_failed(self):
        """A fast-failing, non-timeout exception must call mark_failed() so the status row
        doesn't stay stuck at RUNNING forever (the dividend_data bug)."""
        loader = _make_loader()
        exc = _run_with_crash(loader, run_serial_side_effect=RuntimeError("DB connection lost"))

        assert exc is not None
        loader._status_manager.mark_running.assert_called_once()
        loader._status_manager.mark_failed.assert_called_once()
        (failed_msg,), _ = loader._status_manager.mark_failed.call_args
        assert "DB connection lost" in failed_msg
        loader._status_manager.mark_timeout.assert_not_called()

    def test_sla_timeout_does_not_double_mark(self):
        """When the SLA-timeout path already called mark_timeout(), the generic except-block
        fallback must not also call mark_failed() and downgrade the more specific status."""
        loader = _make_loader()

        def slow_serial(symbols):
            import time as _time

            _time.sleep(0.05)

        exc = _run_with_crash(loader, run_serial_side_effect=slow_serial, sla_timeout_seconds=0)

        assert exc is not None
        loader._status_manager.mark_timeout.assert_called_once()
        loader._status_manager.mark_failed.assert_not_called()
