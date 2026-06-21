#!/usr/bin/env python3
"""Retry Strategy - Configurable retry logic with exponential backoff."""

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStrategy:
    """Implements retry logic with exponential backoff."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 60.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        """Initialize retry strategy.

        Args:
            max_attempts: Maximum retry attempts
            base_delay_seconds: Initial delay between retries
            max_delay_seconds: Maximum delay (caps exponential backoff)
            backoff_multiplier: Exponential backoff multiplier
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay_seconds
        self.max_delay = max_delay_seconds
        self.multiplier = backoff_multiplier
        self.attempt_count = 0

    def execute(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function with retry logic.

        Args:
            func: Callable to execute with retries
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of successful function execution

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.attempt_count = attempt
                result = func(*args, **kwargs)
                if attempt > 1:
                    logger.info(f"[RETRY] Success on attempt {attempt}/{self.max_attempts}")
                return result
            except Exception as e:
                last_exception = e
                if attempt < self.max_attempts:
                    delay = min(self.base_delay * (self.multiplier ** (attempt - 1)), self.max_delay)
                    logger.warning(f"[RETRY] Attempt {attempt} failed, retrying in {delay:.1f}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"[RETRY] All {self.max_attempts} attempts failed: {e}")

        raise last_exception or Exception("Retry exhausted without exception")

    def get_attempt_count(self) -> int:
        """Get current attempt count."""
        return self.attempt_count

    def reset(self) -> None:
        """Reset attempt counter."""
        self.attempt_count = 0
