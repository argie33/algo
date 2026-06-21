"""Fetcher functions for dashboard data from API endpoints."""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")

from utils.safe_data_conversion import (
    StrictValidationError,
    safe_bool,
    safe_float,
    safe_float_strict,
    safe_int,
    safe_int_strict,
    safe_json_parse,
)

from .api_data_layer import API_MAX_BACKOFF, api_call
from .panels.data_extractors import safe_get_dict, safe_get_field, safe_get_list
from .utilities import (
    CY,
    G,
    R,
    Y,
    logger,
    record_data_quality_issue,
)


# Fetcher metadata: endpoint and description for better error context
FETCHER_METADATA = {
    "run": {"endpoint": "/api/algo/last-run", "desc": "Last algo run status"},
    "cfg": {"endpoint": "/api/algo/config", "desc": "Algo configuration"},
    "mkt": {"endpoint": "/api/algo/markets", "desc": "Market data"},
    "port": {"endpoint": "/api/algo/portfolio", "desc": "Portfolio snapshot"},
    "perf": {"endpoint": "/api/algo/performance", "desc": "Performance metrics"},
    "pos": {"endpoint": "/api/algo/positions", "desc": "Open positions"},
    "trades": {"endpoint": "/api/algo/trades", "desc": "Recent trades"},
    "sig": {"endpoint": "/api/algo/dashboard-signals", "desc": "Dashboard signals"},
    "health": {"endpoint": "/api/algo/data-status", "desc": "Data loader health"},
    "cb": {"endpoint": "/api/algo/circuit-breakers", "desc": "Circuit breakers"},
    "srank": {"endpoint": "/api/sectors", "desc": "Sector rankings"},
    "activity": {"endpoint": "/api/algo/audit-log", "desc": "Activity log"},
    "eco": {
        "endpoint": "/api/economic/yield-curve-full + /api/economic/indicators",
        "desc": "Economic macro indicators",
    },
    "notifs": {"endpoint": "/api/algo/notifications", "desc": "Notifications"},
    "sentiment": {"endpoint": "/api/algo/sentiment", "desc": "Market sentiment"},
    "econ_cal": {
        "endpoint": "/api/algo/economic-calendar",
        "desc": "Economic calendar",
    },
    "risk": {"endpoint": "/api/algo/risk-metrics", "desc": "Risk metrics"},
    "perf_anl": {
        "endpoint": "/api/algo/performance-analytics",
        "desc": "Performance analytics",
    },
    "sig_eval": {"endpoint": "/api/algo/rejection-funnel", "desc": "Signal evaluation"},
    "sec_rot": {
        "endpoint": "/api/algo/sector-rotation",
        "desc": "Sector rotation signal",
    },
    "algo_metrics": {"endpoint": "/api/algo/metrics", "desc": "Algo metrics"},
    "irank": {"endpoint": "/api/industries", "desc": "Industry rankings"},
    "audit": {"endpoint": "/api/algo/audit-log", "desc": "Audit log"},
    "exec_hist": {
        "endpoint": "/api/algo/execution/recent",
        "desc": "Execution history",
    },
    "exp_factors": {
        "endpoint": "/api/algo/markets",
        "desc": "Market exposure factors (12-factor breakdown)",
    },
    "scores": {
        "endpoint": "/api/scores",
        "desc": "Top stock scores for signals panel display",
    },
}


def _format_fetcher_error(fetcher_name: str, error: Exception) -> str:
    """Format fetcher error with endpoint context for better troubleshooting.

    Returns error string like: "Fetcher run (/api/algo/last-run: Last algo run status) timed out"
    """
    meta = FETCHER_METADATA.get(fetcher_name)
    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
    desc = meta.get("desc", "") if meta else ""

    error_type = type(error).__name__
    error_msg = str(error)

    context = f"{endpoint}"
    if desc:
        context += f": {desc}"

    if error_msg:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}: {error_msg}"
    else:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}"


def _get_endpoint_path(fetcher_key: str, params: dict | None = None) -> str:
    """Map fetcher key to full endpoint path with optional query parameters.

    Examples:
      _get_endpoint_path('pos') → '/api/algo/positions'
      _get_endpoint_path('trades', params={'limit': 10}) → '/api/algo/trades' (params passed to api_call)
    """
    meta = FETCHER_METADATA.get(fetcher_key)
    if not meta:
        # For endpoints with direct paths (like '/api/algo/last-run')
        return fetcher_key
    endpoint = meta.get("endpoint", "")
    if not endpoint:
        return fetcher_key
    return endpoint


def _is_api_error(response: dict) -> bool:
    """Check if API response indicates an error (network error or statusCode >= 400)."""
    return "_error" in response or response.get("statusCode", 200) >= 400


def _get_error_message(response: dict) -> str:
    """Extract error message from API response."""
    if "_error" in response:
        error_val = response["_error"]
        return str(error_val) if error_val is not None else "Unknown API error"
    # Extract from statusCode-based error response
    msg = response.get("message")
    status = response.get("statusCode")
    if msg:
        return str(msg)
    return f"API error {status if status is not None else 'unknown'}"


