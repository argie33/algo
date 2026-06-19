"""API-based data layer for dashboard.

Issue 3 FIX: Dual data architecture consolidation.

This module consolidates all dashboard data fetching through a single API layer
instead of dual DB/API sources. It eliminates field name mismatches and ensures
consistent data freshness.

ISSUE 1.1 FIX: Consistent API Response Handling
================================================
All API responses follow a standardized format from the backend via _wrap_response():
- Format: {statusCode: 200, data: {...payload...}, ...metadata}
- Error format: {statusCode: 4xx, errorType: "...", message: "...", _error: "..."}

FIX IMPLEMENTATION:
1. api_call() invokes _unwrap_api_response() to extract just the payload
2. _unwrap_api_response() returns response["data"] directly
3. All data fetchers work with unwrapped payloads (no more nested data fields)

Result: Consistent response handling — all methods access fields at same nesting level.

Migration status:
- Positions, Trades, Performance, Signals: ✅ API-only + standardized
- Portfolio Status: ✅ API-only (via /api/algo/status)
- Health/Data Status: ✅ API-only (via /api/algo/data-status)
- Config: ✅ API-only (via /api/algo/config)
- Economic/Market data: Still DB-based (no dedicated API endpoints yet)
"""

import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, cast

import requests
import requests.exceptions


try:
    from urllib3.util.retry import Retry
except ImportError:
    from requests.packages.urllib3.util.retry import Retry  # type: ignore


logger = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("DASHBOARD_API_URL", "")
API_TIMEOUT = 20
API_MAX_RETRIES = 3
API_MAX_BACKOFF = 30


def set_api_url(url: str):
    """Set API base URL at runtime (used by -local mode)."""
    global API_BASE_URL
    API_BASE_URL = url


def get_api_url() -> str:
    """Get the current API base URL."""
    return API_BASE_URL

# Circuit breaker for preventing hammering a downed API
_circuit_breaker_state = "closed"
_circuit_breaker_failures = 0
_circuit_breaker_lock = threading.Lock()
_circuit_breaker_reset_time: float | None = None
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_RESET_SECONDS = 60

# Response caching for fallback during outages
_response_cache: dict[str, dict[str, Any]] = {}
_response_cache_lock = threading.Lock()

# HTTP session with connection pooling (reuse TCP connections across parallel fetchers)
_http_session = requests.Session()
_http_adapter = requests.adapters.HTTPAdapter(
    pool_connections=16,
    pool_maxsize=16,
    max_retries=Retry(
        total=0, backoff_factor=0  # Retries handled by api_call() instead
    ),
)
_http_session.mount("http://", _http_adapter)
_http_session.mount("https://", _http_adapter)

# Cognito auth support
_cognito_auth = None
_cognito_auth_lock = threading.Lock()


def set_cognito_auth(auth):
    """Set the Cognito authentication instance for API calls."""
    global _cognito_auth
    with _cognito_auth_lock:
        _cognito_auth = auth


def get_cognito_auth():
    """Get the current Cognito authentication instance."""
    with _cognito_auth_lock:
        return _cognito_auth


def _check_circuit_breaker():
    """Check if circuit breaker is open; attempt half-open state after reset time."""
    global _circuit_breaker_state
    global _circuit_breaker_failures
    global _circuit_breaker_reset_time
    with _circuit_breaker_lock:
        if _circuit_breaker_state != "open":
            return False
        if (
            _circuit_breaker_reset_time
            and time.time() - _circuit_breaker_reset_time
            > CIRCUIT_BREAKER_RESET_SECONDS
        ):
            _circuit_breaker_state = "half-open"
            _circuit_breaker_failures = 0
            logger.info("Circuit breaker attempting half-open state")
            return False
        return True


