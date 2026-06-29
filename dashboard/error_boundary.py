"""Error boundary utilities for dashboard panels.

Ensures all panels gracefully handle missing or error data, preventing silent failures
and making error state visible to operators.

Contract:
- All .get() calls use explicit safe defaults (never empty strings for required fields)
- Functions returning None log explicitly when no errors found (visibility)
- data_unavailable markers used consistently across all optional data paths
"""

import logging
from typing import Any

from rich.markup import escape
from rich.panel import Panel

logger = logging.getLogger(__name__)

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


def create_data_unavailable_marker(reason: str) -> dict[str, Any]:
    """Create explicit data_unavailable marker for optional data paths.

    Used when dashboard fetchers cannot retrieve data, ensuring callers
    distinguish "no data" from "error occurred" vs "loading".

    Args:
        reason: Human-readable explanation for missing data

    Returns:
        Dict with explicit unavailability flag and reason
    """
    if not reason or not reason.strip():
        raise ValueError("[CRITICAL] data_unavailable reason cannot be empty")

    return {
        "data_unavailable": True,
        "reason": reason.strip(),
    }


def has_error(data: Any) -> bool:
    """Check if data dict contains an error marker.

    Safe to call on any type; returns False for non-dict.
    Contract: _error marker means data structure is invalid.

    Args:
        data: Any value to check

    Returns:
        True if data is dict with _error marker, False otherwise
    """
    return isinstance(data, dict) and "_error" in data


def is_data_stale(data: Any) -> bool:
    """Check if data dict is marked as stale.

    Safe to call on any type; returns False for non-dict.
    Validates: _stale_cache must be boolean True, never truthy other values.
    Contract: Stale data means cache is old, may still be usable with warning.

    Args:
        data: Any value to check

    Returns:
        True if data is dict with _stale_cache=True, False otherwise
    """
    return isinstance(data, dict) and data.get("_stale_cache") is True


def get_error_message_plain(data: Any) -> str | None:
    """Extract error message from data without Rich formatting.

    Always returns explicit error message or raises on invalid state.
    Validates: error message must exist and be valid when _error marker present.
    """
    if not isinstance(data, dict):
        return None

    # Fail-fast: if _error marker present, message MUST be valid
    if "_error" in data:
        error_msg = data["_error"]  # Direct access, not .get() — required field
        if error_msg is None or (isinstance(error_msg, str) and not error_msg.strip()):
            logger.error("Error marker present but message empty/None — invalid error state")
            raise ValueError("[CRITICAL] _error marker present but message is empty/None")
        return str(error_msg)

    return None


def get_error_message(data: Any) -> str | None:
    """Extract error message from data with Rich markup formatting.

    Distinguishes between stale data and hard errors for better visibility.
    Validates: if _stale_cache present, it must be boolean True.
    Raises if stale data marker present but error message missing.
    """
    plain_msg = get_error_message_plain(data)
    if plain_msg is None:
        return None

    if is_data_stale(data):
        # If stale, error message MUST exist and be valid
        if isinstance(data, dict) and "_error" in data:
            stale_error = data["_error"]  # Direct access — required if _stale_cache=True
            if stale_error is None or (isinstance(stale_error, str) and not stale_error.strip()):
                logger.error("Stale data marker present but error message empty/None — invalid state")
                raise ValueError("[CRITICAL] _stale_cache=True but _error message is empty/None")
            return f"[yellow]⚠ STALE[/]: {stale_error}"
        # If stale but no error marker, this is an invalid state
        logger.error("Data marked stale but missing _error marker — inconsistent state")
        raise ValueError("[CRITICAL] Data marked _stale_cache=True but _error marker missing")

    return plain_msg


def safe_get(data: Any, key: str) -> Any:
    """Safely get nested value, raising on error or missing key.

    Fail-fast contract:
    - Raises ValueError if data has error marker (data structure invalid)
    - Raises ValueError if key missing (required field unavailable)
    - Raises ValueError if wrong type (not dict)
    Ensures response structure issues are surfaced rather than hidden.

    Args:
        data: Response dict to extract from
        key: Required key to fetch

    Returns:
        Value at data[key]

    Raises:
        ValueError: If data has error marker, wrong type, or key missing
    """
    if has_error(data):
        # Direct access to _error — it MUST exist if has_error() returned True
        if isinstance(data, dict) and "_error" in data:
            error_msg = data["_error"]
        else:
            error_msg = "[CRITICAL] has_error returned True but _error marker missing"
        logger.error(f"safe_get: Data contains error marker: {error_msg}")
        raise ValueError(f"Data contains error: {error_msg}")

    if not isinstance(data, dict):
        logger.error(f"safe_get: Expected dict, got {type(data).__name__}")
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    if key not in data:
        logger.error(f"safe_get: Missing required key '{key}'. Available: {list(data.keys())}")
        raise ValueError(f"Response dict missing required key '{key}'. Available keys: {list(data.keys())}")

    return data[key]


