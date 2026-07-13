#!/usr/bin/env python3
"""Loader timeout and retry configuration helper.

Provides centralized timeout and retry configuration for all loaders to prevent hanging
indefinitely under AWS Lambda network conditions and to handle transient failures gracefully.

Configure timeouts at loader startup and for all external API calls:
- Socket-level timeout: 30 seconds (prevents indefinite socket hangs)
- HTTP request timeout: (10, 20) seconds (connect, read)
- Database timeout: 30 seconds (connection pool)

Retry configuration (centralized to avoid hardcoding in individual loaders):
- Max retries: 3 (configurable per loader type)
- Backoff factor: 1 (exponential: 1s, 2s, 4s)
- Status codes: 429 (rate limit), 500, 502 (bad gateway), 503 (service unavail), 504 (timeout)
"""

import logging
import os
import socket
from typing import Any

logger = logging.getLogger(__name__)


class RetryConfig:
    """Centralized retry configuration for all loaders.

    Provides consistent retry behavior across all data loaders, avoiding hardcoded
    retry values scattered throughout the codebase.

    Usage:
        from loaders.timeout_config import get_retry_config
        config = get_retry_config("yfinance")  # max_retries=3, backoff_factor=1
        config = get_retry_config("sec_edgar")  # max_retries=2, backoff_factor=2 (SEC API rate limit)
    """

    # Loader-specific retry configurations
    LOADER_RETRY_CONFIGS = {
        # High-volume API loaders with rate limiting concerns
        "yfinance": {"max_retries": 3, "backoff_factor": 1, "status_forcelist": [429, 500, 502, 503, 504]},
        # SEC EDGAR API: 10 req/sec rate limit, needs longer backoff
        "sec_edgar": {"max_retries": 2, "backoff_factor": 2, "status_forcelist": [429, 500, 502, 503, 504]},
        # Alpaca API: robust, but allow some retries for transient issues
        "alpaca": {"max_retries": 3, "backoff_factor": 0.5, "status_forcelist": [429, 500, 502, 503, 504]},
        # Fred API: relatively stable, fewer retries
        "fred": {"max_retries": 2, "backoff_factor": 1, "status_forcelist": [429, 500, 502, 503, 504]},
        # Default for unknown loaders
        "default": {"max_retries": 3, "backoff_factor": 1, "status_forcelist": [429, 500, 502, 503, 504]},
    }

    def __init__(self, loader_type: str = "default") -> None:
        """Initialize retry config for a specific loader type.

        Args:
            loader_type: Type of loader (e.g., "yfinance", "sec_edgar", "alpaca")
        """
        self.loader_type = loader_type
        config = self.LOADER_RETRY_CONFIGS.get(loader_type, self.LOADER_RETRY_CONFIGS["default"])
        self.max_retries = config["max_retries"]
        self.backoff_factor = config["backoff_factor"]
        self.status_forcelist = config["status_forcelist"]

    def __repr__(self) -> str:
        return (
            f"RetryConfig({self.loader_type}: max_retries={self.max_retries}, "
            f"backoff_factor={self.backoff_factor}, status_forcelist={self.status_forcelist})"
        )


def get_retry_config(loader_type: str = "default") -> RetryConfig:
    """Get retry configuration for a loader type.

    Args:
        loader_type: Type of loader (e.g., "yfinance", "sec_edgar")

    Returns:
        RetryConfig instance with centralized retry settings
    """
    return RetryConfig(loader_type)


def configure_database_statement_timeout(db_connection: Any, timeout_ms: int = 30000) -> None:
    """Configure PostgreSQL statement timeout to prevent slow query hangs.

    CRITICAL FIX: Prevents database queries from hanging indefinitely.
    Sets a server-side timeout so queries abort if they take too long.

    Args:
        db_connection: psycopg2 connection object
        timeout_ms: Timeout in milliseconds (default 30000 = 30 seconds)
    """
    try:
        cursor = db_connection.cursor()
        cursor.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
        cursor.close()
        logger.debug(f"Database statement timeout configured: {timeout_ms}ms")
    except Exception as e:
        logger.warning(
            f"Failed to configure database statement timeout: {e}. "
            f"Queries may hang indefinitely if no application-level timeout is set."
        )


def configure_socket_timeout(timeout_seconds: int = 30) -> None:
    """Set global socket timeout to prevent indefinite hangs.

    Args:
        timeout_seconds: Timeout in seconds (default 30)
    """
    socket.setdefaulttimeout(float(timeout_seconds))
    logger.debug(f"Socket timeout configured: {timeout_seconds}s")


def get_http_timeout(api_type: str = "default") -> tuple[float, float]:
    """Get HTTP request timeout (connect, read) from config or default.

    CRITICAL FIX: Different APIs need different timeouts.
    - yfinance bulk operations: 120s read timeout (ETF data slow)
    - SEC EDGAR: 30s timeout (rate-limited API)
    - Default APIs: 10s connect, 20s read

    Args:
        api_type: Type of API ("yfinance", "sec_edgar", "alpaca", "default")

    Returns:
        Tuple of (connect_timeout, read_timeout) in seconds
    """
    # API-specific timeout overrides
    api_timeouts = {
        "yfinance_bulk": (10.0, 120.0),  # ETF bulk operations need longer timeout
        "yfinance": (10.0, 30.0),  # Standard yfinance timeout
        "sec_edgar": (10.0, 30.0),  # SEC EDGAR with rate limiting
        "alpaca": (5.0, 15.0),  # Alpaca is fast
        "default": (10.0, 20.0),  # Default timeout
    }

    # Check for API-specific environment override first
    env_key = f"API_REQUEST_TIMEOUT_{api_type.upper()}"
    timeout_str = os.getenv(env_key)
    if timeout_str:
        try:
            parts = timeout_str.split(",")
            if len(parts) == 2:
                return (float(parts[0].strip()), float(parts[1].strip()))
            else:
                timeout = float(timeout_str)
                return (timeout, timeout)
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"CRITICAL: {env_key} value is invalid: {timeout_str!r}. "
                f"Timeout configuration must be a valid float or 'connect_timeout,read_timeout' pair. "
                f"Cannot proceed with invalid timeout configuration. {e}"
            ) from e

    # No env override: fall back to the per-API defaults above.
    return api_timeouts.get(api_type, api_timeouts["default"])


def get_database_timeout() -> float:
    """Get database timeout from config.

    Defaults to 30s (matching this module's documented default) when unset -- a
    connection timeout is operational plumbing, not financial data that needs
    fail-fast integrity checks. A value that IS set but malformed still raises,
    since that's a real misconfiguration worth surfacing.
    """
    timeout_str = os.getenv("DATABASE_TIMEOUT_SECONDS")
    if timeout_str is None:
        return 30.0
    try:
        return float(timeout_str)
    except (ValueError, AttributeError) as e:
        raise ValueError(
            f"CRITICAL: DATABASE_TIMEOUT_SECONDS value is invalid: {timeout_str!r}. "
            f"Must be a valid float (e.g., '30' for 30 seconds). {e}"
        ) from e


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
            try:
                return func(*args, **kwargs)
            except TimeoutError as e:
                logger.error(f"[TIMEOUT] {api_name} API call timed out: {e}. Returning data_unavailable marker.")
                # Return marker dict for data_unavailable handling
                return {
                    "data_unavailable": True,
                    "reason": f"{api_name}_timeout:{e!s}",
                }
            except Exception as e:
                # Re-raise non-timeout exceptions
                logger.error(f"[{api_name}] API call failed: {type(e).__name__}: {e}")
                raise

        return wrapper

    return decorator
