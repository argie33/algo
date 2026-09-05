"""Batch-fetch execution and rate-limit/transient-error retry logic for PriceLoader,
extracted from load_prices.py (2026-09-05, file-size ratchet: it's the largest Tier-1
bloater flagged for decomposition). Methods are verbatim, no logic changed - mixed into
PriceLoader, which still defines every instance attribute (fetcher, table_name,
_freshness_validator, _circuit_breaker, _rate_limit_errors, _adaptive_request_interval,
_batch_size_performance, _rate_limit_error_start_time, _is_eod_pipeline,
_rate_limit_circuit_break_threshold) and the _record_batch_result method these read/call via
`self`, so behavior is unchanged - only the method bodies moved file.
"""

import logging
from datetime import date, datetime
from typing import Any

from loaders.price_fetcher import PriceFetcher
from utils.infrastructure.circuit_breaker import CircuitBreaker
from utils.validation.data_freshness import FreshnessValidator, StaleDataError

logger = logging.getLogger(__name__)


class BatchFetchRetryMixin:
    """Batch-fetch execution plus rate-limit/transient-error retry methods for PriceLoader.
    Not usable standalone - relies on instance attributes/methods defined on PriceLoader.
    """

    # Type-only declarations (no values) so mypy resolves the `self.X` reads below - the
    # real values are instance attributes/methods defined on PriceLoader, the only class
    # this mixin is ever combined with. Typed precisely (not `Any`) so this class-level
    # declaration doesn't degrade mypy's inference of these same attributes elsewhere in
    # PriceLoader (a bare `Any` here would leak into every `self.fetcher`/etc. read across
    # the whole class via the shared MRO, not just inside this mixin's own methods).
    fetcher: PriceFetcher
    table_name: str
    _freshness_validator: FreshnessValidator
    _circuit_breaker: CircuitBreaker
    _rate_limit_errors: int
    _adaptive_request_interval: float
    _batch_size_performance: dict[int, list[int]]
    _rate_limit_error_start_time: float | None
    _is_eod_pipeline: bool
    _rate_limit_circuit_break_threshold: float

    def _record_batch_result(self, success_count: int, total_count: int) -> None: ...

    def _execute_batch_fetch(self, symbols: list[str], start: date, end: date) -> dict[str, Any] | None:
        """Execute batch fetch with circuit breaker and validate freshness."""
        result = self.fetcher.execute_batch_fetch(symbols, start, end)

        if result and isinstance(result, dict):
            latest_price_date: datetime | None = None
            for rows in result.values():
                if rows:
                    for row in rows:
                        # CRITICAL: Fail-fast if date field missing (no silent fallback)
                        if "date" not in row:
                            raise RuntimeError(
                                f"[PRICE_LOADER] CRITICAL: Price row missing required 'date' field. "
                                f"Cannot proceed with incomplete price data. Row: {row}"
                            )
                        row_date_str = row["date"]
                        if row_date_str is None:
                            raise RuntimeError(
                                f"[PRICE_LOADER] CRITICAL: Price row has null 'date' value. "
                                f"Cannot calculate freshness without valid date. Row: {row}"
                            )
                        try:
                            row_date = datetime.fromisoformat(row_date_str)
                            if latest_price_date is None or row_date > latest_price_date:
                                latest_price_date = row_date
                        except (ValueError, TypeError) as e:
                            raise RuntimeError(
                                f"[PRICE_LOADER] Cannot parse price date: '{row_date_str}'. "
                                f"Expected ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). "
                                f"Price data may be corrupted. Error: {e}"
                            ) from e

            if latest_price_date is not None:
                try:
                    self._freshness_validator.check("price_data", latest_price_date, allow_missing=False)
                except StaleDataError as e:
                    logger.critical(
                        f"[FRESHNESS_VALIDATION] {e}. Stock prices are too stale for position sizing. Cannot proceed."
                    )
                    self._circuit_breaker.record_failure()
                    raise RuntimeError(f"Price data freshness validation failed: {e}") from e

        return result

    def _handle_successful_fetch(self, result: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
        """Reset rate limit tracking and record batch performance."""
        if self._rate_limit_errors > 0:
            logger.info(
                f"[RATE_LIMIT_RECOVERY] API recovered after {self._rate_limit_errors} errors. "
                f"Decreasing request interval from {self._adaptive_request_interval:.3f}s back to normal."
            )
            self._adaptive_request_interval = max(0.375, self._adaptive_request_interval * 0.9)

        self._rate_limit_errors = 0
        self._rate_limit_error_start_time = None

        batch_size_key = len(symbols)
        if batch_size_key not in self._batch_size_performance:
            self._batch_size_performance[batch_size_key] = [0, 0]
        self._batch_size_performance[batch_size_key][0] += 1

        return result

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
    ) -> dict[str, Any] | None:
        """Retry rate limit errors with pacing or batch reduction."""
        import random
        import time

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
            logger.warning(
                "[AUDIT_TRAIL] Could not publish rate limit metric: %s. This breaks audit trail.",
                metric_err,
            )

        batch_size_key = len(symbols)
        if batch_size_key not in self._batch_size_performance:
            self._batch_size_performance[batch_size_key] = [0, 0]
        self._batch_size_performance[batch_size_key][1] += 1

        if batch_size == 1 and self._rate_limit_errors >= 2:
            raise RuntimeError(
                f"[BATCH=1 RATE LIMIT ABORT] Batch=1 with {self._rate_limit_errors} rate limit errors. "
                "yfinance API appears down. Cannot proceed with price fetching."
            ) from error

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
            logger.debug("[RATE_LIMIT] Waiting %ss before paced retry...", wait_time)
            time.sleep(wait_time)
            return self._fetch_with_explicit_retry(
                symbols,
                start,
                end,
                batch_size,
                attempt + 1,
                max_attempts,
                elapsed_sec,
            )

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

        results: dict[str, Any] = {}
        failed_chunks = []
        for i in range(0, len(symbols), new_batch_size):
            chunk = symbols[i : i + new_batch_size]
            chunk_results = self._fetch_with_explicit_retry(
                chunk,
                start,
                end,
                new_batch_size,
                attempt + 1,
                max_attempts,
                elapsed_sec=total_elapsed,
            )
            if chunk_results is None:
                # CRITICAL: No results returned for chunk - this is a failure
                failed_chunks.append(chunk)
                logger.error(
                    f"[RATE_LIMIT] Chunk {chunk[:5]} returned None results. Cannot proceed with incomplete price data."
                )
            else:
                results.update(chunk_results)
                # Verify all chunk symbols are present (no partial data)
                missing_symbols = [s for s in chunk if s not in chunk_results or chunk_results[s] is None]
                if missing_symbols:
                    failed_chunks.append(missing_symbols)
                    logger.error(
                        f"[RATE_LIMIT] Chunk missing results for symbols: {missing_symbols}. "
                        f"Cannot proceed with incomplete price data."
                    )

        if failed_chunks:
            failed_count = sum(len(c) for c in failed_chunks)
            raise RuntimeError(
                f"[BATCH FETCH] Reduced batch size retry failed for {failed_count} symbols. "
                f"Cannot proceed with incomplete price coverage. "
                f"yfinance API degraded. Failed chunks: {failed_chunks[:3]}"
            )

        # All chunks successful - record batch completion
        successful_chunks = (len(symbols) + new_batch_size - 1) // new_batch_size
        total_chunks = successful_chunks
        self._record_batch_result(successful_chunks, total_chunks)

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
    ) -> dict[str, Any] | None:
        """Retry transient errors with exponential backoff."""
        import random
        import time

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
        return self._fetch_with_explicit_retry(
            symbols,
            start,
            end,
            batch_size,
            attempt + 1,
            max_attempts,
            elapsed_sec=elapsed_sec + wait_time,
        )

    def _fetch_with_explicit_retry(  # noqa: C901 -- pre-existing complexity debt (was covered by loaders/load_prices.py's file-wide C901 ignore before this 2026-09-05 extraction), not introduced by this change
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int,
        attempt: int = 0,
        max_attempts: int = 3,
        elapsed_sec: float = 0,
    ) -> dict[str, Any] | None:
        """Fetch with progressive batch size reduction and adaptive retry with jitter.

        ISSUE #6 FIX: Add upper bound check - if batch_size=1 and still rate limited, fail immediately.
        Attempts: full batch -> split in half -> quarter size -> give up.
        Includes randomized jitter to avoid thundering herd and circuit breaker for persistent errors.

        CRITICAL: Prevents infinite batch reduction + timeout cascade by tracking elapsed time.
        If batch=1 and elapsed > threshold, fail immediately rather than waiting indefinitely.
        """
        import time

        # ISSUE #6 FIX: Prevent infinite batch reduction and Step Function timeout
        # Track elapsed time to detect when we're spending too long on rate limiting
        if elapsed_sec is None:
            elapsed_sec = 0

        # CRITICAL BOUND: If batch_size=1 and rate limiting persists, give up per pipeline context
        # ISSUE #23 FIX: Reduced thresholds - rates at batch=1 usually indicate API is down
        # EOD (85 min deadline): 2 min max wait at batch=1 to fail fast and trigger failsafe
        # Morning (450 min deadline): 5 min max wait at batch=1 (was 10, but if batch=1 hangs, API is likely degraded)
        max_single_batch_wait = 120 if self._is_eod_pipeline else 300
        if batch_size == 1 and elapsed_sec > max_single_batch_wait:
            logger.critical(
                f"[BATCH FETCH TIMEOUT] Batch=1 with {elapsed_sec / 60:.1f}min elapsed. "
                "Failing immediately to prevent Step Function timeout. yfinance severely degraded."
            )
            raise RuntimeError(
                f"[BATCH FETCH TIMEOUT] Batch=1 with {elapsed_sec / 60:.1f}min elapsed. "
                "yfinance API severely degraded - cannot proceed without data."
            )

        # ISSUE #6 FIX: If we've shrunk to batch_size=1 and still rate limiting, give up immediately
        # This prevents infinite reduction and timeout cascade
        if batch_size <= 0 or attempt >= max_attempts:
            logger.critical(
                f"[BATCH FETCH] Exhausted all retry attempts: {attempt}/{max_attempts} with batch_size={batch_size}, elapsed {elapsed_sec:.0f}s"
            )
            raise RuntimeError(
                f"[BATCH FETCH EXHAUSTED] Max attempts ({max_attempts}) exceeded with batch_size={batch_size}. "
                "yfinance API unavailable - cannot fetch price data."
            )

        # Issue #1 FIX (Blocker #1): Proactive early abort if rate limiting detected at batch >= 20
        # CRITICAL: Fail-fast rather than wait through hopeless retry loops.
        # At batch=20 with persistent 429s, loader could take 400+ min for 5000+ symbols.
        # If we've hit 3+ rate limit errors, yfinance is clearly degraded. Timing is context-aware:
        #   - EOD (85-min pipeline): abort immediately after 3 errors (tight deadline, fail-fast required)
        #   - Morning (450-min pipeline): abort after 3 errors + 30s duration (allow brief recovery)
        # This prevents: batch 150->20->10->5->1 cascade where load time balloons from 15 min -> 200+ min
        if batch_size >= 20 and self._rate_limit_errors >= 3:
            error_duration = (
                (time.time() - self._rate_limit_error_start_time) if self._rate_limit_error_start_time else 0
            )
            should_abort = self._is_eod_pipeline or error_duration > 30
            if should_abort:
                context = "EOD (fail-fast)" if self._is_eod_pipeline else f"persistent {error_duration:.0f}s"
                logger.critical(
                    f"[RATE_LIMIT_EARLY_ABORT] Batch size {batch_size} with {self._rate_limit_errors} rate limit errors ({context}). "
                    "yfinance API severely degraded. Aborting early to prevent timeout cascade."
                )
                raise RuntimeError(
                    f"[RATE_LIMIT_EARLY_ABORT] {self._rate_limit_errors} rate limit errors at batch={batch_size} ({context}). "
                    "yfinance API severely degraded - cannot fetch price data."
                )

        # Issue #20 FIX: At batch=1, try longer wait before giving up
        if batch_size == 1 and self._rate_limit_errors > 3:
            # Try with exponential backoff + longer wait times (up to 10 min) at batch=1
            max_batch1_wait = 600  # 10 minutes for batch=1 final attempts
            if error_duration := (
                (time.time() - self._rate_limit_error_start_time) if self._rate_limit_error_start_time else 0
            ):
                remaining_wait = max(0, max_batch1_wait - error_duration)
                if remaining_wait > 60:  # Only if we have >1 min left
                    logger.warning(
                        f"[BATCH=1 BACKOFF] Batch size at minimum with {self._rate_limit_errors} errors. "
                        f"Attempting longer exponential backoff ({remaining_wait:.0f}s remaining) before final failure."
                    )
                    # Don't return yet - let the normal retry loop below handle the backoff
                elif remaining_wait > 0:
                    logger.warning(
                        f"[BATCH=1] Rate limiting at batch=1. Last chance with {remaining_wait:.0f}s remaining before timeout."
                    )

            # If we've exhausted backoff time, fail
            if error_duration and error_duration > max_batch1_wait:
                logger.critical(
                    f"[BATCH FETCH ABORT] Batch size at minimum (1 symbol) with {self._rate_limit_errors} rate limit errors "
                    f"persisting for {error_duration / 60:.1f}min. yfinance API severely degraded. Failing to prevent timeout."
                )
                try:
                    from algo.reporting import MetricsPublisher

                    m = MetricsPublisher()
                    m.add_metric(
                        "BatchFetchMinimumSizeReached",
                        1,
                        unit="Count",
                        dimensions={
                            "table": self.table_name,
                            "error_count": str(self._rate_limit_errors),
                        },
                    )
                    m.flush()
                except Exception as metric_err:
                    logger.debug(
                        "Could not publish batch fetch minimum size metric: %s",
                        metric_err,
                    )
                raise RuntimeError(
                    f"[BATCH FETCH ABORT] Batch at minimum with {self._rate_limit_errors} rate limit errors for {error_duration / 60:.1f}min. "
                    "yfinance API severely degraded - cannot fetch price data."
                )

        # Check circuit breaker: if rate limiting has persisted for > threshold, try smaller batch size
        # Issue #6: Instead of failing completely, reduce batch size to avoid timeout
        # ISSUE #1 FIX: Skip circuit breaker if early abort already triggered (prevents false retry loop)
        if self._rate_limit_error_start_time is not None and not (batch_size >= 20 and self._rate_limit_errors >= 3):
            error_duration = time.time() - self._rate_limit_error_start_time
            if error_duration > self._rate_limit_circuit_break_threshold:
                logger.warning(
                    f"[CIRCUIT BREAKER] Rate limiting persisted for {error_duration / 60:.1f} minutes ({error_duration:.0f}s). "
                    "Attempting to continue with smaller batch size instead of failing completely."
                )

                # Try with progressively smaller batch sizes (10, 5, 1)
                # ISSUE #6 FIX: Stop trying if already spent too long on rate limiting
                if elapsed_sec > max_single_batch_wait * 0.8:  # 8 minutes threshold
                    logger.critical(
                        f"[CIRCUIT BREAKER] Rate limiting {elapsed_sec / 60:.1f}min, approaching timeout. "
                        "Skipping reduced batch size attempts, failing batch immediately."
                    )
                    raise RuntimeError(
                        f"[CIRCUIT BREAKER TIMEOUT] Rate limiting for {elapsed_sec / 60:.1f}min, approaching Step Function timeout. "
                        "yfinance API unavailable - cannot fetch price data."
                    )

                reduced_batch_sizes = [10, 5, 1]
                for reduced_size in reduced_batch_sizes:
                    if reduced_size >= batch_size:
                        continue  # Skip if not smaller than current

                    logger.info(
                        "[CIRCUIT BREAKER] Retrying with reduced batch size: %s (was %s), elapsed %.0fs",
                        reduced_size,
                        batch_size,
                        elapsed_sec,
                    )
                    reduced_attempt = self._fetch_with_explicit_retry(
                        symbols,
                        start,
                        end,
                        batch_size=reduced_size,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                    )
                    # FAIL-FAST: Reduced batch size attempts must return COMPLETE data or None
                    # Partial data (some symbols, missing others) is unacceptable
                    if reduced_attempt is not None and any(v is not None for v in reduced_attempt.values()):
                        # Reduced batch returned partial data
                        symbols_fetched = sum(1 for v in reduced_attempt.values() if v is not None)
                        # FAIL-FAST: Incomplete data from reduced batch is a critical error
                        # Raise immediately without accepting partial data
                        logger.critical(
                            f"[PRICE_LOADER] Batch size reduction resulted in incomplete price data: "
                            f"only {symbols_fetched}/{len(symbols)} symbols available. "
                            f"Batch reduction {batch_size}->{reduced_size} failed to recover full coverage."
                        )
                        raise RuntimeError(
                            f"[PRICE_LOADER] Cannot proceed with incomplete price data. "
                            f"Requested {len(symbols)} symbols but only retrieved {symbols_fetched} after rate-limit batch reduction. "
                            f"Price coverage MUST be complete for downstream calculations (technical indicators, buy/sell signals). "
                            f"yfinance API is experiencing degradation; cannot complete load cycle."
                        )
                    # If reduced_attempt is None or all values None, continue to next reduced size

                # All reduced sizes failed - circuit breaker triggered, fail immediately
                logger.critical(
                    f"[CIRCUIT_BREAKER] Rate limiting persisted {error_duration / 60:.1f}min despite batch size reduction. "
                    "yfinance API experiencing degradation. Cannot proceed without price data. Failing fast."
                )
                try:
                    from algo.reporting import AlertManager

                    alerts = AlertManager()
                    alerts.send_position_alert(
                        "YFINANCE",
                        "RATE_LIMIT_CIRCUIT_BREAK",
                        f"yfinance rate limiting persisted {error_duration / 60:.1f}min despite batch reduction. "
                        f"EOD pipeline may be impacted. {self._rate_limit_errors} rate limit errors detected.",
                        {
                            "duration_seconds": error_duration,
                            "error_count": self._rate_limit_errors,
                        },
                    )
                except Exception as alert_err:
                    logger.debug("Could not send rate limit alert: %s", alert_err)

                raise RuntimeError(
                    f"[CIRCUIT_BREAKER] Rate limiting persisted {error_duration / 60:.1f}min despite batch reduction. "
                    "yfinance API severely degraded. Cannot fetch price data."
                )

        try:
            result = self._execute_batch_fetch(symbols, start, end)
            if result:
                return self._handle_successful_fetch(result, symbols)
            return result
        except Exception as e:
            error_str = str(e).lower()

            is_circuit_open = "circuit" in error_str.lower() and (
                "open" in error_str.lower() or "unavailable" in error_str.lower()
            )
            if is_circuit_open:
                logger.critical(
                    f"[CIRCUIT_BREAKER] yfinance_prices circuit open: {e}. "
                    "Cannot fetch price data when API is down. Failing fast."
                )
                raise RuntimeError(
                    f"[CIRCUIT_BREAKER] Price data circuit open: {e}. "
                    "Cannot proceed without price data. Waiting for API recovery."
                ) from e

            is_rate_limit = "rate" in error_str or "429" in error_str or "too many" in error_str

            if is_rate_limit:
                return self._handle_rate_limit_error(
                    symbols,
                    start,
                    end,
                    batch_size,
                    attempt,
                    max_attempts,
                    elapsed_sec,
                    e,
                )
            else:
                return self._handle_transient_error(
                    symbols,
                    start,
                    end,
                    batch_size,
                    attempt,
                    max_attempts,
                    elapsed_sec,
                    e,
                )
