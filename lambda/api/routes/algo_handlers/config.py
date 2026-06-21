"""Route: algo"""

import logging
from datetime import datetime, timezone

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
)

from shared_contracts.response_validator import ResponseValidator


logger = logging.getLogger(__name__)



def _categorize_config_key(key: str) -> str:
    """Categorize configuration key for TIER 3 visibility grouping."""
    if "drawdown" in key or "halt" in key or "risk_reduction" in key:
        return "Drawdown Defense"
    elif (
        "circuit" in key
        or "max_daily_loss" in key
        or "max_consecutive" in key
        or "min_win_rate" in key
        or "max_total_risk" in key
        or "max_weekly" in key
        or "daily_profit_cap" in key
        or "sector_drawdown" in key
    ):
        return "Circuit Breakers"
    elif (
        "swing" in key
        or "swing_weight" in key
        or "swing_grade" in key
        or "swing_min" in key
        or "swing_days" in key
    ):
        return "Swing Trader Scoring"
    elif (
        "vix" in key
        or "put_call" in key
        or "upvol" in key
        or "breadth" in key
        or "yield_curve" in key
        or "beta" in key
        or "max_distribution" in key
        or "require_stage" in key
    ):
        return "Market Conditions"
    elif (
        "min_completeness" in key
        or "min_stock_price" in key
        or "min_signal" in key
        or "min_volume" in key
        or "min_avg_daily" in key
        or "require_stock_stage" in key
        or "max_stop_distance" in key
        or "max_positions_per" in key
        or "min_swing_score" in key
        or "max_total_invested" in key
        or "advanced_filters_grade" in key
    ):
        return "Filter Thresholds"
    elif (
        "require_sma50" in key
        or "min_percent_from" in key
        or "max_percent_from" in key
        or "min_trend_template" in key
    ):
        return "Entry Rules (Minervini)"
    elif (
        "max_signal_age" in key
        or "min_close_quality" in key
        or "min_breakout_volume" in key
        or "require_weekly_stage" in key
        or "min_rs_line" in key
        or "max_rs_pct" in key
        or "rs_slope_gate" in key
        or "volume_decay_gate" in key
    ):
        return "Entry Quality Gates"
    elif (
        "require_target_pullback" in key
        or "t1_target" in key
        or "t2_target" in key
        or "t3_target" in key
        or "imported_position" in key
        or "min_hold" in key
        or "max_hold" in key
        or "exit_on" in key
        or "use_chandelier" in key
        or "switch_to_21ema" in key
        or "eight_week_rule" in key
        or "chandelier_atr" in key
        or "move_be" in key
    ):
        return "Exit Rules"
    elif "re_engage" in key:
        return "Re-engagement"
    elif (
        "position_halt_flag" in key
        or "max_reentries" in key
        or "min_days_before_reentry" in key
    ):
        return "Position Monitoring"
    elif (
        "earnings" in key or "halt_entries_before" in key or "block_days_before" in key
    ):
        return "Economic & Earnings"
    elif (
        "min_price_history" in key
        or "min_daily_volume" in key
        or "max_spread" in key
        or "min_market_cap" in key
        or "min_float" in key
        or "max_short_interest" in key
    ):
        return "Fundamental Filters"
    elif "max_extension" in key or "strong_sector" in key:
        return "Advanced Filters"
    elif (
        "var_percentile" in key
        or "cvar_percentile" in key
        or "stressed_var" in key
        or "dashboard_grade" in key
    ):
        return "Risk Metrics"
    elif (
        "execution_mode" in key
        or "alpaca_paper" in key
        or "max_trades_per_day" in key
        or "default_portfolio" in key
    ):
        return "Execution Mode"
    elif "enable_" in key or "verbose_" in key:
        return "Feature Flags"
    elif "api_request" in key or "db_connection" in key:
        return "Network Configuration"
    elif "failsafe" in key:
        return "Failsafe Configuration"
    elif "base_risk" in key or "max_position_size" in key or "max_concentration" in key:
        return "Risk Management"
    else:
        return "Other"



