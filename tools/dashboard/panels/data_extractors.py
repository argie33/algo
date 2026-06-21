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


def safe_get_dict(data: Any) -> dict[str, Any] | None:
    """Get dict from data if not error. Returns None if data is None (optional field).

    Fail-fast: Raises if data is error dict or is invalid type (not None or dict).
    Use for optional dict fields. For critical dicts that must exist, check for None explicitly.
    """
    if data is None:
        return None
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict but got {type(data).__name__}")
    if has_error(data):
        raise ValueError(f"Data contains error: {data.get('_error', 'unknown error')}")
    return data


def safe_get_list(data: Any) -> list | None:
    """Get list from data if not error. Returns None if data is None (optional field).

    Fail-fast: Raises if data is error dict or is invalid type (not None, list, or dict with error).
    Use for optional list fields. For critical lists that must exist, check for None explicitly.
    """
    if data is None:
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if has_error(data):
            raise ValueError(f"Data contains error: {data.get('_error', 'unknown error')}")
        if "items" in data and isinstance(data["items"], list):
            return data["items"]
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        return None
    raise TypeError(f"Expected dict or list but got {type(data).__name__}")


# Extract common field accessors as functions to reduce repetition in panels
def extract_config_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract common config display parameters.

    Fail-fast: All config fields are critical (validated at API boundary).
    Raises KeyError if required fields missing.
    """
    if not isinstance(cfg, dict) or has_error(cfg):
        return {"_error": "Config data unavailable"}
    required = ["mode", "enabled", "max_pos_n", "max_sec_n", "min_score", "base_risk", "t1_r"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise KeyError(f"Config missing critical fields: {missing}")
    return {
        "mode": cfg["mode"],
        "enabled": cfg["enabled"],
        "max_pos_n": cfg["max_pos_n"],
        "max_sec_n": cfg["max_sec_n"],
        "min_score": cfg["min_score"],
        "base_risk": cfg["base_risk"],
        "t1_r": cfg["t1_r"],
    }


def extract_risk_metrics(risk: dict[str, Any]) -> dict[str, Any]:
    """Extract risk metrics for display (only if valid data).

    Fail-fast: Risk metrics (VaR, CVaR, Beta, concentration) are critical
    financial data. Missing values raise error—cannot position size with None.
    Raises KeyError if required fields missing.
    """
    if not isinstance(risk, dict) or has_error(risk):
        return {"_error": "Risk metrics unavailable"}
    required = ["var95", "cvar95", "svar", "beta", "conc5"]
    missing = [k for k in required if k not in risk]
    if missing:
        raise KeyError(f"Risk metrics missing critical fields: {missing}")
    return {
        "var95": risk["var95"],
        "cvar95": risk["cvar95"],
        "svar": risk["svar"],
        "beta": risk["beta"],
        "conc5": risk["conc5"],
    }


def extract_run_info(run: dict[str, Any]) -> dict[str, Any]:
    """Extract run status info (error already checked).

    Fail-fast: success, halted, errored, run_id are critical.
    Raises KeyError if required fields missing.
    """
    if not isinstance(run, dict) or has_error(run):
        return {"_error": "Run info unavailable"}
    required = ["success", "halted", "errored", "run_id"]
    missing = [k for k in required if k not in run]
    if missing:
        raise KeyError(f"Run info missing critical fields: {missing}")
    phase_results = run.get("phase_results")
    if not isinstance(phase_results, list):
        phase_results = []
    return {
        "success": run["success"],
        "halted": run["halted"],
        "errored": run["errored"],
        "run_at": run.get("run_at"),
        "run_id": run["run_id"],
        "phase_results": phase_results,
        "halt_reason": run.get("halt_reason"),
        "summary": run.get("summary"),
        "_source": run.get("_source"),
    }


def extract_health_items(hlth: dict[str, Any] | list) -> tuple[list, bool | None]:
    """Extract health items and ready_to_trade status (error already checked).

    Args:
        hlth: Health response dict or list of items

    Returns:
        (items_list, ready_to_trade_bool_or_none) tuple
    """
    items = []
    ready_to_trade = None

    if isinstance(hlth, dict):
        # Fail-fast: if items field exists but is not a list, caller should have caught this error
        if "items" in hlth and isinstance(hlth.get("items"), list):
            items = hlth["items"]
        ready_to_trade = hlth.get("ready_to_trade")
    elif isinstance(hlth, list):
        items = hlth

    return items, ready_to_trade


def extract_phase_results(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and normalize phase results from run data.

    Handles various phase result formats and ensures consistent structure.
    Fail-fast: If phase_results is present but invalid, error should have been caught at API layer.
    """
    if not isinstance(run, dict):
        return []
    # Only return phase_results if it's explicitly a list; don't fall back to empty list
    if "phase_results" in run:
        results = run.get("phase_results")
        return results if isinstance(results, list) else []
    return []


def extract_item_field(item: dict[str, Any], field: str, default: Any = None) -> Any:
    """Extract field from health item (used in loops over items).

    After has_error() check at function entry, direct field access is safe.
    Use this for optional fields only.
    """
    if not isinstance(item, dict):
        return default
    return item.get(field, default)


