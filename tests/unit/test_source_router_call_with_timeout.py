"""Regression tests for utils/data/source_router.py's yf.download timeout protection.

2026-08-29: _call_with_timeout moved from a daemon-thread + `Thread.join(timeout=N)`
design to a process-isolated one (_download_via_process/_yf_download_worker) - see
_download_via_process's docstring and memory
`yfinance_curl_cffi_gil_hostage_hang_diagnosed_not_fixed_20260829` for why: a curl_cffi
call can hold the GIL hostage in native code for the entire hang, which starves
`Thread.join(timeout=N)` itself (it needs the GIL to check elapsed time), so the
thread-based "timeout" could never actually fire against a genuine hang - only a
separate, killable OS process can. _call_with_timeout's signature changed from a
generic `fn: Callable[[], Any]` wrapper to yf.download's actual args (symbols/start/
end/interval), because a closure over local variables can't be pickled across a
process boundary the way plain args can.

Two layers are tested separately:
- _download_via_process: the real subprocess round trip (spawn/kill/exception
  propagation), using module-level fake worker targets - these must be plain
  top-level functions, not closures, for the same pickling reason noted above (a
  closure capturing a test-local `calls` counter cannot cross the process boundary
  the "spawn" start method requires).
- _call_with_timeout: the retry/backoff control flow, tested by mocking
  _download_via_process directly (in-process, no real subprocess) so the closures
  needed to count calls and vary behavior per attempt are unproblematic.

The prior thread-based tests used `threading.Event().wait()` to simulate a hang, which
doesn't actually reproduce the bug this fix targets - a pure-Python wait releases the
GIL and never holds it hostage the way a stuck curl_cffi call does.
"""

from datetime import date
from typing import Any

import pytest

from utils.data import source_router
from utils.data.source_router import _call_with_timeout, _download_via_process


def _fake_worker_echo(response_queue: Any, symbols: Any, start: date, end: date, interval: str) -> None:
    response_queue.put((True, f"{symbols}:{start}:{end}:{interval}"))


def _fake_worker_raises(response_queue: Any, symbols: Any, start: date, end: date, interval: str) -> None:
    response_queue.put((False, ValueError("real failure")))


def _fake_worker_hangs_forever(response_queue: Any, symbols: Any, start: date, end: date, interval: str) -> None:
    import time

    time.sleep(3600)  # Never actually returns within any test's timeout


class TestDownloadViaProcess:
    """Real subprocess round trip - spawn/kill/exception propagation."""

    def test_returns_result_when_worker_completes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(source_router, "_yf_download_worker", _fake_worker_echo)
        result = _download_via_process("AAPL", date(2026, 1, 1), date(2026, 1, 2), "1d", timeout_sec=15)
        assert result == "AAPL:2026-01-01:2026-01-02:1d"

    def test_reraises_worker_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(source_router, "_yf_download_worker", _fake_worker_raises)
        with pytest.raises(ValueError, match="real failure"):
            _download_via_process("AAPL", date(2026, 1, 1), date(2026, 1, 2), "1d", timeout_sec=15)

    def test_returns_promptly_on_genuine_hang(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A worker that never responds must be killed and reported within timeout_sec,
        not left hanging - the core claim this whole fix rests on. Unlike a thread-based
        timeout, a real subprocess can actually be killed regardless of what it's doing
        internally, so this genuinely bounds the wait (checked via elapsed wall-clock
        time, not just that it eventually raises).
        """
        import time

        monkeypatch.setattr(source_router, "_yf_download_worker", _fake_worker_hangs_forever)
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            _download_via_process("AAPL", date(2026, 1, 1), date(2026, 1, 2), "1d", timeout_sec=1)
        elapsed = time.monotonic() - started
        assert elapsed < 10.0, f"_download_via_process blocked for {elapsed:.1f}s past its 1s timeout"


class TestCallWithTimeoutRetryLogic:
    """Retry/backoff control flow, mocked at the _download_via_process boundary (no real
    subprocess needed to test pure Python control flow)."""

    def test_retries_on_timeout_and_recovers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake_download(symbols: str, start: date, end: date, interval: str, timeout_sec: float) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("simulated hang")
            return "recovered"

        monkeypatch.setattr(source_router, "_download_via_process", fake_download)
        result = _call_with_timeout("AAPL", date(2026, 1, 1), date(2026, 1, 2), "1d", timeout_sec=1, retries=2)
        assert result == "recovered"
        assert calls["n"] == 2

    def test_does_not_retry_on_real_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A genuine failure (e.g. rate limit) from the download itself must propagate
        immediately without burning through retries - only a timeout retries.
        """
        calls = {"n": 0}

        def fake_download(symbols: str, start: date, end: date, interval: str, timeout_sec: float) -> str:
            calls["n"] += 1
            raise ValueError("real failure")

        monkeypatch.setattr(source_router, "_download_via_process", fake_download)
        with pytest.raises(ValueError, match="real failure"):
            _call_with_timeout("AAPL", date(2026, 1, 1), date(2026, 1, 2), "1d", timeout_sec=15, retries=3)
        assert calls["n"] == 1

    def test_raises_timeout_after_exhausting_all_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def always_times_out(symbols: str, start: date, end: date, interval: str, timeout_sec: float) -> str:
            calls["n"] += 1
            raise TimeoutError("simulated hang")

        monkeypatch.setattr(source_router, "_download_via_process", always_times_out)
        with pytest.raises(TimeoutError):
            _call_with_timeout("AAPL", date(2026, 1, 1), date(2026, 1, 2), "1d", timeout_sec=1, retries=3)
        assert calls["n"] == 3
