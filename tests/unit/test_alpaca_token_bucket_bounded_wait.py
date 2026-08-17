#!/usr/bin/env python3
"""Regression test for utils/external/alpaca_market_data.py's _TokenBucket.

Live-caught 2026-08-17: load_prices.py hung for 5+ hours in local dev (py-spy stack dump
showed the worker thread parked in _TokenBucket.acquire()'s time.sleep) because the bucket
slept in an unbounded loop with no logging and no way to give up when real server-side rate
limiting outlasted the client-side budget. Guards that acquire() now raises after
max_total_wait_sec instead of blocking forever, so callers (_alpaca_batch_or_none, which
already catches Exception and falls back to yfinance) can actually recover.
"""

import time

import pytest

from utils.external.alpaca_market_data import _TokenBucket, _TokenBucketExhaustedError


class TestTokenBucketBoundedWait:
    def test_acquire_succeeds_immediately_when_under_limit(self):
        bucket = _TokenBucket(per_minute=5, max_total_wait_sec=1.0)
        for _ in range(5):
            bucket.acquire()  # must not raise or block meaningfully

    def test_acquire_raises_after_max_total_wait_when_saturated(self):
        bucket = _TokenBucket(per_minute=1, max_total_wait_sec=0.2)
        bucket.acquire()  # fills the only slot

        start = time.monotonic()
        with pytest.raises(_TokenBucketExhaustedError):
            bucket.acquire()
        elapsed = time.monotonic() - start

        assert elapsed < 5.0  # bounded, not the old unbounded 60s-increment sleep loop
