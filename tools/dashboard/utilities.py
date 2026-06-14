"""Shared utilities, globals, and helper functions for dashboard modules."""

import hashlib
import json
import logging
import os
import random
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
import requests.exceptions

from data_validation import (
    safe_float, safe_int, safe_json_parse, safe_bool, safe_str,
    validate_required_fields, validate_field_types, log_data_issue
)

try:
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("pip install rich>=13.0.0")

# ── globals ───────────────────────────────────────────────────────────────────
ET      = ZoneInfo("America/New_York")
CONSOLE = Console(force_terminal=True, legacy_windows=False, highlight=False)

# Issue 2.2 FIX: Consolidate duplicate fetchers for /api/algo/data-status endpoint
_data_status_lock = threading.Lock()
_data_status_cache = {}

# Thread-safe cache for sector aggregation (Issue: Race condition during cache eviction)
_sector_cache_lock = threading.Lock()

G   = "bright_green"
R   = "bright_red"
Y   = "yellow"
CY  = "cyan"
DIM = "dim"
MG  = "magenta"
WH  = "white"

TIER_COLOR = {
    "confirmed_uptrend": "bright_green",
    "healthy_uptrend":   "green",
    "pressure":          "yellow",
    "caution":           "orange1",
    "correction":        "bright_red",
}

TIER_SHORT = {
    "confirmed_uptrend": "CONF UP",
    "healthy_uptrend":   "HLTH UP",
    "pressure":          "PRESSURE",
    "caution":           "CAUTION",
    "correction":        "CORRECT",
}

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"

PHASE_NAMES = {
    "phase_0":  "Pre-flight",
    "phase_1":  "Data",
    "phase_2":  "Circuits",
    "phase_3":  "Positions",
    "phase_3a": "Reconcile",
    "phase_3b": "Exposure",
    "phase_4":  "Exits",
    "phase_4b": "Pyramid",
    "phase_5":  "Signals",
    "phase_6":  "Entries",
    "phase_7":  "Wrap-up",
}

# ── mascot (dancing monkey) ──────────────────────────────────────────────────
MASCOT_W = 13  # 1 left border + 11 content + 1 right border

MASCOT_FRAMES = [
    ("  @(^_^)@  ", "  \\{~~~}/  ", "  |{~~~}|  ", "  _|   |_  "),  # 0  groove
    ("  @(^_^)@  ", "  |{~~~}/  ", "  |{~~~}|  ", "  _|   /   "),  # 1  lean R
    ("  @(^_^)@  ", "  \\{~~~}|  ", "  |{~~~}|  ", "   \\   |_  "),  # 2  lean L
    ("  @(^_^)@  ", "  \\{~~~}|  ", "  |{~~~}|  ", "  _\\   |_  "),  # 3  step L
    (" /@(^_^)@\\ ", "   {~~~}   ", "  /|   |\\  ", " /      \\  "),  # 4  star jump
    ("  @(-_-)@  ", "  \\{~~~}/  ", "  |{~~~}|  ", "  _|   |_  "),  # 5  chill
    ("  @(o_o)@  ", "  \\{~~~}/  ", "  |{~~~}|  ", "  _|   |_  "),  # 6  meh
    ("  @(O_O)!  ", "  !{~~~}!  ", "  |{~~~}|  ", "  _|   |_  "),  # 7  freeze (CB)
]
MASCOT_COLORS = [
    "bright_green", "green", "bright_cyan", "cyan",
    "bright_yellow", "white", "yellow", "bright_red",
]
LOAD_SEQ = [0, 1, 4, 3]  # groove → step R → JUMP → step L

# Configure logging for stability monitoring
_log_dir = os.path.expanduser("~/.algo/logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "dashboard.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(_log_file, encoding="utf-8")]
)
logger = logging.getLogger(__name__)

# API configuration
API_BASE_URL = os.environ.get("DASHBOARD_API_URL", "")
API_TIMEOUT = 20  # Increased from 10s to handle network latency + slow responses
API_MAX_RETRIES = 3
API_MAX_BACKOFF = 30  # Cap exponential backoff at 30 seconds

def set_api_url(url: str):
    """Set API base URL at runtime (used by -local mode)."""
    global API_BASE_URL
    API_BASE_URL = url

def get_api_url() -> str:
    """Get the current API base URL."""
    return API_BASE_URL

# HTTP session with connection pooling (reuse TCP connections across 25+ parallel fetchers)
_http_session = requests.Session()
_http_adapter = requests.adapters.HTTPAdapter(
    pool_connections=16,
    pool_maxsize=16,
    max_retries=requests.packages.urllib3.util.retry.Retry(
        total=0,  # Retries handled by api_call() instead
        backoff_factor=0
    )
)
_http_session.mount("http://", _http_adapter)
_http_session.mount("https://", _http_adapter)

