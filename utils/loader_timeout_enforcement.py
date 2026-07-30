#!/usr/bin/env python3
"""
CRITICAL: Timeout enforcement for long-running loaders to prevent hangs.

Problem: current_reports_8k and sec_segment_info loaders have hung for 12000+ seconds,
leaving orphaned RDS locks that accumulate and degrade system performance.

Solution: Wrap all loader execution with configurable timeout (default 10 minutes max).
If a loader exceeds timeout, it's force-killed to prevent lock accumulation.

Loader developers should use this wrapper instead of raw API calls to prevent hangs.
"""

import logging
import signal
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Max runtime for any loader (seconds)
LOADER_MAX_RUNTIME_SECONDS = int(10 * 60)  # 10 minutes default, configurable


class LoaderTimeoutError(Exception):
    """Raised when a loader exceeds max runtime."""
    pass


def _timeout_handler(signum: int, frame: Any) -> None:
    """Signal handler for timeout."""
    raise LoaderTimeoutError(f"Loader exceeded maximum runtime of {LOADER_MAX_RUNTIME_SECONDS}s")


@contextmanager
def loader_timeout_context(loader_name: str, timeout_seconds: Optional[int] = None):
    """
    Context manager to enforce timeout on loader execution.

    Usage:
        with loader_timeout_context("current_reports_8k", timeout_seconds=600):
            # Run expensive API calls here
            response = requests.get(...)

    Args:
        loader_name: Name of loader for logging
        timeout_seconds: Override default timeout (default: LOADER_MAX_RUNTIME_SECONDS)

    Raises:
        LoaderTimeoutError: If loader exceeds timeout
    """
    timeout = timeout_seconds or LOADER_MAX_RUNTIME_SECONDS
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)

    try:
        start_time = time.time()
        signal.alarm(timeout)
        logger.info(f"[LOADER_TIMEOUT] {loader_name}: timeout enforcement enabled ({timeout}s max)")

        try:
            yield
        finally:
            elapsed = time.time() - start_time
            signal.alarm(0)  # Cancel alarm
            if elapsed > timeout * 0.8:  # Warn if used 80%+ of timeout
                logger.warning(f"[LOADER_TIMEOUT] {loader_name}: used {elapsed:.1f}s of {timeout}s limit")

    except LoaderTimeoutError as e:
        logger.critical(f"[LOADER_TIMEOUT] {loader_name} EXCEEDED TIMEOUT: {e}")
        raise
    finally:
        signal.signal(signal.SIGALRM, old_handler)


def with_loader_timeout(timeout_seconds: Optional[int] = None):
    """
    Decorator to add timeout enforcement to a loader function.

    Usage:
        @with_loader_timeout(timeout_seconds=600)
        def load_current_reports_8k():
            # Function code

    Args:
        timeout_seconds: Override default timeout

    Raises:
        LoaderTimeoutError: If loader exceeds timeout
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with loader_timeout_context(func.__name__, timeout_seconds):
                return func(*args, **kwargs)
        return wrapper
    return decorator
