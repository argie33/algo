"""Safe dictionary access utilities - Enforce fail-fast on missing required fields.

Replaces unsafe .get() patterns with explicit validation.

FAIL-FAST PRINCIPLE: Financial data must never silently become None or default values.
Missing required fields must raise exceptions for explicit error handling.
"""

from typing import Any, TypeVar

T = TypeVar("T")


class SafeDictAccessError(Exception):
    """Raised when required dict field is missing or wrong type."""


def safe_get(data: dict[str, Any], key: str, required: bool = False, field_name: str | None = None) -> Any:
    """Safely access dict field with explicit error handling (no silent defaults).

    Args:
        data: Dictionary to access
        key: Key to retrieve
        required: If True, raise error if key missing (for critical financial data)
        field_name: For error messages (context about what field this is)

    Returns:
        Value at key, or None if optional and missing

    Raises:
        SafeDictAccessError: If required field is missing or data is not a dict
    """
    if not isinstance(data, dict):
        raise SafeDictAccessError(f"Cannot access field {key}: data is not a dict (got {type(data).__name__})")

    if key not in data:
        if required:
            context = f" ({field_name})" if field_name else ""
            raise SafeDictAccessError(f"Required field missing: {key}{context}")
        return None

    return data[key]


def safe_get_int(data: dict[str, Any], key: str, required: bool = False, field_name: str | None = None) -> int | None:
    """Safely get int field with type validation.

    Args:
        data: Dictionary to access
        key: Key to retrieve
        required: If True, raise error if key missing or value is not int
        field_name: For error messages

    Returns:
        Integer value, or None if optional and missing

    Raises:
        SafeDictAccessError: If field missing/wrong type and required
    """
    value = safe_get(data, key, required=required, field_name=field_name)
    if value is None:
        return None
    if not isinstance(value, int):
        context = f" ({field_name})" if field_name else ""
        raise SafeDictAccessError(f"Field {key}{context} must be int, got {type(value).__name__}: {value}")
    return value


def safe_get_float(
    data: dict[str, Any], key: str, required: bool = False, field_name: str | None = None
) -> float | None:
    """Safely get float field with type validation.

    Args:
        data: Dictionary to access
        key: Key to retrieve
        required: If True, raise error if key missing or value is not numeric
        field_name: For error messages

    Returns:
        Float value, or None if optional and missing

    Raises:
        SafeDictAccessError: If field missing/wrong type and required
    """
    value = safe_get(data, key, required=required, field_name=field_name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        context = f" ({field_name})" if field_name else ""
        raise SafeDictAccessError(f"Field {key}{context} must be numeric, got {type(value).__name__}: {value}") from e


def safe_get_str(data: dict[str, Any], key: str, required: bool = False, field_name: str | None = None) -> str | None:
    """Safely get string field with type validation.

    Args:
        data: Dictionary to access
        key: Key to retrieve
        required: If True, raise error if key missing or value is not str
        field_name: For error messages

    Returns:
        String value, or None if optional and missing

    Raises:
        SafeDictAccessError: If field missing/wrong type and required
    """
    value = safe_get(data, key, required=required, field_name=field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        context = f" ({field_name})" if field_name else ""
        raise SafeDictAccessError(f"Field {key}{context} must be str, got {type(value).__name__}: {value}")
    return value
