#!/usr/bin/env python3
"""PriceFetcher specialist - handles API interaction and fetch logic.

Extracted from PriceLoader to eliminate God Object code smell.
Responsibility: Fetch price data from yfinance API with error handling, retries, and rate limiting.
"""

import logging
import random
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class PriceFetcher:
    """Specialist for fetching price data from yfinance API.

    Handles:
    - API calls to yfinance
    - Error handling and retries
    - Rate limiting and adaptive request pacing
    - Batch fetch orchestration
    """

    def __init__(
        self,
        router: Any = None,
        interval: str = "1d",
        asset_class: str = "stock",
        is_eod_pipeline: bool = False,
        rate_limit_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize PriceFetcher with rate limiting config."""
        self.router = router
        self.interval = interval
        self.asset_class = asset_class
        self._is_eod_pipeline = is_eod_pipeline

        # Rate limit: 160 API calls per minute (safe margin below yfinance's 200/min)
        self._rate_limit_tokens: float = 300  # Initial burst
        self._rate_limit_max_tokens: float = 300
        self._rate_limit_last_refill: float = time.time()
        self._rate_limit_refill_rate = 160 / 60  # 2.67 tokens/sec
        self._rate_limit_lock = threading.Lock()
        self._rate_limit_event = threading.Condition(self._rate_limit_lock)

        # Rate limit error tracking
        self._rate_limit_errors: int = 0
        self._rate_limit_error_start_time: float | None = None
        self._rate_limit_circuit_break_threshold: int = 10

        # Market close timeout tracking
        self._market_close_timeout_count: int = 0
        self._last_market_close_timeout_time: float | None = None

        # Batch success tracking
        self._batch_success_count: int = 0
        self._batch_total_count: int = 0
        self._batch_failure_ratio: float = 0.0

        # Adaptive request pacing
        self._request_latency_samples: list[tuple[float, float]] = []
        self._latency_window_sec = 60
        self._min_request_interval = 0.1
        self._adaptive_request_interval = 0.375
        self._last_request_time: float | None = None

        # Batch sizing optimization
        self._batch_size_performance: dict[int, list[int]] = {}
        self.batch_size = 500

        # Circuit breaker integration
        self._circuit_breaker = None

    def _rate_limit_wait(self, tokens_needed: int = 1) -> None:
        """Wait until enough tokens are available (thread-safe)."""
        """Wait until enough tokens are available (thread-safe)."""
        with self._rate_limit_event:
            while self._rate_limit_tokens < tokens_needed:
                self._rate_limit_event.wait(timeout=0.1)
                self._refill_tokens()
            self._rate_limit_tokens -= tokens_needed

    def _refill_tokens(self) -> None:
        """Refill rate limit tokens based on elapsed time."""
        """Refill rate limit tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._rate_limit_last_refill
        tokens_earned = elapsed * self._rate_limit_refill_rate
        self._rate_limit_tokens = min(self._rate_limit_max_tokens, self._rate_limit_tokens + tokens_earned)
        self._rate_limit_last_refill = now

    def _adaptive_request_pacing(self) -> None:
        """Adjust request pacing based on observed API latency."""
        """Adjust request pacing based on observed API latency."""
        now = time.time()

        # Remove old samples outside the window
        cutoff = now - self._latency_window_sec
        self._request_latency_samples = [(ts, lat) for ts, lat in self._request_latency_samples if ts > cutoff]

        if len(self._request_latency_samples) > 10:
            avg_latency = sum(lat for _, lat in self._request_latency_samples) / len(self._request_latency_samples)
            # If API is slow (avg latency > 0.5s), increase request interval
            if avg_latency > 0.5:
                self._adaptive_request_interval = min(1.0, self._adaptive_request_interval * 1.1)
            # If API is fast (avg latency < 0.1s), decrease request interval
            elif avg_latency < 0.1:
                self._adaptive_request_interval = max(self._min_request_interval, self._adaptive_request_interval * 0.9)

    def _record_request_latency(self, latency_sec: float) -> None:
        """Record API request latency for adaptive pacing."""
        """Record API request latency for adaptive pacing."""
        self._request_latency_samples.append((time.time(), latency_sec))

    def _get_smart_batch_size(self) -> int:
        """Determine optimal batch size based on performance history."""
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
            if len(self._batch_size_performance) >= 50:
                self._batch_size_performance.clear()

            self._batch_size_performance[batch_size] = [0, 0]

        self._batch_size_performance[batch_size][0] += success_count
        self._batch_size_performance[batch_size][1] += total_count - success_count

    def set_circuit_breaker(self, circuit_breaker: Any) -> None:
        """Set circuit breaker for API call protection."""
        if circuit_breaker is None:
            logger.warning(
                "[PRICE_FETCHER] Circuit breaker not configured. "
                "Price fetches will execute without API outage protection. "
                "This is a degraded state - consider re-checking initialization."
            )
        self._circuit_breaker = circuit_breaker

    def get_current_batch_size(self) -> int:
        """Get the current adaptive batch size based on performance and pipeline context."""
        """Get the current adaptive batch size based on performance and pipeline context."""
        smart_size = self._get_smart_batch_size()
        if smart_size != 500:  # If smart sizing found a different size
            return smart_size
        # Fallback: conservative during EOD
        return 20 if self._is_eod_pipeline else 100

    def get_rate_limit_error_count(self) -> int:
        """Get the current count of rate limit errors encountered."""
        """Get the current count of rate limit errors encountered."""
        return self._rate_limit_errors

    def fetch_incremental(self, symbol: str, since: date | None, is_eod_pipeline: bool = False) -> Any:
        """Fetch OHLCV from yfinance at specified interval.

        Args:
            symbol: Stock symbol
            since: Start date for incremental fetch
            is_eod_pipeline: Whether this is end-of-day pipeline (affects end date logic)
        """
        from utils.infrastructure.timezone import EASTERN_TZ

        now_utc = datetime.now().astimezone()
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date() + timedelta(days=1)

        if since is None:
            start = end - timedelta(days=101)
        else:
            start = since

        if start > end:
            error_msg = f"Invalid date range: start ({start}) > end ({end})"
            logger.error(error_msg)
            raise ValueError(error_msg)

        rows = self._try_fetch(symbol, start, end)
        return rows

    def fetch_batch_incremental(
        self, symbols: list[str], since: date | None, is_eod_pipeline: bool = False
    ) -> dict[str, Any] | None:
        """Fetch OHLCV for multiple symbols at once (50x faster than per-symbol).

        Returns: dict[symbol] -> rows or None
        """
        from utils.infrastructure.timezone import EASTERN_TZ

        now_utc = datetime.now().astimezone()
        now_et = now_utc.astimezone(EASTERN_TZ)

        if is_eod_pipeline:
            end = now_et.date()
            logger.info(f"[EOD_CONTEXT] Fetching data ending at {end} (yesterday's complete data for EOD)")
        else:
            end = now_et.date() + timedelta(days=1)
            logger.debug(f"[INTRADAY_CONTEXT] Fetching data ending at {end} (including today)")

        start = end - timedelta(days=101) if since is None else since

        if start >= end:
            error_msg = f"Invalid date range for batch fetch: start ({start}) >= end ({end})"
            logger.error(error_msg)
            raise ValueError(error_msg)

        adaptive_batch_size = min(len(symbols), self._get_smart_batch_size())
        logger.debug(f"[FETCH] {len(symbols)} symbols, adaptive batch size: {adaptive_batch_size}")

        result = self._fetch_with_fallback(symbols, start, end, batch_size=adaptive_batch_size, attempt=0)
        if result:
            self._record_successful_fetch()
        return result

    def _try_fetch(self, symbol: str, start: date, end: date, max_retries: int = 5) -> Any:
        """Try to fetch data from yfinance with retry logic for transient failures."""
        for attempt in range(max_retries):
            try:
                if not self.router:
                    raise RuntimeError("Router not configured in PriceFetcher")
                return self.router.fetch_ohlcv_interval(symbol, start, end, self.interval)
            except Exception as e:
                error_str = str(e).lower()
                # Rate limit errors - retry with exponential backoff + jitter
                if "rate" in error_str or "429" in error_str or "too many" in error_str:
                    if attempt < max_retries - 1:
                        base_wait = min(120, (2**attempt) * 2)
                        jitter = random.uniform(0.9, 1.1)
                        wait_time = base_wait * jitter
                        logger.warning(
                            f"[{symbol}] Rate limited (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {wait_time:.1f}s (base {base_wait}s)..."
                        )
                        time.sleep(wait_time)
                        continue
                    raise RuntimeError(
                        f"[{symbol}] Rate limited after {max_retries} attempts. "
                        "Cannot fetch price data when API is rate limited."
                    ) from e
                # Network/timeout errors - retry with backoff + jitter
                if any(x in error_str for x in ["timeout", "json", "parse", "connection", "reset"]):
                    if attempt < max_retries - 1:
                        base_wait = 2**attempt
                        jitter = random.uniform(0.8, 1.2)
                        wait_time = base_wait * jitter
                        logger.warning(
                            f"[{symbol}] Transient error (attempt {attempt + 1}/{max_retries}): {e}, "
                            f"retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    raise RuntimeError(
                        f"[{symbol}] Transient error after {max_retries} attempts: {e}. "
                        "Cannot fetch price data after exhausting retries."
                    ) from e
                # Auth errors - must fail fast
                if "403" in error_str or "401" in error_str or "unauthorized" in error_str:
                    raise RuntimeError(
                        f"[{symbol}] Authentication error accessing price data: {e}. "
                        "Cannot proceed without valid credentials."
                    ) from e
                logger.error(f"[{symbol}] Unexpected error: {e}")
                raise
        raise RuntimeError(f"[{symbol}] Exhausted all fetch attempts without successful data fetch")

    def execute_batch_fetch(self, symbols: list[str], start: date, end: date) -> dict[str, Any]:
        """Execute batch fetch with circuit breaker and validate freshness.

        Raises:
            RuntimeError: If fetch fails or returns invalid data type (price data is critical)
        """
        self._adaptive_request_pacing()
        request_start = time.time()

        def fetch_batch() -> dict[str, Any]:
            if not self.router:
                raise RuntimeError("Router not configured in PriceFetcher")
            batch_result = self.router.fetch_ohlcv_batch(symbols, start, end, interval=self.interval)
            if batch_result is None:
                raise RuntimeError(
                    f"Price batch fetch returned None for {len(symbols)} symbols ({start} to {end}). "
                    f"Router may be unavailable or API returned empty result."
                )
            if not isinstance(batch_result, dict):
                raise RuntimeError(
                    f"Price batch fetch returned invalid type {type(batch_result).__name__} "
                    f"(expected dict). Router response format mismatch."
                )
            return batch_result

        try:
            if self._circuit_breaker:
                from utils.infrastructure.circuit_breaker import DataImportance

                result = self._circuit_breaker.execute(fetch_func=fetch_batch, importance=DataImportance.CRITICAL)
            else:
                result = fetch_batch()

            if result is None:
                raise RuntimeError("Circuit breaker returned None for price batch fetch. Cannot proceed without price data.")
        except RuntimeError as e:
            error_str = str(e).lower()
            if any(x in error_str for x in ["circuit", "breaker", "open", "unavailable"]):
                raise
            raise RuntimeError(
                f"Price batch fetch failed: {e}. "
                f"Likely transient API error - retry with smaller batch size may succeed."
            ) from e

        request_latency = time.time() - request_start
        self._record_request_latency(request_latency)
        return result

    def _fetch_with_fallback(
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int = 500,
        attempt: int = 0,
        max_attempts: int = 3,
        elapsed_sec: float = 0,
    ) -> dict[str, Any]:
        """Fetch batch with fallback to smaller batch size on rate limiting."""
        """Fetch batch with fallback to smaller batch size on rate limiting."""
        batch_size = min(len(symbols), batch_size)
        logger.debug(f"[FETCH_BATCH] Attempting with batch_size={batch_size}, attempt={attempt}")

        if batch_size < 1:
            raise RuntimeError("Cannot further reduce batch size for fallback")

        # Split symbols into batches
        all_results = {}
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            try:
                result = self.execute_batch_fetch(batch, start, end)
                if result:
                    all_results.update(result)
                    success_count = len([r for r in result.values() if r is not None])
                    self._record_batch_result(batch_size, success_count, len(batch))
            except RuntimeError as e:
                error_str = str(e).lower()
                # Rate limit errors - use dedicated handler
                if "rate" in error_str or "429" in error_str:
                    return self._handle_rate_limit_error(
                        batch,
                        start,
                        end,
                        batch_size,
                        attempt,
                        max_attempts,
                        elapsed_sec,
                        e,
                    )
                # Transient errors - retry with backoff
                if any(x in error_str for x in ["timeout", "connection", "reset"]):
                    return self._handle_transient_error(
                        batch,
                        start,
                        end,
                        batch_size,
                        attempt,
                        max_attempts,
                        elapsed_sec,
                        e,
                    )
                raise

        return all_results

    def _record_successful_fetch(self) -> None:
        """Record a successful fetch and reset rate limit counters if API has recovered."""
        if self._rate_limit_errors > 0:
            error_window = time.time() - (self._rate_limit_error_start_time or time.time())
            logger.info(
                f"[RATE_LIMIT] API recovered after {self._rate_limit_errors} errors "
                f"({error_window:.0f}s duration). Resetting rate limit counters."
            )
            self._rate_limit_errors = 0
            self._rate_limit_error_start_time = None
            self._adaptive_request_interval = max(0.1, self._adaptive_request_interval * 0.9)

    def _handle_rate_limit_error(
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int,
        attempt: int,
        max_attempts: int,
        elapsed_sec: float,
        error: Exception,
    ) -> dict[str, Any]:
        """Retry rate limit errors with pacing or batch reduction."""
        """Retry rate limit errors with pacing or batch reduction."""
        self._rate_limit_errors += 1
        if self._rate_limit_error_start_time is None:
            self._rate_limit_error_start_time = time.time()
            logger.warning(
                f"[RATE_LIMIT] First rate limiting error detected (error #{self._rate_limit_errors}). "
                "Circuit will break if persists >5 minutes. Monitoring yfinance API recovery."
            )

        self._adaptive_request_interval = min(2.0, self._adaptive_request_interval * 1.5)
        logger.info(
            f"[RATE_LIMIT_PREDICT] Rate limit detected, increasing request interval to {self._adaptive_request_interval:.3f}s"
        )

        try:
            from algo.reporting import MetricsPublisher

            metrics = MetricsPublisher()
            metrics.add_metric(
                "RateLimitErrors",
                1,
                unit="Count",
                dimensions={"Loader": "stock_prices_daily"},
            )
            metrics.flush()
        except Exception as metric_err:
            logger.debug(f"Could not publish rate limit metric: {metric_err}")

        batch_size_key = len(symbols)
        if batch_size_key not in self._batch_size_performance:
            self._batch_size_performance[batch_size_key] = [0, 0]
        self._batch_size_performance[batch_size_key][1] += 1

        # Fail fast if batch size 1 and already rate limited
        if batch_size == 1 and self._rate_limit_errors >= 2:
            raise RuntimeError(
                f"[BATCH=1 RATE LIMIT ABORT] Batch=1 with {self._rate_limit_errors} rate limit errors. "
                "yfinance API appears down. Cannot proceed with price fetching."
            ) from error

        # Fail if EOD pipeline and heavily rate limited
        if self._is_eod_pipeline and batch_size <= 20 and self._rate_limit_errors >= 3:
            raise RuntimeError(
                f"[BATCH FETCH ABORT] Batch={batch_size} with {self._rate_limit_errors} rate limit errors. "
                "yfinance severely degraded. Cannot proceed with price fetching."
            )

        if attempt == 0:
            logger.info(
                f"[RATE_LIMIT] Retrying batch={batch_size} with increased request pacing (attempt {attempt + 1}/{max_attempts})..."
            )
            error_duration = time.time() - self._rate_limit_error_start_time if self._rate_limit_error_start_time else 0
            base_wait = min(30, (2**attempt) * 5)
            jitter = random.uniform(0.9, 1.1)
            wait_time = base_wait * jitter
            logger.debug(f"[RATE_LIMIT] Waiting {wait_time:.1f}s before paced retry...")
            time.sleep(wait_time)
            return self._fetch_with_fallback(symbols, start, end, batch_size, attempt + 1, max_attempts, elapsed_sec)

        # Reduce batch size and retry
        new_batch_size = max(1, batch_size // 2)
        error_duration = time.time() - self._rate_limit_error_start_time if self._rate_limit_error_start_time else 0
        total_elapsed = elapsed_sec + error_duration

        base_wait = min(60, (2**attempt) * 2)
        jitter = random.uniform(0.8, 1.2)
        wait_time = base_wait * jitter

        logger.warning(
            f"[BATCH FETCH] Rate limited after paced retry (attempt {attempt + 1}/{max_attempts}, error #{self._rate_limit_errors}, "
            f"duration {error_duration:.0f}s, total elapsed {total_elapsed:.0f}s). "
            f"Batch {batch_size} -> {new_batch_size}, waiting {wait_time:.1f}s..."
        )
        time.sleep(wait_time)

        results = {}
        successful_chunks = 0
        for i in range(0, len(symbols), new_batch_size):
            chunk = symbols[i : i + new_batch_size]
            chunk_results = self._fetch_with_fallback(
                chunk,
                start,
                end,
                new_batch_size,
                attempt + 1,
                max_attempts,
                elapsed_sec=total_elapsed,
            )
            results.update(chunk_results)
            if any(v is not None for v in chunk_results.values()):
                successful_chunks += 1

        total_chunks = (len(symbols) + new_batch_size - 1) // new_batch_size
        self._record_batch_result(new_batch_size, successful_chunks, total_chunks)

        return results

    def _handle_transient_error(
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int,
        attempt: int,
        max_attempts: int,
        elapsed_sec: float,
        error: Exception,
    ) -> dict[str, Any]:
        """Retry transient errors with exponential backoff."""
        """Retry transient errors with exponential backoff."""
        error_str = str(error).lower()
        is_timeout = "timeout" in error_str or "timed out" in error_str
        is_connection = any(x in error_str for x in ["connection", "reset", "broken", "closed"])

        error_type = (
            "timeout (API slowness)" if is_timeout else "connection (network)" if is_connection else "other transient"
        )

        if is_timeout or is_connection:
            self._adaptive_request_interval = min(2.0, self._adaptive_request_interval * 1.2)
            logger.warning(
                f"[BATCH FETCH] Transient {error_type} error, increasing request interval to {self._adaptive_request_interval:.3f}s for recovery"
            )

        base_wait = min(30, 2**attempt)
        jitter = random.uniform(0.9, 1.1)
        wait_time = base_wait * jitter

        logger.warning(
            f"[BATCH FETCH] Transient {error_type} error (attempt {attempt + 1}/{max_attempts}, elapsed {elapsed_sec:.0f}s): {error}. "
            f"Retrying {len(symbols)} symbols with same batch_size={batch_size} in {wait_time:.1f}s... "
            "(Note: batch size not reduced for timeouts - if API fundamentally slow, increasing wait time not batch reduction)"
        )
        time.sleep(wait_time)

        if attempt < max_attempts - 1:
            return self._fetch_with_fallback(symbols, start, end, batch_size, attempt + 1, max_attempts, elapsed_sec)

        raise RuntimeError(
            f"[BATCH FETCH] Exhausted retries after {max_attempts} attempts with transient {error_type} errors. "
            f"Last error: {error}"
        ) from error
