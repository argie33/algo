"""Consolidated Response Validators — unified validation for all API responses.

This module consolidates dashboard and Lambda response validators into a single
canonical implementation using a factory pattern with endpoint-specific validators.

GOVERNANCE:
- All API responses are validated at intake boundaries (Dashboard, Lambda routes)
- Fail-fast approach: Missing/invalid required fields raise ResponseValidationError
- No silent fallbacks to empty collections — explicit data_unavailable flags required
- Error responses (containing _error field) pass through without validation

VALIDATION PATTERNS:
1. Dashboard mode: Validates inbound responses from backend API
2. Lambda mode: Validates outbound responses against contract schema
3. Both: Support error handling, data unavailability checking, and sanitization
"""

from __future__ import annotations

import logging
from typing import Any, Callable, TypedDict

from .framework import StrictValidationError, safe_float, safe_int

logger = logging.getLogger(__name__)


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


class ValidationResult(TypedDict):
    """Result of data validation."""

    valid: bool
    error_code: str | None
    error_message: str | None
    http_status: int


def has_error(data: dict[str, Any]) -> bool:
    """Check if response contains error marker.

    Returns True if data has _error field, indicating upstream error.
    """
    return isinstance(data, dict) and "_error" in data


def _check_required_fields(data: dict[str, Any], required_fields: list[str], source: str) -> None:
    """Validate required fields are present and non-None.

    Raises ResponseValidationError if any required field is missing/None.
    """
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        raise ResponseValidationError(f"Missing critical fields in {source}: {missing}")


