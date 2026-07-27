"""Regression test for a process-hang bug in dashboard.dashboard.run_once().

run_once() gives up waiting for data after 30s (logs "exiting after 30s with no data" and
breaks out of the render loop), but the background preload thread that calls load_all() is
started with daemon=False and is never cancelled. If load_all() takes longer than 30s (it has
its own internal timeouts up to ~60-300s), the interpreter cannot exit until that thread
finishes on its own - so `python dashboard.py` appears to hang indefinitely on a cleared
screen after already having logged that it was exiting, with no way for the user to tell.

Daemon threads die with the process, so making the preload thread daemon=True fixes this
without changing any of the intentional "wait a little for data" behavior.
"""

import threading
import time
from unittest.mock import patch

from dashboard import dashboard


def test_preload_thread_is_daemon_so_process_can_exit_on_slow_load_all() -> None:
    """If load_all() hangs past the 30s give-up window, the preload thread must not
    block process exit. A non-daemon thread here means the interpreter waits for it
    forever even after run_once() has already logged that it is exiting."""
    never_finishes = threading.Event()

    def hanging_load_all():
        never_finishes.wait()  # simulates load_all() still running past the give-up window
        return {}

    threads_before = set(threading.enumerate())

    # Fast-forward the 30s give-up clock without a real sleep: the first two monotonic()
    # calls (state.last_load, then loop_start) read as 0.0, every call after reads as
    # +100s so elapsed_loop = 100.0 - 0.0 exceeds 30 on the loop's first iteration.
    call_count = [0]

    def fake_monotonic() -> float:
        call_count[0] += 1
        return 0.0 if call_count[0] <= 2 else 100.0

    with (
        patch("dashboard.dashboard.load_all", side_effect=hanging_load_all),
        patch("dashboard.dashboard.time.monotonic", side_effect=fake_monotonic),
        patch("dashboard.dashboard.time.sleep", return_value=None),
        patch("dashboard.dashboard._keypress", return_value=""),
        patch("dashboard.dashboard.Live"),
    ):
        dashboard.run_once(compact=False)

    new_threads = set(threading.enumerate()) - threads_before
    preload_threads = [t for t in new_threads if t.is_alive()]

    try:
        assert preload_threads, "expected the still-hanging preload thread to exist after run_once() returns"
        for t in preload_threads:
            assert t.daemon, (
                f"preload thread {t.name!r} is non-daemon - a genuinely slow load_all() call "
                "would prevent the process from ever exiting after run_once() has already "
                "logged that it gave up waiting"
            )
    finally:
        never_finishes.set()
        for t in preload_threads:
            t.join(timeout=2)
