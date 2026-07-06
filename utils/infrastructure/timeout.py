#!/usr/bin/env python3
"""
Execution timeout utility for long-running loaders.

Implements a hard timeout using signal (Unix) or threading (Windows) to abort
loaders that exceed their time budget. This prevents RDS connection leaks when
yfinance rate limiting causes extended delays.

Usage:
    with ExecutionTimeout(max_seconds=5400):
        loader.run(symbols, parallelism=8)
"""

import logging
import os
import signal
import sys
import threading
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


class ExecutionTimeoutError(Exception):
    """Raised when execution exceeds timeout limit."""


def _timeout_handler_unix(signum: int, frame: Any) -> None:
    """Signal handler for Unix-based timeout (SIGALRM)."""
    raise ExecutionTimeoutError("Execution timeout: exceeded maximum allowed time")


@contextmanager
def execution_timeout(max_seconds: int = 5400, label: str = "loader") -> Any:
    """
    Context manager that enforces a hard execution timeout.

    On Unix: Uses signal.SIGALRM (more reliable, no threading overhead)
    On Windows: Uses threading.Timer (compatible but less reliable under thread saturation)

    Args:
        max_seconds: Maximum execution time in seconds (default 90 min)
        label: Human-readable label for logging (e.g., "stock_prices_daily")

    Raises:
        ExecutionTimeoutError: If execution exceeds max_seconds

    Usage:
        try:
            with ExecutionTimeout(5400, "stock_prices_daily"):
                loader.run(symbols)
        except TimeoutError:
            logger.error("Loader timeout exceeded")
            raise
    """
    timeout_thread = None
    platform = sys.platform

    try:
        # Unix: Use signal-based timeout (more reliable)
        if platform in ("linux", "linux2", "darwin"):
            logger.info(f"[TIMEOUT] Using signal-based timeout for {label}: {max_seconds}s")

            # Set SIGALRM handler
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler_unix)
            signal.alarm(max_seconds)
            try:
                yield
            finally:
                # Cancel alarm and restore old handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        # Windows / Other: Use threading-based timeout
        else:
            logger.info(f"[TIMEOUT] Using threading-based timeout for {label}: {max_seconds}s (non-signal platform)")

            def _timeout_func() -> None:
                logger.critical(
                    f"[TIMEOUT] TIMEOUT EXCEEDED for {label} after {max_seconds}s. "
                    "Aborting execution to prevent RDS connection leaks."
                )
                # Use os._exit to forcefully terminate (threading.Timer can't kill threads)
                # This is intentional - better to hard-exit than leak connections
                os._exit(1)

            timeout_thread = threading.Timer(max_seconds, _timeout_func)
            timeout_thread.daemon = True
            timeout_thread.start()

            try:
                yield
            finally:
                if timeout_thread and timeout_thread.is_alive():
                    timeout_thread.cancel()

    except ExecutionTimeoutError:
        logger.error(
            f"[TIMEOUT] {label} exceeded timeout limit: {max_seconds}s. "
            "This indicates either slow API responses or resource contention. "
            "Raising ExecutionTimeoutError to halt loader gracefully."
        )
        # Attempt to log failure before exit
        raise


class ExecutionTimeout:
    """Context manager class for execution timeouts.

    Wraps execution_timeout for convenient use with `with` statements.
    Usage: with ExecutionTimeout(max_seconds=5400, label="loader"):
    """

    def __init__(self, max_seconds: int = 5400, label: str = "loader") -> None:
        self.max_seconds = max_seconds
        self.label = label
        self._context: Any = None

    def __enter__(self) -> Any:
        self._context = execution_timeout(self.max_seconds, self.label)
        return self._context.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        if self._context:
            return self._context.__exit__(exc_type, exc_val, exc_tb)