def _make_validator(
    required_fields: list[str] | None = None,
    numeric_fields: dict[str, type] | None = None,
    item_validators: list[Callable[[Any, Any], None]] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Factory function to create response validators with common patterns.

    Args:
        required_fields: Fields that must be present in response
        numeric_fields: Map of field names to their expected types (int or float)
        item_validators: List of validation functions for array items

    Returns:
        Validator function that takes data dict and returns validated data
    """

    def validator(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ResponseValidationError(f"Response not a dict: {type(data)}")

        # Pass through error responses without validation
        if has_error(data):
            return data

        if required_fields:
            _check_required_fields(data, required_fields, "response")

        if numeric_fields:
            for field, field_type in numeric_fields.items():
                if field in data and data[field] is not None:
                    try:
                        if field_type is int:
                            safe_int(data[field], strict=True, field_name=field)
                        else:
                            safe_float(data[field], strict=True, field_name=field)
                    except StrictValidationError as e:
                        raise ResponseValidationError(f"Field {field} validation failed: {e}") from e

        if item_validators:
            if "items" in data and isinstance(data["items"], list):
                for i, item in enumerate(data["items"]):
                    for item_validator in item_validators:
                        item_validator(i, item)

        return data

    return validator


def _validate_items_structure(data: dict[str, Any], item_key: str = "items") -> list[Any]:
    """Validate and return items array.

    FAIL-FAST: Raises ResponseValidationError if items field missing or wrong type.
    Never returns empty list as fallback - requires explicit 'items' field.
    """
    if item_key not in data:
        raise ResponseValidationError(
            f"Response missing required '{item_key}' field. "
            f"API structure may have changed or response is incomplete."
        )
    if not isinstance(data[item_key], list):
        raise ResponseValidationError(f"Items field must be list, got {type(data[item_key])}")
    return data[item_key]


def _validate_position(i: int, pos: Any) -> None:
    if not isinstance(pos, dict):
        raise ResponseValidationError(f"Position {i} is not a dict: {type(pos)}")
    if "symbol" not in pos:
        raise ResponseValidationError(f"Position {i} missing critical field: symbol")


def _validate_signal(i: int, sig: Any) -> None:
    if not isinstance(sig, dict):
        raise ResponseValidationError(f"Signal {i} is not a dict: {type(sig)}")
    if "symbol" not in sig:
        raise ResponseValidationError(f"Signal {i} missing critical field: symbol")


def _validate_portfolio(data: dict[str, Any]) -> dict[str, Any]:
    required_keys = ["total_portfolio_value", "total_cash", "position_count"]
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        raise ResponseValidationError(f"Missing critical fields in portfolio: {missing_keys}")
    numeric_fields = {
        "total_portfolio_value": float,
        "total_cash": float,
        "position_count": int,
    }
    return _make_validator(numeric_fields=numeric_fields)(data)


def _validate_performance(data: dict[str, Any]) -> dict[str, Any]:
    if has_error(data):
        return data
    if "n" in data:
        return _make_validator(
            required_fields=["n", "w", "l", "streak"],
            numeric_fields={"n": int, "w": int, "l": int, "streak": int},
        )(data)
    return data


def _validate_positions(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Positions response not a dict: {type(data)}")
    if has_error(data):
        return data
    if "items" in data:
        if not isinstance(data["items"], list):
            raise ResponseValidationError(
                f"Positions items field must be list, got {type(data['items'])}"
            )
        items = data["items"]
        if items is None:
            raise ResponseValidationError("Positions response 'items' field is None")
        for i, pos in enumerate(items):
            _validate_position(i, pos)
    return data


def _validate_config(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Config response not a dict: {type(data)}")
    if has_error(data):
        return data

    # Flatten items array into dict if present
    if "items" in data and isinstance(data["items"], list):
        flat = {i["key"]: i.get("value") for i in data["items"] if isinstance(i, dict) and "key" in i}
        data = {**data, **flat}

    required_fields = [
        "min_signal_quality_score",
        "min_completeness_score",
        "min_volume_ma_50d",
        "min_avg_daily_dollar_volume",
        "earnings_blackout_days_before",
        "earnings_blackout_days_after",
    ]
    _check_required_fields(data, required_fields, "config")

    field_types = {
        "min_signal_quality_score": int,
        "min_completeness_score": int,
        "min_volume_ma_50d": int,
        "min_avg_daily_dollar_volume": float,
        "earnings_blackout_days_before": int,
        "earnings_blackout_days_after": int,
    }

    for field, expected_type in field_types.items():
        if field in data and data[field] is not None:
            try:
                if expected_type is int:
                    safe_int(data[field], strict=True, field_name=field)
                else:
                    safe_float(data[field], strict=True, field_name=field)
            except StrictValidationError as e:
                raise ResponseValidationError(f"Config field {field} validation failed: {e}") from e
    return data


def _validate_health(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Health response not a dict: {type(data)}")
    if has_error(data):
        return data
    if not data:
        raise ResponseValidationError("Health response is empty dict")
    return data


def _validate_markets(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Markets response not a dict: {type(data)}")
    if has_error(data):
        return data
    if not data or all(k.startswith("_") for k in data.keys()):
        raise ResponseValidationError("Markets response is empty or contains only metadata")
    return data


# Factory-created validators for common response types
validate_portfolio_response = _validate_portfolio
validate_performance_response = _validate_performance
validate_positions_response = _validate_positions
validate_signals_response = _make_validator()
validate_risk_response = _make_validator(
    numeric_fields={"var95": float, "cvar95": float, "beta": float, "conc5": float, "svar": float}
)
validate_market_data_response = _make_validator()
validate_health_response = _validate_health
validate_last_run_response = _make_validator(required_fields=["run_id"])
validate_trades_response = _make_validator()
validate_markets_response = _validate_markets
validate_dashboard_signals_response = _make_validator()
validate_circuit_breakers_response = _make_validator()
validate_sector_rotation_response = _make_validator()
validate_generic_response = _make_validator()
validate_config_response = _validate_config


# Endpoint to validator mapping for quick lookup
VALIDATORS = {
    # Critical endpoints (used for position sizing, risk mgmt)
    "/api/algo/portfolio": validate_portfolio_response,
    "/api/algo/performance": validate_performance_response,
    "/api/algo/markets": validate_markets_response,
    "/api/algo/last-run": validate_last_run_response,
    "/api/algo/risk-metrics": validate_risk_response,
    "/api/algo/data-status": validate_health_response,
    # Core dashboard endpoints
    "/api/algo/positions": validate_positions_response,
    "/api/algo/trades": validate_trades_response,
    "/api/algo/dashboard-signals": validate_dashboard_signals_response,
    "/api/algo/config": validate_config_response,
    # Support endpoints
    "/api/algo/circuit-breakers": validate_circuit_breakers_response,
    "/api/algo/sector-rotation": validate_sector_rotation_response,
    # Legacy endpoint paths (for backwards compatibility)
    "/api/algo/risk": validate_risk_response,
    "/api/algo/market": validate_market_data_response,
    "/api/algo/signals": validate_signals_response,
}


def validate_response(endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validate API response using endpoint-specific validator.

    Looks up validator from VALIDATORS mapping and applies it. Falls back
    to generic validator for unregistered endpoints.

    Args:
        endpoint: API endpoint path (e.g., "/api/algo/portfolio")
        data: Response data dict to validate

    Returns:
        Validated data dict (unchanged if validation passes)

    Raises:
        ResponseValidationError: If validation fails
    """
    validator = VALIDATORS.get(endpoint)
    if validator:
        return validator(data)
    # No specific validator defined; use generic validator as fallback
    logger.debug(f"No specific validator for {endpoint}, using generic validation")
    return validate_generic_response(data)


class ResponseValidator:
    """Unified response validator with static methods for advanced validation patterns.

    Supports:
    - Schema validation (quick type checks)
    - Critical data validation (error detection)
    - Required field validation
    - Contract validation (against schema definitions)
    - Response sanitization
    """

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
        """Quick schema validation for known endpoints.

        Args:
            endpoint: Endpoint identifier
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
        """Validate critical data markers (errors and unavailability).

        Checks for _error and data_unavailable fields. Returns ValidationResult
        with appropriate HTTP status codes.

        Args:
            data: Response data to validate
            field_name: Name of field for error reporting

        Returns:
            ValidationResult dict with valid, error_code, error_message, http_status
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
        """Validate required fields are present and non-None.

        Args:
            data: Response data to validate
            required_fields: List of field names that must be present
            context: Context string for error messages

        Returns:
            ValidationResult dict
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
        """Validate response against contract schema.

        Checks required fields, strict fields, and type validation.

        Args:
            endpoint_name: Endpoint identifier
            response: Response data to validate
            contract_schemas: Schema definitions mapping endpoints to schemas

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

        # Check for extra fields not in schema (log warning but don't fail)
        allowed_fields = set(schema.required_fields) | set(schema.optional_fields)
        extra_fields = set(response.keys()) - allowed_fields
        if extra_fields:
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

        This is the primary validation method for Lambda routes to verify
        responses match the DASHBOARD_ENDPOINTS contract before returning to dashboard.

        Args:
            endpoint_name: Short endpoint code (e.g., 'run', 'mkt', 'port')
            response_data: Response dict to validate (the 'data' field)

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
        """Combined validation and sanitization.

        Validates schema first (fast path), then sanitizes response.

        Args:
            endpoint_name: Endpoint identifier
            response: Response data to validate
            strict: If True, raise on validation failure; if False, log warning

        Returns:
            (is_valid, error_message, sanitized_response) tuple
        """
        # Try schema validation first (fast path)
        is_valid, error_msg = ResponseValidator.validate_schema(endpoint_name, response)

        if not is_valid:
            if strict:
                raise ResponseValidationError(f"Validation failed for {endpoint_name}: {error_msg}")
            logger.warning(f"Validation failed for {endpoint_name}: {error_msg}")

        sanitized = ResponseValidator.sanitize_response(response)
        return is_valid, error_msg, sanitized
