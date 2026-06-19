"""Safe data extraction from validated API responses.

Since API responses are validated at the boundary (response_validators.py),
this module provides convenient extraction helpers that assume validated data
while gracefully handling error responses.
"""

import logging
from typing import Any, Dict


logger = logging.getLogger(__name__)


def extract_field(data: Dict[str, Any], field_name: str, default: Any = None) -> Any:
    """Extract field from data dict with safe error handling.

    If data has _error, returns default. Otherwise accesses field directly.
    Use this instead of data.get(field_name, default) to make intent clear:
    - If response has error, field access returns default
    - If response is validated, field is guaranteed to exist (no fallback chain needed)
    """
    if not isinstance(data, dict):
        return default

    if data.get("_error"):
        return default

    return data.get(field_name, default)


def extract_items_list(data: Dict[str, Any]) -> list:
    """Extract items array from paginated API response.

    Handles: {items: [...]}, {_error: "..."}, or non-dict responses.
    Returns empty list if items missing or on error.
    """
    if not isinstance(data, dict):
        return []

    if data.get("_error"):
        return []

    items = data.get("items")
    return items if isinstance(items, list) else []


def extract_data_or_empty(data: Any, default_type: type = dict) -> Any:
    """Extract data or return empty default if error/missing.

    Args:
        data: Data to extract (could be dict, list, or None)
        default_type: Type to return on error (dict, list, etc.)

    Returns:
        data if valid and no error, otherwise empty instance of default_type
    """
    if isinstance(data, dict) and data.get("_error"):
        if default_type is list:
            return []
        return {}

    if isinstance(data, default_type):
        return data

    if default_type is dict:
        return {}
    elif default_type is list:
        return []

    return default_type()


# Extraction patterns for common dashboard endpoints
class DashboardDataExtractor:
    """Convenience class for extracting validated dashboard data."""

    def __init__(self, aggregated_data: Dict[str, Any]):
        """Initialize with aggregated API response data."""
        self.data = aggregated_data

    def run(self) -> Dict[str, Any]:
        """Extract run state (circuit breaker, orchestrator state)."""
        return extract_data_or_empty(self.data.get("run"), dict)

    def config(self) -> Dict[str, Any]:
        """Extract configuration."""
        return extract_data_or_empty(self.data.get("cfg"), dict)

    def market(self) -> Dict[str, Any]:
        """Extract market data."""
        return extract_data_or_empty(self.data.get("mkt"), dict)

    def portfolio(self) -> Dict[str, Any]:
        """Extract portfolio (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("port"), dict)

    def performance(self) -> Dict[str, Any]:
        """Extract performance metrics (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("perf"), dict)

    def positions(self) -> Dict[str, Any]:
        """Extract positions (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("pos"), dict)

    def signals(self) -> Dict[str, Any]:
        """Extract active signals (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("sig"), dict)

    def health(self) -> Dict[str, Any]:
        """Extract health/readiness status."""
        return extract_data_or_empty(self.data.get("health"), dict)

    def circuit_breaker(self) -> Dict[str, Any]:
        """Extract circuit breaker state."""
        return extract_data_or_empty(self.data.get("cb"), dict)

    def trades(self) -> Dict[str, Any]:
        """Extract recent trades."""
        return extract_data_or_empty(self.data.get("trades"), dict)

    def activity(self) -> Dict[str, Any]:
        """Extract activity log."""
        return extract_data_or_empty(self.data.get("activity"), dict)

    def exposure(self) -> Dict[str, Any]:
        """Extract exposure factors."""
        return extract_data_or_empty(self.data.get("exp_factors"), dict)

    def economic(self) -> Dict[str, Any]:
        """Extract economic indicators."""
        return extract_data_or_empty(self.data.get("eco"), dict)

    def notifications(self) -> list:
        """Extract notifications."""
        notifs = self.data.get("notifs")
        return notifs if isinstance(notifs, list) else []

    def risk(self) -> Dict[str, Any]:
        """Extract risk metrics."""
        return extract_data_or_empty(self.data.get("risk"), dict)

    def perf_analytics(self) -> Dict[str, Any]:
        """Extract performance analytics (rolling metrics)."""
        return extract_data_or_empty(self.data.get("perf_anl"), dict)