def _record_api_failure():
    """Record API failure, open circuit breaker if threshold exceeded."""
    global _circuit_breaker_state
    global _circuit_breaker_failures
    global _circuit_breaker_reset_time
    with _circuit_breaker_lock:
        _circuit_breaker_failures += 1
        if _circuit_breaker_failures >= CIRCUIT_BREAKER_THRESHOLD:
            if _circuit_breaker_state != "open":
                logger.error(
                    f"Circuit breaker OPEN after {_circuit_breaker_failures} failures"
                )
                _circuit_breaker_state = "open"
                _circuit_breaker_reset_time = time.time()


def _record_api_success():
    """Record API success, close circuit breaker if in half-open state."""
    global _circuit_breaker_state, _circuit_breaker_failures
    with _circuit_breaker_lock:
        if _circuit_breaker_state == "half-open":
            logger.info("Circuit breaker CLOSED - API recovered")
            _circuit_breaker_state = "closed"
            _circuit_breaker_failures = 0


def cache_response(endpoint: str, data: dict) -> None:
    """Cache successful API response for fallback during outages."""
    if not isinstance(data, dict) or data.get("_error"):
        return
    with _response_cache_lock:
        _response_cache[endpoint] = {
            "data": data,
            "timestamp": datetime.now(timezone.utc),
        }


def get_cached_response(endpoint: str) -> dict | None:
    """Get cached response if available, mark as stale if > 30 minutes old."""
    with _response_cache_lock:
        cached = _response_cache.get(endpoint)
        if not cached:
            return None
    cached_data = cached.get("data", {})
    timestamp = cached.get("timestamp")
    age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()
    if age_seconds > 1800:
        logger.warning(
            f"API {endpoint}: using cached response (30+ min old, API unavailable)"
        )
        return {**cached_data, "_cached": True, "_cache_age_seconds": int(age_seconds)}
    return cached_data


