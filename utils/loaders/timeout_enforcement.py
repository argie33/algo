"""Timeout enforcement for in-process loader execution.

SESSION 111 FIX: Prevents hung loaders from blocking orchestrator.
Used by:
- algo/orchestrator/phase1_failsafe_retry.py (Phase 1 failsafe retry)
- algo/orchestrator/phase7_signal_generation.py (Signal quality scores)
"""

import logging
import os
import signal
import threading

logger = logging.getLogger(__name__)

# Module-level state for timeout enforcement
_LOADER_TIMEOUT_SECONDS: int | None = None
_TIMEOUT_TIMER: threading.Timer | None = None


def _timeout_handler(_signum: int, _frame: object) -> None:
    """Signal handler for SIGALRM timeout. Raises RuntimeError to interrupt hung loader."""
    if _LOADER_TIMEOUT_SECONDS is None:
        timeout_msg = "Loader execution exceeded timeout (timeout value unknown)"
    else:
        timeout_min = _LOADER_TIMEOUT_SECONDS // 60
        timeout_sec = _LOADER_TIMEOUT_SECONDS % 60
        timeout_msg = f"Loader execution exceeded timeout of {_LOADER_TIMEOUT_SECONDS}s ({timeout_min}m {timeout_sec}s)"
    raise RuntimeError(timeout_msg)


def _force_exit_on_timeout() -> None:
    """threading.Timer callback for Windows fallback - log then exit forcefully.

    Used when signal.SIGALRM is unavailable (Windows). Exits immediately without
    cleanup since loader may be stuck in DB transaction.
    """
    active_threads = threading.enumerate()
    thread_info = "; ".join(f"{t.name}(daemon={t.daemon})" for t in active_threads if not t.name.startswith("Timer"))
    timeout_str = f"{_LOADER_TIMEOUT_SECONDS // 60}m" if _LOADER_TIMEOUT_SECONDS else "N/A"
    logger.critical(
        f"[TIMEOUT] Loader exceeded {timeout_str} timeout. Exiting forcefully. Active threads: {thread_info}"
    )
    os._exit(1)


def setup_loader_timeout(loader_name: str, timeout_seconds: int) -> None:
    """Set up process-level timeout using signal.SIGALRM or threading.Timer.

    SESSION 111 FIX: Enforce timeout for in-process loader execution.
    This matches the timeout mechanism used in loaders/runner.py but adapted for
    orchestrator phases that call loaders sequentially.

    Args:
        loader_name: Name of loader for logging
        timeout_seconds: Timeout in seconds
    """
    global _LOADER_TIMEOUT_SECONDS, _TIMEOUT_TIMER

    _LOADER_TIMEOUT_SECONDS = timeout_seconds
    timeout_min = timeout_seconds // 60
    timeout_sec = timeout_seconds % 60

    if hasattr(signal, "SIGALRM"):
        # Unix-like systems: use SIGALRM
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout_seconds)
        logger.info(f"[TIMEOUT] {loader_name}: SIGALRM timeout set to {timeout_min}m {timeout_sec}s")
    else:
        # Windows fallback: use threading.Timer
        logger.warning(
            f"[TIMEOUT] {loader_name}: SIGALRM not available (Windows). "
            f"Using threading.Timer fallback for {timeout_min}m {timeout_sec}s"
        )
        _TIMEOUT_TIMER = threading.Timer(timeout_seconds, _force_exit_on_timeout)
        _TIMEOUT_TIMER.daemon = True
        _TIMEOUT_TIMER.start()


def cancel_loader_timeout() -> None:
    """Cancel any active timeout (SIGALRM or threading.Timer).

    Called after loader completes to prevent timeout from firing on unrelated code.
    """
    global _LOADER_TIMEOUT_SECONDS, _TIMEOUT_TIMER

    if hasattr(signal, "SIGALRM"):
        # Unix: cancel SIGALRM
        signal.alarm(0)

    if _TIMEOUT_TIMER is not None:
        # Windows: cancel threading.Timer
        _TIMEOUT_TIMER.cancel()
        _TIMEOUT_TIMER = None

    _LOADER_TIMEOUT_SECONDS = None


def is_timeout_error(error: Exception) -> bool:
    """Check if an exception is a timeout-related error.

    Args:
        error: Exception to check

    Returns:
        True if error is a timeout (RuntimeError from signal handler or TimeoutError)
    """
    if isinstance(error, RuntimeError) and "timeout" in str(error).lower():
        return True
    if isinstance(error, TimeoutError):
        return True
    # Check for concurrent.futures timeout
    if type(error).__name__ == "TimeoutError":
        return True
    return False
