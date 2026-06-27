"""Fetcher functions for algo configuration, health, circuit breakers, and status."""

import logging
import threading
from typing import Any, cast

from utils.safe_data_conversion import safe_bool

from .api_data_layer import api_call

logger = logging.getLogger(__name__)


def record_data_quality_issue(*args: object, **kwargs: object) -> None:
    """Placeholder for data quality issue recording."""


_data_status_cache: dict[str, Any] = {}
_data_status_lock = threading.Lock()


def clear_data_status_cache() -> None:
    """Clear the data-status cache to ensure fresh data on next fetch.

    Called by load_all() to prevent stale data between refresh cycles.
    """
    with _data_status_lock:
        _data_status_cache.clear()


def _format_fetcher_error(fetcher_name: str, error: Exception) -> str:
    """Format fetcher error with endpoint context for better troubleshooting.

    Returns error string like: "Fetcher run (/api/algo/last-run: Last algo run status) timed out"
    """
    from .fetchers_common import FETCHER_METADATA

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


def _get_endpoint_path(fetcher_key: str, params: dict[str, Any] | None = None) -> str:
    """Map fetcher key to full endpoint path with optional query parameters.

    Examples:
      _get_endpoint_path('pos') → '/api/algo/positions'
      _get_endpoint_path('trades', params={'limit': 10}) → '/api/algo/trades' (params passed to api_call)
    """
    from .fetchers_common import FETCHER_METADATA

    meta = FETCHER_METADATA.get(fetcher_key)
    if not meta:
        # For endpoints with direct paths (like '/api/algo/last-run')
        return fetcher_key
    endpoint = meta.get("endpoint", "")
    if not endpoint:
        return fetcher_key
    return endpoint


