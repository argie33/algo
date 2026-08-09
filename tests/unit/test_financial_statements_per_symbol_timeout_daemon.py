"""Regression test for the financial_statements loader's per-symbol timeout (commit
8be6408a6, "Add per-symbol timeout (30s) to financial_statements loader to prevent hang
on stuck SEC API calls") and a same-day follow-up fix to it.

The timeout works by running loader.load_symbol() in a background thread and abandoning
it via thread.join(timeout=...) if it runs long. Python cannot force-kill a thread, so:

1. The abandoned thread MUST be daemon=True. A symbol whose load_symbol() call is
   genuinely stuck (not just slow - e.g. hangs before the socket ever connects, so
   configure_socket_timeout(30) never engages) leaves that thread alive forever after
   being abandoned. A non-daemon thread left running blocks the whole Python process
   from exiting (CPython's interpreter shutdown waits on every non-daemon thread) -
   that would silently recreate the exact "hangs 5+ hours in prod" bug this timeout
   exists to prevent, just moved from mid-loop to process-exit time.

2. The main pass loop must actually move on to the next symbol within roughly the
   configured timeout, not block indefinitely on the stuck one.

Both are exercised here with a genuinely-hanging (blocks on a never-set Event, not just
slow) fake load_symbol(), using a short LOADER_PER_SYMBOL_TIMEOUT_SECONDS so the test
itself stays fast.
"""

import threading
import time

from loaders.load_financial_statements import _run_symbol_pass


class _FakeStats:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def increment(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1


class _FakeShutdownWatcher:
    def check_shutdown_requested(self) -> bool:
        return False


class _HangingLoader:
    """load_symbol() blocks forever (until the test process exits) for one symbol,
    behaves normally for others - mirrors a genuinely stuck SEC API call, not just a
    slow one."""

    table_name = "annual_income_statement"

    def __init__(self, hang_on_symbol: str, never_set_event: threading.Event):
        self.hang_on_symbol = hang_on_symbol
        self._never_set_event = never_set_event
        self.processed: list[str] = []
        self._stats = _FakeStats()

    def load_symbol(self, symbol: str) -> None:
        if symbol == self.hang_on_symbol:
            self._never_set_event.wait()  # never set - simulates a genuine hang
            return
        self.processed.append(symbol)


class TestPerSymbolTimeoutDaemonThread:
    def test_stuck_symbol_does_not_block_subsequent_symbols(self, monkeypatch):
        monkeypatch.setenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "1")
        never_set_event = threading.Event()
        loader = _HangingLoader(hang_on_symbol="STUCK", never_set_event=never_set_event)

        start = time.time()
        _run_symbol_pass(
            active=[loader],
            symbols=["A", "STUCK", "B", "C"],
            shutdown_watcher=_FakeShutdownWatcher(),
            start=start,
        )
        elapsed = time.time() - start

        # Every non-stuck symbol still got processed - the hang didn't block the pass.
        assert loader.processed == ["A", "B", "C"]
        # STUCK counted as failed (timeout), not silently dropped or crashing the pass.
        assert loader._stats.counts.get("symbols_failed") == 1
        assert loader._stats.counts.get("symbols_processed") == 3
        # The whole pass took roughly one timeout window, not one per remaining symbol
        # and not "forever" (this would hang the test itself if the fix regressed).
        assert elapsed < 5

        # Release the real abandoned thread so it doesn't linger into other tests in
        # this process (harmless with daemon=True, but keep the run clean regardless).
        never_set_event.set()

    def test_abandoned_thread_is_daemon_so_process_can_exit(self, monkeypatch):
        # This is the actual bug: a non-daemon abandoned thread blocks process exit.
        # We can't spawn a real subprocess cheaply here, so assert the property directly
        # by capturing the thread object while it's still alive (blocked on the event).
        monkeypatch.setenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "1")
        never_set_event = threading.Event()
        loader = _HangingLoader(hang_on_symbol="STUCK", never_set_event=never_set_event)

        threads_before = {t.ident for t in threading.enumerate()}

        _run_symbol_pass(
            active=[loader],
            symbols=["STUCK"],
            shutdown_watcher=_FakeShutdownWatcher(),
            start=time.time(),
        )

        new_threads = [t for t in threading.enumerate() if t.ident not in threads_before]
        # The abandoned thread is still alive (blocked on never_set_event) - exactly the
        # scenario that would hang process exit if it weren't a daemon thread.
        assert len(new_threads) == 1, "expected the abandoned stuck-symbol thread to still be alive"
        assert new_threads[0].daemon is True, (
            "abandoned per-symbol timeout thread must be daemon=True - a non-daemon "
            "thread left running blocks the whole process from exiting"
        )

        # Cleanup: release the real thread so it doesn't leak into other tests.
        never_set_event.set()
        new_threads[0].join(timeout=5)