def extract_signal_overview(sig: dict[str, Any]) -> dict[str, Any]:
    """Extract signal overview fields for compact & expanded displays (error already checked).

    Fail-fast: Do not fall back to empty dicts/lists. If optional fields are truly optional,
    caller should check them for None. If they should never be None, validation at API layer
    should have caught missing data and returned error.
    """
    if not isinstance(sig, dict) or has_error(sig):
        return {"_error": "Signal data unavailable"}
    return {
        "n": sig.get("n"),
        "total": sig.get("total"),
        "date": sig.get("date"),
        "grades": sig.get("grades"),
        "top_a": sig.get("top_a"),
        "near": sig.get("near"),
        "trend": sig.get("trend"),
        "buy_sigs": sig.get("buy_sigs"),
        "timestamp": sig.get("timestamp"),
    }


def extract_eval_funnel(sig_eval: dict[str, Any] | None) -> dict[str, Any]:
    """Extract evaluation funnel data (error already checked, data optional).

    Fail-fast: Do not fall back to empty list. If rejected field is optional,
    caller should handle None values.
    """
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
        "rejected": sig_eval.get("rejected"),
    }


def extract_portfolio_metrics(port: dict[str, Any]) -> dict[str, Any]:
    """Extract portfolio metrics for display (error already checked).

    Fail-fast: total_portfolio_value, total_cash, position_count are critical.
    Raises KeyError if required fields missing.
    """
    if not isinstance(port, dict) or has_error(port):
        return {"_error": "Portfolio data unavailable"}
    required = ["total_portfolio_value", "total_cash", "position_count"]
    missing = [k for k in required if k not in port]
    if missing:
        raise KeyError(f"Portfolio missing critical fields: {missing}")
    return {
        "pv": port["total_portfolio_value"],
        "dr": port.get("daily_return_pct"),
        "urp": port.get("unrealized_pnl_pct"),
        "cash": port["total_cash"],
        "npos": port["position_count"],
        "cum": port.get("cumulative_return_pct"),
        "mxdd": port.get("max_drawdown_pct"),
        "lgpos": port.get("largest_position_pct"),
        "snap": port.get("snapshot_date"),
    }


def extract_performance_metrics(perf: dict[str, Any]) -> dict[str, Any]:
    """Extract performance metrics for display (error already checked).

    Fail-fast: total_trades, winning_trades, losing_trades are critical.
    Raises KeyError if required fields missing.
    """
    if not isinstance(perf, dict) or has_error(perf):
        return {"_error": "Performance data unavailable"}
    required = ["n", "w", "l"]
    missing = [k for k in required if k not in perf]
    if missing:
        raise KeyError(f"Performance metrics missing critical fields: {missing}")
    return {
        "n": perf["n"],
        "w": perf["w"],
        "l": perf["l"],
        "streak": perf.get("streak"),
        "pnl": perf.get("pnl"),
        "unrlzd": perf.get("unrealized_pnl"),
        "pf": perf.get("profit_factor"),
        "sharpe": perf.get("sharpe"),
        "exp": perf.get("expectancy"),
        "avg_win": perf.get("avg_win"),
        "avg_loss": perf.get("avg_loss"),
        "equity_vals": perf.get("equity_vals"),
        "recent_rets": perf.get("recent_rets"),
        "open_count": perf.get("open_count"),
        "maxdd": perf.get("maxdd"),
    }


def extract_risk_data(risk: dict[str, Any]) -> dict[str, Any]:
    """Extract risk data for display (error already checked).

    Fail-fast: var95, cvar95, beta, conc5, svar are critical financial metrics.
    Raises KeyError if required fields missing.
    """
    if not isinstance(risk, dict) or has_error(risk):
        return {"_error": "Risk data unavailable"}
    required = ["var95", "cvar95", "beta", "conc5", "svar"]
    missing = [k for k in required if k not in risk]
    if missing:
        raise KeyError(f"Risk data missing critical fields: {missing}")
    return {
        "var95": risk["var95"],
        "cvar95": risk["cvar95"],
        "beta": risk["beta"],
        "conc5": risk["conc5"],
        "svar": risk["svar"],
        "date": risk.get("date"),
    }


def extract_economic_indicators(eco: dict[str, Any]) -> dict[str, Any]:
    """Extract all economic indicator fields for display (error already checked)."""
    if not isinstance(eco, dict) or has_error(eco):
        return {"_error": "Economic data unavailable"}
    return {
        "t10": eco.get("t10"),
        "t2": eco.get("t2"),
        "t3m": eco.get("t3m"),
        "t6m": eco.get("t6m"),
        "yc_10_2": eco.get("yc_10_2"),
        "yc_10_3m": eco.get("yc_10_3m"),
        "hy": eco.get("hy"),
        "ig": eco.get("ig"),
        "oil": eco.get("oil"),
        "nfci": eco.get("nfci"),
        "fed_funds": eco.get("fed_funds"),
        "cpi_yoy": eco.get("cpi_yoy"),
        "unrate": eco.get("unrate"),
        "be10": eco.get("be10"),
        "be5": eco.get("be5"),
        "dxy": eco.get("dxy"),
        "mortgage": eco.get("mortgage"),
        "umcsent": eco.get("umcsent"),
    }
