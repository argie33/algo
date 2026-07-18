#!/usr/bin/env python3
"""Standardized exception handling for loaders.

Provides consistent error classification and data_unavailable marker creation
across all loaders. Distinguishes between:

1. TRANSIENT ERRORS (retryable):
   - TimeoutError, socket.timeout → timeout_retryable
   - ConnectionError, requests.ConnectionError → connection_error
   - HTTPError 429, 503 → rate_limit_or_service_unavailable

2. PERMANENT DATA ISSUES (non-retryable):
   - KeyError, missing fields → api_schema_mismatch
   - ValueError, type mismatches → data_invalid
   - No results found → no_data_found

3. UNEXPECTED ERRORS:
   - All other exceptions → propagated with logging (fail-fast)

Usage:
    try:
        data = fetch_data(symbol)
    except TimeoutError as e:
        return [handle_timeout_error(symbol, e)]
    except KeyError as e:
        return [handle_schema_error(symbol, e)]
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
        raise  # Fail-fast for unknown issues
"""

import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# TRANSIENT ERROR HANDLERS (retryable, try again later)
# ============================================================================


def handle_timeout_error(symbol: str, error: Exception, context: str = "") -> dict[str, Any]:
    """Handle timeout errors (transient, retryable).

    Args:
        symbol: Stock ticker symbol
        error: The TimeoutError or socket.timeout exception
        context: Optional context description (e.g., "fetching company facts")

    Returns:
        data_unavailable marker with reason="timeout_retryable"
    """
    error_msg = f"{type(error).__name__}: {str(error)[:100]}"
    if context:
        logger.warning(f"[{symbol}] Transient timeout {context}: {error_msg}")
    else:
        logger.warning(f"[{symbol}] Transient timeout: {error_msg}")

    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": "timeout_retryable",
        "reason_type": "temporary",
    }


def handle_connection_error(symbol: str, error: Exception, context: str = "") -> dict[str, Any]:
    """Handle connection errors (transient, retryable).

    Args:
        symbol: Stock ticker symbol
        error: The ConnectionError or network-related exception
        context: Optional context description

    Returns:
        data_unavailable marker with reason="connection_error"
    """
    error_msg = f"{type(error).__name__}: {str(error)[:100]}"
    if context:
        logger.warning(f"[{symbol}] Connection error {context}: {error_msg}")
    else:
        logger.warning(f"[{symbol}] Connection error: {error_msg}")

    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": "connection_error",
        "reason_type": "temporary",
    }


def handle_rate_limit_error(symbol: str, error: Exception, context: str = "") -> dict[str, Any]:
    """Handle rate limit or service unavailable errors (transient, retryable).

    Args:
        symbol: Stock ticker symbol
        error: The HTTPError or rate limit exception
        context: Optional context description

    Returns:
        data_unavailable marker with reason="rate_limit_or_service_unavailable"
    """
    error_msg = f"{type(error).__name__}: {str(error)[:100]}"
    if context:
        logger.warning(f"[{symbol}] Rate limit/service unavailable {context}: {error_msg}")
    else:
        logger.warning(f"[{symbol}] Rate limit/service unavailable: {error_msg}")

    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": "rate_limit_or_service_unavailable",
        "reason_type": "temporary",
    }


# ============================================================================
# PERMANENT DATA ISSUE HANDLERS (non-retryable)
# ============================================================================


def handle_schema_mismatch(symbol: str, error: Exception, context: str = "") -> dict[str, Any]:
    """Handle API schema changes or missing fields (permanent).

    Args:
        symbol: Stock ticker symbol
        error: The KeyError or schema-related exception
        context: Optional context description (e.g., "SEC API missing 'facts' key")

    Returns:
        data_unavailable marker with reason="api_schema_mismatch"
    """
    error_msg = f"{type(error).__name__}: {str(error)[:100]}"
    if context:
        logger.error(f"[{symbol}] API schema mismatch {context}: {error_msg}")
    else:
        logger.error(f"[{symbol}] API schema mismatch: {error_msg}")

    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": "api_schema_mismatch",
        "reason_type": "loader_failed",
    }


