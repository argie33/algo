"""Safe data extraction from validated API responses.

Since API responses are validated at the boundary (response_validators.py),
this module provides convenient extraction helpers that assume validated data
while explicitly signaling errors.

Error responses containing _error field raise DataExtractionError, allowing
callers to distinguish between "no data" and "error fetching data".
"""

import logging
from typing import Any, cast

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


def extract_items_list(data: dict[str, Any]) -> list[Any]:
    """Extract items array from paginated API response.

    Raises DataExtractionError if response contains _error field, or if data structure is invalid.
    Never silently returns empty list — failures must be explicit.

    Args:
        data: Response dict containing "items" array

    Returns:
        List of items (never empty as fallback)

    Raises:
        DataExtractionError: If data is not a dict, contains error, or items key missing/invalid
    """
    if not isinstance(data, dict):
        raise DataExtractionError(f"Expected dict but got {type(data).__name__}. Invalid response structure.")

    if has_error(data):
        raise DataExtractionError(f"Error in response: {data.get('_error')}")

    items = data.get("items")
    if items is None:
        raise DataExtractionError("Response missing required 'items' key")
    if not isinstance(items, list):
        raise DataExtractionError(f"Expected 'items' to be a list but got {type(items).__name__}")
    return items


def extract_data_or_empty(data: Any, default_type: type = dict, allow_empty: bool = False) -> Any:
    """Extract data or return empty default if missing, raise on error.

    Raises DataExtractionError if data is a dict with _error field, or if data
    is missing/None and allow_empty=False (fail-fast for critical finance data).

    Args:
        data: Data to extract (could be dict, list, or None)
        default_type: Type to return if missing (dict, list, etc.)
        allow_empty: If False (default), raise on missing data. If True, return empty.

    Returns:
        data if valid type (and no error), else empty instance of default_type (if allow_empty=True)

    Raises:
        DataExtractionError: If data is dict with _error field, or if data is missing and allow_empty=False
    """
    if has_error(data):
        raise DataExtractionError(f"Error in response: {data.get('_error')}")

    if isinstance(data, default_type):
        return data

    if not allow_empty and data is None:
        raise DataExtractionError("Required data is missing (None). Cannot proceed without this information.")

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
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("run"), dict))

    def config(self) -> dict[str, Any]:
        """Extract configuration."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("cfg"), dict))

    def market(self) -> dict[str, Any]:
        """Extract market data."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("mkt"), dict))

    def portfolio(self) -> dict[str, Any]:
        """Extract portfolio (critical financial data—fail if missing)."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("port"), dict, allow_empty=False))

    def performance(self) -> dict[str, Any]:
        """Extract performance metrics (critical financial data—fail if missing)."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("perf"), dict, allow_empty=False))

    def positions(self) -> dict[str, Any]:
        """Extract positions (critical financial data—fail if missing)."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("pos"), dict, allow_empty=False))

    def signals(self) -> dict[str, Any]:
        """Extract active signals (critical for trading—fail if missing)."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("sig"), dict, allow_empty=False))

    def health(self) -> dict[str, Any]:
        """Extract health/readiness status."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("health"), dict))

    def circuit_breaker(self) -> dict[str, Any]:
        """Extract circuit breaker state."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("cb"), dict))

    def trades(self) -> dict[str, Any]:
        """Extract recent trades."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("trades"), dict))

    def activity(self) -> dict[str, Any]:
        """Extract activity log."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("activity"), dict))

    def exposure(self) -> dict[str, Any]:
        """Extract exposure factors."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("exp_factors"), dict))

    def economic(self) -> dict[str, Any]:
        """Extract economic indicators."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("eco"), dict))

    def notifications(self) -> list[Any]:
        """Extract notifications."""
        notifs = self.data.get("notifs")
        return notifs if isinstance(notifs, list) else []

    def risk(self) -> dict[str, Any]:
        """Extract risk metrics."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("risk"), dict))

    def perf_analytics(self) -> dict[str, Any]:
        """Extract performance analytics (rolling metrics)."""
        return cast(dict[str, Any], extract_data_or_empty(self.data.get("perf_anl"), dict))
