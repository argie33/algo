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


def set_api_url(url: str) -> None:
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
_cognito_auth: Any = None
_cognito_auth_lock = threading.Lock()


def set_cognito_auth(auth: Any) -> None:
    """Set the Cognito authentication instance for API calls."""
    global _cognito_auth
    with _cognito_auth_lock:
        _cognito_auth = auth


def get_cognito_auth() -> Any:
    """Get the current Cognito authentication instance."""
    with _cognito_auth_lock:
        return _cognito_auth


def _check_circuit_breaker() -> bool:
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


def _record_api_failure() -> None:
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


def _record_api_success() -> None:
    """Record API success, close circuit breaker if in half-open state."""
    global _circuit_breaker_state, _circuit_breaker_failures
    with _circuit_breaker_lock:
        if _circuit_breaker_state == "half-open":
            logger.info("Circuit breaker CLOSED - API recovered")
            _circuit_breaker_state = "closed"
            _circuit_breaker_failures = 0


def cache_response(endpoint: str, data: dict[str, Any]) -> None:
    """Cache successful API response for fallback during outages.

    Raises for non-dict responses or error responses. Fail-fast ensures only
    valid responses are cached.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"Cannot cache non-dict API response for {endpoint}: "
            f"got {type(data).__name__}. API response must be dict."
        )
    if "_error" in data:
        raise ValueError(f"Cannot cache error response for {endpoint}: {data.get('_error')}")
    with _response_cache_lock:
        _response_cache[endpoint] = {
            "data": data,
            "timestamp": datetime.now(timezone.utc),
        }


def is_stale_data(data: dict[str, Any]) -> bool:
    """Check if data is marked as stale cache.

    CRITICAL: Dashboard components must check this flag and alert users
    when displaying stale market data during API outages.

    Args:
        data: Response dict (potentially with _stale_cache flag)

    Returns:
        True if data is stale (>30 min old), False if fresh
    """
    return bool(data.get("_stale_cache", False))


def get_cache_age_seconds(data: dict[str, Any]) -> int | None:
    """Get age of cached data in seconds.

    Returns None if data is not from cache, or age in seconds if stale.
    """
    return data.get("_cache_age_seconds")


def get_cached_response(endpoint: str, mark_stale: bool = False) -> dict[str, Any] | None:
    """Get cached response if available and fresh.

    CRITICAL: This function NEVER serves stale data (>30 min old). For a finance
    application, stale data can lead to incorrect position sizing, risk calculations,
    and trade decisions.

    Args:
        endpoint: API endpoint path
        mark_stale: Deprecated parameter. Kept for backwards compatibility but ignored.
                   Stale data is never served under any circumstances.

    Returns:
        Cached data if available and fresh (<30 min old), or None if not cached.

    Raises:
        RuntimeError: If cache is stale (>30 min old), corrupted, or data structure invalid
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
        # FINANCE APP SAFETY: Never serve stale data, regardless of circuit breaker state
        raise RuntimeError(
            f"API {endpoint}: cached response too stale "
            f"(30+ min old, {int(age_seconds)}s). "
            "Cannot serve stale data in finance application — risk calculations would be invalid. "
            "API must be restored or dashboard must show data unavailable."
        )

    return cached_data


