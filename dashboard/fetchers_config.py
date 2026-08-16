"""Fetcher functions for algo configuration, health, circuit breakers, and status."""

import logging
import threading
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from utils.validation.framework import safe_bool

from .api_data_layer import api_call
from .fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


_data_status_cache: dict[str, Any] = {}
_data_status_lock = threading.Lock()


def clear_data_status_cache() -> None:
    """Clear the data-status cache to ensure fresh data on next fetch.

    Called by load_all() to prevent stale data between refresh cycles.
    """
    with _data_status_lock:
        _data_status_cache.clear()


def _get_data_status_cached() -> dict[str, Any]:
    """Issue 2.2 FIX: Unified fetch for /api/algo/data-status endpoint.

    Both fetch_health and fetch_loader_status need the same endpoint. This
    caches the result to avoid duplicate API calls when both are fetched
    in parallel. Thread-safe with lock to ensure single API call.

    CRITICAL: Never returns stale cache. Health status drives UI warnings. Cache TTL
    is 60 seconds (within-cycle only). After 60s, data is considered stale and fresh
    fetch is required.
    """
    import time as time_module

    now = time_module.time()
    if "result" in _data_status_cache and "_time" in _data_status_cache and (now - _data_status_cache["_time"]) < 60:
        return cast(dict[str, Any], _data_status_cache["result"])

    with _data_status_lock:
        if (
            "result" in _data_status_cache
            and "_time" in _data_status_cache
            and (now - _data_status_cache["_time"]) < 60
        ):
            return cast(dict[str, Any], _data_status_cache["result"])

        try:
            data = api_call(get_endpoint_path("health"))
            _data_status_cache["result"] = data
            _data_status_cache["_time"] = now
            return data
        except Exception as e:
            error_result = {"_error": str(e)}
            logger.error(f"[CONFIG_CACHE] API call failed: {e}. Not caching error response.")
            # CRITICAL: Do not cache error responses - only cache successful data
            # Returning error without caching forces retry on next call
            return error_result


_inventory_cache: dict[str, Any] = {}
_inventory_lock = threading.Lock()
_INVENTORY_CACHE_TTL_SEC = 300  # untracked/missing table set changes rarely; the endpoint
# does a COUNT(*) scan across every untracked table server-side, so polling it every
# refresh cycle (like data-status) would add avoidable DB load for data that's effectively
# static between deploys/migrations.


def fetch_table_inventory(c: None) -> dict[str, Any]:
    """Fetch complete table inventory from /api/admin/inventory (non-critical, optional
    enrichment for the DATA FRESHNESS - EXPANDED panel).

    Surfaces two things no other dashboard data source shows:
    - untracked_tables: tables that exist in the DB but have no data_loader_status row
      at all (never wired into loader monitoring).
    - missing_tables: tables tracked in data_loader_status but that no longer exist in
      the DB (schema drift / a dropped table nobody removed from tracking).
    """
    import time as time_module

    from dashboard.fetcher_validator import FetcherValidator

    now = time_module.time()
    with _inventory_lock:
        cached = _inventory_cache.get("result")
        cached_time = _inventory_cache.get("_time")
        if cached is not None and cached_time is not None and (now - cached_time) < _INVENTORY_CACHE_TTL_SEC:
            return cast(dict[str, Any], cached)

    try:
        data = api_call(get_endpoint_path("inventory"))

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("inventory", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(data, dict):
            error_msg = "Table inventory API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("inventory", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        # api_call() already unwraps the {statusCode, data: {...}} envelope, so `data` here
        # IS list_response()'s inner dict: {items, total, summary, missing_tables, as_of}.
        items = data.get("items")
        if not isinstance(items, list):
            error_msg = "Table inventory API response missing 'items' list"
            logger.error(error_msg)
            record_data_quality_issue("inventory", "validation", "missing_items")
            return FetcherValidator.build_error_response(error_msg)

        untracked_tables = sorted(
            str(t.get("name")) for t in items if isinstance(t, dict) and t.get("type") == "untracked" and t.get("name")
        )
        missing_tables_raw = data.get("missing_tables")
        missing_tables = sorted(str(t) for t in missing_tables_raw) if isinstance(missing_tables_raw, list) else []
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}

        result = {
            "untracked_tables": untracked_tables,
            "missing_tables": missing_tables,
            "summary": summary,
        }
        with _inventory_lock:
            _inventory_cache["result"] = result
            _inventory_cache["_time"] = now
        return result
    except Exception as e:
        error_msg = format_fetcher_error("inventory", e)
        logger.error(error_msg)
        record_data_quality_issue("inventory", "exception", type(e).__name__, str(e))
        # Don't cache errors - force a retry next call (same convention as _get_data_status_cached)
        return FetcherValidator.build_error_response(error_msg)


