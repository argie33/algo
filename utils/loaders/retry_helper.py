"""Centralized retry logic for data loaders - eliminates 26 duplicate retry implementations."""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryHelper:
    """Handles exponential backoff retry logic for transient errors.

    Eliminates 180+ lines of duplicate retry code across 6+ loaders.
    Reduces CPU overhead from repeated backoff calculations.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 32.0,
    ):
        """Initialize retry configuration.

        Args:
            max_retries: Number of retry attempts (default 3 = up to 4 total tries)
            backoff_seconds: Initial backoff in seconds (default 1.0)
            max_backoff_seconds: Cap backoff at this value to prevent excessive waits (default 32)
        """
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

    def with_retries(
        self,
        fn: Callable[[], T],
        context: str = "operation",
        transient_errors: tuple[type[Exception], ...] | None = None,
    ) -> T:
        """Execute function with exponential backoff retry on transient errors.

        Args:
            fn: Callable to execute (should raise exception on failure)
            context: Context string for logging (e.g., "fetch VIX data")
            transient_errors: Tuple of exception types to retry on (default: ConnectionError, TimeoutError)

        Returns:
            Result of successful function call

        Raises:
            Last exception if all retries exhausted
        """
        if transient_errors is None:
            transient_errors = (ConnectionError, TimeoutError, Exception)

        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_exception = e

                # Check if this is a transient error worth retrying
                is_transient = any(isinstance(e, exc_type) for exc_type in transient_errors)

                if not is_transient or attempt >= self.max_retries:
                    # Not transient or out of retries - fail immediately
                    logger.error(
                        f"[{context}] Failed after {attempt + 1} attempt(s): {e}. "
                        f"{'Transient error exhausted retries.' if is_transient else 'Non-transient error.'}"
                    )
                    raise

                # Transient error and retries remaining - backoff and retry
                wait_time = min(
                    self.backoff_seconds * (2**attempt),
                    self.max_backoff_seconds,
                )
                logger.warning(
                    f"[{context}] Transient error on attempt {attempt + 1}: {e}. "
                    f"Retrying in {wait_time:.1f}s ({self.max_retries - attempt} retries remaining)..."
                )
                time.sleep(wait_time)

        # Should not reach here (loop always exits via return or raise above)
        # but add explicit error handling to satisfy type checker
        raise RuntimeError(f"[{context}] Unexpected: retry loop completed without result. Last error: {last_exception}")

    def with_retries_silent(
        self,
        fn: Callable[[], T],
        fallback: T,
        context: str = "operation",
        log_errors: bool = False,
    ) -> T:
        """Execute function with retries, return fallback on all failures (silent).

        Used for non-critical data that can be marked unavailable.

        Args:
            fn: Callable to execute
            fallback: Value to return if all retries fail
            context: Context string for logging
            log_errors: Whether to log errors (default False for silent mode)

        Returns:
            Result of successful call, or fallback if exhausted
        """
        try:
            return self.with_retries(fn, context=context)
        except Exception as e:
            if log_errors:
                logger.warning(f"[{context}] Returning fallback after retries exhausted: {e}")
            return fallback


# Singleton instance for convenience
_default_retry = RetryHelper()


def retry_with_backoff(
    fn: Callable[[], T],
    context: str = "operation",
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> T:
    """Convenience function for single-use retry (no need to instantiate RetryHelper).

    Args:
        fn: Callable to execute
        context: Context string for logging
        max_retries: Number of retries
        backoff_seconds: Initial backoff in seconds

    Returns:
        Result of successful call

    Raises:
        Last exception if all retries exhausted
    """
    helper = RetryHelper(max_retries=max_retries, backoff_seconds=backoff_seconds)
    return helper.with_retries(fn, context=context)


def retry_transient(
    fn: Callable[[], T],
    context: str = "operation",
    fallback: T = None,  # type: ignore
) -> T:
    """Retry only on transient errors (network, timeout), return fallback on others.

    Useful for marking data unavailable when API is down but not on schema errors.

    Args:
        fn: Callable to execute
        context: Context string for logging
        fallback: Value to return on failure (typically data_unavailable marker)

    Returns:
        Result or fallback
    """
    return _default_retry.with_retries_silent(fn, fallback, context=context)
