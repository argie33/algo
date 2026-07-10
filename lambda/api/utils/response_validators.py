"""Unified Response Validation - consolidates all validation patterns.

This module combines three separate validator modules into one:
- response_schema_validator.py (runtime schema validation)
- response_validator.py (fail-fast data_unavailable checking)
- shared_contracts/response_validator.py (contract validation)

All response validation now goes through this single service.
"""

from __future__ import annotations

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


class ResponseValidationError(Exception):
    """Raised when response doesn't match schema."""


class ValidationResult(TypedDict):
    """Result of data validation."""

    valid: bool
    error_code: str | None
    error_message: str | None
    http_status: int


class ResponseValidator:
    """Unified response validator combining all validation patterns."""

    # Runtime schemas for quick validation
    SCHEMAS = {
        "market/status": {
            "required": ["date", "market_trend", "market_stage", "vix_level"],
            "types": {"date": str, "vix_level": float, "market_stage": int},
        },
        "portfolio": {
            "required": ["value", "cash", "positions", "unrealized_pnl"],
            "types": {"value": float, "cash": float, "positions": int},
        },
    }

    @staticmethod
    def validate_schema(endpoint: str, data: dict[str, Any]) -> tuple[bool, str]:
        """Validate response against runtime schema (fast path).

        Args:
            endpoint: Endpoint name (e.g. "market/status", "portfolio")
            data: Response data to validate

        Returns:
            (is_valid, error_message) tuple
        """
        schema = ResponseValidator.SCHEMAS.get(endpoint)
        if not schema:
            return True, ""  # No schema defined, skip validation

        required = schema.get("required")
        if required is None:
            raise ValueError(f"Schema for endpoint '{endpoint}' missing 'required' field")

        if not isinstance(required, list):
            raise ValueError(f"Schema 'required' field must be a list, got {type(required).__name__}")

        missing = set(required) - set(data.keys())
        if missing:
            return False, f"Missing fields: {missing}"

        return True, ""

    @staticmethod
    def validate_critical_data(data: dict[str, Any], field_name: str) -> ValidationResult:
        """Validate that critical data is not marked as unavailable (fail-fast).

        Args:
            data: Data dict to validate
            field_name: Name of the critical field being validated

        Returns:
            ValidationResult with validation status and error details

        Raises:
            DataUnavailableError: If critical data is marked unavailable
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
            logger.error(f"[VALIDATION] {field_name} returned error: {error_msg}")
            return {
                "valid": False,
                "error_code": "upstream_error",
                "error_message": f"{field_name} unavailable: {error_msg}",
                "http_status": 503,
            }

        # Check for data_unavailable marker (indicates fetch/compute failure)
        if data.get("data_unavailable"):
            reason = data.get("reason", "Unknown")
            logger.warning(f"[VALIDATION] {field_name} marked unavailable: {reason}")
            raise DataUnavailableError(field_name, reason)

        # Data is present and valid
        return {
            "valid": True,
            "error_code": None,
            "error_message": None,
            "http_status": 200,
        }

    @staticmethod
    def validate_required_fields(data: dict[str, Any], required_fields: list[str], context: str) -> ValidationResult:
        """Validate that all required fields are present and not None.

        Args:
            data: Data dict to validate
            required_fields: List of field names that must be present and not None
            context: Context string for error messages

        Returns:
            ValidationResult with details about missing/invalid fields
        """
        missing_fields = [field for field in required_fields if data.get(field) is None]

        if missing_fields:
            error_msg = f"{context}: missing required fields: {', '.join(missing_fields)}"
            logger.error(f"[VALIDATION] {error_msg}")
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

    @staticmethod
    def validate_contract_response(
        endpoint_name: str, response: dict[str, Any], contract_schemas: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate response against dashboard API contract schema.

        Args:
            endpoint_name: Name of endpoint (e.g., 'run', 'mkt', 'port')
            response: API response dict to validate
            contract_schemas: Dict of endpoint contracts (from DASHBOARD_ENDPOINTS)

        Returns:
            (is_valid, error_message) tuple
        """
        if endpoint_name not in contract_schemas:
            return False, f"Unknown endpoint: {endpoint_name}"

        endpoint = contract_schemas[endpoint_name]
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
                valid_types = expected_type if isinstance(expected_type, tuple) else (expected_type,)
                if not isinstance(value, valid_types):
                    type_mismatches.append(
                        f"{field}: expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}, "
                        f"got {type(value).__name__}"
                    )

        if type_mismatches:
            return (
                False,
                f"Type validation failed in {endpoint_name}: {type_mismatches}",
            )

        # Check for extra fields not in schema (log warning but don't fail validation)
        # Extra fields are expected during development/debugging and shouldn't block responses
        # This prevents strict schema validation from rejecting valid responses that add extra fields
        allowed_fields = set(schema.required_fields) | set(schema.optional_fields)
        extra_fields = set(response.keys()) - allowed_fields
        if extra_fields:
            # Log as info level (not error) since extra fields are common and expected
            logger.info(
                f"Response for {endpoint_name} has extra fields not in schema: {sorted(extra_fields)}. "
                f"These will be included in the response but are not validated."
            )

        return True, None

    @staticmethod
    def sanitize_response(response: dict[str, Any], remove_none: bool = True) -> dict[str, Any]:
        """Remove None values and empty structures from response.

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

        sanitized: dict[str, Any] = {}
        for key, value in response.items():
            if value is None:
                continue
            if isinstance(value, dict):
                sanitized[key] = ResponseValidator.sanitize_response(value, remove_none)
            elif isinstance(value, list):
                sanitized[key] = [
                    (ResponseValidator.sanitize_response(item, remove_none) if isinstance(item, dict) else item)
                    for item in value
                    if item is not None
                ]
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def validate_endpoint_response(endpoint_name: str, response_data: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate API response against dashboard API contract schema.

        This is the primary validation method called by all Lambda routes to verify
        responses match the DASHBOARD_ENDPOINTS contract before returning to dashboard.

        Args:
            endpoint_name: Short endpoint code (e.g., 'run', 'mkt', 'port') from contract
            response_data: Response dict to validate (the 'data' field in JSON response)

        Returns:
            (is_valid, error_message) tuple - error_message is None if valid
        """
        try:
            from shared_contracts.dashboard_api_contract import DASHBOARD_ENDPOINTS

            return ResponseValidator.validate_contract_response(endpoint_name, response_data, DASHBOARD_ENDPOINTS)
        except ImportError as e:
            logger.error(f"[VALIDATION] Could not import DASHBOARD_ENDPOINTS: {e}")
            return False, f"Validation unavailable: {e}"
        except Exception as e:
            logger.error(f"[VALIDATION] Unexpected error validating {endpoint_name}: {type(e).__name__}: {e}")
            return False, f"Validation error: {type(e).__name__}: {str(e)[:100]}"

    @staticmethod
    def validate_and_sanitize(
        endpoint_name: str, response: dict[str, Any], strict: bool = True
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Validate response and return sanitized version.

        Args:
            endpoint_name: Name of endpoint
            response: Response to validate and sanitize
            strict: If True, raise exception on validation error

        Returns:
            (is_valid, error_msg, sanitized_response) tuple
        """
        # Try schema validation first (fast path)
        is_valid, error_msg = ResponseValidator.validate_schema(endpoint_name, response)

        if not is_valid:
            if strict:
                raise ResponseValidationError(f"Validation failed for {endpoint_name}: {error_msg}")
            logger.warning(f"Validation failed for {endpoint_name}: {error_msg}")

        sanitized = ResponseValidator.sanitize_response(response)
        return is_valid, error_msg, sanitized
