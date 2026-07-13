"""Dashboard API Response Validator — validates inbound responses at dashboard boundary.

This is the CANONICAL validator for dashboard data integrity. It provides 15+ specialized
validators for critical endpoints (Portfolio, Performance, Markets, etc.) that use a
fail-fast approach with StrictValidationError to prevent silent data corruption.

IMPORTANT: This is NOT used by Lambda API routes. Lambda uses shared_contracts/response_validator.py
for validating outbound responses against the contract schema.

Separation of concerns:
- Dashboard validator (this file): Validates INBOUND API responses with fail-fast patterns
- Lambda validator (shared_contracts/response_validator.py): Validates OUTBOUND responses against contract

Integration:
- Uses safe_float()/safe_int() from utils.safe_data_conversion for type conversion (consolidated from dashboard)
- Uses error_boundary utilities for error detection
- Raises ResponseValidationError for critical validation failures

FAIL-FAST GOVERNANCE: Never returns empty collections as fallback. Missing required fields
raise ResponseValidationError instead of silently defaulting to empty arrays.
"""

import logging
from typing import Any, Callable

from utils.validation.framework import StrictValidationError, safe_float, safe_int

from .error_boundary import has_error

logger = logging.getLogger(__name__)


class ResponseValidationError(Exception):
    """Raised when API response is missing critical fields."""


def _check_required_fields(data: dict[str, Any], required_fields: list[str], source: str) -> None:
    """Check if data has all required fields; raise error if any missing."""
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        raise ResponseValidationError(f"Missing critical fields in {source}: {missing}")


def _make_validator(
    required_fields: list[str] | None = None,
    numeric_fields: dict[str, type] | None = None,
    item_validators: list[Callable[[Any], None]] | None = None,
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
        raise ResponseValidationError(
            f"Items field must be list, got {type(data[item_key])}"
        )
    return data[item_key]


def _validate_position(i: int, pos: Any) -> None:
    """Validate a single position object."""
    if not isinstance(pos, dict):
        raise ResponseValidationError(f"Position {i} is not a dict: {type(pos)}")
    if "symbol" not in pos:
        raise ResponseValidationError(f"Position {i} missing critical field: symbol")


def _validate_signal(i: int, sig: Any) -> None:
    """Validate a single signal object."""
    if not isinstance(sig, dict):
        raise ResponseValidationError(f"Signal {i} is not a dict: {type(sig)}")
    if "symbol" not in sig:
        raise ResponseValidationError(f"Signal {i} missing critical field: symbol")


def _validate_portfolio(data: dict[str, Any]) -> dict[str, Any]:
    """Validate portfolio endpoint response."""
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
    """Validate performance endpoint response."""
    if has_error(data):
        return data
    if "n" in data:
        return _make_validator(
            required_fields=["n", "w", "l", "streak"],
            numeric_fields={"n": int, "w": int, "l": int, "streak": int},
        )(data)
    return data


def _validate_positions(data: dict[str, Any]) -> dict[str, Any]:
    """Validate positions endpoint response."""
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
    """Validate config endpoint response."""
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Config response not a dict: {type(data)}")
    if has_error(data):
        return data

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
    """Validate health endpoint response."""
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Health response not a dict: {type(data)}")
    if has_error(data):
        return data
    if not data:
        raise ResponseValidationError("Health response is empty dict")
    return data


def _validate_markets(data: dict[str, Any]) -> dict[str, Any]:
    """Validate markets endpoint response."""
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Markets response not a dict: {type(data)}")
    if has_error(data):
        return data
    if not data or all(k.startswith("_") for k in data.keys()):
        raise ResponseValidationError("Markets response is empty or contains only metadata")
    return data


# Factory-created validators
validate_portfolio_response = _make_validator()
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


# Mapping of endpoints to their validators
# Keep updating this as new endpoints are added to ensure validation coverage
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
    # Generic fallback for unregistered endpoints
}


def validate_response(endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validate API response using endpoint-specific validator.

    Args:
        endpoint: API endpoint path
        data: Response data dict

    Returns:
        Validated data (pass-through if valid)

    Raises:
        ResponseValidationError: If validation fails
    """
    validator = VALIDATORS.get(endpoint)
    if validator:
        return validator(data)
    # No validator defined; use generic validator as fallback
    logger.debug(f"No specific validator for {endpoint}, using generic validation")
    return validate_generic_response(data)
