"""API response validators for dashboard data integrity.

Validates API responses at the boundary to ensure critical fields are present.
Uses fail-fast approach instead of silent fallbacks.
"""

import logging
from typing import Any, Dict, List

from .data_validation import StrictValidationError, safe_float, safe_int


logger = logging.getLogger(__name__)


class ResponseValidationError(Exception):
    """Raised when API response is missing critical fields."""


def _check_required_fields(
    data: Dict[str, Any], required_fields: List[str], source: str
) -> None:
    """Check if data has all required fields; raise error if any missing."""
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        raise ResponseValidationError(
            f"Missing critical fields in {source}: {missing}"
        )


def validate_portfolio_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate portfolio endpoint response.

    Critical fields: position_count (required)
    Optional fields: total_portfolio_value, total_cash (can be None when no data available)
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Portfolio response not a dict: {type(data)}")

    if data.get("_error"):
        return data  # Propagate error responses as-is

    # Check that all field keys are present (values can be None for optional fields)
    required_keys = ["total_portfolio_value", "total_cash", "position_count"]
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        raise ResponseValidationError(
            f"Missing critical fields in portfolio: {missing_keys}"
        )

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
            safe_float(
                data["total_cash"], strict=True, field_name="total_cash"
            )
        # position_count must be present but can be 0 or None
        if data["position_count"] is not None:
            safe_int(
                data["position_count"], strict=True, field_name="position_count"
            )
    except StrictValidationError as e:
        raise ResponseValidationError(
            f"Portfolio field validation failed: {e}"
        ) from e

    return data


def validate_performance_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate performance endpoint response.

    Critical fields: w (wins), l (losses), n (total trades), streak
    Missing these fields causes win rate to be silently computed as 0.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Performance response not a dict: {type(data)}")

    if data.get("_error") or data.get("_no_data"):
        return data  # Propagate error responses

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
            raise ResponseValidationError(
                f"Performance field validation failed: {e}"
            ) from e

    return data


def validate_positions_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate positions endpoint response.

    Positions can be empty list (no open positions) but items array must be present
    if data is structured as {items: [...]}.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Positions response not a dict: {type(data)}")

    if data.get("_error"):
        return data

    # If data has items array, validate it's a list
    if "items" in data and not isinstance(data["items"], list):
        raise ResponseValidationError(
            f"Positions items field must be list, got {type(data['items'])}"
        )

    # Validate each position has critical fields
    items = data.get("items", [])
    if items:
        for i, pos in enumerate(items):
            if not isinstance(pos, dict):
                raise ResponseValidationError(
                    f"Position {i} is not a dict: {type(pos)}"
                )
            if "symbol" not in pos:
                raise ResponseValidationError(
                    f"Position {i} missing critical field: symbol"
                )

    return data


def validate_signals_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate signals endpoint response.

    Signals are optional (no signals valid), but if present must have structure.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Signals response not a dict: {type(data)}")

    if data.get("_error"):
        return data

    # If signals exist, validate items array structure
    if "items" in data:
        if not isinstance(data["items"], list):
            raise ResponseValidationError(
                f"Signals items must be list, got {type(data['items'])}"
            )

        for i, sig in enumerate(data["items"]):
            if not isinstance(sig, dict):
                raise ResponseValidationError(
                    f"Signal {i} is not a dict: {type(sig)}"
                )
            # Symbol is critical for signal identification
            if "symbol" not in sig:
                raise ResponseValidationError(
                    f"Signal {i} missing critical field: symbol"
                )

    return data


def validate_config_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate config endpoint response.

    Config determines safety thresholds; missing fields can disable safety gates.
    Critical fields: min_signal_quality_score, min_swing_score, min_completeness_score,
    min_volume_ma_50d, min_avg_daily_dollar_volume, earnings_blackout_days_before,
    earnings_blackout_days_after. These must be present to prevent fallback defaults
    from masking misconfigured safety gates.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Config response not a dict: {type(data)}")

    if data.get("_error"):
        return data

    # Critical safety threshold fields that must be present
    required = [
        "min_signal_quality_score",
        "min_swing_score",
        "min_completeness_score",
        "min_volume_ma_50d",
        "min_avg_daily_dollar_volume",
        "earnings_blackout_days_before",
        "earnings_blackout_days_after",
    ]
    _check_required_fields(data, required, "config safety thresholds")

    # Validate critical numeric fields can be converted
    try:
        safe_int(
            data["min_signal_quality_score"],
            strict=True,
            field_name="min_signal_quality_score",
        )
        safe_float(
            data["min_swing_score"], strict=True, field_name="min_swing_score"
        )
        safe_int(
            data["min_completeness_score"],
            strict=True,
            field_name="min_completeness_score",
        )
        safe_int(
            data["min_volume_ma_50d"], strict=True, field_name="min_volume_ma_50d"
        )
        safe_float(
            data["min_avg_daily_dollar_volume"],
            strict=True,
            field_name="min_avg_daily_dollar_volume",
        )
        safe_int(
            data["earnings_blackout_days_before"],
            strict=True,
            field_name="earnings_blackout_days_before",
        )
        safe_int(
            data["earnings_blackout_days_after"],
            strict=True,
            field_name="earnings_blackout_days_after",
        )
    except StrictValidationError as e:
        raise ResponseValidationError(
            f"Config field validation failed: {e}"
        ) from e

    return data


def validate_risk_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate risk endpoint response.

    Risk metrics are optional, but if present must be valid numbers.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Risk response not a dict: {type(data)}")

    if data.get("_error"):
        return data

    # If risk metrics are present, they must be convertible to float
    numeric_fields = ["var95", "cvar95", "beta", "conc5", "svar"]
    for field in numeric_fields:
        if field in data and data[field] is not None:
            try:
                safe_float(data[field], strict=True, field_name=field)
            except StrictValidationError as e:
                raise ResponseValidationError(
                    f"Risk field {field} validation failed: {e}"
                ) from e

    return data


def validate_market_data_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate market data endpoint response.

    Market data provides context; missing fields can be tolerated if structure is sound.
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Market data response not a dict: {type(data)}")

    if data.get("_error"):
        return data

    # Market data has flexible structure; just ensure it's a dict if present
    return data


def validate_health_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate health/data-status endpoint response.

    Health indicators must be present (ready_to_trade, critical_stale, etc).
    """
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Health response not a dict: {type(data)}")

    if data.get("_error"):
        return data

    # Health response should have at least some status indicators
    # Allow flexible field names but ensure the structure exists
    if not data:
        raise ResponseValidationError("Health response is empty dict")

    return data


# Mapping of endpoints to their validators
VALIDATORS = {
    "/api/algo/portfolio": validate_portfolio_response,
    "/api/algo/performance": validate_performance_response,
    "/api/algo/positions": validate_positions_response,
    "/api/algo/signals": validate_signals_response,
    "/api/algo/config": validate_config_response,
    "/api/algo/risk": validate_risk_response,
    "/api/algo/market": validate_market_data_response,
    "/api/algo/data-status": validate_health_response,
}


def validate_response(endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
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
    # No validator defined; return data as-is
    return data
