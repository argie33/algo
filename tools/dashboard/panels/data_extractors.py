"""Data extraction helpers for dashboard panels - fail-fast pattern.

Replaces defensive .get() calls with up-front validation + direct access.
Pattern:
  1. Check has_error() once at entry point
  2. If error: display error panel immediately
  3. Then use direct access for validated fields (no .get() needed)
  4. Use .get() ONLY for truly optional fields
"""

from typing import Any

from ..error_boundary import has_error


def safe_extract(data: dict[str, Any], *keys: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract multiple fields from data, validating presence.

    Args:
        data: Data dict to extract from (already checked for error)
        *keys: Field names to extract
        defaults: Optional default dict for missing optional fields

    Returns:
        Dict with extracted values. Critical fields raise KeyError if missing.
        Optional fields get default or None.

    Example:
        from ..error_boundary import has_error
        if has_error(cfg):
            return error_panel(cfg)
        result = safe_extract(cfg, "mode", "enabled", "max_pos_n")
        mode = result["mode"]  # Guaranteed to exist
    """
    defaults = defaults or {}
    result = {}

    for key in keys:
        if key in data:
            result[key] = data[key]
        elif key in defaults:
            result[key] = defaults[key]
        else:
            raise KeyError(f"Required field '{key}' missing from data")

    return result


def safe_get_dict(data: Any) -> dict[str, Any]:
    """Get dict from data if not error, else empty dict."""
    if isinstance(data, dict) and not has_error(data):
        return data
    return {}


def safe_get_list(data: Any) -> list:
    """Get list from data if not error, else empty list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and not has_error(data):
        if "items" in data and isinstance(data["items"], list):
            return data["items"]
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
    return []


def safe_get_field(data: dict[str, Any], field: str, default: Any = None) -> Any:
    """Get field from validated data dict (error already checked)."""
    if not isinstance(data, dict):
        return default
    return data.get(field, default)


# Extract common field accessors as functions to reduce repetition in panels
def extract_config_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract common config display parameters.

    Returns dict with all required config fields. No defaults—validation already
    confirmed data presence at API boundary layer. Call only after has_error() check.
    """
    if not isinstance(cfg, dict) or has_error(cfg):
        return {"_error": "Config data unavailable"}
    return {
        "mode": cfg.get("mode"),
        "enabled": cfg.get("enabled"),
        "max_pos_n": cfg.get("max_pos_n"),
        "max_sec_n": cfg.get("max_sec_n"),
        "min_score": cfg.get("min_score"),
        "base_risk": cfg.get("base_risk"),
        "t1_r": cfg.get("t1_r"),
    }


def extract_risk_metrics(risk: dict[str, Any]) -> dict[str, Any]:
    """Extract risk metrics for display (only if valid data).

    Fail-fast: Risk metrics (VaR, CVaR, Beta, concentration) are critical
    financial data. Missing values are not replaced with 0; that would be
    catastrophically misleading for position sizing. All fields must be
    present after error check passes. Returns error marker if data invalid.
    """
    if not isinstance(risk, dict) or has_error(risk):
        return {"_error": "Risk metrics unavailable"}
    return {
        "var95": risk.get("var95"),
        "cvar95": risk.get("cvar95"),
        "svar": risk.get("svar"),
        "beta": risk.get("beta"),
        "conc5": risk.get("conc5"),
    }


def extract_run_info(run: dict[str, Any]) -> dict[str, Any]:
    """Extract run status info (error already checked).

    Returns only for valid run data. If error present, caller should
    have already checked has_error() and returned error panel.
    Returns error marker if data invalid.
    """
    if not isinstance(run, dict) or has_error(run):
        return {"_error": "Run info unavailable"}
    phase_results = run.get("phase_results")
    if phase_results is None:
        phase_results = []
    return {
        "success": run.get("success"),
        "halted": run.get("halted"),
        "errored": run.get("errored"),
        "run_at": run.get("run_at"),
        "run_id": run.get("run_id"),
        "phase_results": phase_results,
        "halt_reason": run.get("halt_reason"),
        "summary": run.get("summary"),
        "_source": run.get("_source"),
    }


def extract_health_items(hlth: dict[str, Any] | list) -> tuple[list, bool]:
    """Extract health items and ready_to_trade status (error already checked).

    Args:
        hlth: Health response dict or list of items

    Returns:
        (items_list, ready_to_trade_bool) tuple
    """
    items = []
    ready_to_trade = None

    if isinstance(hlth, dict):
        items = hlth.get("items", []) if isinstance(hlth.get("items"), list) else []
        ready_to_trade = hlth.get("ready_to_trade")
    elif isinstance(hlth, list):
        items = hlth

    return items, ready_to_trade


def extract_phase_results(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and normalize phase results from run data.

    Handles various phase result formats and ensures consistent structure.
    """
    if not isinstance(run, dict):
        return []
    results = run.get("phase_results", [])
    return results if isinstance(results, list) else []


def extract_item_field(item: dict[str, Any], field: str, default: Any = None) -> Any:
    """Extract field from health item (used in loops over items).

    After has_error() check at function entry, direct field access is safe.
    Use this for optional fields only.
    """
    if not isinstance(item, dict):
        return default
    return item.get(field, default)


def extract_signal_overview(sig: dict[str, Any]) -> dict[str, Any]:
    """Extract signal overview fields for compact & expanded displays (error already checked)."""
    if not isinstance(sig, dict) or has_error(sig):
        return {"_error": "Signal data unavailable"}
    return {
        "n": sig.get("n"),
        "total": sig.get("total"),
        "date": sig.get("date"),
        "grades": sig.get("grades") or {},
        "top_a": sig.get("top_a") or [],
        "near": sig.get("near") or [],
        "trend": sig.get("trend") or [],
        "buy_sigs": sig.get("buy_sigs") or [],
        "timestamp": sig.get("timestamp"),
    }


def extract_eval_funnel(sig_eval: dict[str, Any] | None) -> dict[str, Any]:
    """Extract evaluation funnel data (error already checked, data optional)."""
    if not sig_eval or not isinstance(sig_eval, dict) or has_error(sig_eval):
        return {}
    return {
        "total": sig_eval.get("total"),
        "t1": sig_eval.get("t1"),
        "t2": sig_eval.get("t2"),
        "t3": sig_eval.get("t3"),
        "t4": sig_eval.get("t4"),
        "t5": sig_eval.get("t5"),
        "avg_score": sig_eval.get("avg_score"),
        "rejected": sig_eval.get("rejected") or [],
    }
