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
        return data.get("items", []) or data.get("data", []) or []
    return []


def safe_get_field(data: dict[str, Any], field: str, default: Any = None) -> Any:
    """Get field from validated data dict (error already checked)."""
    if not isinstance(data, dict):
        return default
    return data.get(field, default)


# Extract common field accessors as functions to reduce repetition in panels
def extract_config_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract common config display parameters."""
    return {
        "mode": cfg.get("mode", "?"),
        "enabled": cfg.get("enabled", True),
        "max_pos_n": cfg.get("max_pos_n"),
        "max_sec_n": cfg.get("max_sec_n"),
        "min_score": cfg.get("min_score"),
        "base_risk": cfg.get("base_risk"),
        "t1_r": cfg.get("t1_r"),
    }


def extract_risk_metrics(risk: dict[str, Any]) -> dict[str, Any]:
    """Extract risk metrics for display (only if valid data)."""
    if not isinstance(risk, dict):
        return {}
    return {
        "var95": risk.get("var95", 0),
        "cvar95": risk.get("cvar95", 0),
        "svar": risk.get("svar", 0),
        "beta": risk.get("beta", 0),
        "conc5": risk.get("conc5", 0),
    }


def extract_run_info(run: dict[str, Any]) -> dict[str, Any]:
    """Extract run status info (error already checked)."""
    if not isinstance(run, dict):
        return {"success": False, "halted": False, "run_at": None}
    return {
        "success": run.get("success", False),
        "halted": run.get("halted", False),
        "errored": run.get("errored", False),
        "run_at": run.get("run_at"),
        "run_id": run.get("run_id"),
        "phase_results": run.get("phase_results", []),
        "halt_reason": run.get("halt_reason", ""),
        "summary": run.get("summary", ""),
        "_source": run.get("_source", ""),
    }
