"""Shared response validation framework - base class for all validators."""

from __future__ import annotations

from typing import Any

from .framework import safe_float, safe_int


class ResponseValidationError(Exception):
    """Raised when API response is missing critical fields or fails validation."""


class DataUnavailableError(Exception):
    """Raised when critical data is marked as unavailable."""

    def __init__(self, field: str, reason: str | None = None):
        self.field = field
        self.reason = reason
        message = f"Critical data unavailable: {field}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class BaseResponseValidator:
    """Shared validation logic for all response validators."""

    @staticmethod
    def has_error(data: dict[str, Any]) -> bool:
        """Check if response contains error marker."""
        return isinstance(data, dict) and "_error" in data

    @staticmethod
    def has_data_unavailable(data: dict[str, Any], field: str) -> bool:
        """Check if specific field is marked unavailable."""
        if not isinstance(data, dict):
            return False
        field_data = data.get(field)
        if isinstance(field_data, dict):
            return field_data.get("data_unavailable") is True
        return False

    @staticmethod
    def check_required_fields(
        data: dict[str, Any], required_fields: list[str], source: str = "response"
    ) -> None:
        """Validate required fields are present and non-None.

        Raises ResponseValidationError if any required field is missing/None.
        """
        if not isinstance(data, dict):
            raise ResponseValidationError(f"Expected dict, got {type(data).__name__}")

        missing = [f for f in required_fields if f not in data or data[f] is None]
        if missing:
            raise ResponseValidationError(f"Missing critical fields in {source}: {missing}")

    @staticmethod
    def validate_type(value: Any, expected_type: type, field_name: str) -> None:
        """Validate single value matches expected type."""
        if expected_type is int:
            safe_int(value, field_name, strict=True)
        elif expected_type is float:
            safe_float(value, field_name, strict=True)
        elif not isinstance(value, expected_type):
            raise ResponseValidationError(
                f"Field '{field_name}' must be {expected_type.__name__}, got {type(value).__name__}"
            )

    @staticmethod
    def validate_numeric_fields(
        data: dict[str, Any], numeric_fields: dict[str, type], source: str = "response"
    ) -> None:
        """Validate numeric fields are correct type and convertible."""
        for field, field_type in numeric_fields.items():
            if field not in data:
                continue
            try:
                BaseResponseValidator.validate_type(data[field], field_type, field)
            except (ValueError, ResponseValidationError) as e:
                raise ResponseValidationError(f"{source} field '{field}': {e}") from e

    @staticmethod
    def sanitize_response(data: dict[str, Any] | None, remove_none: bool = True) -> dict[str, Any]:
        """Remove None values and clean up response for display.

        Args:
            data: Response dict to sanitize
            remove_none: If True, recursively remove None values

        Returns:
            Cleaned response dict
        """
        if not isinstance(data, dict):
            return {}

        if not remove_none:
            return data

        return {
            key: (
                BaseResponseValidator.sanitize_response(val, remove_none=True)
                if isinstance(val, dict)
                else [BaseResponseValidator.sanitize_response(item, remove_none=True) for item in val]
                if isinstance(val, list)
                else val
            )
            for key, val in data.items()
            if val is not None
        }
