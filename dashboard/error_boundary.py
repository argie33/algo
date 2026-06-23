"""Error boundary utilities for dashboard panels.

Ensures all panels gracefully handle missing or error data, preventing silent failures
and making error state visible to operators.
"""

from typing import Any, cast

from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

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
    return isinstance(data, dict) and data.get("_data_stale") is True


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


def safe_get(data: Any, key: str, default: Any = None) -> Any:
    """Safely get nested value, propagating errors instead of hiding them.

    Returns error dict on error, default on missing key, or the value.
    """
    if has_error(data):
        return data
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def safe_list(data: Any) -> list[Any]:
    """Safely extract list from data, propagating errors instead of hiding them.

    Returns error dict on error, items list otherwise.
    Fail-fast: Returns error if data structure is malformed.
    """
    if has_error(data):
        return cast(list[Any], data)
    if isinstance(data, dict):
        if "items" in data:
            items = data["items"]
            if isinstance(items, list):
                return items
            # Malformed: items exists but is not a list
            return cast(list[Any], {"_error": f"'items' is not a list: {type(items).__name__}"})
        elif "data" in data and isinstance(data["data"], list):
            return data["data"]
        else:
            # Malformed: dict has neither 'items' nor 'data' list
            return cast(list[Any], {"_error": "Response dict missing 'items' or 'data' field"})
    if isinstance(data, list):
        return data
    # Malformed: not a dict or list
    return cast(list[Any], {"_error": f"Expected list or dict, got {type(data).__name__}"})


def _classify_errors(
    data_dict: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str]]:
    """Classify data errors into hard errors, stale data, and circuit-breaker-open keys.

    Returns (hard_errors, stale_entries, circuit_open_keys) where each hard/stale
    entry is a (key, plain_message) tuple so callers can format as needed.
    Circuit-breaker-open entries are grouped into circuit_open_keys to avoid flooding
    the panel when a single API outage blocks many fetchers simultaneously.
    """
    hard_errors: list[tuple[str, str]] = []
    stale_entries: list[tuple[str, str]] = []
    circuit_open_keys: list[str] = []

    for key, data in data_dict.items():
        if not has_error(data):
            continue
        if isinstance(data, dict) and data.get("_circuit_open"):
            circuit_open_keys.append(key)
            continue
        plain_msg = get_error_message_plain(data) or "Unknown error"
        if is_data_stale(data):
            stale_entries.append((key, plain_msg))
        else:
            hard_errors.append((key, plain_msg))

    return hard_errors, stale_entries, circuit_open_keys


def error_summary_panel(data_dict: dict[str, Any]) -> Panel | None:
    """Generate a compact panel showing all failed data fetchers and stale data.

    Distinguishes between hard errors (red) and stale data (yellow).
    Circuit-breaker cascades are collapsed into a single entry.
    Returns None if no errors or stale data.
    """
    hard_errors, stale_entries, circuit_open_keys = _classify_errors(data_dict)

    failed_lines: list[str] = []
    stale_lines: list[str] = []

    if circuit_open_keys:
        keys_str = escape(", ".join(sorted(circuit_open_keys)))
        failed_lines.append(
            f"[{R}]✗ circuit breaker OPEN[/]: API unavailable — {len(circuit_open_keys)} fetchers blocked ({keys_str})"
        )

    for key, plain_msg in hard_errors:
        if len(plain_msg) > 80:
            plain_msg = plain_msg[:77] + "..."
        failed_lines.append(f"[{R}]✗ {key}[/]: {escape(plain_msg)}")

    for key, plain_msg in stale_entries:
        if len(plain_msg) > 80:
            plain_msg = plain_msg[:77] + "..."
        stale_lines.append(f"[{Y}]⚠ {key}[/]: [yellow]⚠ STALE[/]: {escape(plain_msg)}")

    if not failed_lines and not stale_lines:
        return None

    content = "\n".join(failed_lines + stale_lines)
    border_color = R if failed_lines else Y
    total = len(failed_lines) + len(stale_lines)
    title = f"[bold {border_color}]{'⚠ ' if stale_lines else '✗ '}Data Issues ({total})[/]  [dim][d] expand[/]"

    return Panel(
        Text.from_markup(content),
        title=title,
        border_style=border_color,
        padding=(0, 1),
    )


def error_summary_panel_expanded(data_dict: dict[str, Any]) -> Panel | None:
    """Generate expanded panel showing all failed data fetchers and stale data with full details.

    Shows complete error messages without truncation.
    Circuit-breaker cascades are collapsed into a single entry.
    Returns None if no errors or stale data.
    """
    hard_errors, stale_entries, circuit_open_keys = _classify_errors(data_dict)

    failed_lines: list[str] = []
    stale_lines: list[str] = []

    if circuit_open_keys:
        keys_str = escape(", ".join(sorted(circuit_open_keys)))
        failed_lines.append(
            f"[{R}]✗ circuit breaker OPEN[/]:\n"
            f"  [dim]API unavailable — {len(circuit_open_keys)} fetchers blocked\n"
            f"  Blocked: {keys_str}[/]"
        )

    for key, plain_msg in hard_errors:
        failed_lines.append(f"[{R}]✗ {key}[/]:\n  [dim]{escape(plain_msg)}[/]")

    for key, plain_msg in stale_entries:
        stale_lines.append(f"[{Y}]⚠ {key}[/]:\n  [dim][yellow]⚠ STALE[/]: {escape(plain_msg)}[/]")

    if not failed_lines and not stale_lines:
        return None

    content = "\n\n".join(failed_lines + stale_lines)
    border_color = R if failed_lines else Y
    total = len(failed_lines) + len(stale_lines)
    title = f"[bold {border_color}]{'⚠ ' if stale_lines else '✗ '}Data Issues ({total})[/]  [dim][d] collapse[/]"

    return Panel(
        Text.from_markup(content),
        title=title,
        border_style=border_color,
        padding=(0, 1),
    )


def make_panel_safe(panel_fn: Any) -> Any:
    """Decorator to wrap panel functions with error handling.

    Catches rendering errors and returns an error panel instead of crashing.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
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
