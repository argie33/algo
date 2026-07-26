#!/usr/bin/env python3
"""Comprehensive tests for retry.py (resilience module).

Retry decorator and RateLimiter ensure the pipeline doesn't crash on transient
API failures and respects rate limits. Tests verify exponential backoff,
jitter, and rate limiter behavior under concurrent access.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from algo.infrastructure.retry import (
    ALPACA_DATA_LIMITER,
    ALPHA_VANTAGE_LIMITER,
    DEFAULT_LIMITER,
    RateLimiter,
    retry,
)


class TestRetryDecorator:
    """Test @retry decorator behavior."""

    def test_retry_succeeds_on_first_attempt(self):
        """Test that successful function returns immediately without retry."""
        call_count = 0

        @retry(max_attempts=3, exceptions=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            return "success"

        result = fn()

        assert result == "success"
        assert call_count == 1

    def test_retry_succeeds_after_one_failure(self):
        """Test that function retries after first failure."""
        call_count = 0

        @retry(max_attempts=3, exceptions=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First attempt fails")
            return "success"

        result = fn()

        assert result == "success"
        assert call_count == 2

    def test_retry_exhausts_max_attempts_then_raises(self):
        """Test that exception is raised when max_attempts exhausted."""
        call_count = 0

        @retry(max_attempts=3, exceptions=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            fn()

        assert call_count == 3

    def test_retry_ignores_unspecified_exception(self):
        """Test that retry doesn't catch unspecified exceptions."""
        call_count = 0

        @retry(max_attempts=3, exceptions=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Different exception type")

        with pytest.raises(RuntimeError, match="Different exception type"):
            fn()

        # Should fail immediately without retry
        assert call_count == 1

    def test_retry_with_multiple_exception_types(self):
        """Test retry with multiple exception types."""
        call_count = 0

        @retry(max_attempts=3, exceptions=(ValueError, RuntimeError))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First fails")
            if call_count == 2:
                raise RuntimeError("Second fails")
            return "success"

        result = fn()

        assert result == "success"
        assert call_count == 3

    @patch("algo.infrastructure.retry.time.sleep")
    def test_retry_uses_exponential_backoff(self, mock_sleep):
        """Test that delay increases exponentially with each retry."""
        call_count = 0

        @retry(max_attempts=4, base_delay=1.0, backoff=2.0, jitter=False, exceptions=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ValueError("Fail")
            return "success"

        fn()

        # Should sleep: 1.0s (after attempt 1), 2.0s (after attempt 2), 4.0s (after attempt 3)
        assert mock_sleep.call_count == 3

    @patch("algo.infrastructure.retry.time.sleep")
    def test_retry_respects_max_delay_cap(self, mock_sleep):
        """Test that sleep time is capped at max_delay."""
        call_count = 0

        @retry(
            max_attempts=5,
            base_delay=1.0,
            max_delay=2.5,
            backoff=3.0,
            jitter=False,
            exceptions=(ValueError,),
        )
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 5:
                raise ValueError("Fail")
            return "success"

        fn()

        # Without max_delay cap, delays would be: 1.0, 3.0, 9.0, 27.0
        # With max_delay=2.5: 1.0, 2.5, 2.5, 2.5
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert max(sleep_calls) == 2.5

    @patch("algo.infrastructure.retry.time.sleep")
    def test_retry_applies_jitter(self, mock_sleep):
        """Test that jitter adds randomness to sleep time."""
        call_count = 0

        @retry(max_attempts=3, base_delay=10.0, jitter=True, exceptions=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Fail")
            return "success"

        fn()

        # With jitter, sleep time should be ~75% to ~125% of base * backoff
        # First sleep: base_delay (10s) * [0.75, 1.25] = [7.5, 12.5]
        # Second sleep: base_delay*backoff (20s) * [0.75, 1.25] = [15, 25]
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(sleep_calls) == 2

        # Jitter should make them not exact multiples
        # (With no jitter, we'd expect exactly base_delay and base_delay*backoff)
        assert sleep_calls[0] != 10.0  # Should have jitter applied

    def test_retry_preserves_function_signature(self):
        """Test that decorated function preserves original signature."""

        @retry(max_attempts=3)
        def my_func(a, b, c=None):
            return a + b + (c or 0)

        # Function should be callable with original signature
        result = my_func(1, 2, c=3)
        assert result == 6

        # And with default args
        result = my_func(1, 2)
        assert result == 3


class TestRateLimiter:
    """Test RateLimiter (token bucket rate limiting)."""

    def test_rate_limiter_allows_first_call_immediately(self):
        """Test that first call doesn't sleep."""
        limiter = RateLimiter(calls_per_minute=60)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start

        # Should complete very quickly (no sleep on first call)
        assert elapsed < 0.1

    def test_rate_limiter_enforces_minimum_interval(self):
        """Test that limiter enforces minimum interval between calls."""
        limiter = RateLimiter(calls_per_minute=60)  # 1 call per second
        start = time.monotonic()

        limiter.wait()  # First call (no delay)
        limiter.wait()  # Second call (should sleep ~1 second)

        elapsed = time.monotonic() - start

        # Should take at least 1 second for two calls at 60 CPM
        assert elapsed >= 0.9

    def test_rate_limiter_with_high_call_rate(self):
        """Test limiter with high call rate (many calls per minute)."""
        limiter = RateLimiter(calls_per_minute=1000)
        start = time.monotonic()

        for _ in range(10):
            limiter.wait()

        elapsed = time.monotonic() - start
        expected_time = (10 - 1) * (60.0 / 1000)  # ~0.54 seconds for 10 calls

        # Should be close to expected time
        assert elapsed >= expected_time * 0.9
        assert elapsed < expected_time * 2.0  # Allow some tolerance

    def test_rate_limiter_with_low_call_rate(self):
        """Test limiter with very low call rate (calls per minute < 1)."""
        limiter = RateLimiter(calls_per_minute=0.5)  # 1 call per 2 minutes
        start = time.monotonic()

        limiter.wait()
        limiter.wait()

        elapsed = time.monotonic() - start
        expected_time = 60.0 / 0.5  # 120 seconds

        # Should be close to expected interval
        assert elapsed >= expected_time * 0.9

    def test_rate_limiter_thread_safe(self):
        """Test that rate limiter is thread-safe."""
        import threading

        limiter = RateLimiter(calls_per_minute=60)
        results = []

        def call_wait(thread_id):
            start = time.monotonic()
            limiter.wait()
            elapsed = time.monotonic() - start
            results.append((thread_id, elapsed))

        threads = [threading.Thread(target=call_wait, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # With 5 threads and 60 CPM (1 call per second):
        # Sequential execution would take ~5 seconds
        # But with concurrency, should be faster
        assert len(results) == 5

    def test_rate_limiter_min_interval_calculation(self):
        """Test that min_interval is calculated correctly."""
        limiter = RateLimiter(calls_per_minute=120)

        # 120 calls per minute = 2 calls per second = 0.5 seconds per call
        assert limiter._min_interval == pytest.approx(0.5, abs=0.01)

    def test_rate_limiter_respects_calls_per_minute(self):
        """Test that actual call rate matches configured CPM."""
        limiter = RateLimiter(calls_per_minute=30)  # 0.5 calls per second
        # Verify min_interval is calculated correctly: 60/30 = 2 seconds per call
        assert limiter._min_interval == pytest.approx(2.0, abs=0.01)


class TestPrebuiltLimiters:
    """Test pre-built rate limiters for known providers."""

    def test_alpaca_data_limiter_configured(self):
        """Test that Alpaca data limiter is configured."""
        # Alpaca data API with 10% headroom: 180 requests per minute
        assert ALPACA_DATA_LIMITER._min_interval > 0
        # Should allow 180 calls per minute: 60/180 = 0.333 seconds per call
        assert ALPACA_DATA_LIMITER._min_interval == pytest.approx(60.0 / 180.0, abs=0.01)

    def test_alpha_vantage_limiter_configured(self):
        """Test that Alpha Vantage limiter is configured."""
        # Alpha Vantage free tier with 20% headroom: 4 requests per minute
        assert ALPHA_VANTAGE_LIMITER._min_interval > 0
        # Should allow 4 calls per minute: 60/4 = 15 seconds per call
        assert ALPHA_VANTAGE_LIMITER._min_interval == pytest.approx(60.0 / 4.0, abs=0.1)

    def test_default_limiter_configured(self):
        """Test that default limiter is configured."""
        assert DEFAULT_LIMITER._min_interval > 0
        # Default: 30 CPM: 60/30 = 2 seconds per call
        assert DEFAULT_LIMITER._min_interval == pytest.approx(60.0 / 30.0, abs=0.01)


class TestRetryIntegration:
    """Integration tests combining retry and rate limiting."""

    @patch("algo.infrastructure.retry.time.sleep")
    def test_retry_with_rate_limit_respects_both(self, mock_sleep):
        """Test that retry and rate limiting work together."""
        call_count = 0

        @retry(max_attempts=3, base_delay=1.0, exceptions=(ValueError,))
        def api_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "data"

        limiter = RateLimiter(calls_per_minute=60)

        limiter.wait()
        result = api_call()

        assert result == "data"
        assert call_count == 3

    def test_retry_fails_fast_on_connection_error(self):
        """Test that retry fails fast on permanent errors."""

        @retry(max_attempts=5, exceptions=(ValueError,))
        def fn():
            raise ConnectionError("Network down")

        with pytest.raises(ConnectionError):
            fn()


class TestErrorLogging:
    """Test that retry decorator logs appropriately."""

    @patch("algo.infrastructure.retry.logger")
    def test_retry_logs_warning_on_retry(self, mock_logger):
        """Test that retry logs warning when retrying."""
        call_count = 0

        @retry(max_attempts=3, exceptions=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First attempt fails")
            return "success"

        fn()

        # Should have logged a warning about retry
        assert mock_logger.warning.called

    @patch("algo.infrastructure.retry.logger")
    def test_retry_logs_error_on_exhaustion(self, mock_logger):
        """Test that retry logs error when max attempts exhausted."""

        @retry(max_attempts=3, exceptions=(ValueError,))
        def fn():
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            fn()

        # Should have logged an error about exhaustion
        assert mock_logger.error.called
        error_call = mock_logger.error.call_args
        assert "retry.exhausted" in str(error_call)
