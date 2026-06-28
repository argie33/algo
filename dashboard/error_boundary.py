"""Error boundary utilities for dashboard panels.

Ensures all panels gracefully handle missing or error data, preventing silent failures
and making error state visible to operators.
"""

from typing import Any

from rich.markup import escape
from rich.panel import Panel

# Color constants for dashboard rendering
G = "bright_green"
R = "bright_red"
Y = "yellow"
CY = "cyan"
DIM = "dim"
MG = "magenta"
WH = "white"

TIER_COLOR = {
    "confirmed_uptrend": "bright_green",
    "healthy_uptrend": "green",
    "pressure": "yellow",
    "caution": "orange1",
    "correction": "bright_red",
}

TIER_SHORT = {
    "confirmed_uptrend": "CONFIRMED UP",
    "healthy_uptrend": "HEALTHY UP",
    "pressure": "PRESSURE",
    "caution": "CAUTION",
    "correction": "CORRECTION",
}


def has_error(data: Any) -> bool:
    """Check if data dict contains an error marker."""
    return isinstance(data, dict) and "_error" in data


def is_data_stale(data: Any) -> bool:
    """Check if data dict is marked as stale."""
    return isinstance(data, dict) and data.get("_stale_cache") is True


def get_error_message_plain(data: Any) -> str | None:
    """Extract error message from data without Rich formatting."""
    if not isinstance(data, dict):
        return None
    return data.get("_error")


def get_error_message(data: Any) -> str | None:
    """Extract error message from data with Rich markup formatting.

    Distinguishes between stale data and hard errors for better visibility.
    """
    plain_msg = get_error_message_plain(data)
    if plain_msg is None:
        return None
    if is_data_stale(data):
        return f"[yellow]⚠ STALE[/]: {data.get('_error', 'Data too old')}"
    return plain_msg


def safe_get(data: Any, key: str) -> Any:
    """Safely get nested value, raising on error or missing key.

    Raises ValueError if data has error marker, on missing key, or wrong type.
    This ensures response structure issues are surfaced rather than hidden.
    """
    if has_error(data):
        raise ValueError(f"Data contains error: {data.get('_error', 'unknown error')}")
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")
    if key not in data:
        raise ValueError(f"Response dict missing required key '{key}'. Available keys: {list(data.keys())}")
    return data[key]


def safe_list(data: Any) -> list[Any]:
    """Safely extract list from data, raising on errors instead of hiding them.

    Raises ValueError if data has error marker or malformed structure.
    Fail-fast: Raises on any data structure issue.
    """
    if has_error(data):
        raise ValueError(f"Data contains error: {data.get('_error', 'unknown error')}")
    if isinstance(data, dict):
        if "items" in data:
            items = data["items"]
            if isinstance(items, list):
                return items
            # Malformed: items exists but is not a list
            raise ValueError(f"'items' field is not a list: {type(items).__name__}")
        elif "data" in data and isinstance(data["data"], list):
            return data["data"]
    # Fallback: raise on invalid type
    if isinstance(data, list):
        return data
    raise ValueError(f"Cannot extract list from {type(data).__name__}: expected dict, list, or dict with 'items'/'data' field")


def error_summary_panel(data: dict[str, Any]) -> Panel | None:
    """Render error summary panel for dashboard.

    Returns None if no errors found, otherwise returns error panel.
    """
    errors = {}
    for key, value in data.items():
        if isinstance(value, dict) and "_error" in value:
            errors[key] = value.get("_error") or "API error (no details available)"

    if not errors:
        return None

    text_lines = []
    for endpoint, msg in sorted(errors.items()):
        text_lines.append(f"[red]{escape(str(endpoint))}[/]: {escape(str(msg)[:100])}")

    return Panel(
        "\n".join(text_lines),
        title="[red]API Errors[/]",
        style="red",
        border_style="red",
    )


def error_summary_panel_expanded(data: dict[str, Any]) -> Panel | None:
    """Render expanded error summary panel for dashboard errors view mode."""
    errors = {}
    for key, value in data.items():
        if isinstance(value, dict) and "_error" in value:
            errors[key] = value.get("_error") or "API error (no details available)"

    if not errors:
        return None

    text_lines = []
    for endpoint, msg in sorted(errors.items()):
        text_lines.append(f"[red]{escape(str(endpoint))}[/]: {escape(str(msg))}")

    return Panel(
        "\n".join(text_lines),
        title="[red]Endpoint Errors[/]",
        style="red",
        border_style="red",
        expand=True,
    )