def fetch_run(c):
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/last-run")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("run", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        inner = data

        # Validate required fields
        required = ["phases", "success", "halted"]
        valid, error_msg = FetcherValidator.require_fields(inner, required, "fetch_run")
        if not valid:
            logger.error(error_msg)
            record_data_quality_issue("run", "validation", "missing_fields", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        phases = inner["phases"]
        halted_phases = [p for p in phases if safe_get_field(p, "status") in ("halt", "halted")]
        errored_phases = [p for p in phases if safe_get_field(p, "status") == "error"]
        completed_phases = [p for p in phases if safe_get_field(p, "status") == "success"]
        halt_reason = safe_get_field(halted_phases[0], "summary") if halted_phases else None

        # Timestamps are required - fail if all are missing (Issue #6)
        run_at = safe_get_field(inner, "run_at") or safe_get_field(inner, "completed_at") or safe_get_field(inner, "started_at")
        # No runs yet (algo hasn't executed) - fail-fast: return error instead of placeholder
        if not run_at and not safe_get_field(inner, "run_id") and not inner["success"] and not inner["halted"]:
            error_msg = "No algo runs available yet (algo has not executed)"
            logger.warning(error_msg)
            record_data_quality_issue("run", "initialization", "no_runs_yet")
            return FetcherValidator.build_error_response(error_msg)
        if not run_at:
            error_msg = "Last-run API response missing all timestamp fields (run_at, completed_at, started_at)"
            logger.error(error_msg)
            record_data_quality_issue("run", "critical_field", "missing_timestamp")
            return FetcherValidator.build_error_response(error_msg)

        # errored: use API field if present, otherwise derive from phase data
        api_errored = safe_get_field(inner, "errored")
        derived_errored = bool(errored_phases) or (
            not inner["success"] and not inner["halted"] and bool(phases)
        )
        return {
            "run_id": safe_get_field(inner, "run_id"),
            "run_at": run_at,
            "success": inner["success"],
            "halted": inner["halted"],
            "errored": api_errored if api_errored is not None else derived_errored,
            "summary": safe_get_field(inner, "summary"),
            "halt_reason": halt_reason,
            "phases_completed": [safe_get_field(p, "action_type") for p in completed_phases],
            "phases_halted": [safe_get_field(p, "action_type") for p in halted_phases],
            "phases_errored": [safe_get_field(p, "action_type") for p in errored_phases],
            "phase_results": phases,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("run", e)
        logger.error(error_msg)
        record_data_quality_issue("run", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_algo_config(c):
    """AWS-only algo configuration (fail-fast: error if unavailable)."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/config")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("cfg", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        if not isinstance(raw, dict):
            error_msg = "Config response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "type", "not_dict", type(raw).__name__)
            return FetcherValidator.build_error_response(error_msg)

        # API returns {items: [{key, value, value_type, ...}], total: N}
        if "items" not in raw:
            error_msg = "Config API response missing 'items' key (API contract violation)"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "missing_items_key")
            return FetcherValidator.build_error_response(error_msg)

        items = raw["items"]
        if not isinstance(items, list):
            error_msg = f"Config 'items' is not a list: {type(items).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "items_not_list")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "Config API response has no items (empty config)"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "empty_items")
            return FetcherValidator.build_error_response(error_msg)

        cfg = {i["key"]: i.get("value") for i in items if "key" in i}

        # Issue #8: enable_algo is REQUIRED - no default to True (fail-closed)
        required_config = [
            "enable_algo",
            "execution_mode",
            "max_position_size_pct",
            "max_positions",
            "max_positions_per_sector",
            "min_swing_score",
            "base_risk_pct",
            "t1_target_r_multiple",
        ]
        missing = [k for k in required_config if k not in cfg]
        if missing:
            error_msg = f"Config missing required fields: {missing}"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "missing_fields", ", ".join(missing))
            return FetcherValidator.build_error_response(error_msg)

        # Boolean string conversion
        en_raw = cfg["enable_algo"]
        enabled = str(en_raw).lower() in ("true", "1", "yes") if en_raw is not None else False
        return {
            "enabled": enabled,
            "mode": cfg["execution_mode"],
            "max_pos_pct": safe_float(cfg["max_position_size_pct"]),
            "max_pos_n": safe_int(cfg["max_positions"]),
            "max_sec_n": safe_int(cfg["max_positions_per_sector"]),
            "min_score": safe_float(cfg["min_swing_score"]),
            "base_risk": safe_float(cfg["base_risk_pct"]),
            "t1_r": safe_float(cfg["t1_target_r_multiple"]),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("cfg", e)
        logger.error(error_msg)
        record_data_quality_issue("cfg", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_market(c):
    """Issue 3 FIX: API-only market data.

    STRICT MODE: SPY price and VIX are critical for position sizing. Missing them
    is a critical data freshness issue, not a fallback-to-None situation.

    If VIX is NULL, it means load_market_health_daily ran but yfinance returned
    no valid data (likely all values < 5.0 threshold). This is a data quality issue,
    not a missing loader issue.

    Issue 14 FIX: Uses cached markets endpoint to avoid duplicate API calls
    when fetch_exp_factors also needs the same data.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        mkt = _get_markets_cached()

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(mkt)
        if is_error:
            record_data_quality_issue("market", "api_call", "api_error", error_msg)
            return mkt

        # API response is unwrapped so data is at top level (statusCode + fields)
        current = mkt.get("current")
        market_health = mkt.get("market_health")
        if not isinstance(current, dict) or not isinstance(market_health, dict):
            error_msg = "Market API response missing 'current' or 'market_health' dict"
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "missing_current_or_health")
            return FetcherValidator.build_error_response(error_msg)

        # VIX and SPY are critical - fail if missing or invalid
        try:
            vix_raw = market_health.get("vix_level")
            spy_raw = current.get("spy_close")

            # Both SPY and VIX are REQUIRED for position sizing
            if vix_raw is None:
                error_msg = "Critical market data missing: VIX level required but not provided by API"
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "missing_vix")
                return FetcherValidator.build_error_response(error_msg)
            if spy_raw is None:
                error_msg = "Critical market data missing: SPY close required but not provided by API"
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "missing_spy")
                return FetcherValidator.build_error_response(error_msg)

            vix = safe_float_strict(vix_raw, "market.vix_level")
            spy = safe_float_strict(spy_raw, "market.spy_close")

            if vix <= 0:
                error_msg = f"Critical market data invalid: VIX = {vix} (must be > 0). Data quality issue in yfinance pipeline."
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "invalid_vix", f"vix={vix}")
                return FetcherValidator.build_error_response(error_msg)
        except StrictValidationError as e:
            error_msg = f"Critical market data conversion failed: {e!s}"
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "conversion_failed", str(e))
            return FetcherValidator.build_error_response(error_msg)

        # Issue #9: Market regime is REQUIRED - no fallback to "unknown"
        tier = current.get("regime")
        if not tier:
            error_msg = (
                f"[MARKET CRITICAL] Market regime missing from current.regime. "
                f"Cannot position size without regime tier. "
                f"Current keys: {list(current.keys())}"
            )
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "missing_regime")
            return FetcherValidator.build_error_response(error_msg)

        return {
            "pct": safe_float(current.get("exposure_pct"), default=None),
            "tier": tier,
            "halts": safe_json_parse(current.get("halt_reasons"), default=[], field_name="halt_reasons"),
            "vix": vix,
            "stage": market_health.get("market_stage"),
            "trend": market_health.get("market_trend"),
            "dist": safe_int(current.get("distribution_days"), default=None),
            "spy": spy,
            "spy_chg": safe_float(market_health.get("spy_change_pct"), default=None),
            "upvol": safe_float(market_health.get("up_volume_percent"), default=None),
            "adr": safe_float(market_health.get("advance_decline_ratio"), default=None),
            "nh": safe_int(market_health.get("new_highs_count"), default=None),
            "nl": safe_int(market_health.get("new_lows_count"), default=None),
            "pcr": safe_float(market_health.get("put_call_ratio"), default=None),
            "bmom": safe_float(market_health.get("breadth_momentum_10d"), default=None),
            "ycs": safe_float(market_health.get("yield_curve_slope"), default=None),
            "fed": market_health.get("fed_rate_environment"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("mkt", e)
        logger.error(error_msg)
        record_data_quality_issue("market", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def _validate_required_fields(data_dict, required_fields, source_name):
    """Validate that all required fields exist in response dict. Return error dict if missing."""
    if not isinstance(data_dict, dict):
        return {"_error": f"{source_name}: expected dict but got {type(data_dict).__name__}"}
    missing = [f for f in required_fields if f not in data_dict]
    if missing:
        logger.warning(f"{source_name}: missing required fields: {missing}")
        return {"_error": f"{source_name}: missing fields {missing}"}
    return None


def _check_data_freshness(
    timestamp_str: str, max_age_seconds: int = 3600, source_name: str = "data"
) -> tuple[bool, str | None]:
    """Check if data timestamp is within acceptable age threshold.

    Args:
        timestamp_str: ISO format timestamp string (e.g., from API response)
        max_age_seconds: Maximum acceptable age in seconds (default 1 hour)
        source_name: Name of data source for error messages

    Returns:
        (is_fresh, error_message) tuple
        - (True, None) if data is fresh
        - (False, error_msg) if data is stale
    """
    if not timestamp_str:
        # No timestamp provided - assume fresh (cannot validate age)
        logger.debug(f"{source_name} data has no timestamp; assuming fresh")
        return True, None

    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ET)
        age_seconds = (datetime.now(ET) - ts).total_seconds()
        if age_seconds > max_age_seconds:
            age_minutes = age_seconds / 60
            error_msg = (
                f"{source_name} data stale ({age_minutes:.0f} min old, threshold: {max_age_seconds / 60:.0f} min)"
            )
            return False, error_msg
        return True, None
    except Exception as e:
        logger.warning(f"Could not parse {source_name} timestamp '{timestamp_str}': {e}")
        return True, None


def fetch_portfolio(c):
    """Fetch portfolio snapshot from API. Fails clean if unavailable.

    STRICT MODE: Uses direct conversion for critical financial fields (no defaults to 0).
    Missing data triggers error, not silent 0 values which are catastrophically misleading.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/portfolio")
        port = data

        # Comprehensive validation using FetcherValidator
        required_fields = ["total_portfolio_value", "total_cash", "position_count", "last_run"]
        valid, error_msg = FetcherValidator.validate_response(
            response=port,
            required_fields=required_fields,
            source_name="fetch_portfolio",
            max_age_seconds=432000,
            timestamp_field="last_run",
        )
        if not valid:
            logger.error(error_msg)
            for field in required_fields:
                if field not in port or port[field] is None:
                    record_data_quality_issue("portfolio", field, "missing_required_field")
            return FetcherValidator.build_error_response(error_msg)

        # Strict conversion for critical financial fields
        try:
            tpv = safe_float_strict(port["total_portfolio_value"], "portfolio.total_portfolio_value")
            tc = safe_float_strict(port["total_cash"], "portfolio.total_cash")
            pc = safe_int_strict(port["position_count"], "portfolio.position_count")
        except StrictValidationError as e:
            error_msg = f"Portfolio data conversion failed: {e!s}"
            logger.error(error_msg)
            record_data_quality_issue("portfolio", "type_conversion", "conversion_failed", str(e))
            return FetcherValidator.build_error_response(error_msg)

        unrealized_pnl_dict = safe_get_dict(safe_get_field(port, "unrealized_pnl"))
        unrealized_pnl_pct = None
        if unrealized_pnl_dict:
            unrealized_pnl_pct = safe_float(safe_get_field(unrealized_pnl_dict, "total_pct"), default=None)

        return {
            "snapshot_date": safe_get_field(port, "last_run"),
            "total_portfolio_value": tpv,
            "total_cash": tc,
            "position_count": pc,
            "daily_return_pct": safe_float(safe_get_field(port, "daily_return_pct"), default=None),
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "cumulative_return_pct": safe_float(safe_get_field(port, "cumulative_return_pct"), default=None),
            "max_drawdown_pct": safe_float(safe_get_field(port, "max_drawdown_pct"), default=None),
            "largest_position_pct": safe_float(safe_get_field(port, "largest_position_pct"), default=None),
            "data_age_seconds": safe_get_field(port, "data_age_seconds"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("port", e)
        logger.error(error_msg)
        record_data_quality_issue("portfolio", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_perf(c):
    """AWS-only performance data (no local fallback).

    STRICT MODE: Trade counts (total, winning, losing) are critical finance metrics.
    Returns 0 for missing counts is catastrophically misleading.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/performance")
        perf = data

        # Check for API error - 503 means no performance data yet (fail-fast: return error)
        is_error, error_msg = FetcherValidator.check_api_error(perf)
        if is_error:
            record_data_quality_issue("per", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Comprehensive validation using FetcherValidator
        required_fields = ["total_trades", "winning_trades", "losing_trades"]
        valid, validation_error = FetcherValidator.validate_response(
            response=perf,
            required_fields=required_fields,
            source_name="fetch_perf",
            max_age_seconds=3600,
            timestamp_field="timestamp",
        )
        if not valid:
            logger.error(validation_error)
            for field in required_fields:
                if field not in perf or perf[field] is None:
                    record_data_quality_issue("per", field, "missing_required_field")
            return FetcherValidator.build_error_response(validation_error)

        # Strict conversion for critical trade count fields
        try:
            n = safe_int_strict(perf["total_trades"], "perf.total_trades")
            w = safe_int_strict(perf["winning_trades"], "perf.winning_trades")
            losing = safe_int_strict(perf["losing_trades"], "perf.losing_trades")
        except StrictValidationError as e:
            error_msg = f"Performance data conversion failed: {e!s}"
            logger.error(error_msg)
            record_data_quality_issue("per", "type_conversion", "conversion_failed", str(e))
            return FetcherValidator.build_error_response(error_msg)

        equity_vals = safe_get_list(safe_get_field(perf, "equity_vals"))
        recent_rets = safe_get_list(safe_get_field(perf, "recent_rets"))

        return {
            "n": n,
            "w": w,
            "l": losing,
            "wr": safe_float(safe_get_field(perf, "win_rate_pct"), default=None),
            "open_count": safe_int(safe_get_field(perf, "open_losses_count") or safe_get_field(perf, "open_positions"), default=None),
            "pnl": safe_float(safe_get_field(perf, "total_pnl_dollars"), default=None),
            "unrealized_pnl": safe_float(safe_get_field(perf, "unrealized_pnl"), default=None),
            "streak": safe_int(safe_get_field(perf, "current_streak"), default=None),
            "sharpe": safe_float(safe_get_field(perf, "sharpe_annualized"), default=None),
            "maxdd": safe_float(safe_get_field(perf, "max_drawdown_pct"), default=None),
            "avg_win": safe_float(safe_get_field(perf, "avg_win_pct"), default=None),
            "avg_loss": safe_float(safe_get_field(perf, "avg_loss_pct"), default=None),
            "profit_factor": safe_float(safe_get_field(perf, "profit_factor"), default=None),
            "expectancy": safe_float(perf.get("expectancy_r"), default=None),
            "avg_r": safe_float(perf.get("expectancy_r"), default=None),
            "equity_vals": equity_vals,
            "recent_rets": recent_rets,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("perf", e)
        logger.error(error_msg)
        record_data_quality_issue("per", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_positions(c):
    """Fetch positions via AWS API only (fail-fast: error if unavailable)."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("pos"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("pos", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        if isinstance(result, dict):
            items = result.get("items")
            if not isinstance(items, list):
                error_msg = "Positions API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("pos", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(result, list):
            items = result
        else:
            error_msg = "Positions API response: expected dict or list"
            logger.error(error_msg)
            record_data_quality_issue("pos", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        return {"items": items, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = _format_fetcher_error("pos", e)
        logger.error(error_msg)
        record_data_quality_issue("pos", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_recent_trades(c):
    """AWS-only trades data. Fail-fast: error only on failure.

    Returns closed trades only - open positions are in the positions panel.
    Note: 503 means no closed trades yet (algo just started) - treat as no data.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(
            _get_endpoint_path("trades"),
            params={"limit": 30, "status": "closed"},
        )

        # Check for API error - fail-fast: return error for all API failures
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("trades", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        if isinstance(result, dict):
            trades = result.get("items")
            if not isinstance(trades, list):
                error_msg = "Trades API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("trades", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(result, list):
            trades = result
        else:
            error_msg = "Trades API response: expected dict or list"
            logger.error(error_msg)
            record_data_quality_issue("trades", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        return {"items": trades, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = _format_fetcher_error("trades", e)
        logger.error(error_msg)
        record_data_quality_issue("trades", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_signals(c):
    """Fetch dashboard signals from API. Fail-fast: error only on failure."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("sig"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sig", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        if not data:
            error_msg = "No data returned from /api/algo/dashboard-signals"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "no_data")
            return FetcherValidator.build_error_response(error_msg)

        result = data
        buy_sigs = result.get("buy_sigs")
        if buy_sigs is not None and not isinstance(buy_sigs, list):
            error_msg = f"Signals response 'buy_sigs' must be list, got {type(buy_sigs).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "buy_sigs_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        near = result.get("near")
        if near is not None and not isinstance(near, list):
            error_msg = f"Signals response 'near' must be list, got {type(near).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "near_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        top_a = result.get("top_a")
        if top_a is not None and not isinstance(top_a, list):
            error_msg = f"Signals response 'top_a' must be list, got {type(top_a).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "top_a_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        trend = result.get("trend")
        if trend is not None and not isinstance(trend, list):
            error_msg = f"Signals response 'trend' must be list, got {type(trend).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "trend_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        grades = result.get("grades")
        if grades is not None and not isinstance(grades, dict):
            error_msg = f"Signals response 'grades' must be dict, got {type(grades).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "grades_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        n = result.get("n")
        if n is None and buy_sigs:
            n = len(buy_sigs)
        total = result.get("total")
        if total is None and n is not None:
            total = n
        elif total is None and buy_sigs:
            total = len(buy_sigs)

        return {
            "n": n,
            "total": total,
            "buy_sigs": buy_sigs,
            "grades": grades,
            "near": near,
            "top_a": top_a,
            "trend": trend,
            "date": result.get("date"),
            "timestamp": datetime.now(ET),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sig", e)
        logger.error(error_msg)
        record_data_quality_issue("sig", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_sector_ranking(c):
    """Fetch per-sector rankings from /api/sectors (fail-fast: error if unavailable)."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/sectors")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("srank", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Sector ranking API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("srank", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Sector ranking API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("srank", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No sector ranking data available"
            logger.error(error_msg)
            record_data_quality_issue("srank", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("srank", e)
        logger.error(error_msg)
        record_data_quality_issue("srank", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_activity(c):
    """Fetch activity from audit log API (fail-fast: error if unavailable)."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("activity"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("activity", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Activity API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("activity", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Activity API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("activity", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No activity data available"
            logger.error(error_msg)
            record_data_quality_issue("activity", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        run_at = items[0].get("action_date")
        phases = [i for i in items if (i.get("action_type") or "").startswith("phase_")]
        return {
            "run_id": None,
            "run_at": run_at,
            "phases": phases,
            "recent_actions": items[:20],
        }
    except Exception as e:
        error_msg = _format_fetcher_error("activity", e)
        logger.error(error_msg)
        record_data_quality_issue("activity", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


_data_status_cache: dict = {}
_data_status_lock = threading.Lock()

_markets_cache: dict = {}
_markets_lock = threading.Lock()


def _get_data_status_cached():
    """Issue 2.2 FIX: Unified fetch for /api/algo/data-status endpoint.

    Both fetch_health and fetch_loader_status need the same endpoint. This
    caches the result to avoid duplicate API calls when both are fetched
    in parallel. Thread-safe with lock to ensure single API call.
    """
    if "result" in _data_status_cache:
        return _data_status_cache["result"]

    with _data_status_lock:
        if "result" in _data_status_cache:
            return _data_status_cache["result"]

        try:
            data = api_call(_get_endpoint_path("health"))
            _data_status_cache["result"] = data
            return data
        except Exception as e:
            error_result = {"_error": str(e)}
            _data_status_cache["result"] = error_result
            return error_result


def _get_markets_cached():
    """Issue 14 FIX: Unified fetch for /api/algo/markets endpoint.

    Both fetch_market and fetch_exp_factors need the same endpoint. This
    caches the result to avoid duplicate API calls when both are fetched
    in parallel. Thread-safe with lock to ensure single API call.
    """
    if "result" in _markets_cache:
        return _markets_cache["result"]

    with _markets_lock:
        if "result" in _markets_cache:
            return _markets_cache["result"]

        try:
            data = api_call("/api/algo/markets")
            _markets_cache["result"] = data
            return data
        except Exception as e:
            error_result = {"_error": str(e)}
            _markets_cache["result"] = error_result
            return error_result


def fetch_health(c):
    """Fetch data loader health status from API. Uses cached data-status (fail-fast: error if unavailable)."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = _get_data_status_cached()

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("health", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        inner = data
        if not isinstance(inner, dict):
            error_msg = "Health API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("health", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        raw_sources = inner.get("sources")
        if not isinstance(raw_sources, list):
            raw_sources = None
        critical_stale = inner.get("critical_stale")
        if not isinstance(critical_stale, list):
            critical_stale = None
        sources = []
        for s in (raw_sources or []):
            name = s.get("name", "")
            # API now returns role (CRIT/IMP/NORM); fall back to freshness_config if absent
            role = s.get("role")
            if not role:
                try:
                    from utils.validation.freshness_config import FRESHNESS_RULES as _FR

                    r = _FR.get(name)
                    role = "CRIT" if r.get("critical") else ("IMP" if r.get("max_age_days", 999) <= 7 else "NORM")
                except ImportError:
                    role = "CRIT" if name in set(critical_stale) else "NORM"
            sources.append(
                {
                    "tbl": name,
                    "st": s.get("status", "ok"),
                    "age": round(s.get("age_hours", 0) / 24, 1),
                    "role": role,
                    # preserve originals for other panels that may use them
                    "name": name,
                    "status": s.get("status", "ok"),
                    "last_updated": s.get("last_updated"),
                    "age_hours": s.get("age_hours"),
                    "row_count": s.get("row_count"),
                }
            )
        summary = inner.get("summary")
        if not isinstance(summary, dict):
            summary = None
        return {
            "items": sources,
            "ready_to_trade": inner.get("ready_to_trade"),
            "summary": summary,
            "critical_stale": critical_stale,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("health", e)
        logger.error(error_msg)
        record_data_quality_issue("health", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_exp_factors(c):
    """Fetch 12-factor market exposure data. Uses /api/algo/markets (public, already fetched).

    Extracts factors from data.current.factors which has the full 12-factor breakdown
    needed by the exposure panel.

    Issue 14 FIX: Uses cached markets endpoint to avoid duplicate API calls
    when fetch_market also needs the same data.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = _get_markets_cached()

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("exp_factors", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Response: {statusCode, data: {current: {exposure_pct, raw_score, regime, factors}, ...}}
        inner = data
        if not isinstance(inner, dict):
            error_msg = "Unexpected response format from markets endpoint"
            logger.error(error_msg)
            record_data_quality_issue("exp_factors", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if "current" not in inner:
            error_msg = "Missing 'current' field in markets response"
            logger.error(error_msg)
            record_data_quality_issue("exp_factors", "validation", "missing_current_field")
            return FetcherValidator.build_error_response(error_msg)

        current = inner.get("current")
        return {
            "exposure_pct": safe_float(current.get("exposure_pct"), default=None),
            "raw_score": safe_float(current.get("raw_score"), default=None),
            "regime": current.get("regime"),
            "factors": current.get("factors"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("exp_factors", e)
        logger.error(error_msg)
        record_data_quality_issue("exp_factors", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_economic_pulse(c):
    """Fetch economic macro indicators. Fail-fast: error only on failure.

    Fetches from /api/economic/yield-curve-full and /api/economic/indicators.
    Both endpoints must succeed; partial data is not accepted (can't distinguish
    None from "API error" vs "field missing in successful response").
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        # Fetch yield curve (treasury yields + credit spreads + breakevens)
        yc_data = api_call("/api/economic/yield-curve-full")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(yc_data)
        if is_error:
            record_data_quality_issue("eco", "api_call", "yield_curve_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Fetch macro indicators (CPI, unemployment, fed funds, oil, DXY, etc.)
        ind_data = api_call("/api/economic/indicators")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(ind_data)
        if is_error:
            record_data_quality_issue("eco", "api_call", "indicators_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Extract yield curve data
        d = yc_data
        curve = None
        spreads = None
        credit = None
        credit_latest = None
        if isinstance(d, dict):
            curve = d.get("currentCurve")
            spreads = d.get("spreads")
            credit = d.get("credit")
        if isinstance(credit, dict):
            credit_latest = credit.get("currentSpreads")

        t10 = safe_float(curve.get("10Y"), default=None) if isinstance(curve, dict) else None
        t2 = safe_float(curve.get("2Y"), default=None) if isinstance(curve, dict) else None
        t3m = safe_float(curve.get("3M"), default=None) if isinstance(curve, dict) else None
        t6m = safe_float(curve.get("6M"), default=None) if isinstance(curve, dict) else None
        yc_10_2 = safe_float(spreads.get("T10Y2Y"), default=None) if isinstance(spreads, dict) else None
        yc_10_3m = safe_float(spreads.get("T10Y3M"), default=None) if isinstance(spreads, dict) else None
        hy = safe_float(credit_latest.get("BAMLH0A0HYM2"), default=None) if isinstance(credit_latest, dict) else None
        ig = None
        if isinstance(credit_latest, dict):
            ig = safe_float(credit_latest.get("BAMLH0A0IG") or credit_latest.get("BAMLC0A0CM"), default=None)

        # Extract indicators data
        d2 = ind_data
        indicators = None
        if isinstance(d2, dict):
            indicators = d2.get("indicators")
            if not isinstance(indicators, list):
                indicators = None
        by_series = {}
        if indicators:
            by_series = {
                i["series_id"]: safe_float(i.get("rawValue"), default=None)
                for i in indicators
                if isinstance(i, dict) and i.get("series_id")
            }
        fed_funds = by_series.get("FEDFUNDS")
        cpi_yoy = by_series.get("CPIAUCSL")
        unrate = by_series.get("UNRATE")
        be10 = by_series.get("T10YIE")
        be5 = by_series.get("T5YIE")
        dxy = by_series.get("DTWEXBGS")
        oil = by_series.get("DCOILWTICO")
        nfci = by_series.get("ANFCI") if by_series.get("ANFCI") is not None else by_series.get("STLFSI4")
        umcsent = by_series.get("UMCSENT")
        mortgage = by_series.get("MORTGAGE30US")

        return {
            "t10": t10,
            "t2": t2,
            "t3m": t3m,
            "t6m": t6m,
            "yc_10_2": yc_10_2,
            "yc_10_3m": yc_10_3m,
            "hy": hy,
            "ig": ig,
            "oil": oil,
            "nfci": nfci,
            "fed_funds": fed_funds,
            "cpi_yoy": cpi_yoy,
            "unrate": unrate,
            "be10": be10,
            "be5": be5,
            "dxy": dxy,
            "mortgage": mortgage,
            "umcsent": umcsent,
        }
    except Exception as e:
        from tools.dashboard.fetcher_validator import FetcherValidator
        error_msg = _format_fetcher_error("eco", e)
        logger.error(error_msg)
        record_data_quality_issue("eco", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_algo_metrics(c):
    """Fetch algo metrics. API returns a single dict {date, total_actions,
    entries, exits, avg_signal_score}; panel expects a flat list so it can
    do valid_metrics[0] and iterate over multiple days."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("algo_metrics"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("algo_metrics", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            return [d]
        error_msg = f"Algo metrics API response unexpected type: expected list or dict, got {type(d).__name__}"
        logger.error(error_msg)
        record_data_quality_issue("algo_metrics", "validation", "invalid_response_type")
        return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = _format_fetcher_error("algo_metrics", e)
        logger.error(error_msg)
        record_data_quality_issue("algo_metrics", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_notifications(c):
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("notifs"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("notifs", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Notifications API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("notifs", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Notifications API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("notifs", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No notifications available"
            logger.error(error_msg)
            record_data_quality_issue("notifs", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("notifs", e)
        logger.error(error_msg)
        record_data_quality_issue("notifs", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_sentiment(c):
    """API-only sentiment data. Fail-fast: error only on failure."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("sentiment"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sentiment", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        # Validate required fields
        required = ["fear_greed_index", "label"]
        valid, error_msg = FetcherValidator.require_fields(d, required, "fetch_sentiment")
        if not valid:
            logger.error(error_msg)
            record_data_quality_issue("sentiment", "validation", "missing_fields")
            return FetcherValidator.build_error_response(error_msg)

        fg = safe_float(d.get("fear_greed_index"))
        label = d.get("label")
        c_fg = R if fg <= 25 else (Y if fg <= 45 else (G if fg >= 75 else CY))
        return {
            "fg": round(fg, 1),
            "label": label,
            "date": d.get("date"),
            "color": c_fg,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sentiment", e)
        logger.error(error_msg)
        record_data_quality_issue("sentiment", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_economic_calendar(c):
    """Fetch economic calendar events. API returns {items: [{event_date,
    event_name, country, importance, category, ...}], total: N}."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("econ_cal"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("econ_cal", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Economic calendar API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("econ_cal", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Economic calendar API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("econ_cal", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No economic calendar events available"
            logger.error(error_msg)
            record_data_quality_issue("econ_cal", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("econ_cal", e)
        logger.error(error_msg)
        record_data_quality_issue("econ_cal", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_risk_metrics(c):
    """API-only risk metrics. Fail-fast: error only on failure."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("risk"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("risk", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        return {
            "date": d.get("report_date"),
            "var95": safe_float(d.get("var_pct_95")),
            "cvar95": safe_float(d.get("cvar_pct_95")),
            "svar": safe_float(d.get("stressed_var_pct")),
            "beta": safe_float(d.get("portfolio_beta")),
            "conc5": safe_float(d.get("top_5_concentration")),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("risk", e)
        logger.error(error_msg)
        record_data_quality_issue("risk", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_perf_analytics(c):
    """API-only performance analytics. Fail-fast: error only on failure."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("perf_anl"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("perf_anl", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        return {
            "sharpe252": safe_float(d.get("rolling_sharpe_252d")),
            "sortino": safe_float(d.get("rolling_sortino_252d")),
            "calmar": safe_float(d.get("calmar_ratio")),
            "wr50": safe_float(d.get("win_rate_50t")),
            "avg_w_r": safe_float(d.get("avg_win_r_50t")),
            "avg_l_r": safe_float(d.get("avg_loss_r_50t")),
            "expectancy": safe_float(d.get("expectancy")),
            "maxdd": safe_float(d.get("max_drawdown_pct")),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("perf_anl", e)
        logger.error(error_msg)
        record_data_quality_issue("perf_anl", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_signal_eval(c):
    """Fetch signal evaluation stats from API."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("sig_eval"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sig_eval", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        return {
            "total": safe_int(result.get("total")),
            "t1": safe_int(result.get("t1")),
            "t2": safe_int(result.get("t2")),
            "t3": safe_int(result.get("t3")),
            "t4": safe_int(result.get("t4")),
            "t5": safe_int(result.get("t5")),
            "avg_score": safe_float(result.get("avg_score")),
            "date": result.get("signal_date"),
            "rejected": result.get("rejected"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sig_eval", e)
        logger.error(error_msg)
        record_data_quality_issue("sig_eval", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_sector_rotation(c):
    """Fetch sector rotation signal from API. Fail-fast: error only on failure."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("srank"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sec_rot", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        if not isinstance(raw, dict):
            error_msg = f"Sector rotation API response: expected dict, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        items = raw.get("items")
        if items is None:
            error_msg = "Sector rotation API response missing required 'items' field"
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "missing_items_field")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(items, list):
            error_msg = f"Sector rotation 'items' field must be list, got {type(items).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "items_not_list")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No sector rotation data available (items array is empty)"
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "empty_items")
            return FetcherValidator.build_error_response(error_msg)

        row = items[0]
        return {
            "date": row.get("date"),
            "signal": row.get("signal", ""),
            "strength": safe_float(row.get("spread"), default=None),
            "weeks": row.get("weeks_persistent", 1),
            "def_score": safe_float(row.get("defensive_lead_score"), default=0),
            "cyc_score": safe_float(row.get("cyclical_weak_score"), default=0),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sec_rot", e)
        logger.error(error_msg)
        record_data_quality_issue("sec_rot", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_industry_ranking(c):
    """Fetch industry rankings. API returns {items: [{industry, sector,
    current_rank, overall_rank, rank_1w_ago, rank_4w_ago}], total: N}."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("irank"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("irank", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Industry ranking API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("irank", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Industry ranking API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("irank", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No industry ranking data available"
            logger.error(error_msg)
            record_data_quality_issue("irank", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("irank", e)
        logger.error(error_msg)
        record_data_quality_issue("irank", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_exec_history(c):
    """Fetch recent execution history. Panel expects a flat list (not wrapped
    in a dict) so it can do valid_hist[:7] directly."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(
            _get_endpoint_path("exec_hist"),
            params={"days": 7, "limit": 10},
        )

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("exec_hist", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Execution history API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("exec_hist", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
            if not items:
                error_msg = "No execution history available"
                logger.error(error_msg)
                record_data_quality_issue("exec_hist", "validation", "no_items")
                return FetcherValidator.build_error_response(error_msg)
            return items
        if isinstance(raw, list):
            if not raw:
                error_msg = "Execution history API returned empty list"
                logger.error(error_msg)
                record_data_quality_issue("exec_hist", "validation", "empty_list")
                return FetcherValidator.build_error_response(error_msg)
            return raw
        error_msg = f"Execution history API response unexpected type: expected list or dict, got {type(raw).__name__}"
        logger.error(error_msg)
        record_data_quality_issue("exec_hist", "validation", "invalid_response_type")
        return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = _format_fetcher_error("exec_hist", e)
        logger.error(error_msg)
        record_data_quality_issue("exec_hist", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_scores(c):
    """Fetch top stock scores from /api/scores. Used by signals panel for composite score display."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        top_data = api_call("/api/scores", params={"limit": 50, "sortOrder": "desc"})

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(top_data)
        if is_error:
            record_data_quality_issue("scores", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Validate response structure - fail-fast if missing items field
        if not isinstance(top_data, dict):
            error_msg = f"Scores API response: expected dict, got {type(top_data).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if "items" not in top_data:
            error_msg = "Scores API response: missing required 'items' field"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "missing_items_field")
            return FetcherValidator.build_error_response(error_msg)

        items = top_data["items"]
        if not isinstance(items, list):
            error_msg = "Scores API response: 'items' field is not a list"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "items_not_list")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No score data available"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"top": items}
    except Exception as e:
        error_msg = _format_fetcher_error("scores", e)
        logger.error(error_msg)
        record_data_quality_issue("scores", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_audit_log(c):
    """Fetch audit log entries. Panel expects a flat list (not wrapped in a
    dict) for direct iteration. API returns {items: [...], total, limit, offset}."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("audit"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("audit", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Audit log API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("audit", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
            if not items:
                error_msg = "No audit log entries available"
                logger.error(error_msg)
                record_data_quality_issue("audit", "validation", "no_items")
                return FetcherValidator.build_error_response(error_msg)
            return items
        if isinstance(raw, list):
            if not raw:
                error_msg = "Audit log API returned empty list"
                logger.error(error_msg)
                record_data_quality_issue("audit", "validation", "empty_list")
                return FetcherValidator.build_error_response(error_msg)
            return raw
        error_msg = f"Audit log API response unexpected type: expected list or dict, got {type(raw).__name__}"
        logger.error(error_msg)
        record_data_quality_issue("audit", "validation", "invalid_response_type")
        return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = _format_fetcher_error("audit", e)
        logger.error(error_msg)
        record_data_quality_issue("audit", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_circuit(c):
    """Fetch circuit breakers from API."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/circuit-breakers")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("cb", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        bs = result.get("breakers")
        if bs is None:
            error_msg = "Circuit breaker API response missing required 'breakers' field"
            logger.error(error_msg)
            record_data_quality_issue("cb", "validation", "missing_breakers_field")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(bs, list):
            error_msg = f"Circuit breaker 'breakers' field must be list, got {type(bs).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("cb", "validation", "breakers_not_list")
            return FetcherValidator.build_error_response(error_msg)

        formatted_bs = []
        for r in bs:
            label = r.get("label") or r.get("breaker_name")
            if not label:
                error_msg = "Circuit breaker entry missing both 'label' and 'breaker_name' fields"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "breaker_missing_label")
                return FetcherValidator.build_error_response(error_msg)

            formatted_bs.append(
                {
                    "lbl": label,
                    "cur": safe_float(r.get("current_value") or r.get("current")),
                    "thr": safe_float(r.get("threshold_value") or r.get("threshold")),
                    "u": r.get("unit", ""),
                    "fired": safe_bool(r.get("is_active") or r.get("triggered")),
                }
            )

        any_triggered = result.get("any_triggered")
        if any_triggered is None:
            error_msg = "Circuit breaker API response missing 'any_triggered' field"
            logger.error(error_msg)
            record_data_quality_issue("cb", "validation", "missing_any_triggered")
            return FetcherValidator.build_error_response(error_msg)

        triggered_count = result.get("triggered_count")
        if triggered_count is None:
            error_msg = "Circuit breaker API response missing 'triggered_count' field"
            logger.error(error_msg)
            record_data_quality_issue("cb", "validation", "missing_triggered_count")
            return FetcherValidator.build_error_response(error_msg)

        return {
            "bs": formatted_bs,
            "any": any_triggered,
            "n": triggered_count,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("cb", e)
        logger.error(error_msg)
        record_data_quality_issue("cb", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


FETCHERS = {
    "run": fetch_run,
    "cfg": fetch_algo_config,
    "mkt": fetch_market,
    "port": fetch_portfolio,
    "perf": fetch_perf,
    "pos": fetch_positions,
    "trades": fetch_recent_trades,
    "sig": fetch_signals,
    "health": fetch_health,
    "cb": fetch_circuit,
    "srank": fetch_sector_ranking,
    "activity": fetch_activity,
    "eco": fetch_economic_pulse,
    "notifs": fetch_notifications,
    "sentiment": fetch_sentiment,
    "econ_cal": fetch_economic_calendar,
    "risk": fetch_risk_metrics,
    "perf_anl": fetch_perf_analytics,
    "sig_eval": fetch_signal_eval,
    "sec_rot": fetch_sector_rotation,
    "algo_metrics": fetch_algo_metrics,
    "irank": fetch_industry_ranking,
    "audit": fetch_audit_log,
    "exec_hist": fetch_exec_history,
    "exp_factors": fetch_exp_factors,
    "scores": fetch_scores,
}


def load_all() -> dict:
    """Load all fetcher data with priority-based execution to prevent RDS connection exhaustion.

    FIXES APPLIED:
    - Issue #1: Removed duplicate api_call() stub
    - Issue #2: Normalized positions data structure {items, count, timestamp}
    - Issue #3: Fetch portfolio metrics from perf API if missing
    - Issue #4: Bounded sector cache with LRU (maxsize=100)
    - Issue #8: Increased thread pool from 8 to 16 workers
    - Issue #9: Increased batch timeout from 100s to 200s
    - C5 FIX: Prioritized fetcher execution (critical first, optional second)

    Issue 10 FIX: Exponential backoff capped at API_MAX_BACKOFF (30s) to prevent runaway delays.
    Issue 11 FIX: Timeout handling ensures orphaned fetchers are marked incomplete and not lost.
    Issue 12 FIX: API calls use retry logic with capped exponential backoff.
    Issue 14 FIX: Consolidated duplicate /api/algo/markets fetches via shared cache.
    Issue #40 FIX: Per-fetcher timeout (critical: 8s, optional: 3s) prevents one slow endpoint from blocking refresh.
    """
    # Clear per-call caches so watch mode gets fresh data on each refresh.
    # _get_data_status_cached() and _get_markets_cached() deduplicate concurrent fetches
    # within one load_all() call but must not persist across refresh cycles.
    _data_status_cache.clear()
    _markets_cache.clear()

    out: dict = {}
    max_retries = 3
    batch_timeout = 200

    # Per-fetcher timeout limits to prevent one slow endpoint from blocking refresh
    fetcher_timeout_seconds = {
        # Critical fetchers: 8 second timeout (must complete)
        "run": 8.0,
        "cfg": 8.0,
        "mkt": 8.0,
        "port": 8.0,
        "perf": 8.0,
        "pos": 8.0,
        "trades": 8.0,
        "sig": 8.0,
        "health": 8.0,
        "cb": 8.0,
        # Optional fetchers: 3 second timeout (nice-to-have)
        "srank": 3.0,
        "activity": 3.0,
        "eco": 3.0,
        "notifs": 3.0,
        "sentiment": 3.0,
        "econ_cal": 3.0,
        "risk": 3.0,
        "perf_anl": 3.0,
        "sig_eval": 3.0,
        "sec_rot": 3.0,
        "algo_metrics": 3.0,
        "irank": 3.0,
        "audit": 3.0,
        "exec_hist": 3.0,
        "exp_factors": 3.0,
        "scores": 3.0,
    }

    # Categorize fetchers by priority to reduce concurrent RDS connections
    critical_fetchers = {
        "run",
        "cfg",
        "mkt",
        "port",
        "perf",
        "pos",
        "trades",
        "sig",
        "health",
        "cb",
    }
    optional_fetchers = {
        "srank",
        "activity",
        "eco",
        "notifs",
        "sentiment",
        "econ_cal",
        "risk",
        "perf_anl",
        "sig_eval",
        "sec_rot",
        "algo_metrics",
        "irank",
        "audit",
        "exec_hist",
        "exp_factors",
        "scores",
    }

    def one(name, fn, timeout_sec):
        """Execute fetcher with exponential backoff retry and per-fetcher timeout.

        Issue #40 FIX: Individual timeout per fetcher prevents one slow endpoint from
        blocking others. If fetcher exceeds timeout, immediately return error instead of
        waiting for global batch timeout.
        """
        start_time = time.monotonic()

        for attempt in range(max_retries + 1):
            # Check if per-fetcher timeout has been exceeded
            elapsed = time.monotonic() - start_time
            if elapsed > timeout_sec:
                meta = FETCHER_METADATA.get(name)
                endpoint = meta.get("endpoint", "unknown endpoint")
                timeout_msg = f"Fetcher {name} ({endpoint}) exceeded per-fetcher timeout ({timeout_sec:.1f}s)"
                logger.warning(timeout_msg)
                return name, {"_error": timeout_msg}

            try:
                return name, fn(None)
            except Exception as e:
                if attempt < max_retries:
                    base_backoff = (2**attempt) + random.random() * (2**attempt)
                    backoff = min(base_backoff, API_MAX_BACKOFF)
                    meta = FETCHER_METADATA.get(name)
                    endpoint = meta.get("endpoint", "unknown endpoint")
                    logger.warning(
                        f"Fetcher {name} ({endpoint}) retry {attempt + 1}/{max_retries} (backoff {backoff:.1f}s): {type(e).__name__}"
                    )
                    time.sleep(backoff)
                    continue
                error_msg = _format_fetcher_error(name, e)
                logger.error(error_msg)
                return name, {"_error": error_msg}

    # Execute critical fetchers first (max 10 concurrent to reduce RDS load)
    critical_start_time = time.monotonic()
    with ThreadPoolExecutor(max_workers=10) as pool:
        critical_items = {k: v for k, v in FETCHERS.items() if k in critical_fetchers}
        futures = {pool.submit(one, k, v, fetcher_timeout_seconds.get(k, 8.0)): k for k, v in critical_items.items()}
        pending_futures = set(futures.keys())

        try:
            for f in as_completed(futures, timeout=batch_timeout):
                try:
                    n, d = f.result()
                    out[n] = d
                    pending_futures.discard(f)
                except Exception as e:
                    k = futures[f]
                    error_msg = _format_fetcher_error(k, e)
                    logger.error(f"Thread exception: {error_msg}")
                    out[k] = {"_error": error_msg}
                    pending_futures.discard(f)
        except TimeoutError:
            logger.error(f"load_all critical timeout after {batch_timeout}s")
            for f in pending_futures:
                k_opt = futures.get(f)
                if k_opt and not f.done():
                    k = k_opt
                    meta = FETCHER_METADATA.get(k)
                    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
                    desc = meta.get("desc", "") if meta else ""
                    context = f"{endpoint}" + (f": {desc}" if desc else "")
                    timeout_msg = f"Fetcher {k} ({context}) timed out (exceeded {batch_timeout}s)"
                    logger.warning(timeout_msg)
                    out[k] = {"_error": timeout_msg}

    # Execute optional fetchers with reduced concurrency
    # Calculate remaining time based on actual elapsed time, not number of fetchers
    critical_elapsed = time.monotonic() - critical_start_time
    remaining_time = max(60, batch_timeout - critical_elapsed)
    optional_timeout = remaining_time
    with ThreadPoolExecutor(max_workers=6) as pool:
        optional_items = {k: v for k, v in FETCHERS.items() if k in optional_fetchers}
        futures = {pool.submit(one, k, v, fetcher_timeout_seconds.get(k, 3.0)): k for k, v in optional_items.items()}
        pending_futures = set(futures.keys())

        try:
            for f in as_completed(futures, timeout=max(60, optional_timeout)):
                try:
                    n, d = f.result()
                    out[n] = d
                    pending_futures.discard(f)
                except Exception as e:
                    k = futures[f]
                    error_msg = _format_fetcher_error(k, e)
                    logger.debug(f"Optional fetcher failed: {error_msg}")
                    out[k] = {"_error": error_msg}
                    pending_futures.discard(f)
        except TimeoutError:
            logger.debug(f"load_all optional timeout - {len(pending_futures)} fetchers incomplete")
            for f in pending_futures:
                k_opt = futures.get(f)
                if k_opt and not f.done():
                    k = k_opt
                    meta = FETCHER_METADATA.get(k)
                    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
                    desc = meta.get("desc", "") if meta else ""
                    context = f"{endpoint}" + (f": {desc}" if desc else "")
                    timeout_msg = f"Optional fetcher {k} ({context}) timed out (exceeded {max(60, optional_timeout)}s)"
                    out[k] = {"_error": timeout_msg}

    return out
