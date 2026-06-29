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
    def check_api_error(response: dict[str, Any]) -> tuple[bool, str | None]:
        """Check if response indicates an API error.

        Returns:
            (is_error: bool, error_message: str|None)
        """
        if isinstance(response, dict) and "_error" in response:
            error_msg = response.get("_error", None)
            # Ensure error message is always a non-empty string, never None
            if not error_msg or not str(error_msg).strip():
                logger.warning("API error marker present but error message is empty or missing")
                return True, "Unknown API error"
            return True, str(error_msg)
        return False, None

    @staticmethod
    def require_fields(data: dict[str, Any], required_fields: list[str], source: str) -> tuple[bool, str | None]:
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
    def extract_field(data: dict[str, Any], field_path: str, required: bool = True) -> tuple[Any, str | None]:
        """Extract nested field from dict using dot notation.

        Example: extract_field(data, "portfolio.total_value")

        Returns:
            (value: Any, error_message: str|None)

        For optional fields (required=False), returns (None, None) when field is missing,
        but logs at DEBUG level to maintain visibility of data extraction patterns.
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
                # Optional field missing — log for visibility but return None with no error
                logger.debug(f"Optional field not present: {field_path}")
                return None, None
            current = current[part]

        if required and current is None:
            return None, f"Field {field_path} is None"
        if not required and current is None:
            logger.debug(f"Optional field is None: {field_path}")
        return current, None

    @staticmethod
    def build_error_response(error_message: str | None) -> dict[str, str]:
        """Build standardized error response dict.

        Returns:
            dict with _error key and message

        Ensures error message is always a non-empty string with actual details.
        Never returns silent empty dict {} or None — always includes explicit error context.

        Args:
            error_message: Error message to include, or None if no message available

        Returns:
            {"_error": "<message>"} — always includes detailed error text
        """
        if error_message is None:
            logger.error("build_error_response called with None message — no context provided")
            return {"_error": "Unknown error (no details provided)"}
        error_str = str(error_message).strip()
        if not error_str:
            logger.error("build_error_response called with empty message after strip")
            return {"_error": "Unknown error (empty error message)"}
        return {"_error": error_str}

    @staticmethod
    def validate_response(
        response: dict[str, Any],
        required_fields: list[str],
        source_name: str,
        max_age_seconds: int | None = None,
        timestamp_field: str | None = None,
    ) -> tuple[bool, str | None]:
        """Perform comprehensive validation on fetched response.

        Returns:
            (valid: bool, error_message: str|None)

        When freshness validation is enabled (max_age_seconds and timestamp_field specified),
        timestamp field MUST be present and valid — missing timestamp triggers freshness error.
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
            # Timestamp field must be explicitly present when freshness validation is enabled
            timestamp = response.get(timestamp_field, None)
            if timestamp is None:
                logger.warning(
                    f"{source_name}: Freshness validation enabled but timestamp field '{timestamp_field}' "
                    f"is missing or None (will be treated as stale)"
                )
            fresh, error_msg = FetcherValidator.check_freshness(timestamp, max_age_seconds)
            if not fresh:
                return False, error_msg

        return True, None
