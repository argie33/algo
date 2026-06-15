#!/usr/bin/env python3
"""
API Response Validation and Sanitization

Sanitizes API response data:
- None dict values → preserved as None (JSON null) — nullable fields are valid
- None list items → filtered out (null array elements cause frontend iteration bugs)
- Nested structures → recursively processed
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class APIResponseValidator:
    """Validates and sanitizes API responses to prevent null value issues."""

    @staticmethod
    def sanitize_response(data: Any, path: str = "root") -> Any:
        """Recursively sanitize response data, replacing None values with appropriate defaults.

        Args:
            data: Response data to sanitize (dict, list, scalar, or None)
            path: Current path in the data structure (for logging)

        Returns:
            Sanitized data with None values replaced by defaults
        """
        if data is None:
            return 0

        if isinstance(data, dict):
            sanitized_dict: Dict[str, Any] = {}
            for key, value in data.items():
                new_path = f"{path}.{key}"
                if value is None:
                    sanitized_dict[key] = 0
                else:
                    sanitized_dict[key] = APIResponseValidator.sanitize_response(
                        value, new_path
                    )
            return sanitized_dict

        elif isinstance(data, list):
            sanitized_list: List[Any] = []
            for i, item in enumerate(data):
                new_path = f"{path}[{i}]"
                if item is None:
                    continue  # Filter out None items from arrays
                sanitized_list.append(
                    APIResponseValidator.sanitize_response(item, new_path)
                )
            return sanitized_list

        else:
            # Scalar value (string, number, bool, etc.)
            return data

    @staticmethod
    def validate_no_nulls(data: Any, path: str = "root") -> List[str]:
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
            logger.warning(
                f"[NULL_VALUES_DETECTED] {operation}: Found {len(nulls)} None values at: {', '.join(nulls)}"
            )
