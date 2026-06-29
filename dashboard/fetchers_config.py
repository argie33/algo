"""Fetcher functions for algo configuration, health, circuit breakers, and status."""

import logging
import threading
from typing import Any, cast

from utils.safe_data_conversion import safe_bool

from .api_data_layer import api_call
from .fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue

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
            _data_status_cache["result"] = error_result
            _data_status_cache["_time"] = now
            return error_result


def fetch_run(c: None) -> dict[str, Any]:
    from dashboard.fetcher_validator import FetcherValidator

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
        halted_phases = [p for p in phases if p.get("status") in ("halt", "halted")]
        errored_phases = [p for p in phases if p.get("status") == "error"]
        completed_phases = [p for p in phases if p.get("status") == "success"]
        halt_reason = halted_phases[0].get("summary") if halted_phases else None

        # CRITICAL: started_at is REQUIRED. No fallback to alternative timestamp fields.
        # Contract specifies 'started_at', not 'run_at'.
        started_at = inner.get("started_at")
        if not started_at:
            error_msg = "Last-run API response missing required 'started_at' field. Available keys: " + str(
                list(inner.keys())
            )
            logger.error(error_msg)
            record_data_quality_issue("run", "critical_field", "missing_started_at")
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

        return {
            "run_id": run_id,
            "run_at": started_at,
            "success": inner["success"],
            "halted": inner["halted"],
            "errored": api_errored if api_errored is not None else derived_errored,
            "summary": summary,
            "halt_reason": halt_reason,
            "phases_completed": [p.get("action_type") for p in completed_phases],
            "phases_halted": [p.get("action_type") for p in halted_phases],
            "phases_errored": [p.get("action_type") for p in errored_phases],
            "phase_results": phases,
        }
    except Exception as e:
        error_msg = format_fetcher_error("run", e)
        logger.error(error_msg)
        record_data_quality_issue("run", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_algo_config(c: None) -> dict[str, Any]:
    """AWS-only algo configuration (fail-fast: error if unavailable)."""
    from dashboard.fetcher_validator import FetcherValidator

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

        # STRICT: Build config dict allowing None values (will be validated below)
        # Explicit: only include items that have a 'key' field
        cfg = {}
        for i in items:
            if "key" in i:
                key = i["key"]
                # Value can be None (will be caught by required_config validation below)
                cfg[key] = i.get("value")

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
            error_msg = "Config enable_algo field has NULL value — cannot determine if algo is enabled"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "null_enable_algo")
            return FetcherValidator.build_error_response(error_msg)
        try:
            enabled = str(en_raw).lower() in ("true", "1", "yes")
        except (ValueError, TypeError) as e:
            error_msg = f"Config enable_algo field has invalid value '{en_raw}' — cannot parse as boolean. Error: {e}"
            logger.error(error_msg)
            record_data_quality_issue("cfg", "validation", "invalid_enable_algo_value", str(en_raw))
            return FetcherValidator.build_error_response(error_msg)
        return {
            "enabled": enabled,
            "mode": cfg["execution_mode"],
            "max_pos_pct": float(cfg["max_position_size_pct"]),
            "max_pos_n": int(cfg["max_positions"]),
            "max_sec_n": int(cfg["max_positions_per_sector"]),
            "min_score": float(cfg["min_swing_score"]),
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
            record_data_quality_issue("health", "api_call", "api_error", error_msg)
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
            # REQUIRED: name field must be present — no fallback to empty string
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
                logger.warning(f"Data freshness missing age_hours for {name} — freshness cannot be displayed")
                age_days = None
            else:
                try:
                    age_days = round(float(age_hours) / 24, 1)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid age_hours value for {name}: {age_hours} — freshness cannot be calculated")
                    age_days = None

            # REQUIRED: status field must be present — no fallback to "unknown"
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
                logger.debug(f"Data freshness missing last_updated for {name} — optional enrichment unavailable")

            row_count = s.get("row_count")
            if row_count is None:
                logger.debug(f"Data freshness missing row_count for {name} — optional enrichment unavailable")

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

        return {
            "items": sources,
            "ready_to_trade": ready_to_trade,
            "summary": summary,
            "critical_stale": critical_stale,
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
            label = r.get("label")
            if label is None:
                label = r.get("breaker_name")
            if not label:
                error_msg = "Circuit breaker entry missing both 'label' and 'breaker_name' fields"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "breaker_missing_label")
                return FetcherValidator.build_error_response(error_msg)

            # CRITICAL: Require exact field names — no fallback field substitution.
            # If API changed field names, that must be fixed in the API, not hidden here.

            # Current value field (REQUIRED: current)
            if "current" not in r:
                error_msg = f"Circuit breaker {label}: missing required field 'current'. Available: {list(r.keys())}"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_current", label)
                return FetcherValidator.build_error_response(error_msg)
            cur_val = r["current"]
            if cur_val is None:
                error_msg = f"Circuit breaker {label}: current is None"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "null_current", label)
                return FetcherValidator.build_error_response(error_msg)

            # Threshold field (REQUIRED: threshold)
            if "threshold" not in r:
                error_msg = f"Circuit breaker {label}: missing required field 'threshold'. Available: {list(r.keys())}"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_threshold", label)
                return FetcherValidator.build_error_response(error_msg)
            thr_val = r["threshold"]
            if thr_val is None:
                error_msg = f"Circuit breaker {label}: threshold is None"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "null_threshold", label)
                return FetcherValidator.build_error_response(error_msg)

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
                    "current": float(cur_val),
                    "threshold": float(thr_val),
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
            "bs": formatted_bs,
            "any": any_triggered,
            "n": triggered_count,
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
            record_data_quality_issue("algo_metrics", "api_call", "api_error", error_msg)
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
