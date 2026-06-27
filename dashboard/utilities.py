"""Shared utilities, globals, and helper functions for dashboard modules."""

import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from rich.console import Console

from utils.safe_data_conversion import safe_float

# ── globals ───────────────────────────────────────────────────────────────────
ET = ZoneInfo("America/New_York")
CONSOLE = Console(force_terminal=True, legacy_windows=False, highlight=False)

# Issue 2.2 FIX: Consolidate duplicate fetchers for /api/algo/data-status endpoint
_data_status_lock = threading.Lock()
_data_status_cache: dict[str, Any] = {}

# Thread-safe cache for sector aggregation (Issue: Race condition during cache eviction)
_sector_cache_lock = threading.Lock()
_sector_agg_cache: OrderedDict[str, Any] = OrderedDict()

G = "bright_green"
R = "bright_red"
Y = "yellow"
CY = "cyan"
DIM = "dim"
MG = "magenta"
WH = "white"

TIER_COLOR = {
    "confirmed_uptrend": "bright_green",
    "healthy_uptrend": "green",
    "pressure": "yellow",
    "caution": "orange1",
    "correction": "bright_red",
}

TIER_SHORT = {
    "confirmed_uptrend": "CONFIRMED UP",
    "healthy_uptrend": "HEALTHY UP",
    "pressure": "PRESSURE",
    "caution": "CAUTION",
    "correction": "CORRECTION",
}

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"

PHASE_NAMES = {
    "phase_0": "Pre-flight",
    "phase_1": "Data",
    "phase_2": "Circuits",
    "phase_3": "Positions",
    "phase_3a": "Reconcile",
    "phase_3b": "Exposure",
    "phase_4": "Exits",
    "phase_5": "Signals",
    "phase_6": "Entries",
    "phase_7": "Wrap-up",
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
    "bright_green",
    "green",
    "bright_cyan",
    "cyan",
    "bright_yellow",
    "white",
    "yellow",
    "bright_red",
]
LOAD_SEQ = [0, 1, 4, 3]  # groove → step R → JUMP → step L

# Configure logging for stability monitoring
_log_dir = os.path.expanduser("~/.algo/logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "dashboard.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(_log_file, encoding="utf-8")],
)
logger = logging.getLogger(__name__)


# Sector aggregation cache (E5 optimization)
_sector_agg_cache = OrderedDict()
_sector_cache_maxsize = 100

# ── Helper functions ──────────────────────────────────────────────────────────


def normalize_positions_data(data: Any) -> tuple[list[Any], Any, bool]:
    """Unified normalization of positions data structure.

    FAIL-CLOSED: Raises exception on unexpected data types instead of silently returning empty list.
    Data format issues must be visible to operators.

    Returns:
        (positions_list, timestamp, has_error) tuple
    """
    from .error_boundary import has_error as check_has_error

    if isinstance(data, dict):
        if check_has_error(data):
            return [], None, True
        if "items" not in data:
            # Dict without items or error — log and fail
            logger.error(
                f"[DATA_FORMAT] Positions dict malformed: missing 'items' and no '_error'. Keys: {list(data.keys())}"
            )
            raise ValueError(
                "Positions data is dict but missing 'items' array. "
                "Check API response schema — may indicate upstream data corruption."
            )
        items = data.get("items")
        if not isinstance(items, list):
            logger.error(f"[DATA_FORMAT] Positions 'items' field is not a list: {type(items).__name__}")
            raise ValueError(
                f"Positions 'items' must be list, got {type(items).__name__}. "
                "Check API response schema — may indicate upstream data corruption."
            )
        return items, data.get("timestamp"), False
    elif isinstance(data, list):
        return data, None, False
    else:
        logger.error(f"[DATA_FORMAT] Positions data has unexpected type: {type(data).__name__}")
        raise TypeError(
            f"Positions data must be dict or list, got {type(data).__name__}. "
            "Check API response schema — may indicate upstream data corruption."
        )


def compute_sector_agg(pos: Any, port: dict[str, Any]) -> tuple[list[tuple[str, dict[str, Any]]], int, float | None]:
    """
    Compute sector aggregation with caching to avoid recomputation on every 30-sec refresh.
    Only recomputes when positions data changes (via content hash, not object identity).

    E5 optimization: Sector aggregation from 100+ positions was O(n) x 2,880 times/day.
    Now computes only when positions change (typically 2-5 times/day).

    Thread-safe: Uses lock during cache reads/writes to prevent race conditions.
    """
    pos_items, pos_timestamp, has_error = normalize_positions_data(pos)
    if has_error:
        raise ValueError("Cannot compute sector aggregation: positions data contains error")

    if not pos_items:
        raise ValueError("Cannot compute sector aggregation: positions data is empty")

    pos_hash = hashlib.md5(json.dumps(pos_items, sort_keys=True, default=str).encode()).hexdigest()

    with _sector_cache_lock:
        if pos_hash in _sector_agg_cache:
            cached = _sector_agg_cache[pos_hash]
            return cached["sorted_secs"], cached["total_secs"], cached.get("pv")

    pv = safe_float(port.get("total_portfolio_value"), default=None)
    sd: dict[str, dict[str, Any]] = {}
    invalid_count = 0
    for p in pos_items:
        if not isinstance(p, dict):
            invalid_count += 1
            logger.error(f"compute_sector_agg: invalid position (not a dict): {type(p).__name__}")
            continue
        # Sector is critical for aggregation; fail if missing instead of silently using "Unknown"
        sec = p.get("sector")
        if not sec:
            invalid_count += 1
            logger.error(f"compute_sector_agg: position missing sector: {p.get('symbol', 'unknown')}")
            continue
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
        raise ValueError(f"Cannot compute sector aggregation: encountered {invalid_count} invalid position(s)")

    sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])
    total_secs = len(sorted_secs)

    with _sector_cache_lock:
        if len(_sector_agg_cache) >= _sector_cache_maxsize and pos_hash not in _sector_agg_cache:
            _sector_agg_cache.popitem(last=False)

        _sector_agg_cache[pos_hash] = {
            "sorted_secs": sorted_secs,
            "total_secs": total_secs,
            "pv": pv,
        }

    return sorted_secs, total_secs, pv