@db_route_handler("fetch algo config")
def _get_algo_config(cur) -> dict:
    """Return all algo configuration rows with defaults and categorization for TIER 3 visibility."""
    from algo.infrastructure import AlgoConfig

    cur.execute(
        "SELECT key, value, value_type, description, updated_at FROM algo_config ORDER BY key"
    )
    rows = cur.fetchall()

    # Build config with defaults and categorization
    config_items = []
    for row in rows:
        config_dict = safe_json_serialize(safe_dict_convert(row))
        key = config_dict["key"]

        # Get default value and metadata from AlgoConfig.DEFAULTS
        if key in AlgoConfig.DEFAULTS:
            default_val, _, _ = AlgoConfig.DEFAULTS[key]
            config_dict["default_value"] = default_val
            config_dict["is_custom"] = (
                str(config_dict["value"]).strip() != str(default_val).strip()
            )
        else:
            config_dict["default_value"] = None
            config_dict["is_custom"] = True

        # Categorize by key name patterns
        config_dict["category"] = _categorize_config_key(key)
        config_items.append(config_dict)

    response = list_response(config_items)

    # Validate config response against contract schema
    is_valid, error_msg = ResponseValidator.validate_endpoint_response("cfg", response["data"])
    if not is_valid:
        logger.error(f"Config response validation failed: {error_msg}")
        return error_response(500, "response_validation_error", error_msg)

    return response



@db_route_handler("fetch algo config key")
def _get_algo_config_key(cur, key: str) -> Dict:
    """Return a single algo config key."""
    cur.execute(
        "SELECT key, value, value_type, description, updated_at FROM algo_config WHERE key = %s",
        (key,),
    )
    row = cur.fetchone()
    return json_response(
        200, safe_json_serialize(safe_dict_convert(row)) if row else {}
    )



@db_route_handler("reset algo config key")
def _reset_algo_config_key(cur, key: str, actor: str) -> Dict:
    """Reset a configuration key to its default value (TIER 5: Reset capability)."""
    from algo.infrastructure import AlgoConfig

    # Validate the key exists
    if key not in AlgoConfig.DEFAULTS:
        return error_response(404, "not_found", f"Config key not found: {key}")

    default_val, _, _ = AlgoConfig.DEFAULTS[key]

    # Get current value for audit
    cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
    old_row = cur.fetchone()
    old_value = old_row["value"] if old_row else None

    # Reset to default
    cur.execute(
        """
        UPDATE algo_config
        SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
        WHERE key = %s
    """,
        (default_val, actor, key),
    )

    # Log to audit trail
    cur.execute(
        """
        INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
    """,
        (key, old_value, default_val, actor),
    )

    logger.info(
        f"[TIER5] Config reset by {actor}: {key} = {default_val} (was {old_value})"
    )

    return json_response(
        200,
        {
            "status": "success",
            "key": key,
            "old_value": old_value,
            "new_value": default_val,
            "reset_to_default": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": actor,
        },
    )



@db_route_handler("update algo config key")
def _update_algo_config_key(cur, key: str, body: Dict, actor: str) -> Dict:
    """Update a configuration key (TIER 4: Configuration Editing)."""
    from algo.infrastructure import AlgoConfig

    if not body or "value" not in body:
        return error_response(400, "bad_request", "value required in request body")

    # Validate the key exists and get its type
    cur.execute("SELECT key, value_type FROM algo_config WHERE key = %s", (key,))
    row = cur.fetchone()
    if row is None:
        return error_response(404, "not_found", f"Config key not found: {key}")

    new_value = body.get("value")

    # Validate the new value against AlgoConfig constraints
    try:
        if not AlgoConfig.DEFAULTS.get(key):
            return error_response(400, "bad_request", f"Unknown config key: {key}")

        _, expected_type, _ = AlgoConfig.DEFAULTS[key]
        # Validate bounds and type
        config = AlgoConfig()
        config._validate_value(key, str(new_value), expected_type)
    except ValueError as e:
        logger.warning(f"Config validation failed for {key}={new_value}: {e}")
        return error_response(400, "bad_request", f"Invalid value for {key}: {str(e)}")

    # Get old value for audit
    cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
    old_row = cur.fetchone()
    old_value = old_row["value"] if old_row else None

    # Update the config
    cur.execute(
        """
            UPDATE algo_config
            SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
            WHERE key = %s
        """,
        (str(new_value), actor, key),
    )

    # Log to audit trail
    cur.execute(
        """
            INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (key, old_value, str(new_value), actor),
    )

    logger.info(
        f"[TIER4] Config updated by {actor}: {key} = {new_value} (was {old_value})"
    )

    return json_response(
        200,
        {
            "status": "success",
            "key": key,
            "old_value": old_value,
            "new_value": str(new_value),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": actor,
        },
    )



