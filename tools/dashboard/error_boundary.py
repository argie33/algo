"""Error boundary utilities for dashboard panels.

Ensures all panels gracefully handle missing or error data, preventing silent failures
and making error state visible to operators.
"""

from typing import Any, Dict, List, Optional
from rich.panel import Panel
from rich.text import Text
from utilities import R, Y, CY, DIM


def has_error(data: Any) -> bool:
    """Check if data has error marker (includes stale data as error state)."""
    if not isinstance(data, dict):
        return False
    return "_error" in data or data.get("_data_stale", False)


def is_data_stale(data: Any) -> bool:
    """Check if data is marked as stale (too old to be reliable)."""
    return isinstance(data, dict) and data.get("_data_stale", False)


def get_error_message(data: Any) -> Optional[str]:
    """Extract error message from data if present.

    Distinguishes between stale data and hard errors for better visibility.
    """
    if not isinstance(data, dict):
        return None
    if is_data_stale(data):
        return f"[yellow]⚠ STALE[/]: {data.get('_error', 'Data too old')}"
    if "_error" in data:
        return data.get("_error", "Unknown error")
    return None


def safe_get(data: Any, key: str, default: Any = None) -> Any:
    """Safely get nested value, propagating errors instead of hiding them.

    Returns error dict on error, default on missing key, or the value.
    """
    if has_error(data):
        return data
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def safe_list(data: Any) -> List:
    """Safely extract list from data, propagating errors instead of hiding them.

    Returns error dict on error, items list otherwise.
    """
    if has_error(data):
        return data
    if isinstance(data, dict):
        return data.get("items", []) if "items" in data else (data.get("data", []) if isinstance(data.get("data"), list) else [])
    if isinstance(data, list):
        return data
    return []


def error_summary_panel(data_dict: Dict[str, Any]) -> Optional[Panel]:
    """Generate a panel showing all failed data fetchers and stale data.

    Distinguishes between hard errors (red) and stale data (yellow).
    Returns None if no errors or stale data, otherwise returns a Panel listing them.
    """
    failed_errors = []
    stale_data = []

    for key, data in data_dict.items():
        if not has_error(data):
            continue
        error_msg = get_error_message(data)
        # Truncate long error messages (keep endpoint/type visible)
        if len(error_msg) > 80:
            error_msg = error_msg[:77] + "..."

        if is_data_stale(data):
            stale_data.append(f"[{Y}]⚠ {key}[/]: {error_msg}")
        else:
            failed_errors.append(f"[{R}]✗ {key}[/]: {error_msg}")

    if not failed_errors and not stale_data:
        return None

    # Show stale data warning in yellow, hard errors in red
    content_parts = failed_errors + stale_data
    content = "\n".join(content_parts)

    border_color = R if failed_errors else Y
    title = f"[bold {border_color}]{'⚠ ' if stale_data else '✗ '}Data Issues ({len(failed_errors) + len(stale_data)})[/]"

    return Panel(
        Text.from_markup(content),
        title=title,
        border_style=border_color,
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
