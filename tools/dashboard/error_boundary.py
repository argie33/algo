"""Error boundary utilities for dashboard panels.

Ensures all panels gracefully handle missing or error data, preventing silent failures
and making error state visible to operators.
"""

from typing import Any, Dict, List, Optional
from rich.panel import Panel
from rich.text import Text
from utilities import R, Y, CY, DIM


def has_error(data: Any) -> bool:
    """Check if data has error marker."""
    return isinstance(data, dict) and "_error" in data


def get_error_message(data: Any) -> Optional[str]:
    """Extract error message from data if present."""
    if has_error(data):
        return data.get("_error", "Unknown error")
    return None


def safe_get(data: Any, key: str, default: Any = None) -> Any:
    """Safely get nested value, returning default if data has error or key missing."""
    if has_error(data):
        return default
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def safe_list(data: Any) -> List:
    """Safely extract list from data, returning empty list on error."""
    if has_error(data):
        return []
    if isinstance(data, dict):
        return data.get("items", []) if "items" in data else (data.get("data", []) if isinstance(data.get("data"), list) else [])
    if isinstance(data, list):
        return data
    return []


def error_summary_panel(data_dict: Dict[str, Any]) -> Optional[Panel]:
    """Generate a panel showing all failed data fetchers.

    Returns None if no errors, otherwise returns a Panel listing them.
    """
    failed = []
    for key, data in data_dict.items():
        if has_error(data):
            error_msg = get_error_message(data)
            # Truncate long error messages (keep endpoint/type visible)
            if len(error_msg) > 80:
                error_msg = error_msg[:77] + "..."
            failed.append(f"[{Y}]{key}[/]: {error_msg}")

    if not failed:
        return None

    content = "\n".join(failed)
    return Panel(
        Text.from_markup(content),
        title=f"[bold {R}]⚠ Data Fetch Failures ({len(failed)})[/]",
        border_style=R,
        padding=(0, 1),
    )


def make_panel_safe(panel_fn):
    """Decorator to wrap panel functions with error handling.

    Catches rendering errors and returns an error panel instead of crashing.
    """
    def wrapper(*args, **kwargs):
        try:
            return panel_fn(*args, **kwargs)
        except Exception as e:
            # Extract first positional arg if it's a data dict for context
            data_name = kwargs.get("title", panel_fn.__name__)
            return Panel(
                Text.from_markup(f"[{R}]Panel rendering failed[/]: {type(e).__name__}\n[{DIM}]{str(e)[:100]}[/]"),
                title=f"[bold]{data_name}[/]",
                border_style=R,
                padding=(0, 1),
            )
    return wrapper
