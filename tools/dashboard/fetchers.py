"""Fetcher functions for dashboard data from API endpoints."""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")

from .api_data_layer import API_MAX_BACKOFF, api_call
from .data_validation import (
    StrictValidationError,
    safe_bool,
    safe_float,
    safe_float_strict,
    safe_int,
    safe_int_strict,
    safe_json_parse,
)
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
    meta = FETCHER_METADATA.get(fetcher_name, {})
    endpoint = meta.get("endpoint", "unknown endpoint")
    desc = meta.get("desc", "")

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
        return response["_error"]
    # Extract from statusCode-based error response
    return response.get("message", f"API error {response.get('statusCode', 'unknown')}")


def fetch_run(c):
    try:
        data = api_call("/api/algo/last-run")
        if _is_api_error(data):
            return data
        # api_call already returns unwrapped data (statusCode + fields at top level)
        inner = data
        # Phases is required — fail if missing (Issue #5)
        if "phases" not in inner:
            error_msg = "Last-run API response missing required field: phases"
            logger.error(error_msg)
            return {"_error": error_msg}
        phases = inner.get("phases") or []
        halted_phases = [p for p in phases if p.get("status") in ("halt", "halted")]
        errored_phases = [p for p in phases if p.get("status") == "error"]
        completed_phases = [p for p in phases if p.get("status") == "success"]
        halt_reason = halted_phases[0].get("summary") if halted_phases else None
        # Timestamps are required — fail if all are missing (Issue #6)
        run_at = inner.get("run_at") or inner.get("completed_at") or inner.get("started_at")
        if not run_at:
            error_msg = "Last-run API response missing all timestamp fields (run_at, completed_at, started_at)"
            logger.error(error_msg)
            return {"_error": error_msg}
        # Success and halted flags are required — fail if missing (Issue #7)
        if "success" not in inner:
            error_msg = "Last-run API response missing required field: success"
            logger.error(error_msg)
            return {"_error": error_msg}
        if "halted" not in inner:
            error_msg = "Last-run API response missing required field: halted"
            logger.error(error_msg)
            return {"_error": error_msg}
        # errored: use API field if present, otherwise derive from phase data
        api_errored = inner.get("errored")
        derived_errored = bool(errored_phases) or (
            not inner.get("success") and not inner.get("halted") and bool(phases)
        )
        return {
            "run_id": inner.get("run_id"),
            "run_at": run_at,
            "success": inner.get("success"),
            "halted": inner.get("halted"),
            "errored": api_errored if api_errored is not None else derived_errored,
            "summary": inner.get("summary"),
            "halt_reason": halt_reason,
            "phases_completed": [p.get("action_type") for p in completed_phases],
            "phases_halted": [p.get("action_type") for p in halted_phases],
            "phases_errored": [p.get("action_type") for p in errored_phases],
            "phase_results": phases,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("run", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_algo_config(c):
    """AWS-only algo configuration (fail-fast: error if unavailable)."""
    try:
        data = api_call("/api/algo/config")
        if _is_api_error(data):
            return data
        raw = data
        if not isinstance(raw, dict):
            return {"_error": "Config response is not a dict"}
        # API returns {items: [{key, value, value_type, ...}], total: N}
        items = raw.get("items", [])
        if not items:
            error_msg = "Config API response has no items (empty config)"
            logger.error(error_msg)
            return {"_error": error_msg}
        cfg = {i["key"]: i.get("value") for i in items if "key" in i}
        # Issue #8: enable_algo is REQUIRED — no default to True (fail-closed)
        if "enable_algo" not in cfg:
            error_msg = "Config missing required field: enable_algo"
            logger.error(error_msg)
            return {"_error": error_msg}
        # Issue #10: All critical config values required; no silent None
        required_config = [
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
            return {"_error": error_msg}
        # Boolean string conversion
        en_raw = cfg.get("enable_algo")
        enabled = str(en_raw).lower() in ("true", "1", "yes") if en_raw is not None else False
        return {
            "enabled": enabled,
            "mode": cfg.get("execution_mode"),
            "max_pos_pct": safe_float(cfg.get("max_position_size_pct")),
            "max_pos_n": safe_int(cfg.get("max_positions")),
            "max_sec_n": safe_int(cfg.get("max_positions_per_sector")),
            "min_score": safe_float(cfg.get("min_swing_score")),
            "base_risk": safe_float(cfg.get("base_risk_pct")),
            "t1_r": safe_float(cfg.get("t1_target_r_multiple")),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("cfg", e)
        logger.error(error_msg)
        return {"_error": error_msg}


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
    try:
        mkt = _get_markets_cached()
        if mkt.get("_error"):
            record_data_quality_issue("market", "api_call", "api_error", mkt.get("_error"))
            return mkt
        # API response is unwrapped so data is at top level (statusCode + fields)
        current = mkt.get("current") or {}
        market_health = mkt.get("market_health") or {}

        # VIX and SPY are critical - fail if missing or invalid
        try:
            vix_raw = market_health.get("vix_level")
            spy_raw = current.get("spy_close")

            # Both SPY and VIX are REQUIRED for position sizing
            if vix_raw is None:
                error_msg = "Critical market data missing: VIX level required but not provided by API"
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "missing_vix")
                return {"_error": error_msg}
            if spy_raw is None:
                error_msg = "Critical market data missing: SPY close required but not provided by API"
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "missing_spy")
                return {"_error": error_msg}

            vix = safe_float_strict(vix_raw, "market.vix_level")
            spy = safe_float_strict(spy_raw, "market.spy_close")

            if vix <= 0:
                error_msg = f"Critical market data invalid: VIX = {vix} (must be > 0). Data quality issue in yfinance pipeline."
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "invalid_vix", f"vix={vix}")
                return {"_error": error_msg}
        except StrictValidationError as e:
            error_msg = f"Critical market data conversion failed: {e!s}"
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "conversion_failed", str(e))
            return {"_error": error_msg}

        # Issue #9: Market regime is REQUIRED — no fallback to "unknown"
        tier = current.get("regime")
        if not tier:
            error_msg = (
                f"[MARKET CRITICAL] Market regime missing from current.regime. "
                f"Cannot position size without regime tier. "
                f"Current keys: {list(current.keys())}"
            )
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "missing_regime")
            return {"_error": error_msg}

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
    try:
        data = api_call("/api/algo/portfolio")
        if _is_api_error(data):
            record_data_quality_issue("portfolio", "api_call", "api_error", _get_error_message(data))
            return data
        port = data

        # Check data freshness before validation (portfolio data > 5 days old is stale;
        # algo only runs on trading days so a long weekend + Monday holiday can mean
        # 4 calendar days between runs)
        snapshot_date = port.get("last_run")
        is_fresh, freshness_error = _check_data_freshness(
            snapshot_date, max_age_seconds=432000, source_name="Portfolio"
        )
        if not is_fresh:
            logger.warning(freshness_error)
            record_data_quality_issue("portfolio", "timestamp", "data_stale", freshness_error)
            return {
                "_error": freshness_error,
                "_data_stale": True,
            }

        required_fields = ["total_portfolio_value", "total_cash", "position_count"]
        validation_error = _validate_required_fields(port, required_fields, "fetch_portfolio")
        if validation_error:
            for field in required_fields:
                if field not in port or port[field] is None:
                    record_data_quality_issue("portfolio", field, "missing_required_field")
            return validation_error

        # Strict conversion for critical financial fields
        try:
            tpv = safe_float_strict(port["total_portfolio_value"], "portfolio.total_portfolio_value")
            tc = safe_float_strict(port["total_cash"], "portfolio.total_cash")
            pc = safe_int_strict(port["position_count"], "portfolio.position_count")
        except StrictValidationError as e:
            error_msg = f"Portfolio data conversion failed: {e!s}"
            logger.error(error_msg)
            record_data_quality_issue("portfolio", "type_conversion", "conversion_failed", str(e))
            return {"_error": error_msg}

        return {
            "snapshot_date": port.get("last_run"),
            "total_portfolio_value": tpv,
            "total_cash": tc,
            "position_count": pc,
            "daily_return_pct": safe_float(port.get("daily_return_pct"), default=None),
            "unrealized_pnl_pct": safe_float((port.get("unrealized_pnl") or {}).get("total_pct"), default=None),
            "cumulative_return_pct": safe_float(port.get("cumulative_return_pct"), default=None),
            "max_drawdown_pct": safe_float(port.get("max_drawdown_pct"), default=None),
            "largest_position_pct": safe_float(port.get("largest_position_pct"), default=None),
            "data_age_seconds": port.get("data_age_seconds"),
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
    try:
        data = api_call("/api/algo/performance")
        if _is_api_error(data):
            # 503 means no performance data yet (no completed trades) — mark as no data
            if "503" in str(_get_error_message(data)):
                return {"_no_data": True}
            record_data_quality_issue("per", "api_call", "api_error", _get_error_message(data))
            return data
        perf = data

        # Check data freshness (performance data > 1 hour old is stale)
        perf_timestamp = perf.get("timestamp") or perf.get("last_updated")
        is_fresh, freshness_error = _check_data_freshness(
            perf_timestamp, max_age_seconds=3600, source_name="Performance"
        )
        if not is_fresh:
            logger.warning(freshness_error)
            record_data_quality_issue("per", "timestamp", "data_stale", freshness_error)
            return {
                "_error": freshness_error,
                "_data_stale": True,
            }

        required_fields = ["total_trades", "winning_trades", "losing_trades"]
        validation_error = _validate_required_fields(perf, required_fields, "fetch_perf")
        if validation_error:
            for field in required_fields:
                if field not in perf or perf[field] is None:
                    record_data_quality_issue("per", field, "missing_required_field")
            return validation_error

        # Strict conversion for critical trade count fields
        try:
            n = safe_int_strict(perf["total_trades"], "perf.total_trades")
            w = safe_int_strict(perf["winning_trades"], "perf.winning_trades")
            losing = safe_int_strict(perf["losing_trades"], "perf.losing_trades")
        except StrictValidationError as e:
            error_msg = f"Performance data conversion failed: {e!s}"
            logger.error(error_msg)
            record_data_quality_issue("per", "type_conversion", "conversion_failed", str(e))
            return {"_error": error_msg}

        return {
            "n": n,
            "w": w,
            "l": losing,
            "wr": safe_float(perf.get("win_rate_pct"), default=None),
            "open_count": safe_int(perf.get("open_positions"), default=None),
            "pnl": safe_float(perf.get("total_pnl_dollars"), default=None),
            "unrealized_pnl": safe_float(perf.get("unrealized_pnl"), default=None),
            "streak": safe_int(perf.get("current_streak"), default=None),
            "sharpe": safe_float(perf.get("sharpe_annualized"), default=None),
            "maxdd": safe_float(perf.get("max_drawdown_pct"), default=None),
            "avg_win": safe_float(perf.get("avg_win_pct"), default=None),
            "avg_loss": safe_float(perf.get("avg_loss_pct"), default=None),
            "profit_factor": safe_float(perf.get("profit_factor"), default=None),
            "expectancy": safe_float(perf.get("expectancy_r"), default=None),
            "avg_r": safe_float(perf.get("expectancy_r"), default=None),
            "equity_vals": perf.get("equity_vals") or [],
            "recent_rets": perf.get("recent_rets") or [],
        }
    except Exception as e:
        error_msg = _format_fetcher_error("perf", e)
        logger.error(error_msg)
        record_data_quality_issue("per", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_positions(c):
    """Fetch positions via AWS API only (fail-fast: error if unavailable)."""
    try:
        data = api_call(_get_endpoint_path("pos"))
        if _is_api_error(data):
            return data
        result = data
        if isinstance(result, dict):
            items = result.get("items")
            if not isinstance(items, list):
                return {"_error": "Positions API response: 'items' field is not a list"}
        elif isinstance(result, list):
            items = result
        else:
            return {"_error": "Positions API response: expected dict or list"}
        return {"items": items, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = _format_fetcher_error("pos", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_recent_trades(c):
    """AWS-only trades data. Fail-fast: error only on failure.

    Returns closed trades only — open positions are in the positions panel.
    Note: 503 means no closed trades yet (algo just started) — treat as no data.
    """
    try:
        data = api_call(
            _get_endpoint_path("trades"),
            params={"limit": 30, "status": "closed"},
        )
        if _is_api_error(data):
            error_msg = _get_error_message(data)
            # 503 means no trades data yet (algo just started or no closed trades)
            if "503" in str(error_msg):
                return {"_no_data": True}
            return {"_error": error_msg}
        result = data
        if isinstance(result, dict):
            trades = result.get("items")
            if not isinstance(trades, list):
                return {"_error": "Trades API response: 'items' field is not a list"}
        elif isinstance(result, list):
            trades = result
        else:
            return {"_error": "Trades API response: expected dict or list"}
        return {"items": trades, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = _format_fetcher_error("trades", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_signals(c):
    """Fetch dashboard signals from API. Fail-fast: error only on failure."""
    try:
        data = api_call(_get_endpoint_path("sig"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        if not data:
            return {"_error": "No data returned from /api/algo/dashboard-signals"}

        result = data
        buy_sigs = result.get("buy_sigs") or []
        near = result.get("near") or []
        top_a = result.get("top_a") or []
        trend = result.get("trend") or []
        grades = result.get("grades") or {}
        return {
            "n": result.get("n", len(buy_sigs)),
            "total": result.get("total", result.get("n", len(buy_sigs))),
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
        return {"_error": error_msg}


def fetch_sector_ranking(c):
    """Fetch per-sector rankings from /api/sectors (fail-fast: error if unavailable)."""
    try:
        data = api_call("/api/sectors")
        if _is_api_error(data):
            return data
        raw = data
        if isinstance(raw, dict):
            items = raw.get("items") or []
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("srank", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_activity(c):
    """Fetch activity from audit log API (fail-fast: error if unavailable)."""
    try:
        data = api_call(_get_endpoint_path("activity"))
        if _is_api_error(data):
            return data
        raw = data
        items = raw.get("items") or [] if isinstance(raw, dict) else []
        run_at = items[0].get("action_date") if items else None
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
        return {"_error": error_msg}


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
    try:
        data = _get_data_status_cached()
        if _is_api_error(data):
            return data
        inner = data
        if not isinstance(inner, dict):
            inner = {}
        raw_sources = inner.get("sources") or []
        critical_stale = inner.get("critical_stale") or []
        sources = []
        for s in raw_sources:
            name = s.get("name", "")
            # API now returns role (CRIT/IMP/NORM); fall back to freshness_config if absent
            role = s.get("role")
            if not role:
                try:
                    from utils.validation.freshness_config import FRESHNESS_RULES as _FR

                    r = _FR.get(name, {})
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
        return {
            "items": sources,
            "ready_to_trade": inner.get("ready_to_trade"),
            "summary": inner.get("summary", {}),
            "critical_stale": critical_stale,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("health", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_exp_factors(c):
    """Fetch 12-factor market exposure data. Uses /api/algo/markets (public, already fetched).

    Extracts factors from data.current.factors which has the full 12-factor breakdown
    needed by the exposure panel.

    Issue 14 FIX: Uses cached markets endpoint to avoid duplicate API calls
    when fetch_market also needs the same data.
    """
    try:
        data = _get_markets_cached()
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        # Response: {statusCode, data: {current: {exposure_pct, raw_score, regime, factors}, ...}}
        inner = data
        if not isinstance(inner, dict):
            return {"_error": "Unexpected response format from markets endpoint"}
        if "current" not in inner:
            return {"_error": "Missing 'current' field in markets response"}
        current = inner.get("current")
        return {
            "exposure_pct": safe_float(current.get("exposure_pct"), default=None),
            "raw_score": safe_float(current.get("raw_score"), default=None),
            "regime": current.get("regime"),
            "factors": current.get("factors", {}),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("exp_factors", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_economic_pulse(c):
    """Fetch economic macro indicators. Fail-fast: error only on failure.

    Fetches from /api/economic/yield-curve-full and /api/economic/indicators.
    Both endpoints must succeed; partial data is not accepted (can't distinguish
    None from "API error" vs "field missing in successful response").
    """
    try:
        # Fetch yield curve (treasury yields + credit spreads + breakevens)
        yc_data = api_call("/api/economic/yield-curve-full")
        if _is_api_error(yc_data):
            return {"_error": _get_error_message(yc_data)}

        # Fetch macro indicators (CPI, unemployment, fed funds, oil, DXY, etc.)
        ind_data = api_call("/api/economic/indicators")
        if _is_api_error(ind_data):
            return {"_error": _get_error_message(ind_data)}

        # Extract yield curve data
        d = yc_data
        curve = d.get("currentCurve", {}) if isinstance(d, dict) else {}
        spreads = d.get("spreads", {}) if isinstance(d, dict) else {}
        credit = d.get("credit", {}) if isinstance(d, dict) else {}
        credit_latest = credit.get("currentSpreads", {}) if isinstance(credit, dict) else {}
        t10 = safe_float(curve.get("10Y"), default=None)
        t2 = safe_float(curve.get("2Y"), default=None)
        t3m = safe_float(curve.get("3M"), default=None)
        t6m = safe_float(curve.get("6M"), default=None)
        yc_10_2 = safe_float(spreads.get("T10Y2Y"), default=None)
        yc_10_3m = safe_float(spreads.get("T10Y3M"), default=None)
        hy = safe_float(credit_latest.get("BAMLH0A0HYM2"), default=None)
        ig = safe_float(credit_latest.get("BAMLH0A0IG") or credit_latest.get("BAMLC0A0CM"), default=None)

        # Extract indicators data
        d2 = ind_data
        indicators = d2.get("indicators", []) if isinstance(d2, dict) else []
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
        error_msg = _format_fetcher_error("eco", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_algo_metrics(c):
    """Fetch algo metrics. API returns a single dict {date, total_actions,
    entries, exits, avg_signal_score}; panel expects a flat list so it can
    do valid_metrics[0] and iterate over multiple days."""
    try:
        data = api_call(_get_endpoint_path("algo_metrics"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        d = data
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            return [d]
        return []
    except Exception as e:
        error_msg = _format_fetcher_error("algo_metrics", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_notifications(c):
    try:
        data = api_call(_get_endpoint_path("notifs"))
        if _is_api_error(data):
            return data
        raw = data
        items = raw.get("items", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("notifs", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_sentiment(c):
    """API-only sentiment data. Fail-fast: error only on failure."""
    try:
        data = api_call(_get_endpoint_path("sentiment"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        d = data
        if "fear_greed_index" not in d or "label" not in d:
            return {"_error": "Missing required sentiment fields: fear_greed_index, label"}
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
        return {"_error": error_msg}


def fetch_economic_calendar(c):
    """Fetch economic calendar events. API returns {items: [{event_date,
    event_name, country, importance, category, ...}], total: N}."""
    try:
        data = api_call(_get_endpoint_path("econ_cal"))
        if _is_api_error(data):
            return data
        raw = data
        items = raw.get("items", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("econ_cal", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_risk_metrics(c):
    """API-only risk metrics. Fail-fast: error only on failure."""
    try:
        data = api_call(_get_endpoint_path("risk"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
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
        return {"_error": error_msg}


def fetch_perf_analytics(c):
    """API-only performance analytics. Fail-fast: error only on failure."""
    try:
        data = api_call(_get_endpoint_path("perf_anl"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
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
        return {"_error": error_msg}


def fetch_signal_eval(c):
    """Fetch signal evaluation stats from API."""
    try:
        data = api_call(_get_endpoint_path("sig_eval"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
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
            "rejected": result.get("rejected", []),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sig_eval", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_sector_rotation(c):
    """Fetch sector rotation signal from API. Fail-fast: error only on failure."""
    try:
        data = api_call(_get_endpoint_path("srank"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        raw = data
        items = raw.get("items", []) if isinstance(raw, dict) else []
        if not items:
            return {"_error": "No sector rotation data available"}
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
        return {"_error": error_msg}


def fetch_industry_ranking(c):
    """Fetch industry rankings. API returns {items: [{industry, sector,
    current_rank, overall_rank, rank_1w_ago, rank_4w_ago}], total: N}."""
    try:
        data = api_call(_get_endpoint_path("irank"))
        if _is_api_error(data):
            return data
        raw = data
        items = raw.get("items", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        return {"items": items}
    except Exception as e:
        error_msg = _format_fetcher_error("irank", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_exec_history(c):
    """Fetch recent execution history. Panel expects a flat list (not wrapped
    in a dict) so it can do valid_hist[:7] directly."""
    try:
        data = api_call(
            _get_endpoint_path("exec_hist"),
            params={"days": 7, "limit": 10},
        )
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        raw = data
        if isinstance(raw, dict):
            return raw.get("items", [])
        if isinstance(raw, list):
            return raw
        return []
    except Exception as e:
        error_msg = _format_fetcher_error("exec_hist", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_scores(c):
    """Fetch top stock scores from /api/scores. Used by signals panel for composite score display."""
    try:
        top_data = api_call("/api/scores", params={"limit": 50, "sortOrder": "desc"})

        if _is_api_error(top_data):
            return {"_error": _get_error_message(top_data)}

        # API response is unwrapped so items is at top level, not under data
        items = top_data.get("items", [])
        if not items:
            return {"_error": "No score data available"}
        return {"top": items}
    except Exception as e:
        error_msg = _format_fetcher_error("scores", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_audit_log(c):
    """Fetch audit log entries. Panel expects a flat list (not wrapped in a
    dict) for direct iteration. API returns {items: [...], total, limit, offset}."""
    try:
        data = api_call(_get_endpoint_path("audit"))
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        raw = data
        if isinstance(raw, dict):
            return raw.get("items", [])
        if isinstance(raw, list):
            return raw
        return []
    except Exception as e:
        error_msg = _format_fetcher_error("audit", e)
        logger.error(error_msg)
        return {"_error": error_msg}


def fetch_circuit(c):
    """Fetch circuit breakers from API."""
    try:
        data = api_call("/api/algo/circuit-breakers")
        if _is_api_error(data):
            return {"_error": _get_error_message(data)}
        result = data
        bs = result.get("breakers", [])
        formatted_bs = []
        for r in bs:
            formatted_bs.append(
                {
                    "lbl": r.get("label", r.get("breaker_name", "")),
                    "cur": safe_float(r.get("current_value", r.get("current"))),
                    "thr": safe_float(r.get("threshold_value", r.get("threshold"))),
                    "u": r.get("unit", ""),
                    "fired": safe_bool(r.get("is_active", r.get("triggered"))),
                }
            )
        return {
            "bs": formatted_bs,
            "any": result.get("any_triggered", False),
            "n": result.get("triggered_count", 0),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("cb", e)
        logger.error(error_msg)
        return {"_error": error_msg}


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
                meta = FETCHER_METADATA.get(name, {})
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
                    meta = FETCHER_METADATA.get(name, {})
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
                    meta = FETCHER_METADATA.get(k, {})
                    endpoint = meta.get("endpoint", "unknown endpoint")
                    desc = meta.get("desc", "")
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
                    meta = FETCHER_METADATA.get(k, {})
                    endpoint = meta.get("endpoint", "unknown endpoint")
                    desc = meta.get("desc", "")
                    context = f"{endpoint}" + (f": {desc}" if desc else "")
                    timeout_msg = f"Optional fetcher {k} ({context}) timed out (exceeded {max(60, optional_timeout)}s)"
                    out[k] = {"_error": timeout_msg}

    return out
