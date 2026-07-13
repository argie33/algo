#!/usr/bin/env python3
"""Dashboard response handler for error detection and HTTP status mapping.

Detects error dicts from dashboard fetchers and maps to appropriate HTTP status codes:
- 503: Critical fetcher(s) failed → data unavailable
- 206: Partial content → only optional fetchers failed
- 200: All data available or acceptable level of errors

This implements fail-fast principle: critical data failures must surface via HTTP status,
not be hidden in response body as "_error" fields.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Critical fetchers whose errors should cause 503 response
# These are fetchers required for core dashboard functionality
CRITICAL_FETCHERS = {
    "run",  # Last algo run status
    "cfg",  # Algo configuration
    "mkt",  # Market data
    "port",  # Portfolio data
    "perf",  # Performance data
    "pos",  # Positions
    "trades",  # Recent trades
    "sig",  # Signals
    "health",  # Health check
    "cb",  # Circuit breaker status
}


class DashboardResponse:
    """Wraps dashboard fetcher results with error detection and HTTP status mapping.

    Detects error dicts returned by fetchers ({"_error": message}) and determines
    appropriate HTTP status code to return to caller.

    Error dicts are returned by fetchers when:
    - API call fails (api_data_layer.py line 277, 305, 308)
    - Validation fails (FetcherValidator.build_error_response)
    - Timeout occurs (fetchers.py line 277)
    - Exception raised (fetchers.py line 305)

    Without this wrapper, HTTP 200 is returned even when critical data is unavailable,
    violating the fail-fast principle. This wrapper detects those error dicts and
    maps them to proper HTTP status codes.
    """

    def __init__(self, fetcher_results: dict[str, Any]) -> None:
        """Initialize response wrapper.

        Args:
            fetcher_results: Dict of fetcher names to results (data or {"_error": msg})
        """
        self.results = fetcher_results
        self.critical_errors = self._find_critical_errors()
        self.optional_errors = self._find_optional_errors()

    def _find_critical_errors(self) -> dict[str, str]:
        """Find errors in critical fetchers.

        Returns:
            Dict mapping critical fetcher names to error messages
        """
        errors: dict[str, str] = {}
        for fetcher_name, result in self.results.items():
            if fetcher_name in CRITICAL_FETCHERS:
                if isinstance(result, dict) and "_error" in result:
                    error_msg = result.get("_error")
                    if not error_msg:
                        error_msg = "Unknown error (no details available)"
                    errors[fetcher_name] = str(error_msg)
        return errors

    def _find_optional_errors(self) -> dict[str, str]:
        """Find errors in optional fetchers.

        Returns:
            Dict mapping optional fetcher names to error messages
        """
        errors: dict[str, str] = {}
        for fetcher_name, result in self.results.items():
            if fetcher_name not in CRITICAL_FETCHERS:
                if isinstance(result, dict) and "_error" in result:
                    error_msg = result.get("_error")
                    if not error_msg:
                        error_msg = "Unknown error (no details available)"
                    errors[fetcher_name] = str(error_msg)
        return errors

    def has_critical_errors(self) -> bool:
        return len(self.critical_errors) > 0

    def has_errors(self) -> bool:
        return self.has_critical_errors() or len(self.optional_errors) > 0

    def get_http_status_code(self) -> int:
        """Determine HTTP status code based on error severity.

        Implements fail-fast principle: critical data unavailability must result
        in error HTTP status, not HTTP 200 with hidden error markers.

        Returns:
            503: Service Unavailable - critical fetcher(s) failed
            206: Partial Content - only optional fetchers failed
            200: OK - no errors or acceptable level
        """
        if self.has_critical_errors():
            return 503  # Service Unavailable
        if self.optional_errors:
            return 206  # Partial Content
        return 200  # OK

    def get_status_string(self) -> str:
        if self.has_critical_errors():
            return "degraded_critical"
        if self.optional_errors:
            return "degraded_partial"
        return "healthy"

    def to_response(self) -> dict[str, Any]:
        """Convert to response dict for HTTP response body.

        Returns dict with explicit error structure that callers can parse:
        {
            "status": "healthy|degraded_partial|degraded_critical",
            "errors": {
                "critical": {fetcher: message, ...},
                "optional": {fetcher: message, ...}
            },
            "data": {fetcher results}
        }

        Returns:
            Response dict ready for JSON serialization
        """
        return {
            "status": self.get_status_string(),
            "errors": {
                "critical": self.critical_errors,
                "optional": self.optional_errors,
            },
            "data": self.results,
        }
