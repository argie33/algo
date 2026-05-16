#!/usr/bin/env python3
"""
Database Operation Retry Helper

Handles transient failures and race conditions in database operations
with exponential backoff. Used for optimistic locking retries when
concurrent updates modify records between read and update.
"""

import time
import logging
from typing import Callable, Any, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(self, max_attempts: int = 3, base_delay_ms: int = 100, max_delay_ms: int = 5000):
        """
        Args:
            max_attempts: Maximum number of retry attempts
            base_delay_ms: Initial delay in milliseconds
            max_delay_ms: Maximum delay between retries
        """
        self.max_attempts = max_attempts
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms

    def get_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay.

        Args:
            attempt: Attempt number (0-indexed)

        Returns: Delay in seconds
        """
        delay_ms = self.base_delay_ms * (2 ** attempt)
        delay_ms = min(delay_ms, self.max_delay_ms)
        return delay_ms / 1000.0


class OptimisticLockRetry:
    """Helper for retrying operations that fail due to optimistic locking."""

    @staticmethod
    def retry_on_race_condition(
        operation: Callable[[], T],
        operation_name: str = "database_operation",
        config: Optional[RetryConfig] = None,
    ) -> T:
        """Retry an operation if it fails due to optimistic lock conflict (rowcount==0).

        Pattern Usage:
            ```python
            def do_update():
                # Read current state
                cursor.execute("SELECT quantity FROM positions WHERE id=%s", (pos_id,))
                row = cursor.fetchone()
                current_qty = row[0]

                # Update conditionally
                cursor.execute(
                    "UPDATE positions SET quantity=%s WHERE id=%s AND quantity=%s",
                    (new_qty, pos_id, current_qty)
                )
                # Return success indicator
                return cursor.rowcount > 0

            success = OptimisticLockRetry.retry_on_race_condition(
                do_update,
                operation_name="update_position_quantity"
            )
            ```

        Args:
            operation: Callable that returns True if successful, False if optimistic lock failed
            operation_name: Name for logging
            config: RetryConfig (uses defaults if None)

        Returns: True if operation succeeded, False if failed after all retries

        Raises: Exception if a non-race-condition error occurs
        """
        if config is None:
            config = RetryConfig()

        last_error = None
        for attempt in range(config.max_attempts):
            try:
                success = operation()
                if success:
                    if attempt > 0:
                        logger.info(f"[Retry] {operation_name} succeeded after {attempt + 1} attempts")
                    return True
                # Optimistic lock failed (rowcount == 0), retry
                if attempt < config.max_attempts - 1:
                    delay = config.get_delay(attempt)
                    logger.debug(f"[Retry] {operation_name} failed (race condition), retrying in {delay:.2f}s...")
                    time.sleep(delay)
            except Exception as e:
                # Non-transient error, fail immediately
                logger.error(f"[Retry] {operation_name} failed with non-transient error: {e}")
                raise

        # All retries exhausted
        logger.error(f"[Retry] {operation_name} failed after {config.max_attempts} attempts (race condition)")
        return False

    @staticmethod
    def retry_on_exception(
        operation: Callable[[], T],
        operation_name: str = "database_operation",
        config: Optional[RetryConfig] = None,
        should_retry: Optional[Callable[[Exception], bool]] = None,
    ) -> Optional[T]:
        """Retry an operation on specific exceptions (e.g., connection timeouts).

        Args:
            operation: Callable that returns result or raises exception
            operation_name: Name for logging
            config: RetryConfig (uses defaults if None)
            should_retry: Callable(Exception) -> bool to determine if exception is retryable

        Returns: Operation result if successful, None if failed after retries

        Raises: Non-retryable exceptions are raised immediately
        """
        if config is None:
            config = RetryConfig()

        def default_should_retry(e: Exception) -> bool:
            """Retry on connection/timeout errors, not on logic errors."""
            error_type = type(e).__name__
            retryable_types = (
                'OperationalError',  # psycopg2 connection lost
                'InterfaceError',    # psycopg2 connection error
                'TimeoutError',      # Timeout
            )
            return any(retryable_type in error_type for retryable_type in retryable_types)

        if should_retry is None:
            should_retry = default_should_retry

        last_error = None
        for attempt in range(config.max_attempts):
            try:
                result = operation()
                if attempt > 0:
                    logger.info(f"[Retry] {operation_name} succeeded after {attempt + 1} attempts")
                return result
            except Exception as e:
                last_error = e
                if not should_retry(e):
                    logger.error(f"[Retry] {operation_name} failed with non-retryable error: {e}")
                    raise

                if attempt < config.max_attempts - 1:
                    delay = config.get_delay(attempt)
                    logger.warning(f"[Retry] {operation_name} failed ({type(e).__name__}), retrying in {delay:.2f}s...")
                    time.sleep(delay)

        logger.error(f"[Retry] {operation_name} failed after {config.max_attempts} attempts: {last_error}")
        return None


__all__ = ['RetryConfig', 'OptimisticLockRetry']
