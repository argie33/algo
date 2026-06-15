"""API Response Validator - validates responses against contract schemas.

Ensures both API responses and dashboard data conform to the shared contract.
This prevents schema drift and catches breaking changes early.
"""

import logging
from typing import Dict, Any, Tuple, Optional

from .dashboard_api_contract import DASHBOARD_ENDPOINTS

logger = logging.getLogger(__name__)

class ResponseValidationError(Exception):
    """Raised when response doesn't match schema."""

class ResponseValidator:
    """Validate API responses against contract schemas."""

    @staticmethod
    def validate_endpoint_response(
        endpoint_name: str, response: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate that a response matches its endpoint's schema.

        Args:
            endpoint_name: Name of endpoint (e.g., 'run', 'mkt', 'port')
            response: API response dict to validate

        Returns:
            (is_valid, error_message) tuple
            - (True, None) if valid
            - (False, error_msg) if invalid
        """
        if endpoint_name not in DASHBOARD_ENDPOINTS:
            return False, f"Unknown endpoint: {endpoint_name}"

        endpoint = DASHBOARD_ENDPOINTS[endpoint_name]
        schema = endpoint.get("response_schema")

        if not schema or not isinstance(response, dict):
            return False, f"Invalid response type for {endpoint_name}"

        # Check required fields
        missing_required = []
        for field in schema.required_fields:
            if field not in response:
                missing_required.append(field)

        if missing_required:
            return (
                False,
                f"Missing required fields in {endpoint_name}: {missing_required}",
            )

        # Check strict fields (must not be None)
        strict_fields = endpoint.get("strict_fields", [])
        none_strict_fields = []
        for field in strict_fields:
            if field in response and response[field] is None:
                none_strict_fields.append(field)

        if none_strict_fields:
            return (
                False,
                f"Strict fields cannot be None in {endpoint_name}: {none_strict_fields}",
            )

        # Validate field types
        field_types = schema.field_types
        type_mismatches = []
        for field, expected_type in field_types.items():
            if field in response and response[field] is not None:
                value = response[field]
                # Handle tuple of types (e.g., (float, int))
                valid_types = (
                    expected_type
                    if isinstance(expected_type, tuple)
                    else (expected_type,)
                )
                if not isinstance(value, valid_types):
                    type_mismatches.append(
                        f"{field}: expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}, got {type(value).__name__}"
                    )

        if type_mismatches:
            return (
                False,
                f"Type validation failed in {endpoint_name}: {type_mismatches}",
            )

        return True, None

    @staticmethod
    def validate_batch_responses(
        responses: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Tuple[bool, Optional[str]]]:
        """Validate multiple endpoint responses.

        Args:
            responses: Dict of {endpoint_name: response_data}

        Returns:
            Dict of {endpoint_name: (is_valid, error_msg)}
        """
        results = {}
        for endpoint_name, response_data in responses.items():
            is_valid, error_msg = ResponseValidator.validate_endpoint_response(
                endpoint_name, response_data
            )
            results[endpoint_name] = (is_valid, error_msg)
        return results

    @staticmethod
    def report_validation_errors(
        validation_results: Dict[str, Tuple[bool, Optional[str]]],
    ) -> str:
        """Generate a formatted error report from validation results.

        Args:
            validation_results: Dict from validate_batch_responses()

        Returns:
            Formatted error report string
        """
        errors = [
            f"  {name}: {error_msg}"
            for name, (is_valid, error_msg) in validation_results.items()
            if not is_valid
        ]

        if not errors:
            return ""

        report = "Response Validation Errors:\n" + "\n".join(errors)
        return report

    @staticmethod
    def sanitize_response(
        response: Dict[str, Any], remove_none: bool = True
    ) -> Dict[str, Any]:
        """Remove None values and empty structures from response (API Issue #14 FIX).

        Args:
            response: Response dict to sanitize
            remove_none: If True, removes all None values recursively

        Returns:
            Sanitized response dict
        """
        if not isinstance(response, dict):
            return response

        if not remove_none:
            return response

        sanitized = {}
        for key, value in response.items():
            if value is None:
                continue
            if isinstance(value, dict):
                sanitized[key] = ResponseValidator.sanitize_response(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    (
                        ResponseValidator.sanitize_response(item)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                    if item is not None
                ]
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def validate_and_sanitize(
        endpoint_name: str, response: Dict[str, Any], strict: bool = True
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Validate response and return sanitized version.

        Args:
            endpoint_name: Name of endpoint
            response: Response to validate and sanitize
            strict: If True, raise exception on validation error

        Returns:
            (is_valid, error_msg, sanitized_response) tuple
        """
        is_valid, error_msg = ResponseValidator.validate_endpoint_response(
            endpoint_name, response
        )

        if not is_valid:
            if strict:
                raise ResponseValidationError(
                    f"Validation failed for {endpoint_name}: {error_msg}"
                )
            logger.warning(f"Validation failed for {endpoint_name}: {error_msg}")

        sanitized = ResponseValidator.sanitize_response(response)
        return is_valid, error_msg, sanitized
