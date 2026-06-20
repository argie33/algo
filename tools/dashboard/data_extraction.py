"""Safe data extraction from validated API responses.

Since API responses are validated at the boundary (response_validators.py),
this module provides convenient extraction helpers that assume validated data
while explicitly signaling errors.

Error responses containing _error field raise DataExtractionError, allowing
callers to distinguish between "no data" and "error fetching data".
"""

import logging
from typing import Any

from .error_boundary import has_error


logger = logging.getLogger(__name__)


class DataExtractionError(Exception):
    """Raised when API response contains an error."""


def extract_field(data: dict[str, Any], field_name: str, default: Any = None) -> Any:
    """Extract field from data dict, raising on error.

    Raises DataExtractionError if response contains _error field.
    Otherwise accesses field directly, returning default if missing.

    Use this instead of data.get(field_name, default) to make intent clear:
    - If response has error, raises DataExtractionError (caller can show error UI)
    - If response is validated, field access returns value or default
    """
    if not isinstance(data, dict):
        return default

    if has_error(data):
        raise DataExtractionError(f"Error in response: {data.get('_error')}")

    return data.get(field_name, default)


def extract_items_list(data: dict[str, Any]) -> list:
    """Extract items array from paginated API response.

    Raises DataExtractionError if response contains _error field.
    Returns empty list only if items key is missing (but no error).

    Args:
        data: Response dict containing "items" array

    Returns:
        List of items, or empty list if items key missing/not a list
    """
    if not isinstance(data, dict):
        return []

    if has_error(data):
        raise DataExtractionError(f"Error in response: {data.get('_error')}")

    items = data.get("items")
    return items if isinstance(items, list) else []


def extract_data_or_empty(data: Any, default_type: type = dict) -> Any:
    """Extract data or return empty default if missing, raise on error.

    Raises DataExtractionError if data is a dict with _error field.
    Returns empty instance of default_type if data is missing/None/wrong type.

    Args:
        data: Data to extract (could be dict, list, or None)
        default_type: Type to return if missing (dict, list, etc.)

    Returns:
        data if valid type (and no error), else empty instance of default_type

    Raises:
        DataExtractionError: If data is dict with _error field
    """
    if has_error(data):
        raise DataExtractionError(f"Error in response: {data.get('_error')}")

    if isinstance(data, default_type):
        return data

    if default_type is dict:
        return {}
    elif default_type is list:
        return []

    return default_type()


# Extraction patterns for common dashboard endpoints
class DashboardDataExtractor:
    """Convenience class for extracting validated dashboard data.

    Methods raise DataExtractionError if any API call in the aggregated response
    returned an error. Callers should wrap method calls in try/except to distinguish
    between "error fetching data" (exception) vs. "no data available" (empty result).
    """

    def __init__(self, aggregated_data: dict[str, Any]):
        """Initialize with aggregated API response data."""
        self.data = aggregated_data

    def run(self) -> dict[str, Any]:
        """Extract run state (circuit breaker, orchestrator state)."""
        return extract_data_or_empty(self.data.get("run"), dict)

    def config(self) -> dict[str, Any]:
        """Extract configuration."""
        return extract_data_or_empty(self.data.get("cfg"), dict)

    def market(self) -> dict[str, Any]:
        """Extract market data."""
        return extract_data_or_empty(self.data.get("mkt"), dict)

    def portfolio(self) -> dict[str, Any]:
        """Extract portfolio (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("port"), dict)

    def performance(self) -> dict[str, Any]:
        """Extract performance metrics (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("perf"), dict)

    def positions(self) -> dict[str, Any]:
        """Extract positions (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("pos"), dict)

    def signals(self) -> dict[str, Any]:
        """Extract active signals (validated at API boundary)."""
        return extract_data_or_empty(self.data.get("sig"), dict)

    def health(self) -> dict[str, Any]:
        """Extract health/readiness status."""
        return extract_data_or_empty(self.data.get("health"), dict)

    def circuit_breaker(self) -> dict[str, Any]:
        """Extract circuit breaker state."""
        return extract_data_or_empty(self.data.get("cb"), dict)

    def trades(self) -> dict[str, Any]:
        """Extract recent trades."""
        return extract_data_or_empty(self.data.get("trades"), dict)

    def activity(self) -> dict[str, Any]:
        """Extract activity log."""
        return extract_data_or_empty(self.data.get("activity"), dict)

    def exposure(self) -> dict[str, Any]:
        """Extract exposure factors."""
        return extract_data_or_empty(self.data.get("exp_factors"), dict)

    def economic(self) -> dict[str, Any]:
        """Extract economic indicators."""
        return extract_data_or_empty(self.data.get("eco"), dict)

    def notifications(self) -> list:
        """Extract notifications."""
        notifs = self.data.get("notifs")
        return notifs if isinstance(notifs, list) else []

    def risk(self) -> dict[str, Any]:
        """Extract risk metrics."""
        return extract_data_or_empty(self.data.get("risk"), dict)

    def perf_analytics(self) -> dict[str, Any]:
        """Extract performance analytics (rolling metrics)."""
        return extract_data_or_empty(self.data.get("perf_anl"), dict)
