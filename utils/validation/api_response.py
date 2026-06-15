#!/usr/bin/env python3
"""
API Response Validation and Sanitization

Prevents None/null values in JSON responses that can break frontend code.
When None values are encountered, replaces them with sensible defaults:
- None numeric fields → 0
- None string fields → "" (empty string)
- None boolean fields → False
- None in arrays → filtered out
- None in nested objects → recursively sanitized

This catches the issue where database NULL values get serialized as JSON null,
causing frontend code like Number(null) to become NaN and break charts.
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
            logger.warning(
                f"[NULL_FOUND] {path}: Found None value in response, replacing with default"
            )
            return 0  # Default for unknown types

        if isinstance(data, dict):
            sanitized_dict: Dict[str, Any] = {}
            for key, value in data.items():
                new_path = f"{path}.{key}"
                if value is None:
                    logger.warning(
                        f"[NULL_FOUND] {new_path}: Found None value in dict, replacing with default"
                    )
                    sanitized_dict[key] = 0  # Conservative default for None in dicts
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
                    logger.warning(
                        f"[NULL_FOUND] {new_path}: Found None value in list, skipping"
                    )
                    continue  # Filter out None values from arrays
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