def handle_invalid_data(symbol: str, error: Exception, context: str = "") -> dict[str, Any]:
    """Handle invalid data or type conversion errors (permanent).

    Args:
        symbol: Stock ticker symbol
        error: The ValueError or type error exception
        context: Optional context description (e.g., "invalid share count")

    Returns:
        data_unavailable marker with reason="data_invalid"
    """
    error_msg = f"{type(error).__name__}: {str(error)[:100]}"
    if context:
        logger.error(f"[{symbol}] Invalid data {context}: {error_msg}")
    else:
        logger.error(f"[{symbol}] Invalid data: {error_msg}")

    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": "data_invalid",
        "reason_type": "loader_failed",
    }


def handle_no_data_found(symbol: str, context: str = "") -> dict[str, Any]:
    """Handle case where no data found (permanent for that period).

    Args:
        symbol: Stock ticker symbol
        context: Optional context description (e.g., "no recent filings found")

    Returns:
        data_unavailable marker with reason="no_data_found"
    """
    if context:
        logger.info(f"[{symbol}] No data found: {context}")
    else:
        logger.info(f"[{symbol}] No data found")

    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": "no_data_found",
        "reason_type": "temporary",
    }


def handle_resource_not_found(symbol: str, resource: str, context: str = "") -> dict[str, Any]:
    """Handle case where a required resource doesn't exist (404s, missing CIK, etc.).

    Args:
        symbol: Stock ticker symbol
        resource: What resource was not found (e.g., "CIK", "submissions")
        context: Optional context description

    Returns:
        data_unavailable marker with reason="{resource}_not_found"
    """
    reason = f"{resource.lower()}_not_found"
    if context:
        logger.warning(f"[{symbol}] {resource} not found: {context}")
    else:
        logger.warning(f"[{symbol}] {resource} not found")

    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": reason,
        "reason_type": "loader_failed",
    }


# ============================================================================
# EXCEPTION CLASSIFICATION & ROUTING
# ============================================================================


def classify_exception(error: Exception) -> str:
    """Classify an exception to determine handling strategy.

    Returns:
        One of: "transient_timeout", "transient_connection", "transient_rate_limit",
                "permanent_schema", "permanent_invalid_data", "unexpected"
    """
    error_type = type(error)
    error_name = error_type.__name__

    # TRANSIENT: Timeout errors
    if error_type is TimeoutError or error_name == "Timeout":
        return "transient_timeout"
    if error_type is socket.timeout:
        return "transient_timeout"

    # TRANSIENT: Connection errors
    if error_type is ConnectionError:
        return "transient_connection"
    if error_name in ("ConnectionError", "ConnectTimeout", "HTTPConnectionError"):
        return "transient_connection"

    # TRANSIENT: Rate limit / service unavailable
    if error_name in ("HTTPError", "TooManyRequests", "ServiceUnavailable"):
        return "transient_rate_limit"

    # PERMANENT: Schema mismatches (API changed)
    if error_type is KeyError:
        return "permanent_schema"

    # PERMANENT: Invalid data or type errors
    if error_type is ValueError or error_name in ("TypeError", "ValidationError"):
        return "permanent_invalid_data"
    if error_name.endswith("Error") and "parse" in error_name.lower():
        return "permanent_invalid_data"

    # UNEXPECTED: Everything else should be propagated
    return "unexpected"


def handle_exception(symbol: str, error: Exception, context: str = "") -> dict[str, Any] | None:
    """Route exception to appropriate handler based on classification.

    Returns:
        data_unavailable marker if exception is known/retryable
        None if exception should be propagated (unexpected)

    Raises:
        The original exception if it's unexpected and should fail-fast
    """
    classification = classify_exception(error)

    if classification == "transient_timeout":
        return handle_timeout_error(symbol, error, context)
    elif classification == "transient_connection":
        return handle_connection_error(symbol, error, context)
    elif classification == "transient_rate_limit":
        return handle_rate_limit_error(symbol, error, context)
    elif classification == "permanent_schema":
        return handle_schema_mismatch(symbol, error, context)
    elif classification == "permanent_invalid_data":
        return handle_invalid_data(symbol, error, context)
    elif classification == "unexpected":
        # Fail-fast: log and re-raise unexpected errors
        logger.critical(
            f"[{symbol}] Unexpected error ({type(error).__name__}): {str(error)[:200]} {context}",
            exc_info=True,
        )
        raise
    else:
        # Defensive: should never reach here, but fail-fast if we do
        logger.critical(
            f"[{symbol}] Unknown exception classification: {classification} {type(error).__name__}",
            exc_info=True,
        )
        raise
