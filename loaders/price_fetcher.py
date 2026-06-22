#!/usr/bin/env python3
"""PriceFetcher specialist - handles API interaction and fetch logic.

Extracted from PriceLoader to eliminate God Object code smell.
Responsibility: Fetch price data from yfinance API with error handling, retries, and rate limiting.
"""

import logging
import threading
import time


logger = logging.getLogger(__name__)


class PriceFetcher:
    """Specialist for fetching price data from yfinance API.

    Handles:
    - API calls to yfinance
    - Error handling and retries
    - Rate limiting and adaptive request pacing
    - Batch fetch orchestration
    """

    def __init__(self, rate_limit_config: dict | None = None):
        """Initialize PriceFetcher with rate limiting config."""
        # Rate limit: 160 API calls per minute (safe margin below yfinance's 200/min)
        self._rate_limit_tokens: float = 300  # Initial burst
        self._rate_limit_max_tokens: float = 300
        self._rate_limit_last_refill: float = time.time()
        self._rate_limit_refill_rate = 160 / 60  # 2.67 tokens/sec
        self._rate_limit_lock = threading.Lock()
        self._rate_limit_event = threading.Condition(self._rate_limit_lock)

        # Adaptive request pacing
        self._request_latency_samples: list[tuple[float, float]] = []
        self._latency_window_sec = 60
        self._min_request_interval = 0.1
        self._adaptive_request_interval = 0.375
        self._last_request_time: float | None = None

        # Batch sizing optimization
        self._batch_size_performance: dict[int, list[int]] = {}
        self.batch_size = 500

    def _rate_limit_wait(self, tokens_needed: int = 1) -> None:
        """Wait until enough tokens are available (thread-safe)."""
        with self._rate_limit_event:
            while self._rate_limit_tokens < tokens_needed:
                self._rate_limit_event.wait(timeout=0.1)
                self._refill_tokens()
            self._rate_limit_tokens -= tokens_needed

    def _refill_tokens(self) -> None:
        """Refill rate limit tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._rate_limit_last_refill
        tokens_earned = elapsed * self._rate_limit_refill_rate
        self._rate_limit_tokens = min(
            self._rate_limit_max_tokens,
            self._rate_limit_tokens + tokens_earned
        )
        self._rate_limit_last_refill = now

    def _adaptive_request_pacing(self) -> None:
        """Adjust request pacing based on observed API latency."""
        now = time.time()

        # Remove old samples outside the window
        cutoff = now - self._latency_window_sec
        self._request_latency_samples = [
            (ts, lat) for ts, lat in self._request_latency_samples
            if ts > cutoff
        ]

        if len(self._request_latency_samples) > 10:
            avg_latency = sum(lat for _, lat in self._request_latency_samples) / len(self._request_latency_samples)
            # If API is slow (avg latency > 0.5s), increase request interval
            if avg_latency > 0.5:
                self._adaptive_request_interval = min(1.0, self._adaptive_request_interval * 1.1)
            # If API is fast (avg latency < 0.1s), decrease request interval
            elif avg_latency < 0.1:
                self._adaptive_request_interval = max(
                    self._min_request_interval,
                    self._adaptive_request_interval * 0.9
                )

    def _record_request_latency(self, latency_sec: float) -> None:
        """Record API request latency for adaptive pacing."""
        self._request_latency_samples.append((time.time(), latency_sec))

    def _get_smart_batch_size(self) -> int:
        """Determine optimal batch size based on performance history."""
        if not self._batch_size_performance:
            return self.batch_size

        # Find batch size with best success ratio
        best_size = self.batch_size
        best_ratio = 0.0
        for size, (successes, failures) in self._batch_size_performance.items():
            total = successes + failures
            ratio = successes / total if total > 0 else 0
            if ratio > best_ratio:
                best_ratio = ratio
                best_size = size

        return best_size

    def _record_batch_result(self, batch_size: int, success_count: int, total_count: int) -> None:
        """Record batch fetch result for smart sizing."""
        if batch_size not in self._batch_size_performance:
            self._batch_size_performance[batch_size] = [0, 0]

        self._batch_size_performance[batch_size][0] += success_count
        self._batch_size_performance[batch_size][1] += (total_count - success_count)
