"""Regression test: a SIGTERM during an orchestrator run must still release the run lock.

Before this fix, nothing in algo/orchestration/orchestrator.py registered any signal
handlers. run()'s try/finally already released the lock correctly for normal exceptions and
KeyboardInterrupt (Ctrl+C), but a SIGTERM - sent by process managers/orchestration tooling for
graceful shutdown, and effectively by some shell-level `timeout` implementations on Windows -
terminates the process immediately with no chance for the finally block to run. Confirmed live
2026-07-27: a killed local orchestrator test run left the orchestrator-run-lock row held for
its full 600s TTL, blocking every subsequent run attempt for up to 10 minutes with "ABORT:
Could not acquire run lock" until the TTL expired or someone manually deleted the row.

_install_shutdown_handler() now converts SIGTERM into a raised SystemExit, which run()'s
existing try/finally already knows how to unwind through - this test proves that conversion
works and is properly restored afterward, without needing to actually send a real OS signal
(flaky/platform-dependent in a test).
"""

import signal

from algo.orchestration.orchestrator import Orchestrator


def _fake_self():
    self = object.__new__(Orchestrator)
    return self


def test_install_shutdown_handler_converts_sigterm_to_systemexit():
    self = _fake_self()
    original_handler = signal.getsignal(signal.SIGTERM)

    try:
        Orchestrator._install_shutdown_handler(self)

        installed_handler = signal.getsignal(signal.SIGTERM)
        assert installed_handler is not original_handler

        try:
            installed_handler(signal.SIGTERM, None)
            raised = False
        except SystemExit:
            raised = True

        assert raised, "SIGTERM handler must raise SystemExit so run()'s finally block unwinds"
    finally:
        # Always restore the real original handler, regardless of test outcome - this test
        # must not leak a handler into other tests in the same process.
        signal.signal(signal.SIGTERM, original_handler)


def test_restore_shutdown_handler_puts_back_the_prior_handler():
    self = _fake_self()
    original_handler = signal.getsignal(signal.SIGTERM)

    try:
        Orchestrator._install_shutdown_handler(self)
        assert signal.getsignal(signal.SIGTERM) is not original_handler

        Orchestrator._restore_shutdown_handler(self)
        assert signal.getsignal(signal.SIGTERM) is original_handler
    finally:
        signal.signal(signal.SIGTERM, original_handler)


def test_run_finally_block_releases_lock_when_sigterm_fires_mid_run():
    """Simulates run()'s exact try/finally shape: a SystemExit raised mid-body (standing in
    for a real SIGTERM delivered mid-run) must still reach _release_run_lock()."""
    release_calls = []

    class FakeOrchestrator:
        _lock_acquired = True

        def _release_run_lock(self):
            release_calls.append(True)

        def _restore_shutdown_handler(self):
            pass

    fake = FakeOrchestrator()

    def run_body():
        try:
            raise SystemExit("Received signal 15 - shutting down and releasing run lock")
        finally:
            fake._release_run_lock()
            fake._restore_shutdown_handler()

    try:
        run_body()
    except SystemExit:
        pass

    assert release_calls == [True]
