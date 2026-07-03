"""API Hardening Utilities - Fail-fast validation for critical endpoints.

This module provides hardening utilities for API routes that consume data
from loaders and dashboard components. It ensures:
1. Critical data is validated before use
2. Missing data is reported with proper HTTP status codes
3. Dashboard consumers can distinguish retryable vs permanent failures
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_response_has_no_errors(response: dict[str, Any], endpoint: str) -> bool:
    """Check if API response contains error markers.

    Args:
        response: Response dict from a loader or data provider
        endpoint: Name of the endpoint for logging

    Returns:
        True if response has no errors, False if _error field is present
    """
    if isinstance(response, dict) and "_error" in response:
        logger.error(f"[API_HARDENING] {endpoint} returned error: {response.get('_error')}")
        return False
    return True


def validate_dashboard_data(
    data: dict[str, Any],
    required_fields: list[str],
    endpoint: str,
) -> tuple[bool, str | None]:
    """Validate dashboard data has required fields and no error markers.

    Args:
        data: Dashboard data dict
        required_fields: Fields that must be present (not None)
        endpoint: Name of endpoint for logging

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid=True: Data is valid
        - is_valid=False: error_message explains what's missing/wrong
    """
    # Check for error marker (highest priority)
    if isinstance(data, dict) and "_error" in data:
        error_msg = data.get("_error", "Unknown error")
        logger.error(f"[API_HARDENING] {endpoint} has error marker: {error_msg}")
        return False, error_msg

    # Check for data_unavailable marker
    if isinstance(data, dict) and data.get("data_unavailable"):
        reason = data.get("reason", "Unknown")
        logger.warning(f"[API_HARDENING] {endpoint} data unavailable: {reason}")
        return False, f"Data unavailable: {reason}"

    # Check for required fields
    if not isinstance(data, dict):
        error_msg = f"Invalid data type: {type(data).__name__}"
        logger.error(f"[API_HARDENING] {endpoint}: {error_msg}")
        return False, error_msg

    missing_fields = [f for f in required_fields if data.get(f) is None]
    if missing_fields:
        error_msg = f"Missing required fields: {', '.join(missing_fields)}"
        logger.error(f"[API_HARDENING] {endpoint}: {error_msg}")
        return False, error_msg

    return True, None


def ensure_critical_data(response: dict[str, Any], field: str) -> dict[str, Any]:
    """Ensure critical field is present and not marked unavailable.

    Args:
        response: Response dict containing the field
        field: Field name that must be present

    Returns:
        The critical field value

    Raises:
        ValueError: If field is missing or marked unavailable
    """
    if not isinstance(response, dict):
        raise ValueError(f"Response is not a dict: {type(response).__name__}")

    # Check for error marker
    if "_error" in response:
        raise ValueError(f"Response contains error: {response.get('_error')}")

    # Check for data_unavailable marker
    if response.get("data_unavailable"):
        reason = response.get("reason", "Unknown")
        raise ValueError(f"Critical field '{field}' unavailable: {reason}")

    # Check field exists and is not None
    if field not in response or response[field] is None:
        raise ValueError(f"Required field '{field}' is missing or None")

    return response[field]


def check_data_error(data: Any, context: str = "") -> str | None:
    """Check if data contains error markers and return error message.

    Args:
        data: Data to check
        context: Context string for logging

    Returns:
        Error message if data contains error markers, None if data is valid
    """
    if not isinstance(data, dict):
        return None

    # Check for error marker
    if "_error" in data:
        error_msg = data.get("_error", "Unknown error")
        logger.warning(f"[HARDENING] {context} error: {error_msg}")
        return error_msg

    # Check for data_unavailable marker
    if data.get("data_unavailable"):
        reason = data.get("reason", "Unknown")
        error_msg = f"Data unavailable: {reason}"
        logger.warning(f"[HARDENING] {context}: {error_msg}")
        return error_msg

    return None


def is_critical_data_missing(data: Any) -> bool:
    """Check if data is marked as unavailable or contains errors.

    Args:
        data: Data to check

    Returns:
        True if data is marked unavailable or has errors, False if data is valid
    """
    if not isinstance(data, dict):
        return False

    # Either error marker or data_unavailable flag means critical data is missing
    return "_error" in data or data.get("data_unavailable", False)