def extract_items_and_error(data: Any) -> tuple[list[Any], str | None]:
    """Extract items array and error message from data dict or list.

    FAIL-CLOSED: Raises exception on unexpected data types instead of silently returning empty list.
    Data format issues must be visible to operators.

    Returns:
        (items_list, error_msg) tuple
    """
    from .error_boundary import get_error_message, has_error

    if isinstance(data, dict):
        if has_error(data):
            return [], get_error_message(data)
        if "items" in data:
            items = data.get("items")
            if isinstance(items, list):
                return items, None
            logger.error(f"[DATA_FORMAT] 'items' field exists but is not a list: {type(items).__name__}. Data keys: {list(data.keys())}")
            raise TypeError(
                f"Data 'items' field must be a list, got {type(items).__name__}. "
                "This indicates API response corruption or schema mismatch."
            )
        # Dict without items or error — log and fail
        logger.error(f"[DATA_FORMAT] Data dict malformed: missing 'items' and no '_error'. Keys: {list(data.keys())}")
        raise ValueError(
            "Data is dict but missing 'items' array. Check API response schema — may indicate upstream data corruption."
        )
    elif isinstance(data, list):
        return data, None
    else:
        logger.error(f"[DATA_FORMAT] Data has unexpected type: {type(data).__name__}")
        raise TypeError(
            f"Data must be dict or list, got {type(data).__name__}. "
            "Check API response schema — may indicate upstream data corruption."
        )


def validate_data_freshness(data: dict[str, Any], max_age_hours: int = 24, field_name: str = "timestamp") -> bool:
    """Validate data freshness by checking timestamp field age.

    FAIL-FAST: Raises exception on unparseable or invalid timestamp (data corruption).
    Finance principle: Do not silently accept malformed data.

    Returns: True if data is fresh, False if stale
    Raises: ValueError if timestamp is malformed or missing (cannot validate freshness)
    """
    if not isinstance(data, dict):
        raise ValueError(f"Data freshness validation requires dict, got {type(data).__name__}")
    if field_name not in data:
        raise ValueError(f"Timestamp field '{field_name}' missing from data. Cannot validate freshness.")
    if data[field_name] is None:
        raise ValueError(f"Timestamp field '{field_name}' is NULL. Data freshness cannot be determined.")

    ts = data[field_name]
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError) as e:
            raise ValueError(
                f"Cannot parse timestamp in '{field_name}': {ts!r}. "
                f"Expected ISO format (got error: {e}). Data may be corrupted."
            ) from e

    if not isinstance(ts, datetime):
        raise ValueError(
            f"Timestamp field '{field_name}' has invalid type {type(ts).__name__}, expected datetime. "
            f"Data schema mismatch or corruption."
        )

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    age_hours = (datetime.now(ET) - ts).total_seconds() / 3600
    if age_hours > max_age_hours:
        logger.warning(f"Data stale: {field_name} is {age_hours:.1f}h old (threshold: {max_age_hours}h)")
        return False
    return True


# ── Data Quality Tracking (Finance Principle: Make Missing Data Visible) ───────

_data_quality_issues: list[dict[str, Any]] = []
_data_quality_lock = threading.Lock()


def record_data_quality_issue(fetcher: str, field: str, issue: str, value: Any = None) -> None:
    """Record a data quality issue for dashboarding and alerting.

    Args:
        fetcher: Fetcher name (e.g., "portfolio", "per", "market")
        field: Field name (e.g., "total_portfolio_value")
        issue: Issue type (e.g., "missing_required_field", "conversion_failed", "data_stale")
        value: Optional value for context
    """
    global _data_quality_issues
    with _data_quality_lock:
        _data_quality_issues.append(
            {
                "timestamp": datetime.now(ET),
                "fetcher": fetcher,
                "field": field,
                "issue": issue,
                "value": str(value)[:100] if value is not None else None,
            }
        )
        if len(_data_quality_issues) > 1000:
            _data_quality_issues = _data_quality_issues[-1000:]
    logger.warning(
        f"Data quality issue: {fetcher}.{field} - {issue}" + (f" (value: {value!r})" if value is not None else "")
    )


def get_data_quality_report(max_age_minutes: int = 30) -> list[dict[str, Any]]:
    """Get data quality issues from the last N minutes.

    Returns:
        List of issue dicts with timestamp, fetcher, field, issue, value
    """
    cutoff = datetime.now(ET) - timedelta(minutes=max_age_minutes)
    with _data_quality_lock:
        recent = [i for i in _data_quality_issues if i["timestamp"] >= cutoff]
    return recent


def clear_data_quality_issues() -> None:
    """Clear the data quality issue history."""
    global _data_quality_issues
    with _data_quality_lock:
        _data_quality_issues = []
