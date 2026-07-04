"""Data extraction helpers for dashboard panels - fail-fast pattern.

Replaces defensive .get() calls with up-front validation + direct access.
Pattern:
  1. Check has_error() once at entry point
  2. If error: display error panel immediately
  3. Then use direct access for validated fields (no .get() needed)
  4. Use .get() ONLY for truly optional fields
"""

import logging
from typing import Any

from ..error_boundary import has_error

logger = logging.getLogger(__name__)


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
    # Explicitly handle None case instead of using "or" operator
    if defaults is None:
        defaults = {}
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
    """Get dict from data if not error. Returns marker dict if data is None (optional field).

    Returns:
        dict: validated non-error dict OR marker dict with data_unavailable=True

    Raises:
        TypeError: if data is not dict, list, or None
        ValueError: if data is error dict
    """
    if data is None:
        logger.debug("safe_get_dict: data is None (optional field not present), returning unavailability marker")
        return {
            "data_unavailable": True,
            "reason": "data_not_present",
        }
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict but got {type(data).__name__}")
    if has_error(data):
        raise ValueError(f"Data contains error: {data.get('_error', 'unknown error')}")
    return data


def safe_get_list(data: Any) -> list[Any] | dict[str, Any]:
    """Get list from data if not error. Returns marker dict if data is None or dict without list (optional field).

    Returns:
        list: extracted list from data or data.items or data.data
        dict: marker dict with data_unavailable=True if data is None or dict without list/items/data fields (optional field not present)

    Raises:
        TypeError: if data is not dict, list, or None
        ValueError: if data is error dict
    """
    if data is None:
        logger.debug("safe_get_list: data is None (optional field not present), returning unavailability marker")
        return {
            "data_unavailable": True,
            "reason": "data_not_present",
        }
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if has_error(data):
            raise ValueError(f"Data contains error: {data.get('_error', 'unknown error')}")
        if "items" in data and isinstance(data["items"], list):
            return data["items"]
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        logger.debug("safe_get_list: dict has no items/data list field (optional field not present), returning unavailability marker")
        return {
            "data_unavailable": True,
            "reason": "list_field_not_found",
        }
    raise TypeError(f"Expected dict or list but got {type(data).__name__}")


# Extract common field accessors as functions to reduce repetition in panels
def extract_config_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract common config display parameters.

    Fail-fast: All config fields are critical (validated at API boundary).
    Raises KeyError if required fields missing.
    """
    if not isinstance(cfg, dict):
        raise TypeError(f"Expected dict but got {type(cfg).__name__}")
    if has_error(cfg):
        raise ValueError(f"Config data contains error: {cfg.get('_error', 'unknown error')}")
    required = [
        "mode",
        "enabled",
        "max_pos_n",
        "max_sec_n",
        "min_score",
        "base_risk",
        "t1_r",
    ]
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
    if not isinstance(risk, dict):
        raise TypeError(f"Expected dict but got {type(risk).__name__}")
    if has_error(risk):
        raise ValueError(f"Risk metrics contain error: {risk.get('_error', 'unknown error')}")
    required = ["var95", "cvar95", "beta", "conc5"]
    missing = [k for k in required if k not in risk]
    if missing:
        raise KeyError(f"Risk metrics missing critical fields: {missing}")
    return {
        "var95": risk["var95"],
        "cvar95": risk["cvar95"],
        "svar": risk.get("svar"),
        "beta": risk["beta"],
        "conc5": risk["conc5"],
    }


def extract_run_info(run: dict[str, Any]) -> dict[str, Any]:
    """Extract run status info (error already checked).

    Fail-fast: success, halted, errored, run_id are critical.
    Raises KeyError if required fields missing.
    """
    if not isinstance(run, dict):
        raise TypeError(f"Expected dict but got {type(run).__name__}")
    if has_error(run):
        raise ValueError(f"Run info contains error: {run.get('_error', 'unknown error')}")
    required = ["success", "halted", "errored", "run_id", "phase_results"]
    missing = [k for k in required if k not in run]
    if missing:
        raise KeyError(f"Run info missing critical fields: {missing}")
    phase_results = run["phase_results"]
    if not isinstance(phase_results, list):
        raise TypeError(f"phase_results must be list, got {type(phase_results).__name__}")
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


def extract_health_items(hlth: dict[str, Any] | list[Any]) -> tuple[list[Any], bool | None]:
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

    Fail-fast: phase_results is required. Missing or invalid phase_results is a critical data error.
    """
    if not isinstance(run, dict):
        raise TypeError(f"extract_phase_results expects dict, got {type(run).__name__}")
    if "phase_results" not in run:
        raise KeyError("Run data missing required 'phase_results' field")
    results = run["phase_results"]
    if not isinstance(results, list):
        raise TypeError(f"phase_results must be list, got {type(results).__name__}")
    return results


def safe_get_field(data: dict[str, Any] | None, field: str, default: Any = None) -> Any:
    """Safely get a field from a dict, returning default if missing.

    Use for optional fields after has_error() check at function entry.
    """
    if not isinstance(data, dict):
        return default
    return data.get(field, default)


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
    if not isinstance(sig, dict):
        raise TypeError(f"Expected dict but got {type(sig).__name__}")
    if has_error(sig):
        raise ValueError(f"Signal data contains error: {sig.get('_error', 'unknown error')}")
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

    Fail-fast: Do not return empty dict—signal evaluation is critical for understanding
    how many candidates were evaluated and rejected. Empty dict hides data unavailability.
    """
    if not sig_eval:
        raise ValueError("Signal evaluation data unavailable")
    if not isinstance(sig_eval, dict):
        raise TypeError(f"Invalid signal evaluation data: expected dict, got {type(sig_eval).__name__}")
    if has_error(sig_eval):
        raise ValueError(f"Signal evaluation contains error: {sig_eval.get('_error', 'unknown error')}")
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
    if not isinstance(port, dict):
        raise TypeError(f"Expected dict but got {type(port).__name__}")
    if has_error(port):
        raise ValueError(f"Portfolio data contains error: {port.get('_error', 'unknown error')}")
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
    if not isinstance(perf, dict):
        raise TypeError(f"Expected dict but got {type(perf).__name__}")
    if has_error(perf):
        raise ValueError(f"Performance data contains error: {perf.get('_error', 'unknown error')}")
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

    Fail-fast: var95, cvar95, beta, conc5 are critical financial metrics.
    svar is optional—requires historical data accumulation.
    Raises KeyError if required fields missing.
    """
    if not isinstance(risk, dict):
        raise TypeError(f"Expected dict but got {type(risk).__name__}")
    if has_error(risk):
        raise ValueError(f"Risk data contains error: {risk.get('_error', 'unknown error')}")
    required = ["var95", "cvar95", "beta", "conc5"]
    missing = [k for k in required if k not in risk]
    if missing:
        raise KeyError(f"Risk data missing critical fields: {missing}")
    return {
        "var95": risk["var95"],
        "cvar95": risk["cvar95"],
        "beta": risk["beta"],
        "conc5": risk["conc5"],
        "svar": risk.get("svar"),
        "date": risk.get("date"),
    }


def extract_economic_indicators(eco: dict[str, Any]) -> dict[str, Any]:
    """Extract all economic indicator fields for display (error already checked)."""
    if not isinstance(eco, dict):
        raise TypeError(f"Expected dict but got {type(eco).__name__}")
    if has_error(eco):
        raise ValueError(f"Economic data contains error: {eco.get('_error', 'unknown error')}")
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
