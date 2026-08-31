"""Regression test for a 2026-08-31 fix (goal: data-coverage sweep, GENI follow-up) to
utils/external/yfinance_analyst_ratings.py's `_yf_attr_worker_loop` (and the identical fix
applied to loaders/load_enhanced_quality_growth_metrics.py's `_yfinance_worker_loop`).

Live-confirmed via a real GENI fetch: `response_queue.put((request_id, False, e))` crashed with
`TypeError: cannot pickle '_cffi_backend._CDataBase' object` inside multiprocessing.Queue's
internal `_feed` thread - asynchronous, so the `put()` call itself never raises and can't be
caught after the fact. Worse, `_feed` crashing only kills that background thread, not the
worker's main loop, so `_YfinanceAttrProcessWorker._ensure_alive`'s `is_alive()` check never
detects it - every future `fetch()` call hangs until its own timeout, for the rest of the
process's lifetime, with no recovery.

Fix: never put the raw caught exception on the queue - always re-wrap into a plain RuntimeError
(type name + message preserved) before enqueueing, so the queue can never receive an unpicklable
payload in the first place.
"""

import multiprocessing

import pytest

from utils.external.yfinance_analyst_ratings import _yf_attr_worker_loop


class _UnpicklableLikeCurlCffiError(Exception):
    """Stand-in for a real curl_cffi exception carrying unpicklable C-level state - __reduce__
    raising TypeError reproduces the exact failure mode pickle.dumps hits on the real object,
    without needing curl_cffi installed/reachable in a unit test."""

    def __reduce__(self):
        raise TypeError("cannot pickle '_cffi_backend._CDataBase' object")


class TestYfAttrWorkerLoopUnpicklableException:
    def test_unpicklable_exception_is_rewrapped_not_enqueued_raw(self, monkeypatch):
        class _FakeTicker:
            def __init__(self, symbol):
                pass

            @property
            def info(self):
                raise _UnpicklableLikeCurlCffiError("simulated curl_cffi network failure")

        import yfinance as yf

        monkeypatch.setattr(yf, "Ticker", _FakeTicker)

        request_queue: multiprocessing.Queue = multiprocessing.Queue()
        response_queue: multiprocessing.Queue = multiprocessing.Queue()
        request_queue.put((1, "GENI", "info"))
        request_queue.put(None)  # sentinel - _yf_attr_worker_loop returns after this

        # If the fix were absent, this call would still complete (the crash happens
        # asynchronously in a background thread) but response_queue.get() below would hang
        # forever since nothing valid was ever actually delivered - bounded by a timeout here
        # so a regression fails the test instead of hanging the suite.
        _yf_attr_worker_loop(request_queue, response_queue)

        request_id, success, payload = response_queue.get(timeout=5.0)
        assert request_id == 1
        assert success is False
        assert isinstance(payload, RuntimeError)
        assert "_UnpicklableLikeCurlCffiError" in str(payload)
        assert "simulated curl_cffi network failure" in str(payload)

        # The actual regression this test guards against: the payload must round-trip through
        # real pickling (multiprocessing.Queue.get() already proved this by returning without
        # hanging, but assert it explicitly too).
        import pickle

        pickle.dumps(payload)  # must not raise

    def test_normal_success_path_unaffected(self, monkeypatch):
        class _FakeTicker:
            def __init__(self, symbol):
                pass

            @property
            def info(self):
                return {"sharesOutstanding": 31_055_542}

        import yfinance as yf

        monkeypatch.setattr(yf, "Ticker", _FakeTicker)

        request_queue: multiprocessing.Queue = multiprocessing.Queue()
        response_queue: multiprocessing.Queue = multiprocessing.Queue()
        request_queue.put((7, "FUBO", "info"))
        request_queue.put(None)

        _yf_attr_worker_loop(request_queue, response_queue)

        request_id, success, payload = response_queue.get(timeout=5.0)
        assert request_id == 7
        assert success is True
        assert payload == {"sharesOutstanding": 31_055_542}