def _get_data_status_cached() -> dict[str, Any]:
    """Issue 2.2 FIX: Unified fetch for /api/algo/data-status endpoint.

    Both fetch_health and fetch_loader_status need the same endpoint. This
    caches the result to avoid duplicate API calls when both are fetched
    in parallel. Thread-safe with lock to ensure single API call.
    """
    if "result" in _data_status_cache:
        return cast(dict[str, Any], _data_status_cache["result"])

    with _data_status_lock:
        if "result" in _data_status_cache:
            return cast(dict[str, Any], _data_status_cache["result"])

        try:
            data = api_call(_get_endpoint_path("health"))
            _data_status_cache["result"] = data
            return data
        except Exception as e:
            error_result = {"_error": str(e)}
            _data_status_cache["result"] = error_result
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

        # Timestamps are required - fail if all are missing (Issue #6)
        # Explicit priority: prefer run_at, then completed_at, then started_at
        run_at = None

        if inner.get("run_at") is not None:
            run_at = inner.get("run_at")
        elif inner.get("completed_at") is not None:
            run_at = inner.get("completed_at")
            logger.debug(
                "Last-run API using fallback field 'completed_at' for timestamp. "
                "Consider verifying API schema: expected 'run_at' field."
            )
        elif inner.get("started_at") is not None:
            run_at = inner.get("started_at")
            logger.warning(
                "Last-run API using fallback field 'started_at' for timestamp (run_at and completed_at missing). "
                "This may indicate API schema issue or incomplete run data."
            )

        # No runs yet (algo hasn't executed) - fail-fast: return error instead of placeholder
        if not run_at and not inner.get("run_id") and not inner["success"] and not inner["halted"]:
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
        api_errored = inner.get("errored")
        derived_errored = bool(errored_phases) or (not inner["success"] and not inner["halted"] and bool(phases))
        return {
            "run_id": inner.get("run_id"),
            "run_at": run_at,
            "success": inner["success"],
            "halted": inner["halted"],
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
            "max_pos_pct": float(cfg["max_position_size_pct"]),
            "max_pos_n": int(cfg["max_positions"]),
            "max_sec_n": int(cfg["max_positions_per_sector"]),
            "min_score": float(cfg["min_swing_score"]),
            "base_risk": float(cfg["base_risk_pct"]),
            "t1_r": float(cfg["t1_target_r_multiple"]),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("cfg", e)
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
        raw_sources = inner.get("sources")
        if raw_sources is None:
            raw_sources = inner.get("items")
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
            name = s.get("name", "")
            if not name:
                error_msg = "Health API source entry missing 'name' field"
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
                logger.warning(f"Data freshness missing age_hours for {name}")
                age_days = None
            else:
                try:
                    age_days = round(float(age_hours) / 24, 1)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid age_hours value for {name}: {age_hours}")
                    age_days = None

            status = s.get("status")
            if status is None:
                logger.warning(f"Data freshness missing status for {name}")
                status = "unknown"

            sources.append(
                {
                    "tbl": name,
                    "st": status,
                    "age": age_days,
                    "role": role,
                    # preserve originals for other panels that may use them
                    "name": name,
                    "status": status,
                    "last_updated": s.get("last_updated"),
                    "age_hours": age_hours,
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

            # Map API field names to fetcher expectations with explicit source tracking.
            # Primary fields: current_value, threshold_value, is_active
            # Fallback fields (for compatibility): current, threshold, triggered
            # FAIL-FAST: Validate which field is present and log source for schema traceability

            # Current value field (required)
            if "current_value" in r:
                cur_val = r["current_value"]
            elif "current" in r:
                cur_val = r["current"]
                logger.debug(f"[CB] {label}: using fallback field 'current' instead of 'current_value'")
            else:
                error_msg = (
                    f"Circuit breaker {label}: missing required fields 'current_value' and 'current'. "
                    f"API response schema incomplete. Available: {list(r.keys())}"
                )
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_current_field", label)
                return FetcherValidator.build_error_response(error_msg)

            if cur_val is None:
                error_msg = f"Circuit breaker {label}: current value is None"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "null_current_value", label)
                return FetcherValidator.build_error_response(error_msg)

            # Threshold value field (required)
            if "threshold_value" in r:
                thr_val = r["threshold_value"]
            elif "threshold" in r:
                thr_val = r["threshold"]
                logger.debug(f"[CB] {label}: using fallback field 'threshold' instead of 'threshold_value'")
            else:
                error_msg = (
                    f"Circuit breaker {label}: missing required fields 'threshold_value' and 'threshold'. "
                    f"API response schema incomplete. Available: {list(r.keys())}"
                )
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_threshold_field", label)
                return FetcherValidator.build_error_response(error_msg)

            if thr_val is None:
                error_msg = f"Circuit breaker {label}: threshold value is None"
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "null_threshold_value", label)
                return FetcherValidator.build_error_response(error_msg)

            # Is active/triggered field (required)
            if "is_active" in r:
                is_triggered = r["is_active"]
            elif "triggered" in r:
                is_triggered = r["triggered"]
                logger.debug(f"[CB] {label}: using fallback field 'triggered' instead of 'is_active'")
            else:
                error_msg = (
                    f"Circuit breaker {label}: missing required fields 'is_active' and 'triggered'. "
                    f"API response schema incomplete. Available: {list(r.keys())}"
                )
                logger.error(error_msg)
                record_data_quality_issue("cb", "validation", "missing_triggered_field", label)
                return FetcherValidator.build_error_response(error_msg)

            formatted_bs.append(
                {
                    "lbl": label,
                    "cur": float(cur_val),
                    "thr": float(thr_val),
                    "u": r.get("unit", ""),
                    "fired": safe_bool(is_triggered),
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


def fetch_algo_metrics(c: None) -> dict[str, Any] | list[Any]:
    """Fetch algo metrics. API returns a single dict {date, total_actions,
    entries, exits, avg_signal_score}; panel expects a flat list so it can
    do valid_metrics[0] and iterate over multiple days."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("algo_metrics"))

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("algo_metrics", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            # Remove statusCode if present (it's API metadata, not application data)
            cleaned = {k: v for k, v in d.items() if k != "statusCode"}
            return [cleaned] if cleaned else [d]
        error_msg = f"Algo metrics API response unexpected type: expected list or dict, got {type(d).__name__}"
        logger.error(error_msg)
        record_data_quality_issue("algo_metrics", "validation", "invalid_response_type")
        return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = _format_fetcher_error("algo_metrics", e)
        logger.error(error_msg)
        record_data_quality_issue("algo_metrics", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
