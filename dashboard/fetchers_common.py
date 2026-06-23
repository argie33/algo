"""Shared utilities for dashboard fetchers - metadata, error handling, validation."""

import logging
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from .api_data_layer import api_call

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def record_data_quality_issue(*args: object, **kwargs: object) -> None:
    """Placeholder for data quality issue recording."""


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


def format_fetcher_error(fetcher_name: str, error: Exception) -> str:
    """Format fetcher error with endpoint context for better troubleshooting."""
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


def get_endpoint_path(fetcher_key: str, params: dict[str, Any] | None = None) -> str:
    """Map fetcher key to full endpoint path."""
    meta = FETCHER_METADATA.get(fetcher_key)
    if not meta:
        return fetcher_key
    endpoint = meta.get("endpoint", "")
    if not endpoint:
        return fetcher_key
    return endpoint


def is_api_error(response: dict[str, Any]) -> bool:
    """Check if API response indicates an error."""
    return "_error" in response or response.get("statusCode", 200) >= 400


def get_error_message(response: dict[str, Any]) -> str:
    """Extract error message from API response."""
    if "_error" in response:
        error_val = response["_error"]
        return str(error_val) if error_val is not None else "Unknown API error"
    msg = response.get("message")
    status = response.get("statusCode")
    if msg:
        return str(msg)
    return f"API error {status if status is not None else 'unknown'}"


def validate_required_fields(data_dict: Any, required_fields: list[str], source_name: str) -> dict[str, Any] | None:
    """Validate that all required fields exist in response dict. Return error dict if missing."""
    if not isinstance(data_dict, dict):
        return {"_error": f"{source_name}: expected dict but got {type(data_dict).__name__}"}
    missing = [f for f in required_fields if f not in data_dict]
    if missing:
        return {"_error": f"{source_name}: missing fields {missing}"}
    return None  # No error


def check_data_freshness(data_dict: Any, max_age_seconds: int = 3600) -> dict[str, Any] | None:
    """Check if data timestamp is within acceptable age. Returns error dict if stale."""
    if not isinstance(data_dict, dict):
        return None
    ts = data_dict.get("timestamp")
    if not ts:
        return None
    try:
        ts_dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        age = (datetime.now(ts_dt.tzinfo or ET) - ts_dt).total_seconds()
        if age > max_age_seconds:
            return {"_error": f"Data too stale: {age:.0f}s old (max {max_age_seconds}s)"}
    except (ValueError, TypeError, AttributeError):
        pass
    return None


# Cache for market data (used by both fetch_market and fetch_exp_factors)
_market_cache: dict[str, object] = {}
_market_cache_lock = __import__("threading").Lock()


def get_markets_cached() -> dict[str, Any]:
    """Get cached market data or fetch fresh."""
    with _market_cache_lock:
        cached = _market_cache.get("_data")
        cached_time = _market_cache.get("_time", 0)
        now = __import__("time").time()

        if cached and (now - cached_time) < 5:  # 5 second cache
            return cast(dict[str, Any], cached)

    mkt = api_call("/api/algo/markets")
    with _market_cache_lock:
        _market_cache["_data"] = mkt
        _market_cache["_time"] = __import__("time").time()
    return mkt


# Cache for data status (used by fetch_health)
_data_status_cache: dict[str, object] = {}
_data_status_cache_lock = __import__("threading").Lock()


def get_data_status_cached() -> dict[str, Any]:
    """Get cached data status or fetch fresh."""
    with _data_status_cache_lock:
        cached = _data_status_cache.get("_data")
        cached_time = _data_status_cache.get("_time", 0)
        now = __import__("time").time()

        if cached and (now - cached_time) < 10:  # 10 second cache
            return cast(dict[str, Any], cached)

    status = api_call("/api/algo/data-status")
    with _data_status_cache_lock:
        _data_status_cache["_data"] = status
        _data_status_cache["_time"] = __import__("time").time()
    return status