def api_call(endpoint: str, params: dict[str, Any] | None = None, method: str = "GET") -> dict[str, Any]:  # noqa: C901
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
        or {"_error": message} on failure. On 503 errors, includes "_is_transient_503" flag
        so callers can decide whether to use stale cache.
    """
    if not API_BASE_URL:
        logger.error("DASHBOARD_API_URL environment variable not set - cannot make API calls")
        return {"_error": ("API_BASE_URL not configured - set DASHBOARD_API_URL environment variable")}

    if _check_circuit_breaker():
        logger.error("Circuit breaker open - API unavailable")
        return {
            "_error": "API unavailable - circuit breaker open",
            "_circuit_open": True,
            "_is_transient_503": True,
        }

    url = f"{API_BASE_URL}{endpoint}"
    headers: dict[str, str] = {"Content-Type": "application/json"}

    # Add Cognito authorization if available
    with _cognito_auth_lock:
        cognito_auth = _cognito_auth
    if cognito_auth:
        try:
            auth_headers = cognito_auth.get_authorization_header()
            headers.update(auth_headers)
        except RuntimeError as auth_err:
            logger.error(f"Cognito authorization failed for {endpoint}: {auth_err}")
            # Do NOT call _record_api_failure() — auth errors are permanent config issues, not transient API failures.
            # They should not trigger circuit breaker accumulation.
            return {"_error": f"Authentication failed: {auth_err}", "_auth_error": True}
    else:
        # For local development without Cognito, inject dev token automatically
        # This allows local testing without needing to configure AWS credentials
        if "localhost" in API_BASE_URL or "127.0.0.1" in API_BASE_URL:
            headers["Authorization"] = "Bearer dev-admin"
            logger.debug(f"Using dev-admin token for local API call to {endpoint}")
    for attempt in range(API_MAX_RETRIES + 1):
        try:
            if method == "GET":
                resp = _http_session.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
            else:
                resp = _http_session.post(url, json=params, headers=headers, timeout=API_TIMEOUT)

            if resp.status_code >= 400:
                logger.warning(f"API {endpoint}: {resp.status_code} - {resp.text[:100]}")
                # Auth errors (401/403) are permanent, don't retry and don't count toward circuit breaker
                if resp.status_code in (401, 403):
                    return {
                        "_error": f"API error {resp.status_code}: Authentication required",
                        "_auth_error": True,
                    }
                # For other 4xx client errors, don't retry; fail immediately
                if resp.status_code < 500:
                    return {
                        "_error": f"API error {resp.status_code}",
                    }
                # For 5xx server errors, retry with backoff
                if attempt < API_MAX_RETRIES:
                    backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                    att_str = f"attempt {attempt + 1}/{API_MAX_RETRIES + 1}"
                    logger.warning(f"API {endpoint} failed ({att_str}), retry in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                _record_api_failure()
                max_att = API_MAX_RETRIES + 1
                # Mark 503 Service Unavailable as transient so callers can use stale cache
                error_result: dict[str, Any] = {"_error": f"API error {resp.status_code} after {max_att} attempts"}
                if resp.status_code == 503:
                    error_result["_is_transient_503"] = True
                return error_result

            data = resp.json()
            if isinstance(data, dict):
                status_code = data.get("statusCode")
                if status_code is None:
                    raise RuntimeError(
                        f"API {endpoint}: response JSON missing required 'statusCode' field. "
                        "Cannot determine request success/failure. Response: {data}"
                    )
                try:
                    status_code_int = int(status_code)
                except (ValueError, TypeError) as e:
                    raise RuntimeError(
                        f"API {endpoint}: statusCode field is not an integer: {status_code}. "
                        "Cannot parse response status. Response: {data}"
                    ) from e

                if status_code_int >= 400:
                    logger.warning(f"API {endpoint}: error in JSON response (status {status_code_int})")
                    # Auth errors (401/403) are permanent config issues, not transient API failures
                    if status_code_int in (401, 403):
                        msg = data.get("message", "Unknown API error")
                        return {
                            "_error": f"API error {status_code_int}: {msg}",
                            "_auth_error": True,
                        }
                    # For other 4xx errors (client errors), don't retry; fail immediately
                    if status_code_int < 500:
                        msg = data.get("message", "Unknown API error")
                        return {
                            "_error": f"API error {status_code_int}: {msg}",
                        }
                    # For 5xx errors (server errors), retry with backoff
                    if attempt < API_MAX_RETRIES:
                        backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                        time.sleep(backoff)
                        continue
                    _record_api_failure()
                    msg = data.get("message", "Unknown API error")
                    max_att = API_MAX_RETRIES + 1
                    error_msg = f"API error {status_code_int} after {max_att} attempts: {msg}"
                    error_result_json: dict[str, Any] = {"_error": error_msg}
                    if status_code_int == 503:
                        error_result_json["_is_transient_503"] = True
                    return error_result_json

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
            return {
                "_error": f"API timeout after {API_MAX_RETRIES + 1} attempts",
                "_is_transient_503": True,
            }
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
            return {
                "_error": f"API unavailable after {max_att} attempts",
                "_is_transient_503": True,
            }
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


def _unwrap_api_response(response: dict[str, Any]) -> dict[str, Any]:
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
        return cast(dict[str, Any], response)

    status_code = response.get("statusCode")
    if status_code is None:
        raise RuntimeError(
            "API response is missing required 'statusCode' field. "
            "Cannot determine request success/failure. Response: {response}"
        )

    # Extract the data field (endpoints wrap payloads in 'data' via _wrap_response)
    # This is the only field that contains actual application data
    if "data" in response:
        data_field = response["data"]
        # Only treat as payload if it's actually a dict; otherwise it's malformed
        if isinstance(data_field, dict):
            payload = cast(dict[str, Any], data_field)
        else:
            # Data field is malformed (string, list, etc) - mark as error
            payload = {"_error": f"Response data field is {type(data_field).__name__}, expected dict"}
    else:
        # Fallback for error responses that have no 'data' field
        # Keep statusCode but remove other metadata markers
        payload = {k: v for k, v in response.items() if k not in ("statusCode", "headers")}

    # Preserve statusCode at top level so callers can distinguish errors from success
    result: dict[str, Any] = {"statusCode": status_code}
    if isinstance(payload, dict):
        result.update(payload)
    return result
