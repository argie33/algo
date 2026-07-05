"""Shared utilities for dashboard fetchers - metadata, error handling, validation."""

import logging
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from .api_data_layer import api_call

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def record_data_quality_issue(fetcher: str, issue_type: str, issue_subtype: str, details: str = "") -> None:
    msg = f"[DATA_QUALITY] {fetcher}: {issue_type}/{issue_subtype}"
    if details:
        msg += f" — {details[:80]}"
    logger.warning(msg)


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
    meta = FETCHER_METADATA.get(fetcher_name)
    if not meta:
        raise ValueError(
            f"CRITICAL: Fetcher metadata missing for '{fetcher_name}'. "
            f"Cannot format error without fetcher configuration. "
            f"Check FETCHER_METADATA registration."
        )

    endpoint = meta.get("endpoint")
    if not endpoint:
        raise ValueError(
            f"CRITICAL: Fetcher '{fetcher_name}' missing required 'endpoint' metadata. "
            f"Cannot format error without endpoint configuration. "
            f"Check FETCHER_METADATA['{fetcher_name}'] has 'endpoint' key."
        )

    desc = meta.get("desc")
    if not desc:
        raise ValueError(
            f"CRITICAL: Fetcher '{fetcher_name}' missing required 'desc' metadata. "
            f"Cannot format error without fetcher description. "
            f"Check FETCHER_METADATA['{fetcher_name}'] has 'desc' key."
        )

    error_type = type(error).__name__
    error_msg = str(error)

    context = f"{endpoint}: {desc}"

    if error_msg:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}: {error_msg}"
    else:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}"


def get_endpoint_path(fetcher_key: str, params: dict[str, Any] | None = None) -> str:
    meta = FETCHER_METADATA.get(fetcher_key)
    if not meta:
        raise ValueError(
            f"CRITICAL: Fetcher metadata missing for '{fetcher_key}'. "
            f"Cannot resolve endpoint without fetcher configuration. "
            f"Check FETCHER_METADATA registration."
        )
    endpoint = meta.get("endpoint")
    if not endpoint:
        raise ValueError(
            f"CRITICAL: Fetcher '{fetcher_key}' missing required 'endpoint' metadata. "
            f"Cannot route request without valid endpoint configuration. "
            f"Check FETCHER_METADATA['{fetcher_key}'] has 'endpoint' key."
        )
    return endpoint


def is_api_error(response: dict[str, Any]) -> bool:
    # CRITICAL: statusCode is REQUIRED. Never default to 200 (success).
    if "_error" in response:
        return True
    status = response.get("statusCode")
    if status is None:
        # CRITICAL: Missing statusCode means we can't validate the response
        # This could be a schema change, API error, or malformed response
        logger.warning(
            "API response missing 'statusCode' field — cannot determine validity. "
            "Treating as error to prevent silent acceptance of malformed responses."
        )
        return True  # Fail-fast: treat missing statusCode as error
    if not isinstance(status, int):
        try:
            status = int(status)
        except (ValueError, TypeError):
            logger.warning(f"API statusCode '{status}' is not numeric — cannot parse. Treating as error.")
            return True  # Fail-fast: unparseable status is an error
    return status >= 400


def get_error_message(response: dict[str, Any]) -> str:
    if "_error" in response:
        error_val = response["_error"]
        return str(error_val) if error_val is not None else "Unknown API error"
    msg = response.get("message")
    status = response.get("statusCode")
    if msg:
        return str(msg)
    return f"API error {status if status is not None else 'unknown'}"


def check_data_freshness(data_dict: Any, max_age_seconds: int = 3600) -> None:
    # CRITICAL: Fail fast on stale data instead of returning error dicts that callers might ignore.
    if not isinstance(data_dict, dict):
        raise ValueError(f"Expected dict for freshness check, got {type(data_dict).__name__}")
    ts = data_dict.get("timestamp")
    if not ts:
        raise ValueError("Data timestamp missing (required to validate data freshness)")
    try:
        ts_dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        age = (datetime.now(ts_dt.tzinfo or ET) - ts_dt).total_seconds()
        if age > max_age_seconds:
            raise ValueError(
                f"Data too stale: {age:.0f}s old (max {max_age_seconds}s). "
                "Cannot use stale data for trading decisions — must use fresh data or show error to user."
            )
    except (ValueError, TypeError, AttributeError) as e:
        if isinstance(e, ValueError) and "too stale" in str(e):
            raise
        raise ValueError(f"Cannot parse data timestamp {ts!r}: {e}") from e


_market_cache: dict[str, object] = {}
_market_cache_lock = __import__("threading").Lock()


def get_markets_cached() -> dict[str, Any]:
    with _market_cache_lock:
        cached = _market_cache.get("_data")
        now = __import__("time").time()
        # CRITICAL: Validate cache time is present AND numeric; missing/invalid _time indicates corrupted cache.
        if cached and "_time" in _market_cache:
            cache_time = _market_cache["_time"]
            if not isinstance(cache_time, (int, float)):
                logger.warning(
                    f"[MARKET_CACHE] Corrupted cache: _time is {type(cache_time).__name__}, not numeric. Force refresh."
                )
            elif (now - cache_time) < 5:
                if not isinstance(cached, dict):
                    logger.warning(
                        f"Market cache corrupted: _data is {type(cached).__name__}, not dict. Force refresh."
                    )
                else:
                    return cast(dict[str, Any], cached)

    mkt = api_call("/api/algo/markets")
    with _market_cache_lock:
        _market_cache["_data"] = mkt
        _market_cache["_time"] = __import__("time").time()
    return mkt


_data_status_cache: dict[str, object] = {}
_data_status_cache_lock = __import__("threading").Lock()


def get_data_status_cached() -> dict[str, Any]:
    with _data_status_cache_lock:
        cached = _data_status_cache.get("_data")
        now = __import__("time").time()
        # CRITICAL: Validate cache time is present AND numeric; missing/invalid _time indicates corrupted cache.
        if cached and "_time" in _data_status_cache:
            cache_time = _data_status_cache["_time"]
            if isinstance(cache_time, (int, float)) and (now - cache_time) < 10:
                return cast(dict[str, Any], cached)
            elif not isinstance(cache_time, (int, float)):
                logger.warning(
                    f"[DATA_STATUS_CACHE] Corrupted cache: _time is {type(cache_time).__name__}, not numeric. Force refresh."
                )

    status = api_call("/api/algo/data-status")
    with _data_status_cache_lock:
        _data_status_cache["_data"] = status
        _data_status_cache["_time"] = __import__("time").time()
    return status
