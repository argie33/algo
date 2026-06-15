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

import os
import signal
import logging
import sys
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class TimeoutError(Exception):
    """Raised when execution exceeds timeout limit."""

def _timeout_handler_unix(signum, frame):
    """Signal handler for Unix-based timeout (SIGALRM)."""
    raise TimeoutError("Execution timeout: exceeded maximum allowed time")

@contextmanager
def ExecutionTimeout(max_seconds: int = 5400, label: str = "loader"):
    """
    Context manager that enforces a hard execution timeout.

    On Unix: Uses signal.SIGALRM (more reliable, no threading overhead)
    On Windows: Uses threading.Timer (compatible but less reliable under thread saturation)

    Args:
        max_seconds: Maximum execution time in seconds (default 90 min)
        label: Human-readable label for logging (e.g., "stock_prices_daily")

    Raises:
        TimeoutError: If execution exceeds max_seconds

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
            logger.info(
                f"[TIMEOUT] Using signal-based timeout for {label}: {max_seconds}s"
            )

            # Set SIGALRM handler
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler_unix)  # type: ignore[attr-defined]
            signal.alarm(max_seconds)  # type: ignore[attr-defined]
            try:
                yield
            finally:
                # Cancel alarm and restore old handler
                signal.alarm(0)  # type: ignore[attr-defined]
                signal.signal(signal.SIGALRM, old_handler)  # type: ignore[attr-defined]

        # Windows / Other: Use threading-based timeout
        else:
            logger.info(
                f"[TIMEOUT] Using threading-based timeout for {label}: {max_seconds}s (non-signal platform)"
            )

            def _timeout_func():
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

    except TimeoutError:
        logger.error(
            f"[TIMEOUT] {label} exceeded timeout limit: {max_seconds}s. "
            "This indicates either slow API responses or resource contention. "
            "Raising TimeoutError to halt loader gracefully."
        )
        # Attempt to log failure before exit
        raise
