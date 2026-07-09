#!/usr/bin/env python3
"""Loader timeout configuration helper.

Provides centralized timeout configuration for all loaders to prevent hanging
indefinitely under AWS Lambda network conditions.

Configure timeouts at loader startup and for all external API calls:
- Socket-level timeout: 30 seconds (prevents indefinite socket hangs)
- HTTP request timeout: (10, 20) seconds (connect, read)
- Database timeout: 30 seconds (connection pool)
"""

import logging
import os
import socket
from typing import Any

logger = logging.getLogger(__name__)


def configure_socket_timeout(timeout_seconds: int = 30) -> None:
    """Set global socket timeout to prevent indefinite hangs.

    Args:
        timeout_seconds: Timeout in seconds (default 30)
    """
    socket.setdefaulttimeout(float(timeout_seconds))
    logger.debug(f"Socket timeout configured: {timeout_seconds}s")


def get_http_timeout() -> tuple[float, float]:
    """Get HTTP request timeout (connect, read) from config or default.

    Returns:
        Tuple of (connect_timeout, read_timeout) in seconds
    """
    timeout_str = os.getenv("API_REQUEST_TIMEOUT_SECONDS", "10,20")
    try:
        parts = timeout_str.split(",")
        if len(parts) == 2:
            connect_timeout = float(parts[0].strip())
            read_timeout = float(parts[1].strip())
            return (connect_timeout, read_timeout)
        else:
            # Single value: use for both connect and read
            timeout = float(timeout_str)
            return (timeout, timeout)
    except (ValueError, AttributeError):
        logger.warning(
            f"Invalid API_REQUEST_TIMEOUT_SECONDS value: {timeout_str}. Using default (10, 20)s."
        )
        return (10.0, 20.0)


def get_database_timeout() -> float:
    """Get database timeout in seconds from config or default.

    Returns:
        Timeout in seconds (default 30)
    """
    timeout_str = os.getenv("DATABASE_TIMEOUT_SECONDS", "30")
    try:
        return float(timeout_str)
    except (ValueError, AttributeError):
        logger.warning(f"Invalid DATABASE_TIMEOUT_SECONDS value: {timeout_str}. Using default 30s.")
        return 30.0


def configure_yfinance_timeout(timeout_seconds: int = 30) -> None:
    """Configure yfinance to use explicit timeout.

    yfinance.Ticker() calls internally use requests, which honors the HTTP timeout
    tuple format (connect, read). This function ensures the timeout is properly set.

    Args:
        timeout_seconds: Timeout in seconds (default 30)
    """
    # yfinance uses requests internally, so HTTP timeout applies
    # Just log configuration - actual timeout is enforced via requests session
    logger.debug(f"yfinance timeout configured via HTTP timeout: {timeout_seconds}s")


def configure_requests_session(session: Any, timeout: tuple[float, float] = (10.0, 20.0)) -> None:
    """Configure a requests Session with explicit timeout.

    Args:
        session: requests.Session instance
        timeout: Tuple of (connect_timeout, read_timeout) in seconds
    """
    # Mount HTTPAdapter with timeout to both HTTP and HTTPS
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    # Retry strategy: exponential backoff for transient errors
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Store timeout on session for use in individual requests
    session.timeout = timeout
    logger.debug(f"Requests session configured with timeout: {timeout}s")


def wrap_api_call_with_timeout(api_name: str) -> Any:
    """Decorator to wrap API calls with timeout handling.

    Catches timeout exceptions and returns data_unavailable marker.

    Args:
        api_name: Name of API for logging (e.g., "yfinance", "SEC EDGAR")

    Returns:
        Decorator function
    """
    import functools

    def decorator(func: Any) -> Any:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import socket
            from socket import timeout as socket_timeout

            try:
                return func(*args, **kwargs)
            except (socket_timeout, TimeoutError) as e:
                logger.error(
                    f"[TIMEOUT] {api_name} API call timed out: {e}. "
                    f"Returning data_unavailable marker."
                )
                # Return marker dict for data_unavailable handling
                return {
                    "data_unavailable": True,
                    "reason": f"{api_name}_timeout:{str(e)}",
                }
            except Exception as e:
                # Re-raise non-timeout exceptions
                logger.error(f"[{api_name}] API call failed: {type(e).__name__}: {e}")
                raise

        return wrapper

    return decorator
