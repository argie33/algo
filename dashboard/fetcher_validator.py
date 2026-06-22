#!/usr/bin/env python3
"""Fail-fast validation for dashboard API responses.

Centralizes validation logic across all fetchers to:
- Fail immediately on missing required fields (no .get() fallbacks)
- Validate data freshness
- Check API error responses
- Ensure consistent error reporting
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class FetcherValidator:
    """Validates dashboard API responses with fail-fast pattern.

    Replaces scattered .get() calls and silent fallbacks with explicit validation
    that surfaces data issues immediately in the error panel.
    """

    @staticmethod
    def check_api_error(response: dict) -> tuple[bool, str | None]:
        """Check if response indicates an API error.

        Returns:
            (is_error: bool, error_message: str|None)
        """
        if isinstance(response, dict) and "_error" in response:
            return True, response.get("_error", "Unknown API error")
        return False, None

    @staticmethod
    def require_fields(data: dict, required_fields: list[str], source: str) -> tuple[bool, str | None]:
        """Validate that all required fields exist with non-None values.

        Returns:
            (valid: bool, error_message: str|None)
        """
        if not isinstance(data, dict):
            return False, f"{source}: Expected dict, got {type(data).__name__}"

        missing = [f for f in required_fields if f not in data or data[f] is None]
        if missing:
            return False, f"{source}: Missing required fields {missing}"
        return True, None

    @staticmethod
    def check_freshness(timestamp: datetime | None, max_age_seconds: int) -> tuple[bool, str | None]:
        """Validate that data is not stale.

        Returns:
            (fresh: bool, error_message: str|None)
        """
        if timestamp is None:
            return False, "Data timestamp is missing"

        if not isinstance(timestamp, datetime):
            try:
                timestamp = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return False, f"Invalid timestamp format: {timestamp}"

        # Make naive datetimes timezone-aware (assume UTC) to avoid TypeError
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - timestamp
        if age.total_seconds() > max_age_seconds:
            return (
                False,
                f"Data is stale ({age.total_seconds():.0f}s old, max {max_age_seconds}s)",
            )
        return True, None

    @staticmethod
    def validate_numeric(
        value: Any,
        field_name: str,
        min_val: float | None = None,
        max_val: float | None = None,
    ) -> tuple[bool, str | None]:
        """Validate numeric field is in acceptable range.

        Returns:
            (valid: bool, error_message: str|None)
        """
        if value is None:
            return False, f"{field_name}: Value is None"

        try:
            num = float(value)
        except (TypeError, ValueError):
            return False, f"{field_name}: Cannot convert to numeric ({value})"

        if min_val is not None and num < min_val:
            return False, f"{field_name}: {num} < minimum {min_val}"
        if max_val is not None and num > max_val:
            return False, f"{field_name}: {num} > maximum {max_val}"
        return True, None

    @staticmethod
    def extract_field(data: dict, field_path: str, required: bool = True) -> tuple[Any, str | None]:
        """Extract nested field from dict using dot notation.

        Example: extract_field(data, "portfolio.total_value")

        Returns:
            (value: Any, error_message: str|None)
        """
        if not isinstance(data, dict):
            return None, f"Expected dict, got {type(data).__name__}"

        parts = field_path.split(".")
        current = data

        for part in parts:
            if not isinstance(current, dict):
                return None, f"Cannot navigate through {part}: not a dict"
            if part not in current:
                if required:
                    return None, f"Missing required field: {field_path}"
                return None, None
            current = current[part]

        if required and current is None:
            return None, f"Field {field_path} is None"
        return current, None

    @staticmethod
    def build_error_response(error_message: str) -> dict[str, str]:
        """Build standardized error response dict.

        Returns:
            dict with _error key and message
        """
        return {"_error": error_message}

    @staticmethod
    def validate_response(
        response: dict,
        required_fields: list[str],
        source_name: str,
        max_age_seconds: int | None = None,
        timestamp_field: str | None = None,
    ) -> tuple[bool, str | None]:
        """Perform comprehensive validation on fetched response.

        Returns:
            (valid: bool, error_message: str|None)
        """
        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(response)
        if is_error:
            return False, error_msg

        # Check required fields
        valid, error_msg = FetcherValidator.require_fields(response, required_fields, source_name)
        if not valid:
            return False, error_msg

        # Check freshness if specified
        if max_age_seconds is not None and timestamp_field:
            timestamp = response.get(timestamp_field)
            fresh, error_msg = FetcherValidator.check_freshness(timestamp, max_age_seconds)
            if not fresh:
                return False, error_msg

        return True, None
