"""Regression tests for utils/external/yfinance_analyst_ratings.py's
_YfinanceAttrProcessWorker - the process-isolated replacement for the previous
`socket.setdefaulttimeout()`-based timeout, which live evidence (multiple 300+ minute
`[REAPED] Stuck in RUNNING` incidents across earnings_calendar, analyst_upgrade_downgrade,
analyst_sentiment_analysis, and analyst_earnings_estimates - all sharing the vulnerable
`_fetch_with_circuit_breaker` helper) showed cannot actually bound a curl_cffi hang.

Unlike a thread/socket-based timeout, a process-based one is genuinely testable against a
real hang - a subprocess that never returns can actually be killed and replaced, which is
exactly what these tests verify end-to-end (real subprocess spawn/kill, deterministic fake
workers instead of depending on network conditions) - same methodology already proven for
loaders/load_enhanced_quality_growth_metrics.py's YfinanceProcessWorker.
"""

import time

import pytest

from utils.external.yfinance_analyst_ratings import _YfinanceAttrProcessWorker


def _fake_worker_loop_echo(request_queue, response_queue) -> None:
    """Deterministic stand-in for _yf_attr_worker_loop: echoes back f"{symbol}:{attr}"
    instead of hitting real yfinance. Module-level (spawn needs to pickle-reference it by
    import path, same constraint as the real target)."""
    while True:
        item = request_queue.get()
        if item is None:
            return
        request_id, symbol, attr = item
        response_queue.put((request_id, True, f"{symbol}:{attr}"))


def _fake_worker_loop_hangs_forever(request_queue, response_queue) -> None:
    """Deterministic stand-in that never responds to any request - simulates the
    curl_cffi hang this whole fix targets, without depending on real network behavior."""
    while True:
        item = request_queue.get()
        if item is None:
            return
        time.sleep(3600)  # Never actually returns within any test's timeout


def _fake_worker_loop_raises(request_queue, response_queue) -> None:
    """Deterministic stand-in that reports a real fetch failure for every request."""
    while True:
        item = request_queue.get()
        if item is None:
            return
        request_id, _symbol, _attr = item
        response_queue.put((request_id, False, ValueError("simulated worker-side fetch failure")))


class TestYfinanceAttrProcessWorker:
    def test_fetch_returns_data_through_a_real_subprocess_round_trip(self):
        worker = _YfinanceAttrProcessWorker(timeout_seconds=15.0, worker_target=_fake_worker_loop_echo)
        try:
            result = worker.fetch("AAPL", "earnings_dates")
            assert result == "AAPL:earnings_dates"
            # A second call must reuse the SAME worker process (no respawn cost) - the
            # whole point of a persistent worker instead of per-call spawning.
            pid_before = worker._process.pid
            worker.fetch("MSFT", "upgrades_downgrades")
            assert worker._process.pid == pid_before
        finally:
            worker._terminate()

    def test_timeout_terminates_hung_worker_and_recovers_on_next_call(self):
        """The core claim this whole fix rests on: a worker that never returns gets
        force-killed within the configured timeout (not left hanging for hours like the
        thread/socket-based predecessor), and the NEXT call transparently succeeds
        through a freshly spawned replacement."""
        worker = _YfinanceAttrProcessWorker(timeout_seconds=2.0, worker_target=_fake_worker_loop_hangs_forever)
        try:
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                worker.fetch("HUNG_SYMBOL", "earnings_dates")
            elapsed = time.monotonic() - started
            # Bounded by the configured 2s timeout (with generous test slack), not left
            # hanging indefinitely - this is what socket.setdefaulttimeout() could NOT
            # actually guarantee against a curl_cffi hang.
            assert elapsed < 10.0

            # The hung worker must have been terminated, not left running as an orphan.
            assert worker._process is None

            # Swap in the well-behaved fake worker to prove the NEXT call recovers
            # cleanly through a freshly spawned process rather than staying broken.
            worker._worker_target = _fake_worker_loop_echo
            result = worker.fetch("RECOVERED_SYMBOL", "upgrades_downgrades")
            assert result == "RECOVERED_SYMBOL:upgrades_downgrades"
        finally:
            worker._terminate()

    def test_worker_exception_propagates_to_caller(self):
        worker = _YfinanceAttrProcessWorker(timeout_seconds=15.0, worker_target=_fake_worker_loop_raises)
        try:
            with pytest.raises(ValueError, match="simulated worker-side fetch failure"):
                worker.fetch("ANY_SYMBOL", "earnings_dates")
        finally:
            worker._terminate()

    def test_per_call_timeout_override(self):
        """The caller (`_fetch_with_circuit_breaker`) passes its own timeout_sec per call
        (e.g. earnings_calendar's 8s vs the 10s default) - fetch() must respect a
        per-call override rather than only the constructor default."""
        worker = _YfinanceAttrProcessWorker(timeout_seconds=15.0, worker_target=_fake_worker_loop_hangs_forever)
        try:
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                worker.fetch("HUNG_SYMBOL", "earnings_dates", timeout_seconds=1.0)
            elapsed = time.monotonic() - started
            assert elapsed < 10.0
        finally:
            worker._terminate()
