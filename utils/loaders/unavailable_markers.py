#!/usr/bin/env python3
"""Standardized data_unavailable markers for loaders.

CRITICAL ISSUE #4 FIX: Distinguishes between:
- "loader_failed:..." - Loader attempted to fetch but failed (ALERT)
- "not_applicable:..." - Measurement doesn't apply to this security type (OK)
- "unavailable_temporary:..." - Transient API/data issue (WARN)

Enables dashboard to distinguish real failures from expected N/A cases,
reducing alert fatigue and improving system observability.
"""

from typing import Any


def marker_loader_failed(symbol: str, reason: str, details: str = "") -> dict[str, Any]:
    """Mark data as unavailable due to loader failure.

    Used when loader attempted to fetch data but failed (e.g., no growth metrics found,
    API returned error, data validation failed).

    Dashboard treats this as a real failure that should be investigated.
    """
    full_reason = f"loader_failed:{reason}"
    if details:
        full_reason = f"{full_reason} - {details}"
    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": full_reason,
        "reason_type": "loader_failed",
    }


def marker_not_applicable(symbol: str, security_type: str, reason: str = "") -> dict[str, Any]:
    """Mark data as unavailable because measurement doesn't apply to this security type.

    Used for securities where a metric genuinely doesn't apply (e.g., institutional
    ownership for REITs, earnings data for ETFs).

    Dashboard treats this as expected, no alert needed.
    """
    full_reason = f"not_applicable:{security_type}"
    if reason:
        full_reason = f"{full_reason} - {reason}"
    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": full_reason,
        "reason_type": "not_applicable",
    }


def marker_temporary_unavailable(symbol: str, reason: str, retry_seconds: int = 300) -> dict[str, Any]:
    """Mark data as temporarily unavailable due to transient API/data issue.

    Used for timeouts, rate limits, or temporary data unavailability that should
    resolve on retry.

    Dashboard treats this as a warning, should retry soon.
    """
    return {
        "symbol": symbol,
        "data_unavailable": True,
        "reason": f"unavailable_temporary:{reason} (retry in {retry_seconds}s)",
        "reason_type": "temporary",
    }


def extract_reason_type(reason_str: str | None) -> str:
    """Extract reason type from standardized reason string.

    Returns:
        - "loader_failed" if reason starts with "loader_failed:"
        - "not_applicable" if reason starts with "not_applicable:"
        - "temporary" if reason starts with "unavailable_temporary:"
        - "unknown" if reason is None or doesn't match known prefixes
    """
    if not reason_str:
        return "unknown"

    if reason_str.startswith("loader_failed:"):
        return "loader_failed"
    if reason_str.startswith("not_applicable:"):
        return "not_applicable"
    if reason_str.startswith("unavailable_temporary:"):
        return "temporary"

    return "unknown"
