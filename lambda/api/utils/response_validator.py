"""API Response Validation - Fail-fast patterns for consumers.

This module ensures API routes validate that critical data is available
before returning responses. When critical data contains 'data_unavailable'
markers, the API fails fast with a proper error response.
"""

import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class DataUnavailableError(Exception):
    """Raised when critical data is marked as unavailable."""

    def __init__(self, field: str, reason: str | None = None):
        self.field = field
        self.reason = reason
        message = f"Critical data unavailable: {field}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class ValidationResult(TypedDict):
    """Result of data validation."""

    valid: bool
    error_code: str | None
    error_message: str | None
    http_status: int


def validate_critical_data(data: dict[str, Any], field_name: str) -> ValidationResult:
    """Validate that critical data is not marked as unavailable.

    Args:
        data: Data dict to validate
        field_name: Name of the critical field being validated

    Returns:
        ValidationResult with valid=True if data is present and available,
        or valid=False with error details if data_unavailable marker is present.

    Raises:
        DataUnavailableError: If critical data is marked unavailable (for fail-fast)
    """
    if not isinstance(data, dict):
        return {
            "valid": False,
            "error_code": "invalid_data_type",
            "error_message": f"{field_name} returned invalid type: {type(data).__name__}",
            "http_status": 500,
        }

    # Check for error marker first (highest priority)
    if "_error" in data:
        error_msg = data.get("_error", "Unknown error")
        logger.error(f"[HARDENING] {field_name} returned error: {error_msg}")
        return {
            "valid": False,
            "error_code": "upstream_error",
            "error_message": f"{field_name} unavailable: {error_msg}",
            "http_status": 503,
        }

    # Check for data_unavailable marker (indicates fetch/compute failure)
    if data.get("data_unavailable"):
        reason = data.get("reason", "Unknown")
        logger.warning(f"[HARDENING] {field_name} marked unavailable: {reason}")
        raise DataUnavailableError(field_name, reason)

    # Data is present and valid
    return {
        "valid": True,
        "error_code": None,
        "error_message": None,
        "http_status": 200,
    }


def validate_required_fields(
    data: dict[str, Any], required_fields: list[str], context: str
) -> ValidationResult:
    """Validate that all required fields are present and not None.

    Args:
        data: Data dict to validate
        required_fields: List of field names that must be present and not None
        context: Context string for error messages

    Returns:
        ValidationResult with details about missing fields
    """
    missing_fields = [field for field in required_fields if data.get(field) is None]

    if missing_fields:
        error_msg = f"{context}: missing required fields: {', '.join(missing_fields)}"
        logger.error(f"[HARDENING] {error_msg}")
        return {
            "valid": False,
            "error_code": "missing_required_fields",
            "error_message": error_msg,
            "http_status": 409,
        }

    return {
        "valid": True,
        "error_code": None,
        "error_message": None,
        "http_status": 200,
    }


def get_safe_value(data: dict[str, Any], key: str, default: Any = None) -> Any:
    """Get value from data dict, handling data_unavailable markers.

    Args:
        data: Data dict to get value from
        key: Key to retrieve
        default: Default value if key is missing or value is None

    Returns:
        The value, or default if missing/None, or None if data_unavailable
    """
    if isinstance(data, dict) and data.get("data_unavailable"):
        return None

    value = data.get(key) if isinstance(data, dict) else None
    return value if value is not None else default
