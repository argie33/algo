#!/usr/bin/env python3
"""Response validation helpers for Phase 3 hardening.

Provides explicit validation patterns for API/dashboard responses to replace
silent .get() patterns with fail-fast error handling.

Enforces governance: No silent fallbacks, all missing data must be explicit.
"""

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def get_required_field(data: dict[str, Any], field: str, field_type: type | None = None) -> Any:
    """Extract required field from dict with explicit validation.

    Raises RuntimeError if field missing or None. Replaces unsafe .get(field) patterns.

    Args:
        data: Dictionary to extract from
        field: Field name (required)
        field_type: Expected type for validation (optional)

    Returns:
        Field value (guaranteed non-None)

    Raises:
        RuntimeError: If field missing, None, or wrong type
    """
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Cannot extract '{field}' from non-dict data. "
            f"Expected dict, got {type(data).__name__}. Data structure corruption detected."
        )

    if field not in data:
        raise RuntimeError(
            f"Required field '{field}' missing from response data. "
            f"Available fields: {list(data.keys())}. "
            f"Response validation failed — incomplete data structure."
        )

    value = data[field]
    if value is None:
        raise RuntimeError(
            f"Required field '{field}' is NULL/None in response. "
            f"Cannot proceed without valid value. Check upstream data source."
        )

    if field_type is not None and not isinstance(value, field_type):
        raise RuntimeError(
            f"Field '{field}' type mismatch: expected {field_type.__name__}, "
            f"got {type(value).__name__} (value: {value!r}). Data structure corrupted."
        )

    return value


def get_optional_field(
    data: dict[str, Any] | None, field: str, default: Any = None, field_type: type | None = None
) -> Any:
    """Extract optional field from dict with explicit validation.

    Returns None or default if field missing/None. Use only for truly optional fields.
    Replaces .get(field, default) for optional enrichment data.

    Args:
        data: Dictionary to extract from (can be None)
        field: Field name
        default: Default value if field missing/None
        field_type: Expected type for validation (optional)

    Returns:
        Field value, default, or None

    Raises:
        RuntimeError: If field exists but wrong type (optional fields must still be valid type if present)
    """
    if not isinstance(data, dict):
        return default

    value = data.get(field)
    if value is None:
        return default

    if field_type is not None and not isinstance(value, field_type):
        raise RuntimeError(
            f"Optional field '{field}' type mismatch: expected {field_type.__name__}, "
            f"got {type(value).__name__} (value: {value!r}). If field is present, type must be valid."
        )

    return value


def get_field_safe(
    data: dict[str, Any] | None, field: str, required: bool = True, default: T | None = None
) -> T | None:
    """Safe field extraction with explicit control over required vs optional behavior.

    Args:
        data: Dictionary to extract from (can be None)
        field: Field name
        required: If True, raise error if missing; if False, return default
        default: Value to return if optional and missing

    Returns:
        Field value or default

    Raises:
        RuntimeError: If required=True and field missing/None
    """
    if data is None:
        if required:
            raise RuntimeError("Cannot extract field from None data dict (data structure is None)")
        return default

    if not isinstance(data, dict):
        if required:
            raise RuntimeError(f"Expected dict, got {type(data).__name__}")
        return default

    value = data.get(field)

    if value is None and required:
        raise RuntimeError(
            f"Required field '{field}' missing or None. "
            f"Available fields: {list(data.keys())}. "
            f"Cannot proceed without value."
        )

    return value if value is not None else default


def validate_response_structure(
    data: dict[str, Any], required_fields: list[str], optional_fields: list[str] | None = None
) -> dict[str, bool]:
    """Validate response has required structure before using.

    Returns dict of field → present status. Raises if any required field missing.

    Args:
        data: Response data to validate
        required_fields: Fields that must be present and non-None
        optional_fields: Fields that may be missing or None

    Returns:
        {"field": bool} indicating presence of each field

    Raises:
        RuntimeError: If any required field missing/None
    """
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected dict response, got {type(data).__name__}")

    status = {}

    for field in required_fields:
        if field not in data:
            raise RuntimeError(f"Required field '{field}' missing from response")
        if data[field] is None:
            raise RuntimeError(f"Required field '{field}' is None in response")
        status[field] = True

    if optional_fields:
        for field in optional_fields:
            status[field] = field in data and data[field] is not None

    return status


def ensure_field_present(data: dict[str, Any], field: str, validator: Callable[[Any], bool] | None = None) -> bool:
    """Check that field is present and optionally valid.

    Raises RuntimeError if validation fails.

    Args:
        data: Dictionary to check
        field: Field name
        validator: Optional validation function (should return True if valid)

    Returns:
        True if field present and valid

    Raises:
        RuntimeError: If field missing, None, or validation fails
    """
    if field not in data:
        raise RuntimeError(f"Field '{field}' missing from data")

    if data[field] is None:
        raise RuntimeError(f"Field '{field}' is None")

    if validator is not None and not validator(data[field]):
        raise RuntimeError(f"Field '{field}' failed validation: {data[field]!r}")

    return True
