#!/usr/bin/env python3
"""
API Response Validation and Sanitization

Sanitizes API response data:
- None dict values → preserved as None (JSON null) - nullable fields are valid
- None list items → filtered out (null array elements cause frontend iteration bugs)
- Nested structures → recursively processed
"""

import logging
from typing import Any, overload

logger = logging.getLogger(__name__)


class APIResponseValidator:
    @staticmethod
    @overload
    def sanitize_response(data: dict[str, Any], path: str = "root") -> dict[str, Any]: ...

    @staticmethod
    @overload
    def sanitize_response(data: list[Any], path: str = "root") -> list[Any]: ...

    @staticmethod
    @overload
    def sanitize_response(data: None, path: str = "root") -> None: ...

    @staticmethod
    def sanitize_response(data: Any, path: str = "root") -> Any:
        """Recursively sanitize response data, filtering nulls from lists while preserving them in dicts.

        CRITICAL CHANGE: Now logs when array items are filtered (None values removed).
        This prevents silent data loss where None tuples are removed without indication.

        Args:
            data: Response data to sanitize (dict, list, scalar, or None)
            path: Current path in the data structure (for logging)

        Returns:
            Sanitized data with None items filtered from lists, None values preserved in dicts
        """
        if data is None:
            return None

        if isinstance(data, dict):
            sanitized_dict: dict[str, Any] = {}
            for key, value in data.items():
                new_path = f"{path}.{key}"
                sanitized_dict[key] = APIResponseValidator.sanitize_response(value, new_path)
            return sanitized_dict

        elif isinstance(data, list):
            sanitized_list: list[Any] = []
            filtered_count = 0
            for i, item in enumerate(data):
                new_path = f"{path}[{i}]"
                if item is None:
                    filtered_count += 1
                    continue  # Filter out None items from arrays
                sanitized_list.append(APIResponseValidator.sanitize_response(item, new_path))

            # GOVERNANCE: Log when data is silently filtered so operators see completeness issues
            if filtered_count > 0:
                logger.warning(
                    f"[DATA_INCOMPLETE] Array at {path} had {filtered_count} None items filtered out. "
                    f"Original length: {len(data)}, After filtering: {len(sanitized_list)}. "
                    f"Consider marking response as data_unavailable if filtering indicates missing upstream data."
                )

            return sanitized_list

        else:
            # Scalar value (string, number, bool, etc.)
            return data

    @staticmethod
    def validate_no_nulls(data: Any, path: str = "root") -> list[str]:
        """Validate that response contains no None values.

        Recursively checks data structure and returns list of paths where None was found.
        This is used for logging/auditing, not for sanitization.

        Args:
            data: Response data to validate
            path: Current path in the data structure

        Returns:
            List of paths where None values were found (empty list if all valid)
        """
        nulls = []

        if data is None:
            return [path]

        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}"
                nulls.extend(APIResponseValidator.validate_no_nulls(value, new_path))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                new_path = f"{path}[{i}]"
                nulls.extend(APIResponseValidator.validate_no_nulls(item, new_path))

        return nulls

    @staticmethod
    def log_null_findings(data: Any, operation: str = "API response") -> None:
        """Log all None/null values found in response for debugging.

        Args:
            data: Response data to check
            operation: Name of operation for context in logs
        """
        nulls = APIResponseValidator.validate_no_nulls(data)
        if nulls:
            logger.warning(f"[NULL_VALUES_DETECTED] {operation}: Found {len(nulls)} None values at: {', '.join(nulls)}")

    @staticmethod
    def validate_critical_response(data: Any, operation: str = "API response") -> None:
        """Validate response for critical endpoints. Raises if nulls detected.

        Critical endpoints must have complete data - validation failures are fatal.
        Use this instead of log_null_findings() for user-facing or trading endpoints.

        Args:
            data: Response data to check
            operation: Name of operation for context in error message

        Raises:
            ValueError: If any None values detected in response
        """
        nulls = APIResponseValidator.validate_no_nulls(data)
        if nulls:
            error_msg = f"[VALIDATION_FAILED] {operation}: Found {len(nulls)} None values at: {', '.join(nulls)}. Cannot continue with invalid data."
            logger.critical(error_msg)
            raise ValueError(error_msg)