def api_call(endpoint: str, params: dict | None = None, method: str = "GET") -> dict:
    """Call API endpoint with exponential backoff retry logic and circuit breaker.

    Returns dict with 'data' key on success, '_error' on failure.
    Implements exponential backoff with maximum cap to prevent runaway delays.
    Circuit breaker pattern prevents hammering downed API.
    Supports Cognito auth and response caching.

    Args:
        endpoint: API endpoint path (e.g., "/api/algo/positions")
        params: Query parameters dict
        method: HTTP method (GET or POST)

    Returns:
        Unwrapped response dict containing actual data fields (no statusCode wrapper),
        or {"_error": message} on failure
    """
    if not API_BASE_URL:
        logger.error(
            "DASHBOARD_API_URL environment variable not set - cannot make API calls"
        )
        return {
            "_error": (
                "API_BASE_URL not configured - "
                "set DASHBOARD_API_URL environment variable"
            )
        }

    if _check_circuit_breaker():
        cached = get_cached_response(endpoint)
        if cached:
            return cached
        return {
            "_error": "API unavailable - circuit breaker open",
            "_circuit_open": True,
        }

    url = f"{API_BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    # Add Cognito authorization if available
    with _cognito_auth_lock:
        cognito_auth = _cognito_auth
    if cognito_auth:
        auth_headers = cognito_auth.get_authorization_header()
        headers.update(auth_headers)

    for attempt in range(API_MAX_RETRIES + 1):
        try:
            if method == "GET":
                resp = _http_session.get(
                    url, params=params, headers=headers, timeout=API_TIMEOUT
                )
            else:
                resp = _http_session.post(
                    url, json=params, headers=headers, timeout=API_TIMEOUT
                )

            if resp.status_code >= 400:
                logger.warning(
                    f"API {endpoint}: {resp.status_code} - {resp.text[:100]}"
                )
                if attempt < API_MAX_RETRIES:
                    backoff = min(
                        (2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF
                    )
                    att_str = f"attempt {attempt+1}/{API_MAX_RETRIES+1}"
                    logger.warning(
                        f"API {endpoint} failed ({att_str}), retry in {backoff:.1f}s"
                    )
                    time.sleep(backoff)
                    continue
                _record_api_failure()
                cached = get_cached_response(endpoint)
                if cached:
                    return cached
                return {"_error": f"API error {resp.status_code}"}

            data = resp.json()
            if isinstance(data, dict) and data.get("statusCode", 200) >= 400:
                logger.warning(f"API {endpoint}: error in JSON response")
                if attempt < API_MAX_RETRIES:
                    backoff = min(
                        (2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF
                    )
                    time.sleep(backoff)
                    continue
                _record_api_failure()
                cached = get_cached_response(endpoint)
                if cached:
                    return cached
                return {"_error": data.get("message", "Unknown API error")}

            cache_response(endpoint, data)
            _record_api_success()
            return _unwrap_api_response(data)
        except requests.exceptions.Timeout:
            if attempt < API_MAX_RETRIES:
                backoff = min(
                    (2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF
                )
                att_str = f"attempt {attempt+1}/{API_MAX_RETRIES+1}"
                logger.warning(
                    f"API {endpoint} timeout ({att_str}), retry in {backoff:.1f}s"
                )
                time.sleep(backoff)
                continue
            logger.error(f"API {endpoint}: timeout after {API_MAX_RETRIES+1} attempts")
            _record_api_failure()
            cached = get_cached_response(endpoint)
            if cached:
                return cached
            return {"_error": "API timeout"}
        except requests.exceptions.ConnectionError:
            if attempt < API_MAX_RETRIES:
                backoff = min(
                    (2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF
                )
                att_str = f"attempt {attempt+1}/{API_MAX_RETRIES+1}"
                logger.warning(
                    f"API {endpoint} connection failed ({att_str}), "
                    f"retry in {backoff:.1f}s"
                )
                time.sleep(backoff)
                continue
            max_att = API_MAX_RETRIES + 1
            logger.error(
                f"API {endpoint}: connection unavailable after {max_att} attempts"
            )
            _record_api_failure()
            cached = get_cached_response(endpoint)
            if cached:
                return cached
            return {"_error": "API unavailable"}
        except Exception as e:
            if attempt < API_MAX_RETRIES:
                backoff = min(
                    (2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF
                )
                att_str = f"attempt {attempt+1}/{API_MAX_RETRIES+1}"
                e_name = type(e).__name__
                e_msg = str(e)[:100]
                logger.warning(
                    f"API {endpoint} error ({att_str}): {e_name}: {e_msg}, "
                    f"retry in {backoff:.1f}s"
                )
                time.sleep(backoff)
                continue
            max_att = API_MAX_RETRIES + 1
            e_name = type(e).__name__
            e_msg = str(e)[:200]
            logger.error(
                f"API {endpoint}: {e_name} after {max_att} attempts\n"
                f"  Last error: {e_msg}\n"
                f"  Endpoint URL: {endpoint}"
            )
            _record_api_failure()
            return {"_error": str(e)}

    return {"_error": "API call failed"}


def _unwrap_api_response(response: dict) -> dict:
    """Unwrap standardized API response wrapper while preserving error status.

    All API responses follow the format: {statusCode: 200, data: {...}, ...metadata}
    This function extracts the payload while preserving statusCode so callers can
    distinguish between successful and error responses.

    Args:
        response: Full API response dict with format {statusCode: X, data: {...}, ...}

    Returns:
        Unwrapped response preserving statusCode and payload. Allows callers to check
        statusCode >= 400 to distinguish errors from successful empty responses.
    """
    if not isinstance(response, dict):
        return cast(dict, response)

    status_code = response.get("statusCode", 200)

    # Extract the data field (endpoints wrap payloads in 'data' via _wrap_response)
    # This is the only field that contains actual application data
    if "data" in response:
        payload = cast(dict, response["data"])
    else:
        # Fallback for error responses that have no 'data' field
        # Keep statusCode but remove other metadata markers
        payload = {
            k: v for k, v in response.items() if k not in ("statusCode", "headers")
        }

    # Preserve statusCode at top level so callers can distinguish errors from success
    result = {"statusCode": status_code}
    result.update(payload)
    return result


class DashboardDataAPI:
    """Consolidated API data layer for all dashboard fetchers."""

    @staticmethod
    def get_portfolio() -> dict[str, Any]:
        """Get portfolio snapshot via /api/algo/status."""
        resp = api_call("/api/algo/status")
        if "_error" in resp:
            return {"_error": resp["_error"]}

        # Response is already unwrapped (data field extracted), use directly
        portfolio = resp.get("portfolio", {})
        return {
            "total_portfolio_value": portfolio.get("total_value"),
            "total_cash": portfolio.get("total_cash"),
            "open_positions": portfolio.get("open_positions"),
            "daily_return_pct": portfolio.get("daily_return_pct"),
            "unrealized_pnl_pct": portfolio.get("unrealized_pnl_pct"),
            "last_run": resp.get("last_run"),
        }

    @staticmethod
    def get_positions() -> dict[str, Any]:
        """Get open positions via /api/algo/positions."""
        resp = api_call("/api/algo/positions")
        if "_error" in resp:
            logger.error(f"get_positions failed: {resp['_error']}")
            return resp
        items = resp.get("items", [])
        if not isinstance(items, list):
            error_msg = f"get_positions: expected list, got {type(items).__name__}"
            logger.error(error_msg)
            return {"_error": error_msg}
        valid_items = [item for item in items if isinstance(item, dict)]
        if len(valid_items) < len(items):
            invalid_count = len(items) - len(valid_items)
            logger.warning(
                f"get_positions: filtered {invalid_count} non-dict items"
            )
        return resp

    @staticmethod
    def get_performance() -> dict[str, Any]:
        """Get performance metrics via /api/algo/performance."""
        resp = api_call("/api/algo/performance")
        if "_error" in resp:
            logger.error(f"get_performance failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_trades(limit: int = 100) -> dict[str, Any]:
        """Get recent trades via /api/algo/trades."""
        resp = api_call("/api/algo/trades", params={"limit": limit})
        if "_error" in resp:
            logger.error(f"get_trades failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_signals() -> dict[str, Any]:
        """Get dashboard signals via /api/algo/dashboard-signals."""
        resp = api_call("/api/algo/dashboard-signals")
        if "_error" in resp:
            logger.error(f"get_signals failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_health() -> dict[str, Any]:
        """Get data health status via /api/algo/data-status."""
        resp = api_call("/api/algo/data-status")
        if "_error" in resp:
            logger.error(f"get_health failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_config() -> dict[str, Any]:
        """Get algo configuration via /api/algo/config."""
        resp = api_call("/api/algo/config")
        if "_error" in resp:
            logger.error(f"get_config failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_notifications(limit: int = 10) -> dict[str, Any]:
        """Get recent notifications via /api/algo/notifications."""
        resp = api_call("/api/algo/notifications", params={"limit": limit})
        if "_error" in resp:
            logger.error(f"get_notifications failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_last_run() -> dict[str, Any]:
        """Get last orchestrator run info via /api/algo/last-run."""
        resp = api_call("/api/algo/last-run")
        if "_error" in resp:
            logger.error(f"get_last_run failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_audit_log(limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Get audit log via /api/algo/audit-log."""
        resp = api_call(
            "/api/algo/audit-log", params={"limit": limit, "offset": offset}
        )
        if "_error" in resp:
            logger.error(f"get_audit_log failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_circuit_breakers() -> dict[str, Any]:
        """Get circuit breaker status via /api/algo/circuit-breakers."""
        resp = api_call("/api/algo/circuit-breakers")
        if "_error" in resp:
            logger.error(f"get_circuit_breakers failed: {resp['_error']}")
            return resp
        return resp

    @staticmethod
    def get_sector_breadth() -> dict[str, Any]:
        """Get sector breadth via /api/algo/sector-breadth."""
        resp = api_call("/api/algo/sector-breadth")
        if "_error" in resp:
            logger.error(f"get_sector_breadth failed: {resp['_error']}")
            return resp
        return resp