def safe_list(data: Any) -> list[Any]:
    """Safely extract list from data, raising on errors instead of hiding them.

    Fail-fast contract:
    - Raises ValueError if data has error marker
    - Raises ValueError if dict has 'items'/'data' but wrong type
    - Raises ValueError if cannot extract list from given structure
    No silent returns or degraded fallbacks.

    Accepted structures:
    - Direct list: [1, 2, 3]
    - Dict with 'items': {"items": [1, 2, 3]}
    - Dict with 'data': {"data": [1, 2, 3]}

    Args:
        data: Response to extract list from

    Returns:
        List of items

    Raises:
        ValueError: If error marker, malformed structure, or cannot extract list
    """
    if has_error(data):
        # Direct access to _error — it MUST exist if has_error() returned True
        if isinstance(data, dict) and "_error" in data:
            error_msg = data["_error"]
        else:
            error_msg = "[CRITICAL] has_error returned True but _error marker missing"
        logger.error(f"safe_list: Data contains error marker: {error_msg}")
        raise ValueError(f"Data contains error: {error_msg}")

    if isinstance(data, dict):
        # Try 'items' field
        if "items" in data:
            items = data["items"]
            if isinstance(items, list):
                return items
            # Malformed: items exists but is not a list
            logger.error(f"safe_list: 'items' field is not a list: {type(items).__name__}")
            raise ValueError(f"'items' field is not a list: {type(items).__name__}")

        # Try 'data' field
        if "data" in data:
            data_field = data["data"]
            if isinstance(data_field, list):
                return data_field
            logger.error(f"safe_list: 'data' field is not a list: {type(data_field).__name__}")
            raise ValueError(f"'data' field is not a list: {type(data_field).__name__}")

    # Direct list passthrough
    if isinstance(data, list):
        return data

    # Cannot extract: raise with clear message
    logger.error(f"safe_list: Cannot extract list from {type(data).__name__}")
    raise ValueError(
        f"Cannot extract list from {type(data).__name__}: "
        f"expected dict with 'items'/'data' field, direct list, or error dict"
    )


def error_summary_panel(data: dict[str, Any]) -> Panel | None:
    """Render error summary panel for dashboard.

    Scans all data endpoints for error markers and renders single error panel.
    Returns None if no errors found (logged for visibility).
    Raises if error marker found but message cannot be extracted.

    Args:
        data: Dict of endpoint responses, some may have _error marker

    Returns:
        Panel with error summaries, or None if no errors (logged)

    Raises:
        ValueError: If _error marker present but message cannot be extracted
    """
    if not isinstance(data, dict):
        logger.error(f"error_summary_panel received non-dict: {type(data).__name__}")
        return None

    errors = {}
    for key, value in data.items():
        if isinstance(value, dict) and "_error" in value:
            # get_error_message_plain will raise if _error marker invalid
            msg = get_error_message_plain(value)
            if msg is None:
                logger.error(f"error_summary_panel: _error marker in {key} but no message extracted")
                raise ValueError(f"[CRITICAL] Endpoint '{key}' has _error marker but message extraction failed")
            errors[key] = msg

    if not errors:
        logger.debug("error_summary_panel: no errors found in data, returning None")
        return None

    logger.warning(f"error_summary_panel: found {len(errors)} endpoint error(s)")

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
    """Render expanded error summary panel for dashboard errors view mode.

    Extended version of error_summary_panel with full error messages (no truncation).
    Returns None if no errors found (logged for visibility).
    Raises if error marker found but message cannot be extracted.

    Args:
        data: Dict of endpoint responses, some may have _error marker

    Returns:
        Expanded Panel with full error text, or None if no errors (logged)

    Raises:
        ValueError: If _error marker present but message cannot be extracted
    """
    if not isinstance(data, dict):
        logger.error(f"error_summary_panel_expanded received non-dict: {type(data).__name__}")
        return None

    errors = {}
    for key, value in data.items():
        if isinstance(value, dict) and "_error" in value:
            # get_error_message_plain will raise if _error marker invalid
            msg = get_error_message_plain(value)
            if msg is None:
                logger.error(f"error_summary_panel_expanded: _error marker in {key} but no message extracted")
                raise ValueError(f"[CRITICAL] Endpoint '{key}' has _error marker but message extraction failed")
            errors[key] = msg

    if not errors:
        logger.debug("error_summary_panel_expanded: no errors found in data, returning None")
        return None

    logger.warning(f"error_summary_panel_expanded: found {len(errors)} endpoint error(s)")

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