def fetch_run(c: None) -> dict[str, Any]:
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/last-run")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("run", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        inner = data

        # Validate required fields (halted can be None - that means not halted)
        required = ["phases", "success"]
        valid, error_msg = FetcherValidator.require_fields(inner, required, "fetch_run")
        if not valid:
            logger.error(error_msg)
            record_data_quality_issue("run", "validation", "missing_fields", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        # Validate halted field exists (can be None, but field must exist)
        if "halted" not in inner:
            error_msg = "fetch_run: Missing field 'halted'"
            logger.error(error_msg)
            record_data_quality_issue("run", "validation", "missing_field_halted")
            return FetcherValidator.build_error_response(error_msg)

        phases = inner["phases"]
        halted_phases = [p for p in phases if p.get("status") in ("halt", "halted")]
        errored_phases = [p for p in phases if p.get("status") == "error"]
        completed_phases = [p for p in phases if p.get("status") == "success"]
        halt_reason = halted_phases[0].get("summary") if halted_phases else None

        # CRITICAL: timestamp field is REQUIRED (can be called 'started_at' or 'run_at')
        # Accept both field names to support different API versions
        # FAIL-FAST: Check explicitly for None to distinguish missing from 0/False
        started_at = inner.get("started_at")
        if started_at is None:
            started_at = inner.get("run_at")
        if not started_at:
            error_msg = (
                "Last-run API response missing required timestamp field (started_at or run_at). Available keys: "
                + str(list(inner.keys()))
            )
            logger.error(error_msg)
            record_data_quality_issue("run", "critical_field", "missing_timestamp")
            return FetcherValidator.build_error_response(error_msg)

        # errored: use API field if present, otherwise derive from phase data
        api_errored = inner.get("errored")
        derived_errored = bool(errored_phases) or (not inner["success"] and not inner["halted"] and bool(phases))

        # Extract optional enrichment fields with explicit logging
        run_id = inner.get("run_id")
        if run_id is None:
            logger.debug("Last-run API response missing run_id (optional enrichment)")

        summary = inner.get("summary")
        if summary is None:
            logger.debug("Last-run API response missing summary (optional enrichment)")

        # Check for missing action_type in phase lists (data quality issue if present)
        phase_lists = [(completed_phases, "completed"), (halted_phases, "halted"), (errored_phases, "errored")]
        for phase_list, phase_type in phase_lists:
            missing = [i for i, p in enumerate(phase_list) if p.get("action_type") is None]
            if missing:
                logger.debug(f"[RUN_FETCH] {phase_type} phases missing action_type: {missing}")

        return {
            "_source": "exec_log",
            "run_id": run_id,
            "run_at": started_at,
            "success": inner["success"],
            "halted": inner["halted"],
            "errored": api_errored if api_errored is not None else derived_errored,
            "summary": summary,
            "halt_reason": halt_reason,
            "phases_completed": [p.get("action_type") for p in completed_phases if p.get("action_type") is not None],
            "phases_halted": [p.get("action_type") for p in halted_phases if p.get("action_type") is not None],
            "phases_errored": [p.get("action_type") for p in errored_phases if p.get("action_type") is not None],
            "phase_results": phases,
        }
    except Exception as e:
        error_msg = format_fetcher_error("run", e)
        logger.error(error_msg)
        record_data_quality_issue("run", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_execution_stats(c: None) -> dict[str, Any]:
    """Fetch orchestrator execution stats (last 24 hours).

    Captures success rate, error rate, and recent failure details to make the
    dashboard aware of orchestrator health, not just the latest run status.
    Critical for detecting 24% failure rates that are invisible when only showing
    the most recent run.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/execution/stats?days=1")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("exec_stats", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(data, dict):
            error_msg = "Execution stats API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("exec_stats", "type", "not_dict", type(data).__name__)
            return FetcherValidator.build_error_response(error_msg)

        # Extract stats: total_runs, by_status dict, success_rate, error_rate, halt_rate
        # BUG FIX 2026-08-10: .get(..., 0)/.get(..., {}) defaults silently masked a missing
        # key as "present with value 0/{}", which defeated the very "missing required fields"
        # check right below (it can only ever see None for an ABSENT key, never for one masked
        # by a default) - a malformed/incomplete API response would pass through undetected.
        total_runs = data.get("total_runs")
        by_status = data.get("by_status")
        success_rate = data.get("success_rate")
        error_rate = data.get("error_rate")
        halt_rate = data.get("halt_rate")

        if total_runs is None or by_status is None:
            error_msg = "Execution stats API missing required fields: total_runs or by_status"
            logger.error(error_msg)
            record_data_quality_issue("exec_stats", "validation", "missing_fields")
            return FetcherValidator.build_error_response(error_msg)

        return {
            "total_runs": total_runs,
            "by_status": by_status,
            "success_rate": success_rate,
            "error_rate": error_rate,
            "halt_rate": halt_rate,
            "period_days": data.get("period_days", 1),
        }
    except Exception as e:
        error_msg = format_fetcher_error("exec_stats", e)
        logger.error(error_msg)
        record_data_quality_issue("exec_stats", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_execution_patterns(c: None) -> dict[str, Any]:
    """Fetch which phases halt/error most often over a 30-day window, with example reasons.

    Wires up an endpoint (/api/algo/execution/patterns) that already existed server-side
    but was never called from the dashboard - the only place "is this phase failing all
    the time or was this a one-off?" could be answered, instead of inferring it by eyeballing
    the last 5 run badges.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/execution/patterns?days=30")

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("exec_patterns", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(data, dict):
            error_msg = "Execution patterns API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("exec_patterns", "type", "not_dict", type(data).__name__)
            return FetcherValidator.build_error_response(error_msg)

        patterns = data.get("patterns")
        if not isinstance(patterns, list):
            error_msg = "Execution patterns API missing required field: patterns"
            logger.error(error_msg)
            record_data_quality_issue("exec_patterns", "validation", "missing_fields")
            return FetcherValidator.build_error_response(error_msg)

        return {
            "patterns": patterns,
            "period_days": data.get("period_days", 30),
        }
    except Exception as e:
        error_msg = format_fetcher_error("exec_patterns", e)
        logger.error(error_msg)
        record_data_quality_issue("exec_patterns", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_orch_extended(c: None) -> dict[str, Any]:
    """Fetch extended orchestrator run history: per-run phase breakdown, 30-day phase
    success rates, halt-reason frequency, loader failure streaks, and 7d-vs-30d trend.

    Wires up /api/algo/freshness/extended (lambda/api/routes/algo_handlers/monitoring.py::
    _get_orchestrator_history_extended) - implemented server-side but never called from the
    dashboard, so panel_data_freshness_expanded() (dashboard/panels/health.py) had nothing
    to render.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/freshness/extended?limit=20")

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("orch_extended", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(data, dict):
            error_msg = "Orchestrator extended history API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("orch_extended", "type", "not_dict", type(data).__name__)
            return FetcherValidator.build_error_response(error_msg)

        return {
            "run_history": data.get("run_history") if isinstance(data.get("run_history"), list) else [],
            "phase_health": data.get("phase_health") if isinstance(data.get("phase_health"), dict) else {},
            "failure_patterns": data.get("failure_patterns") if isinstance(data.get("failure_patterns"), list) else [],
            "loader_health": data.get("loader_health") if isinstance(data.get("loader_health"), list) else [],
            "trend_summary": data.get("trend_summary") if isinstance(data.get("trend_summary"), dict) else {},
            "generated_at": data.get("generated_at"),
        }
    except Exception as e:
        error_msg = format_fetcher_error("orch_extended", e)
        logger.error(error_msg)
        record_data_quality_issue("orch_extended", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_signal_freshness(c: None) -> dict[str, Any]:
    """Fetch signal freshness (status/signal_age_hours) from /api/health.

    /api/algo/data-status (the "health" fetcher above) never carries this field - it's
    only computed by lambda/api/routes/health.py's /api/health handler (the same one
    webapp/frontend's SystemHealthIndicator.jsx already polls). Without this fetcher,
    dashboard/panels/health.py's _build_system_status_section() reads
    hlth_dict.get("signal_freshness") from the data-status response and always gets None -
    the same "computed server-side but nothing calls it" gap fetch_orch_extended fixed
    for /api/algo/freshness/extended.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/health")

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("signal_freshness", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(data, dict):
            error_msg = "Health API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("signal_freshness", "type", "not_dict", type(data).__name__)
            return FetcherValidator.build_error_response(error_msg)

        freshness = data.get("freshness")
        return {"freshness": freshness if isinstance(freshness, dict) else None}
    except Exception as e:
        error_msg = format_fetcher_error("signal_freshness", e)
        logger.error(error_msg)
        record_data_quality_issue("signal_freshness", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def _unwrap_coverage_section(section: Any) -> dict[str, Any] | None:
    """Extract the inner data dict from a data_coverage.py sub-section.

    get_overall_coverage_summary() (lambda/api/routes/data_coverage.py) nests each
    sub-check's own success_response()/error_response() envelope ({"statusCode":200,
    "data":{...}} or {"statusCode":4xx/5xx,...}) inside the outer summary - api_call()
    only unwraps the OUTERMOST envelope, so each section here still needs unwrapping
    individually. Returns None (not {}) for a failed/missing section so callers can
    distinguish "this check errored" from "this check returned empty data".
    """
    if not isinstance(section, dict):
        return None
    if section.get("statusCode") not in (200, None):
        return None
    data = section.get("data")
    return data if isinstance(data, dict) else None


def fetch_data_coverage(c: None) -> dict[str, Any]:
    """Fetch price/technical/market data-quality coverage that's genuinely not shown
    elsewhere on the freshness panel: zero-volume/invalid-price %% in price_daily,
    per-indicator (rsi/ema/atr) null rates in technical_data_daily, and market_health_daily/
    economic_data presence checks.

    Wires up /api/data-coverage - already implemented and registered server-side
    (lambda/api/routes/data_coverage.py) but never called from the dashboard. Distinct
    from dashboard/freshness_enhancements.py's enrich_health_item_with_coverage(), which
    only computes symbol-count coverage for a hardcoded 4-table set and doesn't touch
    per-column data quality or market_health_daily/economic_data at all.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/data-coverage")

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("data_coverage", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(data, dict):
            error_msg = "Data coverage API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("data_coverage", "type", "not_dict", type(data).__name__)
            return FetcherValidator.build_error_response(error_msg)

        return {
            "price_data": _unwrap_coverage_section(data.get("price_data")),
            "technical_data": _unwrap_coverage_section(data.get("technical_data")),
            "market_data": _unwrap_coverage_section(data.get("market_data")),
            "overall_health": data.get("overall_health"),
        }
    except Exception as e:
        error_msg = format_fetcher_error("data_coverage", e)
        logger.error(error_msg)
        record_data_quality_issue("data_coverage", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_algo_config(c: None) -> dict[str, Any]:
    """AWS-only algo configuration (fail-fast: error if unavailable)."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/config")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            # 'cfg' is a critical fetcher (dashboard/fetchers.py) -- raising here would take
            # down the ENTIRE dashboard, not just the panels that use config. An auth error
            # is a real problem worth surfacing loudly, but as a per-panel _error marker (the
            # existing has_error(ctx.cfg) check in renderers/pipeline.py already degrades only
            # the portfolio panel), not a RuntimeError that kills every other panel too.
            if data.get("_auth_error"):
                logger.error(
                    "CRITICAL: Cannot fetch config due to auth error (401). "
                    "This indicates Cognito auth is not properly configured. Check credentials and retry."
                )
                record_data_quality_issue("cfg", "api_call", "auth_error", error_msg or "401 auth error")
                return FetcherValidator.build_error_response(error_msg or "Cognito auth error (401)")

            record_data_quality_issue("cfg", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        if not isinstance(raw, dict):
            error_msg = "Config response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "type", "not_dict", type(raw).__name__)
            return FetcherValidator.build_error_response(error_msg)

        # API returns flat dict: {key: value, key: value, ...}
        # (Previously returned {items: [{key, value, value_type, ...}]})
        if not raw:
            error_msg = "Config API response is empty"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "empty_config")
            return FetcherValidator.build_error_response(error_msg)

        # Use the raw data as config (already a flat dict)
        cfg = raw

        # Issue #8: enable_algo is REQUIRED - no default to True (fail-closed)
        required_config = [
            "enable_algo",
            "execution_mode",
            "max_position_size_pct",
            "max_positions",
            "max_positions_per_sector",
            "base_risk_pct",
            "t1_target_r_multiple",
        ]
        # Check for missing keys
        missing = [k for k in required_config if k not in cfg]
        if missing:
            error_msg = f"Config missing required fields: {missing}"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "missing_fields", ", ".join(missing))
            return FetcherValidator.build_error_response(error_msg)

        # Check for None values in required fields (fail-fast: no silent None defaults)
        null_fields = [k for k in required_config if cfg[k] is None]
        if null_fields:
            error_msg = f"Config has NULL values for required fields: {null_fields}"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "null_required_fields", ", ".join(null_fields))
            return FetcherValidator.build_error_response(error_msg)

        # Boolean string conversion - CRITICAL: Must parse explicitly, no silent False default
        en_raw = cfg["enable_algo"]
        if en_raw is None:
            error_msg = "Config enable_algo field has NULL value - cannot determine if algo is enabled"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "null_enable_algo")
            return FetcherValidator.build_error_response(error_msg)
        try:
            enabled = str(en_raw).lower() in ("true", "1", "yes")
        except (ValueError, TypeError) as e:
            error_msg = f"Config enable_algo field has invalid value '{en_raw}' - cannot parse as boolean. Error: {e}"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "invalid_enable_algo_value", str(en_raw))
            return FetcherValidator.build_error_response(error_msg)
        # Validate all required config fields exist
        required_fields = [
            "execution_mode",
            "max_position_size_pct",
            "max_positions",
            "max_positions_per_sector",
            "base_risk_pct",
            "t1_target_r_multiple",
        ]
        missing_fields = [f for f in required_fields if f not in cfg]
        if missing_fields:
            error_msg = f"Config missing required fields: {missing_fields}"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "missing_fields", str(missing_fields))
            return FetcherValidator.build_error_response(error_msg)

        return {
            "enabled": enabled,
            "mode": cfg["execution_mode"],
            "max_pos_pct": float(cfg["max_position_size_pct"]),
            "max_pos_n": int(cfg["max_positions"]),
            "max_sec_n": int(cfg["max_positions_per_sector"]),
            "base_risk": float(cfg["base_risk_pct"]),
            "t1_r": float(cfg["t1_target_r_multiple"]),
        }
    except Exception as e:
        error_msg = format_fetcher_error("cfg", e)
        logger.error(error_msg)
        record_data_quality_issue("cfg", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_health(c: None) -> dict[str, Any]:
    """Fetch data loader health status from API. Uses cached data-status (fail-fast: error if unavailable)."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = _get_data_status_cached()

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("health", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        inner = data
        if not isinstance(inner, dict):
            error_msg = "Health API response is not a dict"
            logger.error(error_msg)
            record_data_quality_issue("health", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        # REQUIRED FIELD: 'sources' must be present (API contract). Don't fall back to 'items'.
        # If API is returning 'items' instead, that's a schema change that must be explicitly handled.
        raw_sources = inner.get("sources")
        if raw_sources is None:
            # Fallback to 'items' field if 'sources' is missing (for API compatibility during transition)
            raw_sources = inner.get("items")
        if raw_sources is None:
            error_msg = (
                "Health API response missing required 'sources' field (API contract violation). "
                "Expected list of data source health entries. Response keys: " + str(list(inner.keys()))
            )
            logger.error(error_msg)
            record_data_quality_issue("health", "validation", "missing_sources_field")
            return FetcherValidator.build_error_response(error_msg)
        if not isinstance(raw_sources, list):
            error_msg = f"Health API 'sources'/'items' field must be list, got {type(raw_sources).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("health", "validation", "sources_not_list")
            return FetcherValidator.build_error_response(error_msg)
        critical_stale = inner.get("critical_stale")
        if critical_stale is not None and not isinstance(critical_stale, list):
            error_msg = f"Health API 'critical_stale' field must be list or null, got {type(critical_stale).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("health", "validation", "critical_stale_not_list")
            return FetcherValidator.build_error_response(error_msg)
        sources = []
        for s in raw_sources:
            # REQUIRED: name field must be present - no fallback to empty string
            name = s.get("name")
            if not name:
                error_msg = "Health API source entry missing required 'name' field"
                logger.error(error_msg)
                record_data_quality_issue("health", "validation", "missing_source_name")
                return FetcherValidator.build_error_response(error_msg)

            # FAIL-FAST: Require role field from API. Don't fall back to config file.
            # API structure and config file can diverge, causing incorrect role assignments.
            role = s.get("role")
            if not role:
                error_msg = (
                    f"Health API source '{name}': missing required 'role' field (CRIT/IMP/NORM). "
                    "API response schema mismatch. Check backend response format."
                )
                logger.error(error_msg)
                record_data_quality_issue("health", "validation", "missing_role_field", name)
                return FetcherValidator.build_error_response(error_msg)
            # Explicit validation: age_hours required for freshness display
            age_hours = s.get("age_hours")
            if age_hours is None:
                logger.debug(
                    f"Data freshness missing age_hours for {name} - freshness cannot be displayed (expected for derived/local sources)"
                )
                age_days = None
            else:
                try:
                    age_days = round(float(age_hours) / 24, 1)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid age_hours value for {name}: {age_hours} - freshness cannot be calculated")
                    age_days = None

            # REQUIRED: status field must be present - no fallback to "unknown"
            # Missing status means the API response is malformed or incomplete
            status = s.get("status")
            if status is None:
                error_msg = (
                    f"Health API source entry '{name}': missing required 'status' field. "
                    f"Cannot display data freshness without status. API schema incomplete."
                )
                logger.error(error_msg)
                record_data_quality_issue("health", "validation", "missing_status_field", name)
                return FetcherValidator.build_error_response(error_msg)

            # Extract optional enrichment fields with explicit markers
            last_updated = s.get("last_updated")
            if last_updated is None:
                logger.debug(f"Data freshness missing last_updated for {name} - optional enrichment unavailable")

            row_count = s.get("row_count")
            if row_count is None:
                logger.debug(f"Data freshness missing row_count for {name} - optional enrichment unavailable")

            # Loader run diagnostics: written by LoaderStatusManager on every loader run but
            # previously dropped before reaching the dashboard, so a STALE/EMPTY table gave no
            # clue whether the loader is failing (and why) or just hasn't run yet.
            loader_error = s.get("loader_error")
            if loader_error is None:
                logger.debug(f"Data freshness missing loader_error for {name} - optional enrichment unavailable")

            execution_started = s.get("execution_started")
            execution_completed = s.get("execution_completed")
            completion_pct = s.get("completion_pct")
            symbols_loaded = s.get("symbols_loaded")
            symbol_count = s.get("symbol_count")

            # loader_run_status (NOT_STARTED/RUNNING/COMPLETED/FAILED/TIMEOUT) and
            # stale_threshold_days: written/computed by the API but previously dropped here -
            # same class of gap as loader_error above. loader_run_status lets the freshness
            # panel tell "loader never ran" (NOT_STARTED) apart from "ran, produced 0 rows"
            # (status=empty), and TIMEOUT apart from FAILED. stale_threshold_days lets it show
            # *why* a table is still "ok" at N days old (its own configured cadence) instead
            # of just the raw age.
            loader_run_status = s.get("loader_run_status")
            stale_threshold_days = s.get("stale_threshold_days")

            # last_success_at/consecutive_failures (migration 1163): execution_completed alone
            # can't distinguish "last finished successfully" from "last finished at all" (it's
            # stamped on FAILED/TIMEOUT too) - these let the panel tell a loader that's failed
            # once apart from one that's failed every run for days.
            last_success_at = s.get("last_success_at")
            consecutive_failures = s.get("consecutive_failures")

            # Data quality / coverage / failure-pattern / API diagnostics: attached server-side
            # by dashboard/freshness_enhancements.py (see market.py's _get_data_status
            # enrichment block) but previously dropped here since this function rebuilds each
            # source into an explicit whitelist dict - the DATA FRESHNESS - EXPANDED panel's
            # quality/coverage/failure-pattern/API-diagnostics sections (dashboard/panels/
            # health.py's _build_data_quality_section et al.) read these fields and had nothing
            # to show even once the server-side enrichment itself worked.
            data_quality_issues = s.get("data_quality_issues")
            quality_status = s.get("quality_status")
            symbol_coverage_pct = s.get("symbol_coverage_pct")
            missing_symbols = s.get("missing_symbols")
            coverage_status = s.get("coverage_status")
            failure_rate_30d = s.get("failure_rate_30d")
            failure_pattern = s.get("failure_pattern")
            mttr_hours = s.get("mttr_hours")
            last_5_runs = s.get("last_5_runs")
            recovery_trend = s.get("recovery_trend")
            api_status = s.get("api_status")
            rate_limit_quota = s.get("rate_limit_quota")
            retry_strategy = s.get("retry_strategy")

            # Loader performance metrics: execution duration and throughput
            execution_duration_sec = s.get("execution_duration_sec")
            symbols_per_second = s.get("symbols_per_second")

            # Diagnostics written by mark_failed()/mark_timeout() (migration 1164): how many
            # times this run retried before failing, and the raw HTTP status code if the loader
            # captured one. Distinct from api_status/retry_strategy above, which are the
            # enrichment layer's derived category - these are the underlying real values.
            retry_count = s.get("retry_count")
            http_status_code = s.get("http_status_code")

            # Row-count stall detector (dashboard/freshness_enhancements.py): flags a loader
            # that keeps reporting a normal run while its row_count hasn't actually moved -
            # a silent-failure mode age/status alone can't catch.
            row_count_stalled = s.get("row_count_stalled")
            row_count_stalled_since = s.get("row_count_stalled_since")

            sources.append(
                {
                    "tbl": name,
                    "st": status,
                    "age": age_days,
                    "role": role,
                    # preserve originals for other panels that may use them
                    "name": name,
                    "status": status,
                    "last_updated": last_updated,
                    "age_hours": age_hours,
                    "row_count": row_count,
                    # Mark optional fields as unavailable if missing
                    "last_updated_available": last_updated is not None,
                    "row_count_available": row_count is not None,
                    "loader_error": loader_error,
                    "execution_started": execution_started,
                    "execution_completed": execution_completed,
                    "completion_pct": completion_pct,
                    "symbols_loaded": symbols_loaded,
                    "symbol_count": symbol_count,
                    "loader_run_status": loader_run_status,
                    "stale_threshold_days": stale_threshold_days,
                    "last_success_at": last_success_at,
                    "consecutive_failures": consecutive_failures,
                    "data_quality_issues": data_quality_issues,
                    "quality_status": quality_status,
                    "symbol_coverage_pct": symbol_coverage_pct,
                    "missing_symbols": missing_symbols,
                    "coverage_status": coverage_status,
                    "failure_rate_30d": failure_rate_30d,
                    "failure_pattern": failure_pattern,
                    "mttr_hours": mttr_hours,
                    "last_5_runs": last_5_runs,
                    "recovery_trend": recovery_trend,
                    "api_status": api_status,
                    "rate_limit_quota": rate_limit_quota,
                    "retry_strategy": retry_strategy,
                    "execution_duration_sec": execution_duration_sec,
                    "symbols_per_second": symbols_per_second,
                    "retry_count": retry_count,
                    "http_status_code": http_status_code,
                    "row_count_stalled": row_count_stalled,
                    "row_count_stalled_since": row_count_stalled_since,
                }
            )
        summary = inner.get("summary")
        if summary is not None and not isinstance(summary, dict):
            logger.debug(
                f"Health API summary field has unexpected type {type(summary).__name__}, treating as unavailable"
            )
            summary = None

        # Extract optional enrichment fields with explicit logging
        ready_to_trade = inner.get("ready_to_trade")
        if ready_to_trade is None:
            logger.debug("Health API response missing ready_to_trade field (optional enrichment)")

        # Extract Phase 2-9 execution health metrics
        execution_health = inner.get("execution_health")
        if execution_health is None:
            logger.debug("Health API response missing execution_health field (Phase 2-9 metrics unavailable)")

        # trading_halted/trading_halt_reason/expected_date/as_of: computed by the API
        # (_get_data_status) but previously dropped here before reaching any panel - the
        # dashboard's "NOT READY" badge had no way to say whether that meant stale data or
        # a circuit-breaker halt, and the DATA FRESHNESS panel had no real "as of" timestamp
        # of its own (only per-table ages).
        trading_halted = inner.get("trading_halted")
        trading_halt_reason = inner.get("trading_halt_reason")
        trading_halt_at = inner.get("trading_halt_at")
        expected_date = inner.get("expected_date")
        as_of = inner.get("as_of")

        return {
            "items": sources,
            "ready_to_trade": ready_to_trade,
            "summary": summary,
            "critical_stale": critical_stale,
            "execution_health": execution_health,
            "trading_halted": trading_halted,
            "trading_halt_reason": trading_halt_reason,
            "trading_halt_at": trading_halt_at,
            "expected_date": expected_date,
            "as_of": as_of,
        }
    except Exception as e:
        error_msg = format_fetcher_error("health", e)
        logger.error(error_msg)
        record_data_quality_issue("health", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_circuit(c: None) -> dict[str, Any]:
    """Fetch circuit breakers from API."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/circuit-breakers")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("cb", "api_call", "api_error", error_msg or "unknown_error")
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
            label = r.get("label")
            if label is None:
                label = r.get("breaker_name")
            if not label:
                error_msg = "Circuit breaker entry missing both 'label' and 'breaker_name' fields"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "breaker_missing_label")
                return FetcherValidator.build_error_response(error_msg)

            # CRITICAL: Require exact field names - no fallback field substitution.
            # If API changed field names, that must be fixed in the API, not hidden here.

            # Current value field (REQUIRED: current)
            if "current" not in r:
                error_msg = f"Circuit breaker {label}: missing required field 'current'. Available: {list(r.keys())}"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_current", label)
                return FetcherValidator.build_error_response(error_msg)
            cur_val = r["current"]
            if cur_val is None:
                logger.debug(f"Circuit breaker {label}: current is None (optional data unavailable)")

            # Threshold field (REQUIRED: threshold)
            if "threshold" not in r:
                error_msg = f"Circuit breaker {label}: missing required field 'threshold'. Available: {list(r.keys())}"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_threshold", label)
                return FetcherValidator.build_error_response(error_msg)
            thr_val = r["threshold"]
            if thr_val is None:
                logger.debug(f"Circuit breaker {label}: threshold is None (optional data unavailable)")

            # Triggered field (REQUIRED: triggered)
            if "triggered" not in r:
                error_msg = f"Circuit breaker {label}: missing required field 'triggered'. Available: {list(r.keys())}"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_triggered", label)
                return FetcherValidator.build_error_response(error_msg)
            is_triggered = r["triggered"]

            unit = r.get("unit")
            if unit is None:
                logger.debug(f"Circuit breaker {label}: 'unit' field missing (optional enrichment)")
                unit_display = ""
            else:
                unit_display = str(unit)

            formatted_bs.append(
                {
                    "id": r.get("id"),
                    "label": label,
                    "current": float(cur_val) if cur_val is not None else None,
                    "threshold": float(thr_val) if thr_val is not None else None,
                    "unit": unit_display,
                    "unit_available": unit is not None,
                    "triggered": safe_bool(is_triggered),
                    "description": r.get("description"),
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
            "breakers": formatted_bs,
            "any_triggered": any_triggered,
            "triggered_count": triggered_count,
            "data_freshness": result.get("data_freshness"),
            "timestamp": datetime.now(ET),
        }
    except Exception as e:
        error_msg = format_fetcher_error("cb", e)
        logger.error(error_msg)
        record_data_quality_issue("cb", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_algo_metrics(c: None) -> dict[str, Any] | list[Any]:
    """Fetch algo metrics. API returns a single dict {date, total_actions,
    entries, exits, avg_signal_score}; panel expects a flat list so it can
    do valid_metrics[0] and iterate over multiple days."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("algo_metrics"))

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("algo_metrics", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        d = data
        if isinstance(d, list):
            if not d:
                logger.warning("Algo metrics API returned empty list")
                record_data_quality_issue("algo_metrics", "validation", "empty_list")
            return d
        if isinstance(d, dict):
            # Remove statusCode if present (it's API metadata, not application data)
            cleaned = {k: v for k, v in d.items() if k != "statusCode"}
            if not cleaned:
                # Dict was empty or only contained statusCode
                logger.warning(f"Algo metrics API response has no data fields (only statusCode present: {d})")
                record_data_quality_issue("algo_metrics", "validation", "empty_after_cleanup")
                # Return empty data marker rather than statusCode
                return [{}]
            return [cleaned]
        error_msg = f"Algo metrics API response unexpected type: expected list or dict, got {type(d).__name__}"
        logger.error(error_msg)
        record_data_quality_issue("algo_metrics", "validation", "invalid_response_type")
        return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = format_fetcher_error("algo_metrics", e)
        logger.error(error_msg)
        record_data_quality_issue("algo_metrics", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
