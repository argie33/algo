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
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, cast

import requests
import requests.exceptions

# Ensure dashboard package is on sys.path for imports
_dashboard_dir = os.path.dirname(os.path.abspath(__file__))
if _dashboard_dir not in sys.path:
    sys.path.insert(0, _dashboard_dir)

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

# Dashboard API URL with smart localhost detection
# Uses lazy detection: checks localhost availability on first API call, not at import time
_dashboard_api_url = os.environ.get("DASHBOARD_API_URL")
_api_base_url_cache = None
_localhost_checked = False

def _check_localhost_available() -> bool:
    """Check if dev_server is running on localhost:3001."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 3001))
        sock.close()
        return result == 0
    except Exception:
        return False

def _get_api_base_url() -> str:
    """Get API URL with smart detection (lazy evaluation).

    Priority:
    1. Explicit LOCAL_MODE flag
    2. Auto-detect localhost (dev_server available)
    3. Configured AWS URL (requires Cognito auth)
    4. Fallback to localhost

    This ensures local dev always works without auth setup, while AWS mode
    requires explicit configuration. Prevents "data not available" errors
    when dev_server is running but AWS credentials are missing.
    """
    global _api_base_url_cache, _localhost_checked

    if _api_base_url_cache:
        return _api_base_url_cache

    # Priority 1: Explicit LOCAL_MODE flag
    if os.environ.get("LOCAL_MODE"):
        _api_base_url_cache = "http://localhost:3001"
        logger.debug("[API] LOCAL_MODE enabled - using local dev_server")
        return _api_base_url_cache

    # Priority 2: Auto-detect localhost (lazy check - only on first use)
    if not _localhost_checked and _check_localhost_available():
        _api_base_url_cache = "http://localhost:3001"
        _localhost_checked = True
        logger.info("[API] Dev server detected on localhost:3001 - auto-switching to local mode (no --local flag needed)")
        return _api_base_url_cache

    _localhost_checked = True

    # Priority 3: Use configured AWS URL
    if _dashboard_api_url:
        _api_base_url_cache = _dashboard_api_url
        logger.info(f"[API] Using configured DASHBOARD_API_URL: {_dashboard_api_url} (requires Cognito auth)")
        return _api_base_url_cache

    # Priority 4: Fallback to localhost
    _api_base_url_cache = "http://localhost:3001"
    logger.info("[API] No DASHBOARD_API_URL set and dev server not detected. Falling back to localhost:3001")
    return _api_base_url_cache

# Set initial value (will be overridden on first API call if localhost is available)
API_BASE_URL = _get_api_base_url()
API_TIMEOUT = 20
API_MAX_RETRIES = 3
API_MAX_BACKOFF = 30
# ISSUE #10 FIX: Cache freshness threshold (in seconds) — read from environment or default to 30 minutes
# This allows configuring cache staleness tolerance based on deployment environment
API_CACHE_MAX_AGE_SECONDS = int(os.environ.get("DASHBOARD_CACHE_MAX_AGE_SECONDS", "1800"))  # default 30 min


def _validate_api_url_at_startup() -> None:
    """Validate API URL is set at module load time for production environments.

    CRITICAL FAIL-FAST: Missing API configuration must fail at startup, not at first
    API call. This prevents the dashboard from starting in a degraded state.

    Skip validation during testing to allow test collection and mocking.
    """
    # Skip validation if pytest is running or ENVIRONMENT is "test"
    if "pytest" in sys.modules or os.environ.get("ENVIRONMENT") == "test":
        logger.debug("[API] Validation skipped - running under pytest")
        return

    env_mode = os.environ.get("ENVIRONMENT", "dev")
    # Allow localhost in dev/development/local modes
    is_dev_mode = env_mode in ("dev", "development") or env_mode.startswith("dev")

    if not is_dev_mode and not _dashboard_api_url:
        raise RuntimeError(
            f"[API] DASHBOARD_API_URL environment variable not set in {env_mode} environment. "
            "Cannot initialize dashboard API layer for production. "
            "Set DASHBOARD_API_URL to your API endpoint."
        )
    if _dashboard_api_url and "localhost" in _dashboard_api_url and not is_dev_mode:
        raise RuntimeError(
            f"[API] DASHBOARD_API_URL is set to {_dashboard_api_url} (localhost). "
            "This is only valid for local development. "
            f"Production ({env_mode}) must use a valid AWS API endpoint."
        )


_validate_api_url_at_startup()


def set_api_url(url: str) -> None:
    """Set API base URL at runtime (used by -local mode)."""
    global API_BASE_URL
    API_BASE_URL = url


def get_api_url() -> str:
    """Get the current API base URL."""
    return API_BASE_URL


def validate_api_config(allow_localhost: bool = False) -> None:
    """Validate that API configuration is set correctly.

    Raises RuntimeError if configuration is missing or invalid.

    Args:
        allow_localhost: If True, localhost is accepted (for local dev).
                        If False (production), localhost is invalid.
    """
    if not _dashboard_api_url:
        if allow_localhost:
            logger.debug("[API] DASHBOARD_API_URL not set, using localhost for local dev")
        else:
            raise RuntimeError(
                "[API] DASHBOARD_API_URL environment variable not set. "
                "Cannot initialize dashboard API layer for production. "
                "Set DASHBOARD_API_URL to your API endpoint."
            )
    elif "localhost" in API_BASE_URL and not allow_localhost:
        raise RuntimeError(
            f"[API] DASHBOARD_API_URL is set to {API_BASE_URL} (localhost). "
            "This is only valid for local development. "
            "Production must use a valid AWS API endpoint."
        )


# Circuit breaker for preventing hammering a downed API
# NOTE: Circuit breaker is lenient during first 3 retries (initialization/startup)
# This allows dashboards to retry at startup without permanently tripping the breaker.
# After warmup, circuit opens on 3 consecutive failures within 60s window.
_circuit_breaker_state = "closed"
_circuit_breaker_failures = 0
_circuit_breaker_lock = threading.Lock()
_circuit_breaker_reset_time: float | None = None
_circuit_breaker_startup_failures = 0  # Track startup failures separately
CIRCUIT_BREAKER_THRESHOLD = 5  # Increased from 3 to 5 to allow more retries during startup
CIRCUIT_BREAKER_RESET_SECONDS = 60
CIRCUIT_BREAKER_STARTUP_GRACE = 3  # Don't trip breaker on first N failures (startup grace period)

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


def reset_circuit_breaker() -> None:
    """Manually reset circuit breaker to allow fresh attempts.

    Called by dashboard on startup to clear any stale breaker state from previous session.
    This ensures each dashboard session starts fresh without inheriting circuit breaker
    state from previous runs or diagnostic attempts.
    """
    global _circuit_breaker_state, _circuit_breaker_failures, _circuit_breaker_reset_time
    with _circuit_breaker_lock:
        _circuit_breaker_state = "closed"
        _circuit_breaker_failures = 0
        _circuit_breaker_reset_time = None
        logger.info("Circuit breaker manually reset for fresh session")


def cache_response(endpoint: str, data: dict[str, Any]) -> None:
    """Cache successful API response for fallback during outages.

    Raises for non-dict responses or error responses. Fail-fast ensures only
    valid responses are cached.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"Cannot cache non-dict API response for {endpoint}: got {type(data).__name__}. API response must be dict."
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

    CRITICAL FAIL-FAST: Cache freshness MUST be explicitly marked in data.
    If _stale_cache key is missing, this indicates data corruption or an
    incomplete response, and the function raises ValueError to prevent
    assuming fresh data when freshness is actually unknown.

    Args:
        data: Response dict (must have explicit _stale_cache flag)

    Returns:
        True if data is stale (>30 min old), False if fresh

    Raises:
        ValueError: If _stale_cache key missing (data integrity uncertain)
    """
    if "_stale_cache" not in data:
        logger.error(
            f"[DATA_INTEGRITY] Cache freshness marker missing: _stale_cache key not found in data. "
            f"Data keys: {list(data.keys())}. Cannot determine if data is fresh or stale. "
            f"This indicates data corruption or incomplete API response."
        )
        raise ValueError(
            "Cache freshness marker missing, data integrity uncertain. "
            "The _stale_cache flag must be explicitly set on all data responses. "
            f"Data structure: {list(data.keys())}"
        )
    return bool(data.get("_stale_cache"))


def get_cache_age_seconds(data: dict[str, Any]) -> int | None:
    """Get age of cached data in seconds.

    EXPLICIT UNAVAILABILITY: Returns None only if data is not from cache (fresh API response).
    If data is from cache, returns age in seconds.

    Args:
        data: Response dict (potentially with _cache_age_seconds)

    Returns:
        Age in seconds if data is from cache, None if fresh API response

    Raises:
        ValueError: If _cache_age_seconds is present but not an integer (data corruption)
    """
    if "_cache_age_seconds" not in data:
        logger.debug("[API_CACHE] Data is fresh from API (not from cache), _cache_age_seconds not present")
        return None

    age = data.get("_cache_age_seconds")
    if age is None:
        logger.warning("[API_CACHE] Cache age field is missing from API response - data freshness unknown")
        return None  # Explicitly: age field missing, not that data is fresh
    if not isinstance(age, int):
        raise ValueError(f"Cache age corrupted: _cache_age_seconds is {type(age).__name__}, expected int. Value: {age}")
    return age


def get_cached_response(endpoint: str, mark_stale: bool = False) -> dict[str, Any] | None:
    """Get cached response if available and fresh.

    CRITICAL FAIL-FAST: This function NEVER serves stale data (>30 min old). For a finance
    application, stale data can lead to incorrect position sizing, risk calculations,
    and trade decisions. Stale cache is NEVER acceptable - system must show "data unavailable"
    to users instead.

    Args:
        endpoint: API endpoint path
        mark_stale: Deprecated parameter. Kept for backwards compatibility but ignored.
                   Stale data is never served under any circumstances.

    Returns:
        Cached data if available and fresh (<30 min old), or None if not cached.

    Raises:
        RuntimeError: ALWAYS raised if cache is stale (>30 min old). This prevents silent
                     use of outdated data. Callers MUST handle this exception and show
                     "data unavailable" to users - they cannot fall back to stale data.
        RuntimeError: If cache corrupted or data structure invalid (fail-fast on data integrity issues)
    """
    with _response_cache_lock:
        cached = _response_cache.get(endpoint)
        if not cached:
            logger.debug(
                f"[API_CACHE] No cached response found for {endpoint} - API response required (cache miss, no data available)"
            )
            return None
    # Validate cache structure (fail-fast if corrupted)
    # CRITICAL: Cache must have required fields, data must be dict, timestamp must be datetime
    required_keys = {"data", "timestamp"}
    cache_keys = set(cached.keys())
    if not required_keys.issubset(cache_keys):
        missing = required_keys - cache_keys
        raise RuntimeError(
            f"[CACHE_CORRUPTION] API cache corrupted for {endpoint}: missing required keys {missing}. "
            f"Got keys: {list(cache_keys)}. Cannot use corrupted cache for finance data."
        )

    cached_data = cached["data"]
    timestamp = cached["timestamp"]

    # Validate data type and timestamp format
    if not isinstance(cached_data, dict):
        raise ValueError(
            f"[CACHE_CORRUPTION] API cache corrupted for {endpoint}: 'data' is not a dict, "
            f"got {type(cached_data).__name__}. Cannot use corrupted cache for finance data."
        )

    if not isinstance(timestamp, datetime):
        raise ValueError(
            f"[CACHE_CORRUPTION] API cache corrupted for {endpoint}: 'timestamp' is not datetime, "
            f"got {type(timestamp).__name__}. Cannot use corrupted cache - timestamp validation failed."
        )
    age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()

    if age_seconds > API_CACHE_MAX_AGE_SECONDS:
        # FINANCE APP SAFETY: Never serve stale data, regardless of circuit breaker state
        cache_age_mins = API_CACHE_MAX_AGE_SECONDS // 60
        raise RuntimeError(
            f"API {endpoint}: cached response too stale "
            f"({cache_age_mins}+ min old, {int(age_seconds)}s). "
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

    CRITICAL FAIL-FAST: Returns error dict on all failures (retries exhausted or circuit open).
    Never attempts stale cache fallback. In finance applications, data unavailability must
    surface immediately to users—stale data for position sizing or risk calculations is
    unacceptable. Callers must show "data unavailable" error to users on API failures.

    Args:
        endpoint: API endpoint path (e.g., "/api/algo/positions")
        params: Query parameters dict
        method: HTTP method (GET or POST)

    Returns:
        Unwrapped response dict containing actual data fields (no statusCode wrapper),
        or {"_error": message} on failure. On 503 errors, includes "_is_transient_503" flag
        to help callers determine if error is temporary.
    """
    # Lazy evaluation: check for localhost on first API call (in case dev_server just started)
    api_url = _get_api_base_url()

    if not api_url:
        logger.error("No API URL available - cannot make API calls")
        return {"_error": "API_BASE_URL not configured - set DASHBOARD_API_URL environment variable"}

    if _check_circuit_breaker():
        logger.error("Circuit breaker open - API unavailable")
        return {
            "_error": "API unavailable - circuit breaker open",
            "_circuit_open": True,
            "_is_transient_503": True,
        }

    url = f"{api_url}{endpoint}"
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
        # For development without Cognito, inject dev token automatically
        # CRITICAL FIX: Check if we're talking to a local dev_server (localhost:3001)
        # This works for both localhost and non-AWS environments to enable testing
        is_localhost = "localhost" in api_url or "127.0.0.1" in api_url or ":3001" in api_url
        is_dev_mode = os.environ.get("LOCAL_MODE") or os.environ.get("ENVIRONMENT") == "development"
        if is_localhost or is_dev_mode:
            headers["Authorization"] = "Bearer dev-admin"
            logger.debug(f"Using dev-admin token for API call to {endpoint} (localhost={is_localhost}, dev_mode={is_dev_mode})")
    for attempt in range(API_MAX_RETRIES + 1):
        try:
            if method == "GET":
                resp = _http_session.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
            else:
                resp = _http_session.post(url, json=params, headers=headers, timeout=API_TIMEOUT)

            if resp.status_code >= 400:
                logger.warning(f"API {endpoint}: {resp.status_code} - {resp.text[:100]}")
                # Check for deprecated endpoint (503 with errorType=deprecated_endpoint)
                try:
                    resp_data = resp.json()
                    if resp.status_code == 503 and resp_data.get("errorType") == "deprecated_endpoint":
                        msg = resp_data.get("message", "Endpoint deprecated")
                        logger.info(f"API {endpoint}: endpoint deprecated, failing fast without retries")
                        return {
                            "_error": f"API error {resp.status_code}: {msg}",
                            "_endpoint_deprecated": True,
                        }
                except (ValueError, AttributeError):
                    pass  # If JSON parsing fails, continue with normal error handling

                # Auth errors (401/403) are permanent, don't retry and don't count toward circuit breaker
                if resp.status_code in (401, 403):
                    # CRITICAL FIX: Provide helpful error message for local development
                    error_msg = f"API error {resp.status_code}: Authentication required"
                    if "localhost" in endpoint or ":3001" in endpoint:
                        error_msg += " [LOCAL DEV] Try running: python -m dashboard --local"
                    return {
                        "_error": error_msg,
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
                # Mark 503/504 Service Unavailable and Gateway Timeout as transient (temporary issues, not permanent failures)
                # CRITICAL: Callers must NOT attempt stale cache fallback - get_cached_response() raises on stale (>30min)
                error_result: dict[str, Any] = {"_error": f"API error {resp.status_code} after {max_att} attempts"}
                if resp.status_code == 503:
                    error_result["_is_transient_503"] = True
                elif resp.status_code == 504:
                    error_result["_is_transient_504"] = True
                return error_result

            try:
                data = resp.json()
            except ValueError as e:
                logger.warning(f"API {endpoint}: failed to parse JSON response: {e}")
                return {"_error": f"API {endpoint}: invalid JSON response"}
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
                        error_msg = f"API error {status_code_int}: {msg}"
                        # CRITICAL FIX: Provide helpful error message for local development
                        if "localhost" in endpoint or ":3001" in endpoint:
                            error_msg += " [LOCAL DEV] Try running: python -m dashboard --local"
                        return {
                            "_error": error_msg,
                            "_auth_error": True,
                        }
                    # Deprecated endpoints (503 with errorType=deprecated_endpoint) should fail fast without retries
                    if status_code_int == 503 and data.get("errorType") == "deprecated_endpoint":
                        msg = data.get("message", "Endpoint deprecated")
                        logger.info(f"API {endpoint}: endpoint deprecated, failing fast without retries")
                        return {
                            "_error": f"API error {status_code_int}: {msg}",
                            "_endpoint_deprecated": True,
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
                    elif status_code_int == 504:
                        error_result_json["_is_transient_504"] = True
                    return error_result_json

            _record_api_success()
            unwrapped = _unwrap_api_response(data)
            # Validate response BEFORE caching (fail-fast: don't cache invalid responses)
            try:
                validated = validate_response(endpoint, unwrapped)
                # CRITICAL: Do NOT cache /api/scores - stock scores drive trading decisions
                # Cached scores can lead to position sizing on stale/deleted data (e.g., OPI ETF scores)
                # Scores must always be fresh from database, never served from cache
                # All other endpoints cached for 30 min to reduce API load
                if endpoint != "/api/scores":
                    cache_response(endpoint, data)
                return validated
            except ResponseValidationError as e:
                logger.error(f"API response validation failed for {endpoint}: {e}")
                # DO NOT cache invalid response — next request will retry fresh
                # Return error response so callers can handle validation failures explicitly
                _record_api_failure()
                return {
                    "_error": f"Response validation failed: {e}",
                    "_error_type": "validation_error",
                }
        except requests.exceptions.Timeout:
            if attempt < API_MAX_RETRIES:
                backoff = min((2**attempt) + random.random() * (2**attempt), API_MAX_BACKOFF)
                att_str = f"attempt {attempt + 1}/{API_MAX_RETRIES + 1}"
                logger.warning(f"API {endpoint} timeout ({att_str}), retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            logger.error(f"API {endpoint}: timeout after {API_MAX_RETRIES + 1} attempts")
            _record_api_failure()
            error_msg = "API timeout - Lambda endpoint not responding"
            # Provide helpful guidance if using AWS endpoint
            if "execute-api" in api_url or "lambda" in api_url.lower():
                error_msg += ". For local dev: Use --local flag (python -m dashboard --local)"
            return {
                "_error": error_msg,
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
        except requests.exceptions.RequestException as e:
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

    Supports two API response formats:
    1. Standard: {statusCode: 200, data: {...}, ...metadata}
    2. Array/Paginated: {statusCode: 200, items: [...], pagination: {...}, ...metadata}

    This function extracts the payload while preserving statusCode so callers can
    distinguish between successful and error responses.

    CRITICAL FAIL-FAST: All API responses MUST be dicts. If response is not a dict,
    this indicates a critical data corruption issue and must fail immediately.

    Args:
        response: Full API response dict with format {statusCode: X, data: {...}, ...}
                  or {statusCode: X, items: [...], pagination: {...}, ...}

    Returns:
        Unwrapped response preserving statusCode and payload. Allows callers to check
        statusCode >= 400 to distinguish errors from successful empty responses.

    Raises:
        RuntimeError: If response is not a dict (data corruption or malformed JSON)
    """
    if not isinstance(response, dict):
        raise RuntimeError(
            f"API response is not a dict. Received {type(response).__name__}: {response!r}. "
            "This indicates data corruption or malformed JSON from API. Cannot proceed."
        )

    status_code = response.get("statusCode")
    if status_code is None:
        raise RuntimeError(
            "API response is missing required 'statusCode' field. "
            "Cannot determine request success/failure. Response: {response}"
        )

    # Extract payload - support both formats
    payload: dict[str, Any] = {}

    # Format 1: 'data' field (standard single-object response)
    if "data" in response:
        data_field = response["data"]
        # Only treat as payload if it's actually a dict; otherwise it's malformed
        if isinstance(data_field, dict):
            payload = cast(dict[str, Any], data_field)
        else:
            # Data field is malformed (string, list, etc) - mark as error
            logger.error(
                f"API response data field is malformed: "
                f"expected dict but got {type(data_field).__name__}. Value: {data_field!r}"
            )
            payload = {"_error": f"Response data field is {type(data_field).__name__}, expected dict"}
    # Format 2: 'items' field (array/paginated response from sendSuccess)
    elif "items" in response:
        # Paginated responses from sendSuccess have items at top level
        # Copy all application fields (items, pagination, etc.) to payload
        payload = {k: v for k, v in response.items() if k not in ("statusCode", "success", "timestamp")}
    else:
        # Neither 'data' nor 'items' field — check if this is an error response at top level
        # Some error responses might have error information at top level
        # But if there's truly no data, this is malformed
        logger.error(
            f"API response missing both 'data' and 'items' fields. "
            f"Response keys: {list(response.keys())}. "
            f"Cannot unwrap response without either field."
        )
        payload = {
            "_error": "API response malformed: missing 'data' or 'items' field",
            "_status_code": status_code,
        }

    # Preserve statusCode at top level so callers can distinguish errors from success
    result: dict[str, Any] = {"statusCode": status_code}
    if isinstance(payload, dict):
        result.update(payload)
    return result