# Sector aggregation cache (E5 optimization)
_sector_agg_cache = OrderedDict()
_sector_cache_maxsize = 100


# ── Helper functions ──────────────────────────────────────────────────────────

_cognito_auth = None

def set_cognito_auth(auth):
    """Set the Cognito authentication instance for API calls."""
    global _cognito_auth
    _cognito_auth = auth

def api_call(endpoint: str, params: Optional[Dict] = None, method: str = "GET") -> Dict:
    """Call API endpoint with exponential backoff retry logic (Issue 12 FIX).

    Returns dict with 'data' key on success, '_error' on failure.
    Implements exponential backoff with maximum cap to prevent runaway delays.
    E1 FIX: Removed silent fallback to cache; failures are now visible to detect API issues.
    Circuit breaker pattern prevents hammering downed API (Issue 16 FIX).
    """
    if not API_BASE_URL:
        logger.error("DASHBOARD_API_URL environment variable not set - cannot make API calls")
        return {"_error": "API_BASE_URL not configured - set DASHBOARD_API_URL environment variable"}

    if _check_circuit_breaker():
        return {"_error": "API unavailable - circuit breaker open", "_circuit_open": True}

    url = f"{API_BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    # Add Cognito authorization if available
    if _cognito_auth:
        auth_headers = _cognito_auth.get_authorization_header()
        headers.update(auth_headers)

    for attempt in range(API_MAX_RETRIES + 1):
        try:
            if method == "GET":
                resp = _http_session.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
            else:
                resp = _http_session.post(url, json=params, headers=headers, timeout=API_TIMEOUT)

            if resp.status_code >= 400:
                logger.warning(f"API {endpoint}: {resp.status_code} - {resp.text[:100]}")
                return {"_error": f"API error {resp.status_code}"}

            data = resp.json()
            if isinstance(data, dict) and data.get("statusCode", 200) >= 400:
                logger.warning(f"API {endpoint}: error in JSON response")
                return {"_error": data.get("message", "Unknown API error")}

            cache_response(endpoint, data)
            _record_api_success()
            return data
        except requests.exceptions.Timeout:
            if attempt < API_MAX_RETRIES:
                backoff = min((2 ** attempt) + random.random() * (2 ** attempt), API_MAX_BACKOFF)
                logger.warning(f"API {endpoint} timeout (attempt {attempt+1}/{API_MAX_RETRIES+1}), retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            logger.error(f"API {endpoint}: timeout after {API_MAX_RETRIES+1} attempts")
            _record_api_failure()
            return {"_error": "API timeout"}
        except requests.exceptions.ConnectionError:
            if attempt < API_MAX_RETRIES:
                backoff = min((2 ** attempt) + random.random() * (2 ** attempt), API_MAX_BACKOFF)
                logger.warning(f"API {endpoint} connection failed (attempt {attempt+1}/{API_MAX_RETRIES+1}), retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            logger.error(f"API {endpoint}: connection unavailable after {API_MAX_RETRIES+1} attempts")
            _record_api_failure()
            return {"_error": "API unavailable"}
        except Exception as e:
            if attempt < API_MAX_RETRIES:
                backoff = min((2 ** attempt) + random.random() * (2 ** attempt), API_MAX_BACKOFF)
                logger.warning(f"API {endpoint} error (attempt {attempt+1}/{API_MAX_RETRIES+1}): {type(e).__name__}: {str(e)[:100]}, retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            logger.error(f"API {endpoint}: {type(e).__name__} after {API_MAX_RETRIES+1} attempts\n  Last error: {str(e)[:200]}\n  Endpoint URL: {endpoint}")
            _record_api_failure()
            return {"_error": str(e)}


def normalize_positions_data(data):
    """Unified normalization of positions data structure.

    Returns:
        (positions_list, timestamp, has_error)
    """
    if isinstance(data, dict):
        if data.get("_error"):
            return [], None, True
        if "items" in data:
            return data.get("items", []), data.get("timestamp"), False
        return [], None, False
    elif isinstance(data, list):
        return data, None, False
    else:
        return [], None, False


def compute_sector_agg(pos, port):
    """
    Compute sector aggregation with caching to avoid recomputation on every 30-sec refresh.
    Only recomputes when positions data changes (via content hash, not object identity).

    E5 optimization: Sector aggregation from 100+ positions was O(n) × 2,880 times/day.
    Now computes only when positions change (typically 2-5 times/day).

    Thread-safe: Uses lock during cache reads/writes to prevent race conditions.
    """
    pos, _, has_error = normalize_positions_data(pos)
    if has_error:
        return None, None, 0

    if not pos:
        return None, None, 0

    pos_hash = hashlib.md5(json.dumps(pos, sort_keys=True, default=str).encode()).hexdigest()

    with _sector_cache_lock:
        if pos_hash in _sector_agg_cache:
            cached = _sector_agg_cache[pos_hash]
            return cached["sorted_secs"], cached["total_secs"], cached.get("pv")

    pv = safe_float(port.get("total_portfolio_value"), default=None)
    sd = {}
    invalid_count = 0
    for p in pos:
        if not isinstance(p, dict):
            invalid_count += 1
            logger.error(f"compute_sector_agg: invalid position (not a dict): {type(p).__name__}")
            continue
        sec = p.get("sector") or "Unknown"
        val = safe_float(p.get("position_value"), default=None)
        pnl = safe_float(p.get("unrealized_pnl_pct"), default=None)
        if sec not in sd:
            sd[sec] = {"val": 0.0, "n": 0, "pnls": []}
        if val is not None:
            sd[sec]["val"] += val
        sd[sec]["n"] += 1
        if pnl is not None:
            sd[sec]["pnls"].append(pnl)

    if invalid_count > 0:
        logger.error(f"compute_sector_agg: encountered {invalid_count} invalid position(s); sector totals may be incomplete")
        return None, None, 0

    sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])
    total_secs = len(sorted_secs)

    with _sector_cache_lock:
        if len(_sector_agg_cache) >= _sector_cache_maxsize:
            _sector_agg_cache.popitem(last=False)

        _sector_agg_cache[pos_hash] = {
            "sorted_secs": sorted_secs,
            "total_secs": total_secs,
            "pv": pv
        }

    return sorted_secs, total_secs, pv


def extract_items_and_error(data):
    """Extract items array and error message from data dict or list."""
    if isinstance(data, dict) and "items" in data:
        return data.get("items", []), data.get("_error")
    elif isinstance(data, list):
        return data, None
    else:
        return [], None


def validate_data_freshness(data: dict, max_age_hours: int = 24, field_name: str = "timestamp") -> bool:
    """Validate data freshness by checking timestamp field age.

    Returns True if data is fresh or timestamp unavailable, logs warning if stale.
    """
    if not isinstance(data, dict):
        return True
    if field_name not in data or data[field_name] is None:
        return True
    ts = data[field_name]
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except:
            logger.warning(f"Could not parse timestamp in {field_name}")
            return True
    if not isinstance(ts, datetime):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    if age_hours > max_age_hours:
        logger.warning(f"Data stale: {field_name} is {age_hours:.1f}h old (threshold: {max_age_hours}h)")
        return False
    return True


_response_cache = {}
_response_cache_lock = threading.Lock()

_circuit_breaker_state = "closed"
_circuit_breaker_failures = 0
_circuit_breaker_lock = threading.Lock()
_circuit_breaker_reset_time = None
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_RESET_SECONDS = 60

def _check_circuit_breaker():
    """Check if circuit breaker is open; attempt half-open state after reset time."""
    global _circuit_breaker_state, _circuit_breaker_failures, _circuit_breaker_reset_time
    if _circuit_breaker_state != "open":
        return False
    if _circuit_breaker_reset_time and time.time() - _circuit_breaker_reset_time > CIRCUIT_BREAKER_RESET_SECONDS:
        with _circuit_breaker_lock:
            _circuit_breaker_state = "half-open"
            _circuit_breaker_failures = 0
            logger.info("Circuit breaker attempting half-open state")
        return False
    return True

def _record_api_failure():
    """Record API failure, open circuit breaker if threshold exceeded."""
    global _circuit_breaker_state, _circuit_breaker_failures, _circuit_breaker_reset_time
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
            "timestamp": datetime.now(timezone.utc)
        }


def get_cached_response(endpoint: str) -> Optional[dict]:
    """Get cached response if available, mark as stale if > 30 minutes old."""
    with _response_cache_lock:
        cached = _response_cache.get(endpoint)
        if not cached:
            return None
    cached_data = cached.get("data", {})
    age_minutes = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds() / 60
    if age_minutes > 30:
        logger.warning(f"Using stale cached response for {endpoint} ({age_minutes:.0f}m old)")
        cached_data = {**cached_data, "_cached": True, "_stale": True}
    else:
        cached_data = {**cached_data, "_cached": True}
    return cached_data
