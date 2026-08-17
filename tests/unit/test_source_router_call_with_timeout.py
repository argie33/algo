"""Regression test for utils/data/source_router.py's _call_with_timeout.

LIVE-REPRODUCED 2026-08-17: the old implementation ran fn() inside
`with ThreadPoolExecutor(...) as executor: future.result(timeout=timeout_sec)`.
On a genuine hang, future.result() raises FuturesTimeoutError as designed, but
that exception has to unwind through the `with` block first - and
ThreadPoolExecutor.__exit__ calls shutdown(wait=True), which blocks the calling
thread until the hung worker finishes. Since a truly-hung fn() never finishes,
the "timeout" never fired and the whole call hung forever instead. Confirmed
live: load_prices.py's yfinance batch fallback hung silently past its logged
"180s timeout" until an external reaper killed the process minutes later.
"""

import threading
import time

import pytest

from utils.data.source_router import _call_with_timeout


def test_call_with_timeout_returns_promptly_on_genuine_hang() -> None:
    """fn() that never returns must not block the caller past timeout_sec * retries.

    Without the daemon-thread fix, this call blocks forever (pytest would hang
    until killed) instead of raising TimeoutError.
    """
    never_returns = threading.Event()

    def hang_forever() -> None:
        never_returns.wait()  # blocks until the test process exits

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        _call_with_timeout(hang_forever, timeout_sec=0.2, retries=2)
    elapsed = time.monotonic() - started

    # 2 attempts * 0.2s timeout + up to 1s backoff (2**0) between attempts, generous margin.
    assert elapsed < 5.0, f"_call_with_timeout blocked for {elapsed:.1f}s on a hung call"


def test_call_with_timeout_returns_result_when_fn_completes() -> None:
    assert _call_with_timeout(lambda: 42, timeout_sec=1, retries=1) == 42


def test_call_with_timeout_reraises_fn_exception() -> None:
    def boom() -> None:
        raise ValueError("real failure")

    with pytest.raises(ValueError, match="real failure"):
        _call_with_timeout(boom, timeout_sec=1, retries=1)
