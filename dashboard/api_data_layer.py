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
    from .response_validators import ResponseValidationError, validate_response
except ImportError:
    try:
        from response_validators import (  # type: ignore
            ResponseValidationError,
            validate_response,
        )
    except ImportError as e:
        raise ImportError(
            "Cannot import response_validators module. "
            "API response validation is critical for data integrity. "
            "This indicates a deployment/installation issue."
        ) from e


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
        total=0,
        backoff_factor=0,  # Retries handled by api_call() instead
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
    with _circuit_breaker_lock:
        if _circuit_breaker_state != "open":
            return False
        if _circuit_breaker_reset_time and time.time() - _circuit_breaker_reset_time > CIRCUIT_BREAKER_RESET_SECONDS:
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
                logger.error(f"Circuit breaker OPEN after {_circuit_breaker_failures} failures")
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


def get_cached_response(endpoint: str, mark_stale: bool = False) -> dict | None:
    """Get cached response if available.

    Args:
        endpoint: API endpoint path
        mark_stale: If True, add _stale_cache flag when data is >30min old
                   instead of failing. Used during circuit breaker outages to
                   serve stale data with warning flag.

    Returns:
        Cached data with optional _stale_cache flag, or None if not cached.

    Raises:
        RuntimeError: If cache > 30 min old and mark_stale=False
    """
    with _response_cache_lock:
        cached = _response_cache.get(endpoint)
        if not cached:
            return None
    # Validate cache structure (fail-fast if corrupted)
    if "data" not in cached:
        raise RuntimeError(f"API cache corrupted for {endpoint}: missing 'data' key. Got keys: {list(cached.keys())}")
    if "timestamp" not in cached:
        raise RuntimeError(
            f"API cache corrupted for {endpoint}: missing 'timestamp' key. Got keys: {list(cached.keys())}"
        )
    cached_data = cached["data"]
    timestamp = cached["timestamp"]
    if not isinstance(cached_data, dict):
        raise ValueError(f"API cache corrupted for {endpoint}: 'data' is not a dict, got {type(cached_data).__name__}")
    age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()

    if age_seconds > 1800:
        if not mark_stale:
            raise RuntimeError(
                f"API {endpoint}: cached response too stale "
                f"(30+ min old, {int(age_seconds)}s). "
                "API unavailable - cannot serve stale data."
            )
        cached_data = dict(cached_data)
        cached_data["_stale_cache"] = True
        cached_data["_cache_age_seconds"] = int(age_seconds)

    return cached_data


def api_call(endpoint: str, params: dict | None = None, method: str = "GET") -> dict:
    """Call API endpoint with exponential backoff retry logic and circuit breaker.

    Returns dict with 'data' key on success, '_error' on failure.
    Implements exponential backoff with maximum cap to prevent runaway delays.
    Circuit breaker pattern prevents hammering downed API.
    Supports Cognito auth.

    CRITICAL: Returns error dict on all failures (retries exhausted or circuit open).
    Never returns stale cached data—fails fast to surface unavailability to callers.
    Fetchers/consumers can optionally use get_cached_response() if they need stale data.

    Args:
        endpoint: API endpoint path (e.g., "/api/algo/positions")
        params: Query parameters dict
        method: HTTP method (GET or POST)

    Returns:
        Unwrapped response dict containing actual data fields (no statusCode wrapper),
        or {"_error": message} on failure
    """
    if not API_BASE_URL:
        logger.error("DASHBOARD_API_URL environment variable not set - cannot make API calls")
        return {"_error": ("API_BASE_URL not configured - set DASHBOARD_API_URL environment variable")}

    if _check_circuit_breaker():
        logger.error("Circuit breaker open - API unavailable")
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
                resp = _http_session.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
            else:
                resp = _http_session.post(url, json=params, headers=headers, timeout=API_TIMEOUT)

            if resp.status_code >= 400:
                logger.warning(f"API {endpoint}: {resp.status_code} - {resp.text[:100]}")
                if attempt < API_MAX_RETRIES:
                    backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                    att_str = f"attempt {attempt + 1}/{API_MAX_RETRIES + 1}"
                    logger.warning(f"API {endpoint} failed ({att_str}), retry in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                _record_api_failure()
                max_att = API_MAX_RETRIES + 1
                return {"_error": f"API error {resp.status_code} after {max_att} attempts"}

            data = resp.json()
            if isinstance(data, dict) and data.get("statusCode", 200) >= 400:
                logger.warning(f"API {endpoint}: error in JSON response")
                if attempt < API_MAX_RETRIES:
                    backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                    time.sleep(backoff)
                    continue
                _record_api_failure()
                status = data.get("statusCode", "unknown")
                msg = data.get("message", "Unknown API error")
                max_att = API_MAX_RETRIES + 1
                return {"_error": f"API error {status} after {max_att} attempts: {msg}"}

            cache_response(endpoint, data)
            _record_api_success()
            unwrapped = _unwrap_api_response(data)
            # Validate response at boundary (fail fast if critical fields missing)
            try:
                validated = validate_response(endpoint, unwrapped)
                return validated
            except ResponseValidationError as e:
                logger.error(f"API response validation failed for {endpoint}: {e}")
                return {"_error": str(e)}
        except requests.exceptions.Timeout:
            if attempt < API_MAX_RETRIES:
                backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                att_str = f"attempt {attempt + 1}/{API_MAX_RETRIES + 1}"
                logger.warning(f"API {endpoint} timeout ({att_str}), retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            logger.error(f"API {endpoint}: timeout after {API_MAX_RETRIES + 1} attempts")
            _record_api_failure()
            return {"_error": f"API timeout after {API_MAX_RETRIES + 1} attempts"}
        except requests.exceptions.ConnectionError:
            if attempt < API_MAX_RETRIES:
                backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                att_str = f"attempt {attempt + 1}/{API_MAX_RETRIES + 1}"
                logger.warning(f"API {endpoint} connection failed ({att_str}), retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            max_att = API_MAX_RETRIES + 1
            logger.error(f"API {endpoint}: connection unavailable after {max_att} attempts")
            _record_api_failure()
            return {"_error": f"API unavailable after {max_att} attempts"}
        except Exception as e:
            if attempt < API_MAX_RETRIES:
                backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                att_str = f"attempt {attempt + 1}/{API_MAX_RETRIES + 1}"
                e_name = type(e).__name__
                e_msg = str(e)[:100]
                logger.warning(f"API {endpoint} error ({att_str}): {e_name}: {e_msg}, retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            max_att = API_MAX_RETRIES + 1
            e_name = type(e).__name__
            e_msg = str(e)[:200]
            logger.error(
                f"API {endpoint}: {e_name} after {max_att} attempts\n  Last error: {e_msg}\n  Endpoint URL: {endpoint}"
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
        payload = {k: v for k, v in response.items() if k not in ("statusCode", "headers")}

    # Preserve statusCode at top level so callers can distinguish errors from success
    result = {"statusCode": status_code}
    result.update(payload)
    return result
