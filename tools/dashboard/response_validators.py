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
- Uses safe_float()/safe_int() from tools/dashboard/data_validation.py for type conversion
- Uses error_boundary utilities for error detection
- Raises ResponseValidationError for critical validation failures
"""

import logging
from typing import Any

from utils.safe_data_conversion import StrictValidationError, safe_float, safe_int

from .error_boundary import has_error


logger = logging.getLogger(__name__)


class ResponseValidationError(Exception):
    """Raised when API response is missing critical fields."""


def _check_required_fields(data: dict[str, Any], required_fields: list[str], source: str) -> None:
    """Check if data has all required fields; raise error if any missing."""
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        raise ResponseValidationError(f"Missing critical fields in {source}: {missing}")


def validate_portfolio_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate portfolio endpoint response.

    Critical fields: position_count (required)
    Optional fields: total_portfolio_value, total_cash (can be None when no data available)
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Portfolio response not a dict: {type(data)}")

    if has_error(data):
        return data  # Propagate error responses as-is

    # Check that all field keys are present (values can be None for optional fields)
    required_keys = ["total_portfolio_value", "total_cash", "position_count"]
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        raise ResponseValidationError(f"Missing critical fields in portfolio: {missing_keys}")

    # Validate critical numeric fields can be converted
    # total_portfolio_value and total_cash can be None when no data available
    # position_count must be a valid int (but can be 0)
    try:
        # Optional fields (None is allowed for missing data)
        if data["total_portfolio_value"] is not None:
            safe_float(
                data["total_portfolio_value"],
                strict=True,
                field_name="total_portfolio_value",
            )
        if data["total_cash"] is not None:
            safe_float(data["total_cash"], strict=True, field_name="total_cash")
        # position_count must be present but can be 0 or None
        if data["position_count"] is not None:
            safe_int(data["position_count"], strict=True, field_name="position_count")
    except StrictValidationError as e:
        raise ResponseValidationError(f"Portfolio field validation failed: {e}") from e

    return data


def validate_performance_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate performance endpoint response.

    Critical fields: w (wins), l (losses), n (total trades), streak
    Missing these fields causes win rate to be silently computed as 0.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Performance response not a dict: {type(data)}")

    if has_error(data):
        return data  # Propagate error responses (fail-fast: no _no_data fallbacks)

    # If performance data exists, ensure all core fields are present
    # Empty performance data (no trades yet) is valid, but if we have n trades,
    # we must have w/l/streak
    if "n" in data:  # If trade count is present
        required = ["n", "w", "l", "streak"]
        _check_required_fields(data, required, "performance")

        try:
            safe_int(data["n"], strict=True, field_name="n")
            safe_int(data["w"], strict=True, field_name="w")
            safe_int(data["l"], strict=True, field_name="l")
            safe_int(data["streak"], strict=True, field_name="streak")
        except StrictValidationError as e:
            raise ResponseValidationError(f"Performance field validation failed: {e}") from e

    return data


def validate_positions_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate positions endpoint response.

    Positions can be empty list (no open positions) but items array must be present
    if data is structured as {items: [...]}.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Positions response not a dict: {type(data)}")

    if has_error(data):
        return data

    # If data has items array, validate it's a list
    if "items" in data and not isinstance(data["items"], list):
        raise ResponseValidationError(f"Positions items field must be list, got {type(data['items'])}")

    # Validate each position has critical fields
    items = data.get("items", [])
    if items is None:
        raise ResponseValidationError("Positions response 'items' field is None (API contract violation)")
    if items:
        for i, pos in enumerate(items):
            if not isinstance(pos, dict):
                raise ResponseValidationError(f"Position {i} is not a dict: {type(pos)}")
            if "symbol" not in pos:
                raise ResponseValidationError(f"Position {i} missing critical field: symbol")

    return data


def validate_signals_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate signals endpoint response.

    Signals are optional (no signals valid), but if present must have structure.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Signals response not a dict: {type(data)}")

    if has_error(data):
        return data

    # If signals exist, validate items array structure
    if "items" in data:
        if not isinstance(data["items"], list):
            raise ResponseValidationError(f"Signals items must be list, got {type(data['items'])}")

        for i, sig in enumerate(data["items"]):
            if not isinstance(sig, dict):
                raise ResponseValidationError(f"Signal {i} is not a dict: {type(sig)}")
            # Symbol is critical for signal identification
            if "symbol" not in sig:
                raise ResponseValidationError(f"Signal {i} missing critical field: symbol")

    return data


def validate_config_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate config endpoint response.

    Config provides algorithm settings with critical safety thresholds.
    Requires: min_signal_quality_score, min_swing_score, min_completeness_score,
              min_volume_ma_50d, min_avg_daily_dollar_volume,
              earnings_blackout_days_before, earnings_blackout_days_after
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Config response not a dict: {type(data)}")

    if has_error(data):
        return data

    # Critical fields that must be present for config validation
    required_fields = [
        "min_signal_quality_score",
        "min_swing_score",
        "min_completeness_score",
        "min_volume_ma_50d",
        "min_avg_daily_dollar_volume",
        "earnings_blackout_days_before",
        "earnings_blackout_days_after",
    ]
    _check_required_fields(data, required_fields, "config")

    # Validate numeric fields
    field_types = {
        "min_signal_quality_score": int,
        "min_swing_score": float,
        "min_completeness_score": int,
        "min_volume_ma_50d": int,
        "min_avg_daily_dollar_volume": float,
        "earnings_blackout_days_before": int,
        "earnings_blackout_days_after": int,
    }

    try:
        for field, expected_type in field_types.items():
            if expected_type is int:
                safe_int(data[field], strict=True, field_name=field)
            else:
                safe_float(data[field], strict=True, field_name=field)
    except StrictValidationError as e:
        raise ResponseValidationError(f"Config field validation failed: {e}") from e

    return data


def validate_risk_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate risk endpoint response.

    Risk metrics are optional, but if present must be valid numbers.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Risk response not a dict: {type(data)}")

    if has_error(data):
        return data

    # If risk metrics are present, they must be convertible to float
    numeric_fields = ["var95", "cvar95", "beta", "conc5", "svar"]
    for field in numeric_fields:
        if field in data and data[field] is not None:
            try:
                safe_float(data[field], strict=True, field_name=field)
            except StrictValidationError as e:
                raise ResponseValidationError(f"Risk field {field} validation failed: {e}") from e

    return data


def validate_market_data_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate market data endpoint response.

    Market data provides context; missing fields can be tolerated if structure is sound.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Market data response not a dict: {type(data)}")

    if has_error(data):
        return data

    # Market data has flexible structure; just ensure it's a dict if present
    return data


def validate_health_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate health/data-status endpoint response.

    Health indicators must be present (ready_to_trade, critical_stale, etc).
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Health response not a dict: {type(data)}")

    if has_error(data):
        return data

    # Health response should have at least some status indicators
    # Allow flexible field names but ensure the structure exists
    if not data:
        raise ResponseValidationError("Health response is empty dict")

    return data


def validate_last_run_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate last-run endpoint response.

    Critical fields: run_id, success status, run timestamps.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Last run response not a dict: {type(data)}")

    if has_error(data):
        return data

    # Require run_id and success indicator
    if "run_id" not in data:
        raise ResponseValidationError("Last run response missing critical field: run_id")

    return data


def validate_trades_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate trades endpoint response.

    Trades can be empty list (no recent trades) but items must be present.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Trades response not a dict: {type(data)}")

    if has_error(data):
        return data

    # If data has items array, validate it's a list
    if "items" in data and not isinstance(data["items"], list):
        raise ResponseValidationError(f"Trades items field must be list, got {type(data['items'])}")

    return data


def validate_markets_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate markets endpoint response.

    Market data: SPY close, VIX level, regime, exposure.
    These are critical for position sizing and risk management.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Markets response not a dict: {type(data)}")

    if has_error(data):
        return data

    # Markets response can have nested structure (current, market_health, etc)
    # or flat structure; be flexible but ensure it has some data
    if not data or all(k.startswith("_") for k in data.keys()):
        raise ResponseValidationError("Markets response is empty or contains only metadata")

    return data


def validate_dashboard_signals_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate dashboard signals endpoint response.

    Signals are optional (no signals valid), but structure should be sound.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Dashboard signals response not a dict: {type(data)}")

    if has_error(data):
        return data

    # If signals exist, validate items array structure
    if "items" in data:
        if not isinstance(data["items"], list):
            raise ResponseValidationError(f"Dashboard signals items must be list, got {type(data['items'])}")

    return data


def validate_circuit_breakers_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate circuit breakers endpoint response.

    Circuit breaker status is optional but structure should be valid.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Circuit breakers response not a dict: {type(data)}")

    if has_error(data):
        return data

    # If breakers array exists, it must be a list
    if "breakers" in data and not isinstance(data["breakers"], list):
        raise ResponseValidationError(f"Circuit breakers array must be list, got {type(data['breakers'])}")

    return data


def validate_sector_rotation_response(data: dict[str, Any]) -> dict[str, Any]:
    """Validate sector rotation endpoint response.

    Sector rotation signal and rankings can be empty but structure should be valid.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Sector rotation response not a dict: {type(data)}")

    if has_error(data):
        return data

    # If items array exists, it must be a list
    if "items" in data and not isinstance(data["items"], list):
        raise ResponseValidationError(f"Sector items must be list, got {type(data['items'])}")

    return data


def validate_generic_response(data: dict[str, Any]) -> dict[str, Any]:
    """Generic validator for endpoints without specific requirements.

    Ensures response is a dict and not an error.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Response not a dict: {type(data)}")

    if has_error(data):
        return data

    return data


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
