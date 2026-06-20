"""Error type detection and messaging utilities."""

from typing import Any


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
