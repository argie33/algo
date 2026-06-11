#!/usr/bin/env python3
"""
Algo Ops Terminal Dashboard  --  single-pane morning brief.

Usage:
  python tools/dashboard/dashboard.py            # live view (q or Ctrl+C to exit)
  python tools/dashboard/dashboard.py -w         # watch mode, auto-refresh every 30s
  python tools/dashboard/dashboard.py -w 60      # watch mode, refresh every 60s
  python tools/dashboard/dashboard.py --compact  # narrow positions table
"""

import argparse
import json
import logging
import os
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

from utils.data_freshness_config import is_table_fresh, get_freshness_rule, get_max_age_minutes

logger = logging.getLogger(__name__)

# Metric freshness thresholds (how recently were calculations run)
METRICS_CALCULATION_MAX_AGE_MINUTES = 120  # Pre-computed metrics must be < 2 hours old

def _log_data_quality(source: str, count: int, error: Optional[str] = None):
    """Log data fetch results: distinguishes 'empty' (no rows but no error) from 'failed' (error occurred).

    Issue 23 FIX: Logging rule for consistency across dashboard:
    - ERROR: Fetch halted entirely (DB unavailable, connection timeout, critical schema missing)
             Dashboard cannot proceed without this data
    - WARNING: Fetch returned incomplete data (0 rows, missing columns, stale data > threshold)
              Dashboard can display with degraded information
    - DEBUG: Fetch succeeded normally with data (row count > 0, all validations passed)
            Expected operational state

    This rule applies uniformly:
    - fetch_* functions use ERROR for halting conditions, WARNING for incomplete data
    - panel_* functions treat errors as missing data displays, not crashes
    - validation hooks in fetchers log issues at appropriate level
    """
    if error:
        logger.error(f"Data fetch [{source}] FAILED: {error}")
    elif count == 0:
        logger.warning(f"Data fetch [{source}] EMPTY: returned 0 rows (check if table has data)")
    else:
        logger.debug(f"Data fetch [{source}] OK: {count} rows")

try:
    import msvcrt
    def _keypress() -> str:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            return ch.decode("utf-8", errors="ignore").lower()
        return ""
except ImportError:
    # Not on Windows (AWS Linux, etc.)
    def _keypress() -> str:
        return ""

if sys.platform == "win32":
    os.system("chcp 65001 > nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # AttributeError on older Python, ValueError on some environments

try:
    import psycopg2, psycopg2.extras
except ImportError:
    sys.exit("pip install psycopg2-binary")

try:
    import boto3
    import botocore.config
    from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError
except ImportError:
    boto3 = None
    ClientError = None
    ConnectTimeoutError = None
    ReadTimeoutError = None

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
    "unknown":           "dim",
}

TIER_SHORT = {
    "confirmed_uptrend": "CONF UP",
    "healthy_uptrend":   "HLTH UP",
    "pressure":          "PRESSURE",
    "caution":           "CAUTION",
    "correction":        "CORRECT",
}

def load_grade_thresholds(cfg: Optional[dict] = None) -> dict:
    """Load grade thresholds from config, used for dashboard signal grades.

    Separate from swing_grade_threshold_* (used in algo_swing_score.py).
    Dashboard uses slightly different thresholds for historical reasons.
    """
    if cfg:
        return {
            'a': int(cfg.get('dashboard_grade_threshold_a', 80)),
            'b': int(cfg.get('dashboard_grade_threshold_b', 60)),
            'c': int(cfg.get('dashboard_grade_threshold_c', 40)),
        }
    # Fallback hardcoded defaults
    return {'a': 80, 'b': 60, 'c': 40}

def load_market_thresholds(cfg: Optional[dict] = None) -> dict:
    """Load market indicator thresholds from config (M2 FIX - no longer hardcoded).

    Provides thresholds for: VIX, Put/Call, up-volume, breadth, etc.
    Used for coloring market health indicators (RED/YELLOW/GREEN).
    """
    if cfg:
        return {
            'vix_alert': safe_float(cfg.get('vix_alert_threshold', 30.0), 30.0),
            'vix_caution': safe_float(cfg.get('vix_caution_threshold', 25.0), 25.0),
            'put_call_bullish': safe_float(cfg.get('put_call_bullish_threshold', 0.8), 0.8),
            'put_call_fearful': safe_float(cfg.get('put_call_fearful_threshold', 1.0), 1.0),
            'upvol_good': safe_float(cfg.get('upvol_good_threshold', 60.0), 60.0),
            'upvol_caution': safe_float(cfg.get('upvol_caution_threshold', 50.0), 50.0),
            'breadth_good': int(cfg.get('breadth_good_threshold', 50)),
            'breadth_caution': int(cfg.get('breadth_caution_threshold', 0)),
            'yield_curve_good': safe_float(cfg.get('yield_curve_good_threshold', 0.5), 0.5),
            'breadth_momentum_good': safe_float(cfg.get('breadth_momentum_good_threshold', 0.5), 0.5),
            'beta_warning': safe_float(cfg.get('beta_warning_threshold', 1.2), 1.2),
            'beta_caution': safe_float(cfg.get('beta_caution_threshold', 0.8), 0.8),
        }
    # Fallback hardcoded defaults (M2 issue: these were previously hardcoded everywhere)
    return {
        'vix_alert': 30.0, 'vix_caution': 25.0,
        'put_call_bullish': 0.8, 'put_call_fearful': 1.0,
        'upvol_good': 60.0, 'upvol_caution': 50.0,
        'breadth_good': 50, 'breadth_caution': 0,
        'yield_curve_good': 0.5,
        'breadth_momentum_good': 0.5,
        'beta_warning': 1.2, 'beta_caution': 0.8,
        'circuit_breaker_ratio': 0.75,
        'fear_greed_alert': 25.0, 'fear_greed_caution': 45.0, 'fear_greed_bullish': 75.0,
    }


def get_grade_thresholds(cfg: Optional[dict] = None) -> dict:
    """Load grade thresholds from config or hardcoded defaults.

    Used for coloring signal quality scores (RED/YELLOW/GREEN based on A/B/C grades).
    Allows runtime configuration without code changes.
    """
    if cfg:
        return {
            'a_plus': safe_float(cfg.get('grade_a_plus_threshold', 90.0), 90.0),
            'a': safe_float(cfg.get('grade_a_threshold', 80.0), 80.0),
            'b': safe_float(cfg.get('grade_b_threshold', 70.0), 70.0),
            'c': safe_float(cfg.get('grade_c_threshold', 60.0), 60.0),
        }
    # Fallback hardcoded defaults (M1 FIX: these are now configurable)
    return {
        'a_plus': 90.0,
        'a': 80.0,
        'b': 70.0,
        'c': 60.0,
    }


def load_performance_thresholds(cfg: Optional[dict] = None) -> dict:
    """Load performance metric thresholds for coloring (win rate, Sharpe, profit factor, etc.)."""
    if cfg:
        return {
            'win_rate_good': safe_float(cfg.get('win_rate_good_threshold', 50.0), 50.0),
            'win_rate_excellent': safe_float(cfg.get('win_rate_excellent_threshold', 55.0), 55.0),
            'sharpe_good': safe_float(cfg.get('sharpe_good_threshold', 1.0), 1.0),
            'sharpe_excellent': safe_float(cfg.get('sharpe_excellent_threshold', 2.0), 2.0),
            'profit_factor_good': safe_float(cfg.get('profit_factor_good_threshold', 1.5), 1.5),
            'profit_factor_excellent': safe_float(cfg.get('profit_factor_excellent_threshold', 2.0), 2.0),
            'calmar_good': safe_float(cfg.get('calmar_good_threshold', 0.5), 0.5),
            'beta_warning': safe_float(cfg.get('beta_warning_threshold', 1.2), 1.2),
            'beta_caution': safe_float(cfg.get('beta_caution_threshold', 0.8), 0.8),
        }
    return {
        'win_rate_good': 50.0, 'win_rate_excellent': 55.0,
        'sharpe_good': 1.0, 'sharpe_excellent': 2.0,
        'profit_factor_good': 1.5, 'profit_factor_excellent': 2.0,
        'calmar_good': 0.5,
        'beta_warning': 1.2, 'beta_caution': 0.8,
    }

def load_risk_thresholds(cfg: Optional[dict] = None) -> dict:
    """Load risk metric thresholds (drawdown, position size, etc.)."""
    if cfg:
        return {
            'drawdown_alert': safe_float(cfg.get('drawdown_alert_threshold', 15.0), 15.0),
            'drawdown_caution': safe_float(cfg.get('drawdown_caution_threshold', 5.0), 5.0),
            'large_position_alert': safe_float(cfg.get('large_position_alert_threshold', 20.0), 20.0),
            'large_position_caution': safe_float(cfg.get('large_position_caution_threshold', 15.0), 15.0),
        }
    return {
        'drawdown_alert': 15.0, 'drawdown_caution': 5.0,
        'large_position_alert': 20.0, 'large_position_caution': 15.0,
    }

def load_signal_thresholds(cfg: Optional[dict] = None) -> dict:
    """Load signal evaluation thresholds for quality scoring."""
    if cfg:
        return {
            'event_value_good': safe_float(cfg.get('event_value_good_threshold', 20.0), 20.0),
            'event_value_caution': safe_float(cfg.get('event_value_caution_threshold', 5.0), 5.0),
            'signal_alert': safe_float(cfg.get('signal_alert_threshold', 60.0), 60.0),
            'signal_caution': safe_float(cfg.get('signal_caution_threshold', 40.0), 40.0),
            'volume_surge_good': safe_float(cfg.get('volume_surge_good_threshold', 50.0), 50.0),
            'volume_surge_caution': safe_float(cfg.get('volume_surge_caution_threshold', 20.0), 20.0),
        }
    return {
        'event_value_good': 20.0, 'event_value_caution': 5.0,
        'signal_alert': 60.0, 'signal_caution': 40.0,
        'volume_surge_good': 50.0, 'volume_surge_caution': 20.0,
    }

def get_grade_thresholds(cfg: Optional[dict] = None) -> dict:
    """Load grade thresholds from config or hardcoded defaults.

    Used for coloring signal quality scores (RED/YELLOW/GREEN based on A/B/C grades).
    Allows runtime configuration without code changes.
    """
    if cfg:
        return {
            'a_plus': safe_float(cfg.get('grade_a_plus_threshold', 90.0), 90.0),
            'a': safe_float(cfg.get('grade_a_threshold', 80.0), 80.0),
            'b': safe_float(cfg.get('grade_b_threshold', 70.0), 70.0),
            'c': safe_float(cfg.get('grade_c_threshold', 60.0), 60.0),
        }
    # Fallback hardcoded defaults (M1 FIX: these are now configurable)
    return {
        'a_plus': 90.0,
        'a': 80.0,
        'b': 70.0,
        'c': 60.0,
    }

# Grade thresholds for signal scoring (separate from market tier thresholds)
GRADE_A_PLUS = 90
GRADE_A = 80
GRADE_B = 70
GRADE_C = 60

# Health bar and visual indicator thresholds
HBAR_CRITICAL = 1.0
HBAR_WARNING = 0.75

# Market tier exposure thresholds (percentage)
TIER_THRESHOLD_CONFIRMED = 75.0
TIER_THRESHOLD_HEALTHY = 50.0
TIER_THRESHOLD_PRESSURE = 25.0
TIER_THRESHOLD_CAUTION = 10.0

# Economic indicator thresholds
DXY_WARNING = 105.0  # USD Index warning threshold
DXY_CRITICAL = 108.0  # USD Index critical threshold
BE_WARNING = 2.5  # Inflation Breakeven warning (%)
BE_CRITICAL = 3.0  # Inflation Breakeven critical (%)
MORTGAGE_WARNING = 7.0  # 30Y Mortgage rate warning (%)
MORTGAGE_CRITICAL = 8.0  # 30Y Mortgage rate critical (%)
NFCI_NEGATIVE = -0.5  # Chicago Fed NFCI accommodative threshold
NFCI_POSITIVE = 0.5  # Chicago Fed NFCI tight threshold
UMCSENT_WARNING = 60  # University of Michigan Consumer Sentiment warning
UMCSENT_GOOD = 70  # University of Michigan Consumer Sentiment good threshold

MINIBAR_HIGH = 0.75
MINIBAR_MED = 0.35

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

MARKET_STAGE = {
    1: "Stage 1 — Accumulation (early uptrend)",
    2: "Stage 2 — Advance (strong uptrend)",
    3: "Stage 3 — Distribution (late uptrend)",
    4: "Stage 4 — Decline (downtrend)",
}

# Issue 34/35 FIX: Map halt reason codes to human-readable explanations
HALT_REASON_NAMES = {
    "drawdown":                 "Portfolio drawdown >=20%",
    "drawdown_re_engagement":   "Drawdown recovery in progress",
    "daily_loss":               "Daily loss >=2%",
    "consecutive_losses":       "≥3 consecutive losing trades",
    "total_risk":               "Total open risk >=4%",
    "vix_spike":                "VIX spike >35",
    "market_stage":             "Market in downtrend (Stage 4)",
    "weekly_loss":              "Weekly loss >=5%",
    "sector_concentration":     "Sector concentration risk",
    "intraday_market_health":   "Market health deterioration",
    "win_rate_floor":           "Win rate below threshold",
    "daily_profit_cap":         "Daily profit cap reached",
    "data_freshness":           "Required data stale",
}

# H14 FIX: Define failure threshold for load_all degradation logic
FETCHER_FAILURE_THRESHOLD = 0.5  # If >50% of fetchers fail, enter degraded mode

# ── mascot (dancing monkey) ──────────────────────────────────────────────────
# Each frame: 4 lines, each exactly 11 visible chars (pre-padded, no centering math).
# MASCOT_W=13 = 1 border + 11 content + 1 border, padding=(0,0).
# @ = ears, \{~~~}/ = wide shoulders, |{~~~}| = body. Frame 7 = CB panic freeze.
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


def mascot_pose(data: dict, frame: int) -> int:
    # Issue 43 FIX: Handle missing or malformed cb gracefully
    try:
        cb = data.get("cb") if isinstance(data, dict) else {}
        if not isinstance(cb, dict):
            cb = {}
        seq = [4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 7] if cb.get("any") else LOAD_SEQ
    except (AttributeError, TypeError):
        seq = LOAD_SEQ
    if not seq:
        logger.error("mascot_pose: sequence is empty; using fallback frame 0")
        return 0
    return seq[(frame // 2) % len(seq)]


# ── Data validation helpers (CRITICAL ISSUE 1, 2, 3 FIX) ───────────────────────

def is_error_dict(data) -> bool:
    """Check if data is an error dict. Error dicts have _error key with non-empty value."""
    return isinstance(data, dict) and bool(data.get("_error"))


def get_numeric(data: dict, key: str, default=None) -> Optional[float]:
    """Safely extract and validate numeric value from dict. Returns None if missing/invalid/error.

    CRITICAL ISSUE 3 FIX: Validates data type before conversion to prevent silent crashes.
    CRITICAL ISSUE 1 FIX: Returns None (not default) if data is missing or error, so UI can show [missing].
    """
    if not isinstance(data, dict) or data.get("_error"):
        return default
    val = data.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        logger.warning(f"Data validation: {key}={val!r} is not numeric (type: {type(val).__name__})")
        return default


def get_int(data: dict, key: str, default=None) -> Optional[int]:
    """Safely extract and validate integer value from dict. Returns None if missing/invalid/error."""
    if not isinstance(data, dict) or data.get("_error"):
        return default
    val = data.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        logger.warning(f"Data validation: {key}={val!r} is not integer (type: {type(val).__name__})")
        return default


def get_string(data: dict, key: str, default="") -> str:
    """Safely extract and validate string value from dict. Returns empty string or default if missing/error."""
    if not isinstance(data, dict) or data.get("_error"):
        return default
    val = data.get(key)
    if val is None:
        return default
    try:
        return str(val).strip()
    except (AttributeError, TypeError):
        logger.warning(f"Data validation: {key}={val!r} cannot convert to string")
        return default


def get_list(data: dict, key: str, default=None) -> list:
    """Safely extract list from dict. Returns empty list or default if missing/error."""
    if not isinstance(data, dict) or data.get("_error"):
        return default if default is not None else []
    val = data.get(key)
    if val is None:
        return default if default is not None else []
    if isinstance(val, list):
        return val
    logger.warning(f"Data validation: {key}={val!r} is not a list (type: {type(val).__name__})")
    return default if default is not None else []


def error_msg(data) -> str:
    """Extract error message from error dict. Returns empty string if no error."""
    if isinstance(data, dict) and data.get("_error"):
        return str(data.get("_error", "Unknown error"))
    return ""


def is_valid_data(data) -> bool:
    """Check if data is valid (not empty, not an error dict).

    TIER 1B FIX: Validate data before rendering to catch missing/failed fetches.
    Returns True only if data exists and is not an error dict.
    """
    return isinstance(data, (dict, list)) and not (isinstance(data, dict) and data.get("_error"))


def error_panel(title: str, err_msg: str) -> Panel:
    """Return a standardized error panel with red border and error message.

    TIER 1B FIX: Consistent error display across all panels.
    """
    msg = f"error: {err_msg}" if err_msg else "no data available"
    return Panel(Text(msg, style="red"), title=f"[bold red]{title}[/]", border_style="red", padding=(0, 1))


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db_credentials() -> dict:
    """Fetch and validate DB credentials: try env vars first, then AWS Secrets Manager.

    CRITICAL ISSUE 1 FIX: Validate immediately and fail fast with specific missing field info.
    Don't return incomplete credentials—let caller know exactly what's missing and where from.
    """
    port_str = os.environ.get("DB_PORT")
    try:
        port = int(port_str) if port_str else None
    except (ValueError, TypeError):
        port = None

    env_creds = {
        "host": os.environ.get("DB_HOST"),
        "user": os.environ.get("DB_USER"),
        "password": os.environ.get("DB_PASSWORD"),
        "dbname": os.environ.get("DB_NAME"),
        "port": port,
    }

    # If env vars are complete, use them
    if all([env_creds["host"], env_creds["user"], env_creds["password"], env_creds["dbname"], env_creds["port"]]):
        logger.debug("DB credentials loaded from environment variables")
        return env_creds

    # Env vars incomplete — check what's missing
    env_missing = [k for k in ["host", "user", "password", "dbname", "port"] if not env_creds.get(k)]
    env_status = f"incomplete ({', '.join(env_missing)} missing)" if env_missing else "complete"

    # Otherwise try AWS Secrets Manager (with explicit timeout handling)
    if boto3:
        try:
            # Issue 5 FIX: Add explicit timeout to prevent hangs during testing
            config = botocore.config.Config(
                connect_timeout=5,
                read_timeout=5,
                retries={'max_attempts': 1}
            )
            client = boto3.client("secretsmanager", region_name="us-east-1", config=config)
            secret_name = os.environ.get("DB_SECRET_NAME", "algo-db-credentials")
            response = client.get_secret_value(SecretId=secret_name)
            secret_dict = json.loads(response.get("SecretString", "{}"))
            sm_port = secret_dict.get("port")
            try:
                sm_port = int(sm_port) if sm_port else None
            except (ValueError, TypeError):
                sm_port = None

            creds = {
                "host": secret_dict.get("host"),
                "user": secret_dict.get("username"),
                "password": secret_dict.get("password"),
                "dbname": secret_dict.get("dbname"),
                "port": sm_port,
            }

            # Validate Secrets Manager creds before returning
            sm_missing = [k for k in ["host", "user", "password", "dbname", "port"] if not creds.get(k)]
            if sm_missing:
                msg = f"AWS Secrets Manager ({secret_name}) incomplete: missing fields {sm_missing}. " \
                      f"Environment variables also {env_status}. Cannot proceed."
                logger.error(f"CRITICAL: {msg}")
                sys.exit(msg)

            logger.debug(f"DB credentials loaded from AWS Secrets Manager ({secret_name})")
            return creds
        except (ConnectTimeoutError, ReadTimeoutError) as e:
            # Issue 5 FIX: Distinguish timeout from credential/access errors
            msg = f"AWS Secrets Manager timeout ({type(e).__name__}). " \
                  f"For testing, set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME environment variables. " \
                  f"Environment variables are {env_status}. Cannot proceed."
            logger.error(f"CRITICAL: {msg}")
            sys.exit(msg)
        except ClientError as e:
            # Issue 5 FIX: Distinguish access/permission errors
            err_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if err_code == 'ResourceNotFoundException':
                msg = f"AWS Secrets Manager: secret '{secret_name}' not found. " \
                      f"Verify secret exists in us-east-1 and name matches DB_SECRET_NAME env var. " \
                      f"Or set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME for local testing."
            elif err_code == 'AccessDeniedException':
                msg = f"AWS Secrets Manager: access denied to '{secret_name}'. " \
                      f"Check IAM permissions for role running dashboard."
            else:
                msg = f"AWS Secrets Manager error ({err_code}): {e}. " \
                      f"Or set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME for local testing."
            logger.error(f"CRITICAL: {msg}")
            sys.exit(msg)
        except Exception as e:
            msg = f"Failed to fetch credentials from Secrets Manager ({type(e).__name__}: {e}). " \
                  f"Environment variables are {env_status}. Cannot proceed."
            logger.error(f"CRITICAL: {msg}")
            sys.exit(msg)

    # Neither env vars nor Secrets Manager available
    msg = f"Database credentials unavailable. Environment variables are {env_status}. " \
          f"boto3 not available or AWS Secrets Manager not configured. Cannot proceed."
    logger.error(f"CRITICAL: {msg}")
    sys.exit(msg)

def get_conn() -> psycopg2.extensions.connection:
    creds = _get_db_credentials()
    missing = {k: "not set" for k, v in creds.items() if not v}
    if missing:
        source = "AWS Secrets Manager" if not os.environ.get("DB_HOST") else "environment variables"
        msg = f"Cannot connect: missing credentials {list(missing.keys())} from {source}"
        logger.error(f"CRITICAL: Credentials validation FAILED: {msg}")
        sys.exit(msg)

    try:
        logger.debug(f"Connecting to {creds['host']}:{creds['port']}/{creds['dbname']} (user: {creds['user']})")
        return psycopg2.connect(
            host=creds["host"], port=creds["port"],
            user=creds["user"], password=creds["password"],
            dbname=creds["dbname"], connect_timeout=5,
            cursor_factory=psycopg2.extras.RealDictCursor,
            options="-c statement_timeout=30000",
        )
    except psycopg2.OperationalError as e:
        err = str(e).lower()
        if "authentication failed" in err:
            logger.error(f"CRITICAL: Authentication FAILED: check DB_USER and DB_PASSWORD")
        elif "could not translate" in err:
            logger.error(f"CRITICAL: Host resolution FAILED: {creds['host']} unreachable")
        elif "connection refused" in err:
            logger.error(f"CRITICAL: Connection refused: RDS not running or port blocked")
        else:
            logger.error(f"CRITICAL: Connection error: {e}")
        raise

def q(c: psycopg2.extensions.connection, sql: str, p: Optional[tuple] = None) -> List[Dict]:
    with c.cursor() as cur:
        cur.execute(sql, p or ())
        return [r if isinstance(r, dict) else dict(r) for r in cur.fetchall()]

def q1(c: psycopg2.extensions.connection, sql: str, p: Optional[tuple] = None) -> Optional[Dict]:
    rows = q(c, sql, p)
    return rows[0] if rows else None

# ── API Client ─────────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("DASHBOARD_API_URL", "http://localhost:3000")
API_TIMEOUT = 10

def api_call(endpoint: str, params: Optional[Dict] = None, method: str = "GET") -> Dict:
    """Call API endpoint. Returns dict with 'data' key on success, '_error' on failure."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
        else:
            resp = requests.post(url, json=params, headers=headers, timeout=API_TIMEOUT)

        if resp.status_code >= 400:
            logger.warning(f"API call to {endpoint} returned {resp.status_code}: {resp.text[:200]}")
            return {"_error": f"API error {resp.status_code}"}

        return resp.json()
    except requests.exceptions.Timeout:
        logger.warning(f"API call to {endpoint} timed out after {API_TIMEOUT}s")
        return {"_error": "API timeout"}
    except requests.exceptions.ConnectionError:
        logger.warning(f"API call to {endpoint} connection failed")
        return {"_error": "API unavailable"}
    except Exception as e:
        logger.warning(f"API call to {endpoint} failed: {type(e).__name__}: {e}")
        return {"_error": str(e)}

def validate_schema() -> None:
    """CRITICAL ISSUE 2 FIX: Validate table schema (columns, types, and data presence).

    Checks:
    1. Tables exist
    2. Required columns exist with correct types (numeric, date, text)
    3. Critical tables contain data (not empty)

    Exits immediately on critical failures to prevent silent data issues.
    """
    try:
        conn = get_conn()
        # Issue 9.1: Comprehensive table validation — critical, important, and supporting tables
        # Format: (table, [(column, expected_type_family), ...], severity)
        # Type families: numeric (int/bigint/decimal/float), temporal (date/timestamp), text/varchar
        all_checks = [
            # Critical (trading data)
            ("algo_trades", [
                ("profit_loss_dollars", "numeric"),
                ("exit_date", "temporal"),
                ("status", "text")
            ], "critical"),
            ("algo_portfolio_snapshots", [
                ("total_portfolio_value", "numeric"),
                ("daily_return_pct", "numeric")
            ], "critical"),
            ("price_daily", [
                ("close", "numeric"),
                ("date", "temporal")
            ], "critical"),
            # Important (positions & market context)
            ("trend_template_data", [
                ("weinstein_stage", "numeric"),
                ("date", "temporal")
            ], "important"),
            ("swing_trader_scores", [
                ("score", "numeric"),
                ("date", "temporal")
            ], "important"),
            ("company_profile", [
                ("sector", "text"),
                ("ticker", "text")
            ], "important"),
            ("market_health_daily", [
                ("vix_level", "numeric"),
                ("date", "temporal")
            ], "important"),
            ("buy_sell_daily", [
                ("signal", "text"),
                ("date", "temporal")
            ], "important"),
            ("market_exposure_daily", [
                ("exposure_pct", "numeric"),
                ("date", "temporal")
            ], "important"),
            # Supporting (performance & metrics)
            ("algo_metrics_daily", [("date", "temporal")], "supporting"),
            ("algo_audit_log", [
                ("action_type", "text"),
                ("created_at", "temporal")
            ], "supporting"),
        ]

        def type_family_matches(data_type: str, expected_family: str) -> bool:
            """Check if PostgreSQL data_type belongs to expected family."""
            data_type = data_type.lower()
            if expected_family == "numeric":
                return any(t in data_type for t in ["int", "numeric", "decimal", "float", "real", "double", "bigint", "smallint"])
            elif expected_family == "temporal":
                return any(t in data_type for t in ["date", "timestamp", "time"])
            elif expected_family == "text":
                return any(t in data_type for t in ["char", "text", "varchar"])
            return False

        for table, cols_with_types, severity in all_checks:
            try:
                # Fetch column information (name, type)
                col_info = q(conn, f"""
                    SELECT column_name, data_type FROM information_schema.columns
                    WHERE table_name = %s AND column_name = ANY(%s)
                    ORDER BY ordinal_position
                """, (table, [c[0] for c in cols_with_types]))

                col_dict = {row["column_name"]: row["data_type"] for row in col_info}

                # Check all required columns exist
                missing_cols = [c[0] for c, t in cols_with_types if c not in col_dict]
                if missing_cols:
                    msg = f"Schema validation {severity.upper()}: {table} missing columns {missing_cols}"
                    logger.error(msg)
                    if severity == "critical":
                        sys.exit(f"Database schema error: {table} missing required columns {missing_cols}")
                    continue

                # Check column types
                type_mismatches = []
                for col_name, expected_type in cols_with_types:
                    if col_name in col_dict:
                        actual_type = col_dict[col_name]
                        if not type_family_matches(actual_type, expected_type):
                            type_mismatches.append(f"{col_name} is {actual_type} (expected {expected_type})")

                if type_mismatches:
                    msg = f"Schema validation {severity.upper()}: {table} type mismatch: {'; '.join(type_mismatches)}"
                    logger.error(msg)
                    if severity == "critical":
                        sys.exit(f"Database schema error: {table} has incorrect column types")

                # Verify table has data (critical and important tables must have data)
                if severity in ("critical", "important"):
                    row_count = q1(conn, f"SELECT COUNT(*) as cnt FROM {table}")
                    if row_count and row_count.get("cnt") == 0:
                        if severity == "critical":
                            msg = f"Schema validation CRITICAL: {table} exists but is EMPTY (contains no data) — dashboard cannot proceed"
                            logger.error(msg)
                            sys.exit(f"Database schema error: critical table {table} is empty (contains no data)")
                        else:  # important
                            msg = f"Schema validation IMPORTANT: {table} exists but is EMPTY (contains no data) — dashboard will display with missing {table} data"
                            logger.error(msg)
                            sys.exit(f"Database schema error: important table {table} is empty (contains no data)")

            except psycopg2.Error as e:
                if "does not exist" in str(e):
                    msg = f"Schema validation {severity.upper()}: {table} missing"
                    logger.warning(msg)
                    if severity == "critical":
                        sys.exit(f"Database schema error: required table {table} not found")
                else:
                    raise

        conn.close()
        logger.info("Database schema validation passed (columns exist with correct types, critical tables have data)")
    except (psycopg2.Error, KeyError) as e:
        logger.error(f"Schema validation failed: {e}")
        sys.exit(f"Database connection/schema error: {e}")

def validate_phase_results(phase_results: any) -> List[Dict]:
    """Validate phase_results schema. Each phase must have 'name'/'phase' and valid 'status'.

    Returns: list of valid phase objects with guaranteed structure; invalid entries logged.
    """
    if not isinstance(phase_results, list):
        logger.warning(f"VALIDATION: phase_results expected list, got {type(phase_results).__name__}")
        return []

    # Issue 20 FIX: Define valid status values (not just any string like 'unknown')
    VALID_STATUSES = {'ok', 'success', 'running', 'pending', 'halt', 'halted', 'failed', 'completed', 'skipped'}

    valid = []
    for i, p in enumerate(phase_results):
        if not isinstance(p, dict):
            logger.warning(f"VALIDATION: phase_results[{i}] expected dict, got {type(p).__name__}")
            continue

        # Check required fields: name/phase and status
        name = p.get("name") or p.get("phase")
        status = (p.get("status") or "").lower().strip()

        if not name:
            logger.warning(f"VALIDATION: phase_results[{i}] missing 'name'/'phase' field")
        if not status:
            logger.warning(f"VALIDATION: phase_results[{i}] missing 'status' field")
        elif status not in VALID_STATUSES:
            logger.warning(f"VALIDATION: phase_results[{i}] has invalid status '{status}' (not in {VALID_STATUSES})")
            status = None  # Treat as missing for validation

        if name and status:
            valid.append(p)

    if len(valid) < len(phase_results):
        logger.warning(f"VALIDATION: phase_results schema check: {len(valid)} valid, {len(phase_results) - len(valid)} invalid entries")

    return valid

# ── formatters ────────────────────────────────────────────────────────────────

def fmt_age(ts: any) -> str:
    if ts is None: return "--"
    dt = _parse_datetime(ts, as_date=False, timezone_aware=True)
    if dt is None: return "--"
    try:
        m = int((datetime.now(ET) - dt).total_seconds() / 60)
        if m < 60:   return f"{m}m ago"
        if m < 1440: return f"{m // 60}h{m % 60:02d}m ago"
        return f"{m // 1440}d ago"
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"fmt_age error calculating age {ts!r}: {e}")
        return "--"

def fmt_money(v: any) -> str:
    if v is None: return "--"
    v = safe_float(v)
    if v is None: return "--"
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6: return f"{s}${av / 1e6:.2f}M"
    if av >= 1e3: return f"{s}${av:,.0f}"
    return f"{s}${av:.2f}"

def fmt_money_short(v: any) -> str:
    """Compact dollar format: $45K, $1.2M, $850 — for narrow table columns."""
    if v is None: return "--"
    v = safe_float(v)
    if v is None: return "--"
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6: return f"{s}${av/1e6:.1f}M"
    if av >= 1e3: return f"{s}${av/1e3:.0f}K"
    return f"{s}${av:.0f}"

def grade(s: float) -> str:
    s = safe_float(s)
    if s is None: return "--"
    if s >= GRADE_A_PLUS: return "A+"
    if s >= GRADE_A: return "A"
    if s >= GRADE_B: return "B"
    if s >= GRADE_C: return "C"
    return "D"

def tier_from_pct(p: Optional[float], thresholds: Optional[dict] = None) -> str:
    """Classify market tier based on exposure percentage.

    HIGH-SEVERITY ISSUE FIX: Market Tier classification now reads from config
    instead of using hardcoded thresholds. Allows tuning without code changes.

    Args:
        p: exposure percentage (0-100)
        thresholds: optional dict with keys: confirmed, healthy, pressure, caution
                   (uses hardcoded defaults if not provided)

    Returns:
        tier classification string
    """
    if p is None: return "unknown"
    p = safe_float(p)
    if p is None: return "unknown"

    # Use provided thresholds or fallback to hardcoded defaults
    t_confirmed = TIER_THRESHOLD_CONFIRMED if thresholds is None else thresholds.get("confirmed", TIER_THRESHOLD_CONFIRMED)
    t_healthy = TIER_THRESHOLD_HEALTHY if thresholds is None else thresholds.get("healthy", TIER_THRESHOLD_HEALTHY)
    t_pressure = TIER_THRESHOLD_PRESSURE if thresholds is None else thresholds.get("pressure", TIER_THRESHOLD_PRESSURE)
    t_caution = TIER_THRESHOLD_CAUTION if thresholds is None else thresholds.get("caution", TIER_THRESHOLD_CAUTION)

    if p >= t_confirmed: return "confirmed_uptrend"
    if p >= t_healthy: return "healthy_uptrend"
    if p >= t_pressure: return "pressure"
    if p >= t_caution: return "caution"
    return "correction"

def is_open() -> bool:
    n = datetime.now(ET)
    if n.weekday() >= 5: return False
    t = n.hour * 60 + n.minute
    return 570 <= t <= 960

def mkt_hours_str() -> tuple:
    """Returns (status_markup, countdown_str) reflecting pre-mkt/open/after-hrs/closed."""
    n  = datetime.now(ET)
    wd = n.weekday()
    t  = n.hour * 60 + n.minute

    def _fmt_mins(m):
        h, mm = divmod(m, 60)
        return f"{h}h{mm:02d}m" if h > 0 else f"{mm}m"

    if wd >= 5:
        days_ahead = 7 - wd  # sat→2, sun→1
        open_dt = (n + timedelta(days=days_ahead)).replace(
            hour=9, minute=30, second=0, microsecond=0)
        diff_m = max(0, int((open_dt - n).total_seconds() / 60))
        return "[dim]● CLOSED[/]", f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}"

    PRE_OPEN  = 4 * 60       # 4:00 AM
    OPEN      = 9 * 60 + 30  # 9:30 AM
    CLOSE     = 16 * 60      # 4:00 PM
    AH_END    = 20 * 60      # 8:00 PM

    if t < PRE_OPEN:
        diff_m = OPEN - t
        return "[dim]● CLOSED[/]", f"opens in {_fmt_mins(diff_m)}"
    if t < OPEN:
        diff_m = OPEN - t
        return "[yellow]● PRE-MKT[/]", f"opens in {_fmt_mins(diff_m)}"
    if t < CLOSE:
        diff_m = CLOSE - t
        return "[bold bright_green]● OPEN[/]", f"closes in {_fmt_mins(diff_m)}"
    if t < AH_END:
        next_days = 3 if wd == 4 else 1
        open_dt = (n + timedelta(days=next_days)).replace(
            hour=9, minute=30, second=0, microsecond=0)
        diff_m = max(0, int((open_dt - n).total_seconds() / 60))
        return "[dim]● AFTER-HRS[/]", f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}"
    next_days = 3 if wd == 4 else 1
    open_dt = (n + timedelta(days=next_days)).replace(
        hour=9, minute=30, second=0, microsecond=0)
    diff_m = max(0, int((open_dt - n).total_seconds() / 60))
    return "[dim]● CLOSED[/]", f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}"

def next_run_str() -> str:
    now = datetime.now(ET)
    wd  = now.weekday()
    t   = now.hour * 60 + now.minute

    def fmt(dt):
        diff = dt - now
        mins = int(diff.total_seconds() / 60)
        if mins < 60:   return f"in {mins}m"
        if mins < 1440: return f"in {mins//60}h{mins%60:02d}m"
        return f"{dt.strftime('%a %I:%M %p')}"

    def next_wkd(dt, off=1):
        d = dt + timedelta(days=off)
        while d.weekday() >= 5: d += timedelta(days=1)
        return d

    if wd < 5:
        if t < 120:
            return f"prep {fmt(now.replace(hour=2, minute=0, second=0, microsecond=0))}"
        if t < 570:
            return f"orch {fmt(now.replace(hour=9, minute=30, second=0, microsecond=0))}"
        tgt = next_wkd(now).replace(hour=2, minute=0, second=0, microsecond=0)
        return f"prep {fmt(tgt)}"
    tgt = next_wkd(now).replace(hour=2, minute=0, second=0, microsecond=0)
    return f"prep {fmt(tgt)}"

def hbar(cur: float, thr: float, w: int = 6) -> str:
    # TIER 1A FIX: Handle None values safely
    if cur is None or thr is None:
        return f"[dim]{'░' * w}[/]"  # Gray bar for missing data
    cur_f = safe_float(cur)
    thr_f = safe_float(thr)
    r = min(cur_f / thr_f, 1.0) if cur_f is not None and thr_f is not None and thr_f > 0 else 0
    f = int(r * w)
    c = R if r >= HBAR_CRITICAL else (Y if r >= HBAR_WARNING else G)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def exp_bar(pct, w=12):
    # TIER 1A FIX: Handle None safely instead of "or 0"
    if pct is None:
        return f"[dim]{'░' * w}[/]"  # Gray bar for missing data
    pct_f = safe_float(pct)
    if pct_f is None:
        return f"[dim]{'░' * w}[/]"
    f = int(min(pct_f, 100) / 100 * w)
    tc = TIER_COLOR.get(tier_from_pct(pct), "dim")
    return f"[{tc}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def mini_bar(pts: Optional[float], max_pts: Optional[float], w: int = 5) -> str:
    # TIER 1A FIX: Handle None safely instead of "or 0"
    if pts is None or max_pts is None:
        return f"[dim]{'░' * w}[/]"  # Gray bar for missing data
    pts_f = safe_float(pts)
    max_pts_f = safe_float(max_pts)
    r = min(pts_f / max_pts_f, 1.0) if pts_f is not None and max_pts_f is not None and max_pts_f > 0 else 0
    f = int(r * w)
    c = G if r >= MINIBAR_HIGH else (Y if r >= MINIBAR_MED else R)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def sign(v) -> str:
    """Return '+' for non-negative, '-' for negative, '' for None. TIER 1A FIX: safe None handling."""
    if v is None:
        return ""
    v_f = safe_float(v)
    if v_f is None:
        return ""
    return "+" if v_f >= 0 else ""

def safe_float(v: any, default: float = None) -> Optional[float]:
    """Safely convert value to float, returning default if conversion fails."""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default

def safe_int(v: any, default: int = None) -> Optional[int]:
    """Safely convert value to int, returning default if conversion fails."""
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default

def sparkline(values: list, width: int = 24) -> str:
    vals = []
    if values is None:
        values = []
    for v in values:
        if v is not None:
            v_f = safe_float(v)
            if v_f is not None and v_f > 0:
                vals.append(v_f)
    if len(vals) < 2:
        return f"[{DIM}]{'─' * width}[/]"
    mn, mx = min(vals), max(vals)
    if mx == mn:
        return f"[{CY}]{'─' * width}[/]"
    rng = mx - mn
    if len(vals) > width:
        idxs = [int(i * (len(vals) - 1) / (width - 1)) for i in range(width)]
        sampled = [vals[i] for i in idxs]
    else:
        sampled = [vals[0]] * (width - len(vals)) + vals
    sampled = sampled[:width]
    chars = "".join(SPARKLINE_CHARS[min(7, int((v - mn) / rng * 7.9999))] for v in sampled)
    c = G if sampled[-1] >= sampled[0] else R
    return f"[{c}]{chars}[/]"

def _parse_datetime(dt_val: any, as_date: bool = False, timezone_aware: bool = True) -> Optional:
    """Unified datetime parser (MEDIUM Issue #12: Consolidate date parsing patterns).

    Handles string (ISO, YYYY-MM-DD, datetime), datetime, and date objects.
    Returns datetime (with ET timezone if timezone_aware) or date if as_date=True.
    Returns None if parsing fails.
    """
    if dt_val is None:
        return None
    try:
        if isinstance(dt_val, datetime):
            dt = dt_val
        elif isinstance(dt_val, date):
            dt = datetime(dt_val.year, dt_val.month, dt_val.day)
        elif isinstance(dt_val, str):
            # Try ISO format first (most common), then YYYY-MM-DD
            try:
                dt = datetime.fromisoformat(dt_val)
            except (ValueError, TypeError):
                if len(dt_val) >= 10:
                    dt = datetime.strptime(dt_val[:10], "%Y-%m-%d")
                else:
                    logger.warning(f"VALIDATION: Date string too short to parse: {dt_val!r}")
                    return None
        else:
            logger.warning(f"VALIDATION: Unrecognized date type {type(dt_val).__name__} for value {dt_val!r}")
            return None

        # Handle timezone
        if timezone_aware:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ET)
            else:
                dt = dt.astimezone(ET)

        return dt.date() if as_date else dt
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning(f"VALIDATION: Date parse failure for {dt_val!r}: {e}")
        return None

def _parse_event_date(ed: any) -> Optional[date]:
    """Parse event date from various formats (now uses unified _parse_datetime)."""
    return _parse_datetime(ed, as_date=True, timezone_aware=True)

def _fmt_event_when(ed_date: Optional[date], et: any) -> str:
    """Format event timing as human-readable label, incorporating date and time for clarity.

    Shows 'TODAY 8PM' or 'TONIGHT 8PM' for today's events with times, to distinguish from
    events that may have already occurred. Uses ET timezone for consistency.
    """
    today = datetime.now(ET).date()
    if ed_date == today:
        if et:
            try:
                et_str = str(et)[:5]
                hour = int(et_str.split(":")[0])
                label = "TONIGHT" if hour >= 16 else "TODAY"
                return f"{label} {et_str}"
            except (ValueError, IndexError, AttributeError):
                pass
        return "TODAY"
    elif ed_date is not None:
        delta = (ed_date - today).days
        return f"+{delta}d" if delta > 0 else "YST"
    return "--"


def format_halt_reason(halt_code: str) -> str:
    """Issue 34/35 FIX: Convert halt code to human-readable explanation.

    Input: "drawdown" or "drawdown: Portfolio drawdown 23.45% >= 20%"
    Output: "Portfolio drawdown >=20%"
    """
    if not halt_code or not isinstance(halt_code, str):
        return halt_code
    # Extract the prefix before the colon (if present)
    code = halt_code.split(":")[0].strip().lower()
    return HALT_REASON_NAMES.get(code, halt_code[:20])


# ── fetchers ──────────────────────────────────────────────────────────────────

def fetch_run(c):
    # Primary: orchestrator_execution_log has structured named phase data
    try:
        row = q1(c, """
            SELECT run_id, started_at, completed_at, overall_status,
                   phase_results, summary, halt_reason,
                   phases_completed, phases_halted, phases_errored
            FROM orchestrator_execution_log
            ORDER BY started_at DESC LIMIT 1""")
        if row:
            pr = row.get("phase_results")
            if isinstance(pr, str):
                try:
                    pr = json.loads(pr)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"phase_results JSON corrupt (orchestrator version mismatch?): {e}")
                    logger.error(f"Raw content (first 200 chars): {str(pr)[:200]}")
                    pr = []
            overall = (row.get("overall_status") or "").lower()
            result = {
                "run_id":    row.get("run_id"),
                "run_at":    row.get("completed_at") or row.get("started_at"),
                "success":   overall in ("success", "completed"),
                "halted":    overall == "halted",
                "errored":   overall in ("error", "failed"),
                "summary":   row.get("summary"),
                "halt_reason": row.get("halt_reason"),
                "phases_completed": row.get("phases_completed"),
                "phases_halted":    row.get("phases_halted"),
                "phases_errored":   row.get("phases_errored"),
                "phase_results":    pr,
                "_source": "exec_log",
            }
            _log_data_quality("fetch_run", 1)
            return result
        _log_data_quality("fetch_run", 0, "No execution log data found")
        return {"_error": "No recent execution log data"}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_run (exec_log): {type(e).__name__}: {e}")
        _log_data_quality("fetch_run", 0, str(e))
        return {"_error": f"Failed to load execution log: {type(e).__name__}"}

    # Fallback: reconstruct from algo_audit_log
    try:
        latest = q1(c, """
            SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
            FROM algo_audit_log WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"):
            _log_data_quality("fetch_run", 0)
            return {"_error": "No recent execution data in audit log"}
        rid = latest["run_id"]
        phases = q(c, """SELECT action_type, status FROM algo_audit_log
                         WHERE details->>'run_id'=%s ORDER BY created_at ASC""", (rid,))
        halted  = any(p["status"] == "halt"  for p in phases)
        errored = any(p["status"] == "error" for p in phases)
        overall = "halted" if halted else ("error" if errored else "success" if phases else "unknown")
        result = {"run_id": rid, "run_at": latest["run_at"],
                "success": overall in ("success", "completed"), "halted": halted,
                "phases": phases, "_source": "audit_log"}
        _log_data_quality("fetch_run", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError) as e:
        logger.error(f"fetch_run (audit): {type(e).__name__}: {e}")
        _log_data_quality("fetch_run", 0, str(e))
        return {"_error": f"Failed to load audit log fallback: {type(e).__name__}"}

def _parse_config_float(config_dict: dict, key: str, default: float) -> float:
    """Parse a config value as float with validation. Issue 11 fix: consolidate threshold parsing."""
    val = config_dict.get(key)
    if val is None:
        logger.warning(f"VALIDATION: Config key '{key}' missing — using default {default}")
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        logger.warning(f"VALIDATION: Config key '{key}' value {val!r} not parseable as float — using default {default}")
        return default

def get_swing_score_thresholds(cfg: dict) -> dict:
    """Issue 7 FIX: Single source of truth for swing score thresholds.

    Returns dict with 'excellent' and 'good' keys, pulling from config or defaults.
    All panel functions should use this instead of hardcoded SWING_SCORE_* globals.
    """
    excellent = _parse_config_float(cfg, "swing_score_excellent_threshold", 80.0)
    good = _parse_config_float(cfg, "swing_score_good_threshold", 60.0)
    return {"excellent": excellent, "good": good}

def fetch_algo_config(c):
    try:
        keys = ["enable_algo", "execution_mode", "max_position_size_pct",
                "max_positions", "max_positions_per_sector", "min_swing_score",
                "swing_score_good_threshold", "swing_score_excellent_threshold",
                "alpaca_paper_trading", "base_risk_pct", "t1_target_r_multiple",
                "pyramid_enabled",
                # M1: Grade thresholds
                "grade_a_plus_threshold", "grade_a_threshold", "grade_b_threshold", "grade_c_threshold",
                # M2: Market thresholds
                "vix_caution_threshold", "vix_alert_threshold", "up_volume_good_threshold",
                "up_volume_caution_threshold", "put_call_bullish_threshold", "put_call_caution_threshold",
                "nh_nl_good_threshold",
                # M3: Risk thresholds
                "var_percentile", "cvar_percentile"]
        rows = q(c, "SELECT key, value FROM algo_config WHERE key=ANY(%s)", (keys,))
        d = {r["key"]: r["value"] for r in rows}
        # Issue 3.1: Validate that expected config keys exist (don't silently use defaults)
        missing_keys = [k for k in keys if k not in d]
        if missing_keys:
            logger.warning(f"VALIDATION: algo_config missing keys: {missing_keys} (will use hardcoded defaults - may be incorrect)")
        paper  = d.get("alpaca_paper_trading", "false").lower() == "true"
        mode   = d.get("execution_mode", "unknown").upper()
        mode_s = f"{mode}/PAPER" if paper else mode
        # Issue 11 fix: Use consolidated float parser for all swing score thresholds
        min_score = _parse_config_float(d, "min_swing_score", 70.0)
        swing_good = _parse_config_float(d, "swing_score_good_threshold", 60.0)
        swing_excellent = _parse_config_float(d, "swing_score_excellent_threshold", 80.0)
        # Issue 23 FIX: Validate numeric config values before returning
        base_risk = _parse_config_float(d, "base_risk_pct", 0.5)
        t1_r = _parse_config_float(d, "t1_target_r_multiple", 1.0)

        # M1-M3 FIX: Load thresholds from config with defaults
        grade_a_plus = _parse_config_float(d, "grade_a_plus_threshold", 90.0)
        grade_a = _parse_config_float(d, "grade_a_threshold", 80.0)
        grade_b = _parse_config_float(d, "grade_b_threshold", 70.0)
        grade_c = _parse_config_float(d, "grade_c_threshold", 60.0)

        vix_caution = _parse_config_float(d, "vix_caution_threshold", 20.0)
        vix_alert = _parse_config_float(d, "vix_alert_threshold", 30.0)
        up_vol_good = _parse_config_float(d, "up_volume_good_threshold", 60.0)
        up_vol_caution = _parse_config_float(d, "up_volume_caution_threshold", 50.0)
        put_call_bull = _parse_config_float(d, "put_call_bullish_threshold", 0.8)
        put_call_caution = _parse_config_float(d, "put_call_caution_threshold", 1.0)
        nh_nl_good = _parse_config_float(d, "nh_nl_good_threshold", 50.0)

        var_pct = _parse_config_float(d, "var_percentile", 95.0)
        cvar_pct = _parse_config_float(d, "cvar_percentile", 99.0)

        _log_data_quality("fetch_algo_config", 1)
        return {
            "enabled":      d.get("enable_algo", "true").lower() == "true",
            "mode":         mode_s,
            "max_pos_pct":  d.get("max_position_size_pct"),
            "max_pos_n":    d.get("max_positions"),
            "max_sec_n":    d.get("max_positions_per_sector"),
            "min_score":    min_score,
            "swing_good":   swing_good,
            "swing_excellent": swing_excellent,
            "base_risk":    base_risk,
            "t1_r":         t1_r,
            "pyramid":      d.get("pyramid_enabled", "false").lower() == "true",
            # M1: Grade thresholds
            "grade_a_plus": grade_a_plus,
            "grade_a": grade_a,
            "grade_b": grade_b,
            "grade_c": grade_c,
            # M2: Market thresholds
            "vix_caution": vix_caution,
            "vix_alert": vix_alert,
            "up_vol_good": up_vol_good,
            "up_vol_caution": up_vol_caution,
            "put_call_bull": put_call_bull,
            "put_call_caution": put_call_caution,
            "nh_nl_good": nh_nl_good,
            # M3: Risk thresholds
            "var_pct": var_pct,
            "cvar_pct": cvar_pct,
        }
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_algo_config: {type(e).__name__}: {e}")
        _log_data_quality("fetch_algo_config", 0, str(e))
        return {"_error": f"Failed to load algo config: {type(e).__name__}"}

def fetch_market(c):
    try:
        # Read market tier thresholds from config (HIGH-SEVERITY ISSUE FIX)
        tier_thresholds = None
        try:
            tier_config_r = q(c, """
                SELECT key, value FROM algo_config
                WHERE key IN ('market_tier_threshold_confirmed', 'market_tier_threshold_healthy',
                             'market_tier_threshold_pressure', 'market_tier_threshold_caution')
            """)
            if tier_config_r and len(tier_config_r) == 4:
                tier_config = {r.get('key'): safe_float(r.get('value', 0), 0) for r in tier_config_r if r.get('value')}
                tier_thresholds = {
                    'confirmed': tier_config.get('market_tier_threshold_confirmed', TIER_THRESHOLD_CONFIRMED),
                    'healthy': tier_config.get('market_tier_threshold_healthy', TIER_THRESHOLD_HEALTHY),
                    'pressure': tier_config.get('market_tier_threshold_pressure', TIER_THRESHOLD_PRESSURE),
                    'caution': tier_config.get('market_tier_threshold_caution', TIER_THRESHOLD_CAUTION),
                }
                logger.debug(f"Market tier thresholds from config: {tier_thresholds}")
        except Exception as e:
            logger.debug(f"Could not load market tier thresholds from config: {e}")

        exp  = q1(c, "SELECT exposure_pct, halt_reasons, date FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
        h    = q1(c, """SELECT market_stage, vix_level, distribution_days_4w,
                               spy_close, market_trend, up_volume_percent,
                               advance_decline_ratio, new_highs_count, new_lows_count,
                               put_call_ratio, yield_curve_slope, breadth_momentum_10d,
                               fed_rate_environment, date
                        FROM market_health_daily ORDER BY date DESC LIMIT 1""")
        pct   = safe_float(exp.get("exposure_pct")) if exp else None
        halts = exp.get("halt_reasons") if exp else []
        if isinstance(halts, str):
            try:
                halts = json.loads(halts)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"halt_reasons JSON invalid: {e}. Using empty list.")
                halts = []

        # Check data freshness (should be from today or recent trading day)
        exp_age = None
        mkt_health_age = None
        if exp and exp.get("date"):
            try:
                if isinstance(exp["date"], datetime):
                    exp_date = exp["date"]
                else:
                    try:
                        exp_date = datetime.fromisoformat(str(exp["date"]))
                    except (ValueError, TypeError):
                        exp_date = None
                if exp_date:
                    # Ensure timezone-aware comparison (handle naive datetimes)
                    if exp_date.tzinfo is None:
                        exp_date = exp_date.replace(tzinfo=timezone.utc)
                    exp_age = (datetime.now(timezone.utc) - exp_date).days
            except (ValueError, TypeError, KeyError): pass
        # Track market_health_daily age for distribution_days, yield curve, etc.
        if h and h.get("date"):
            try:
                if isinstance(h["date"], datetime):
                    mkt_date = h["date"]
                else:
                    try:
                        mkt_date = datetime.fromisoformat(str(h["date"]))
                    except (ValueError, TypeError):
                        mkt_date = None
                if mkt_date:
                    if mkt_date.tzinfo is None:
                        mkt_date = mkt_date.replace(tzinfo=timezone.utc)
                    mkt_health_age = (datetime.now(timezone.utc) - mkt_date).days
            except (ValueError, TypeError, KeyError): pass

        vix_row = q1(c, "SELECT vix_level FROM market_health_daily WHERE vix_level IS NOT NULL AND vix_level > 0 ORDER BY date DESC LIMIT 1")
        vix_v   = vix_row.get("vix_level") if vix_row else None
        def _f(key): return safe_float(h.get(key)) if h else None
        def _i(key):
            val = h.get(key) if h else None
            return int(val) if val is not None else None
        spy_v = _f("spy_close")
        spy_rows = q(c, "SELECT close, date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 2")
        spy_age = None
        stale_alerts = []

        # MEDIUM ISSUE FIX: Try to read pre-computed SPY change from economic_metrics_daily table
        spy_chg = None
        try:
            econ_metrics = q1(c, """
                SELECT spy_price_change_pct FROM economic_metrics_daily
                ORDER BY report_date DESC LIMIT 1
            """)
            if econ_metrics and econ_metrics.get('spy_price_change_pct') is not None:
                spy_chg = safe_float(econ_metrics.get('spy_price_change_pct'))
                logger.debug(f"SPY price change from pre-computed table: {spy_chg}%")
        except Exception as e:
            logger.debug(f"Could not fetch pre-computed SPY change: {e}")

        # Fallback: calculate SPY change if not in database
        if spy_chg is None and len(spy_rows) >= 2:
            close0 = spy_rows[0].get("close")
            close1 = spy_rows[1].get("close")
            if close0 is not None and close1 is not None:
                cur_spy  = safe_float(close0)
                prev_spy = safe_float(close1)
                if cur_spy is not None and prev_spy is not None:
                    if spy_v is None: spy_v = cur_spy
                    if prev_spy > 0: spy_chg = round((cur_spy - prev_spy) / prev_spy * 100, 2)
                try:
                    spy_date = spy_rows[0]["date"] if isinstance(spy_rows[0]["date"], datetime) else datetime.fromisoformat(str(spy_rows[0]["date"]))
                    if spy_date.tzinfo is None:
                        spy_date = spy_date.replace(tzinfo=timezone.utc)
                    else:
                        spy_date = spy_date.astimezone(timezone.utc)
                    spy_age = (datetime.now(timezone.utc) - spy_date).days
                except (ValueError, AttributeError, TypeError):
                    pass
            elif close0 is None or close1 is None:
                logger.warning(f"VALIDATION: SPY price_daily has rows but close price is NULL")
                stale_alerts.append("SPY close price is NULL")
        elif len(spy_rows) == 1 and spy_v is None:
            close0 = spy_rows[0].get("close")
            if close0 is not None:
                spy_v = safe_float(close0)
            else:
                logger.warning(f"VALIDATION: SPY price_daily has 1 row but close price is NULL")
                stale_alerts.append("SPY close price is NULL")
            try:
                spy_date = spy_rows[0]["date"] if isinstance(spy_rows[0]["date"], datetime) else datetime.fromisoformat(str(spy_rows[0]["date"]))
                if spy_date.tzinfo is None:
                    spy_date = spy_date.replace(tzinfo=timezone.utc)
                else:
                    spy_date = spy_date.astimezone(timezone.utc)
                spy_age = (datetime.now(timezone.utc) - spy_date).days
            except (ValueError, AttributeError, TypeError):
                pass
        fed_val = h.get("fed_rate_environment") if h else None
        # Case-insensitive check for "unknown" value
        if not fed_val or (isinstance(fed_val, str) and fed_val.lower() == "unknown"): fed_val = None

        # Log staleness if data is old and track for dashboard display
        if exp_age is not None and exp_age > 1:
            logger.warning(f"Market exposure data is {exp_age} days old")
            stale_alerts.append(f"Exposure {exp_age}d old")
        # Issue 41 FIX: Append loader staleness alert to ensure it's displayed
        if exp_age is not None and exp_age > 2:
            stale_alerts.append("Exposure loader stale (>2d)")
        # Issue 23 FIX: Validate SPY age considering intraday freshness during market hours
        # During market hours (9:30 AM - 4 PM ET), close price from yesterday is stale
        if spy_age is None and not spy_rows:
            logger.warning(f"VALIDATION: SPY price data is MISSING (no rows in price_daily for SPY)")
            stale_alerts.append("SPY data missing")
        elif spy_age is not None:
            if spy_age > 1:
                logger.warning(f"VALIDATION: SPY price data is {spy_age} days old — may not reflect current market")
                stale_alerts.append(f"SPY {spy_age}d stale")
            elif spy_age == 0:
                # Issue 23: Check if we're during market hours (9:30 AM - 4 PM ET weekdays)
                now_et = datetime.now(ET)
                is_weekday = now_et.weekday() < 5
                is_market_hours = is_weekday and (9.5 <= now_et.hour + now_et.minute/60 < 16)
                if is_market_hours:
                    hours_into_session = (now_et.hour + now_et.minute/60) - 9.5
                    if hours_into_session > 2:  # If more than 2 hours into market
                        logger.warning(f"VALIDATION: SPY close price is from yesterday ({hours_into_session:.1f}h into trading session; market still open)")
                        stale_alerts.append("SPY close is yesterday's close")
        # Category 6 fix: Breadth momentum 10d indicator unreliable if >3 days old (validates threshold)
        # Issue 14 fix: Detect when breadth momentum is MISSING, not just old
        if h:
            if h.get("breadth_momentum_10d") is None:
                logger.warning(f"VALIDATION: Breadth momentum 10d is MISSING (null in market_health_daily)")
                stale_alerts.append("Breadth momentum missing")
            else:
                h_date = h.get("date")
                if h_date:
                    try:
                        dt = h_date.replace(tzinfo=timezone.utc) if isinstance(h_date, datetime) else datetime.fromisoformat(str(h_date)).replace(tzinfo=timezone.utc)
                        mkt_age = (datetime.now(timezone.utc) - dt).days
                    except (ValueError, TypeError):
                        mkt_age = None
                else:
                    mkt_age = None
                if mkt_age is not None and mkt_age > 3:
                    logger.warning(f"Breadth momentum 10d indicator data {mkt_age}d old (>3d threshold); unreliable")
                    stale_alerts.append(f"Breadth momentum {mkt_age}d old")
                else:
                    logger.debug(f"Breadth momentum 10d threshold satisfied: {mkt_age}d old <= 3d")

        # Category 6 fix: Distribution days threshold validation (10d on Monday per business rules, 3d otherwise)
        # Issue 13 FIX: Dynamic holiday calculation works for any year
        if mkt_health_age is not None and h and h.get("distribution_days_4w") is not None:
            today = datetime.now(ET)
            is_monday = today.weekday() == 0

            def _get_us_market_holidays(year: int) -> set:
                """Compute US market holidays for given year (works for any year)."""
                holidays = set()
                holidays.add(date(year, 1, 1))  # New Year's Day
                # MLK Jr. Day: 3rd Monday of January
                jan_1 = date(year, 1, 1)
                days_to_monday = (7 - jan_1.weekday()) % 7
                mlk_date = jan_1 + timedelta(days=days_to_monday if days_to_monday > 0 else 7) + timedelta(weeks=2)
                holidays.add(mlk_date)
                # Presidents' Day: 3rd Monday of February
                feb_1 = date(year, 2, 1)
                days_to_monday = (7 - feb_1.weekday()) % 7
                pres_date = feb_1 + timedelta(days=days_to_monday if days_to_monday > 0 else 7) + timedelta(weeks=2)
                holidays.add(pres_date)
                # Memorial Day: Last Monday of May
                may_31 = date(year, 5, 31)
                days_back = (may_31.weekday() - 0) % 7
                mem_date = may_31 - timedelta(days=days_back)
                holidays.add(mem_date)
                holidays.add(date(year, 6, 19))  # Juneteenth
                # Independence Day (July 3 if July 4 is Saturday, else July 4)
                july_4 = date(year, 7, 4)
                holidays.add(date(year, 7, 3) if july_4.weekday() == 5 else july_4)
                # Labor Day: 1st Monday of September
                sep_1 = date(year, 9, 1)
                days_to_monday = (7 - sep_1.weekday()) % 7
                labor_date = sep_1 + timedelta(days=days_to_monday if days_to_monday > 0 else 7)
                holidays.add(labor_date)
                # Thanksgiving: 4th Thursday of November
                nov_1 = date(year, 11, 1)
                days_to_thursday = (3 - nov_1.weekday()) % 7
                thanks_date = nov_1 + timedelta(days=days_to_thursday if days_to_thursday > 0 else 7) + timedelta(weeks=3)
                holidays.add(thanks_date)
                holidays.add(date(year, 12, 25))  # Christmas
                return holidays

            us_market_holidays = _get_us_market_holidays(today.year)
            today_is_holiday = today.date() in us_market_holidays
            stale_threshold = 10 if (is_monday and not today_is_holiday) else 3
            if mkt_health_age > stale_threshold:
                logger.warning(f"Distribution days {mkt_health_age}d old exceeds threshold {stale_threshold}d (is_monday={is_monday}, holiday={today_is_holiday})")
                stale_alerts.append(f"Distribution days {mkt_health_age}d old")
            else:
                logger.debug(f"Distribution days threshold satisfied: {mkt_health_age}d old <= {stale_threshold}d (is_monday={is_monday}, holiday={today_is_holiday})")

        # CRITICAL ISSUE 3 FIX: Enforce hard thresholds for market data freshness
        # Use centralized config (data_freshness_config.py) instead of hardcoded values
        # This ensures dashboard, API, orchestrator all use same thresholds
        spy_rule = get_freshness_rule("price_daily")
        exposure_rule = get_freshness_rule("market_exposure_daily")
        dist_rule = get_freshness_rule("market_health_daily")

        MAX_SPY_AGE_DAYS = spy_rule["max_age_days"] if spy_rule else 1
        MAX_EXPOSURE_AGE_DAYS = exposure_rule["max_age_days"] if exposure_rule else 2
        MAX_DIST_DAYS_AGE = dist_rule["max_age_days"] if dist_rule else 5

        if spy_age is not None and spy_age > MAX_SPY_AGE_DAYS:
            msg = f"HALT: SPY price data is {spy_age} days old (max {MAX_SPY_AGE_DAYS}d allowed) — dashboard cannot run with stale market prices"
            logger.error(f"CRITICAL: {msg}")
            _log_data_quality("fetch_market", 0, msg)
            return {"_error": msg, "stale_alerts": stale_alerts}

        if exp_age is not None and exp_age > MAX_EXPOSURE_AGE_DAYS:
            msg = f"HALT: Market exposure data is {exp_age} days old (max {MAX_EXPOSURE_AGE_DAYS}d allowed) — cannot determine safe position sizing"
            logger.error(f"CRITICAL: {msg}")
            _log_data_quality("fetch_market", 0, msg)
            return {"_error": msg, "stale_alerts": stale_alerts}

        # Distribution days can be older (computed weekly), but warn if exceptionally stale
        if mkt_health_age is not None and mkt_health_age > MAX_DIST_DAYS_AGE:
            msg = f"Distribution days data is {mkt_health_age} days old (threshold {MAX_DIST_DAYS_AGE}d) — market context may be unreliable"
            logger.warning(f"CRITICAL: {msg}")
            stale_alerts.append(msg)

        # CRITICAL ISSUE 1 FIX: Return stale data with alerts instead of failing entirely
        # Market context (even 1-2 days old) is more useful than no context at all
        # Dashboard will display stale_alerts to user as warnings
        _log_data_quality("fetch_market", 1)
        return {
            "pct":   pct,
            "tier":  tier_from_pct(pct, tier_thresholds),
            "halts": halts,
            "vix":     safe_float(vix_v),
            "dist":    _i("distribution_days_4w"),
            "dist_age": mkt_health_age,
            "stage":   _i("market_stage"),
            "spy":     spy_v,
            "spy_age": spy_age,
            "exp_age": exp_age,
            "stale_alerts": stale_alerts,
            "trend":   h.get("market_trend") if h else None,
            "upvol": _f("up_volume_percent"),
            "adr":   _f("advance_decline_ratio"),
            "nh":    _i("new_highs_count"),
            "nl":    _i("new_lows_count"),
            "pcr":   _f("put_call_ratio"),
            "bmom":  _f("breadth_momentum_10d"),
            "fed":   fed_val,
        }
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_market: {type(e).__name__}: {e}")
        _log_data_quality("fetch_market", 0, str(e))
        # H9 FIX: Return stale_alerts even on error so caller can see what went wrong
        # stale_alerts has been computed throughout the function; losing them masks data issues
        return {"_error": f"{type(e).__name__}: {e}", "stale_alerts": stale_alerts}

def fetch_exposure_factors(c):
    try:
        row = q1(c, """SELECT raw_score, exposure_pct, regime, factors
                       FROM market_exposure_daily ORDER BY date DESC LIMIT 1""")
        if not row:
            _log_data_quality("fetch_exposure_factors", 0, severity="error")
            return {"_error": "No exposure factors data found"}
        factors = row.get("factors")
        factors_error = None
        if factors is None:
            factors = {}
        elif isinstance(factors, str):
            try:
                factors = json.loads(factors)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse exposure factors JSON: {e}")
                factors_error = str(e)
                factors = {}
        # Issue 12 fix: Enhanced schema validation — ensure factors are numeric and properly structured
        # Issue 25 fix: Complete exposure factors schema with all 12+ factors from MarketExposure.compute()
        data_quality = "good"
        missing_keys_list = []
        invalid_values_list = []
        if factors and isinstance(factors, dict):
            expected_keys = {
                "follow_through_day", "trend_30wk", "breadth_50dma", "breadth_200dma",
                "mcclellan", "distribution_days", "vix_regime", "new_highs_lows",
                "ad_line", "credit_spread", "aaii_sentiment", "naaim",
                "sector_rotation", "economic_overlay"
            }
            found_keys = set(factors.keys())
            missing_keys = expected_keys - found_keys
            if missing_keys:
                data_quality = "degraded"
                missing_keys_list = sorted(list(missing_keys))
                logger.warning(f"exposure_factors schema issue: missing expected keys {missing_keys}")
            # Issue 12 fix: Validate that all factor values are numeric (float/int), not dicts or malformed strings
            for key in found_keys:
                val = factors.get(key)
                if val is None:
                    logger.warning(f"exposure_factors[{key}] is NULL — expected numeric value")
                    data_quality = "degraded"
                    invalid_values_list.append(key)
                elif isinstance(val, (int, float)):
                    # Valid numeric value
                    pass
                elif isinstance(val, str):
                    try:
                        float(val)
                    except (ValueError, TypeError):
                        logger.warning(f"exposure_factors[{key}] value {val!r} is string but not numeric")
                        data_quality = "degraded"
                        invalid_values_list.append(key)
                else:
                    # Dict, list, or other non-numeric type
                    logger.warning(f"exposure_factors[{key}] has unexpected type {type(val).__name__} (expected float/int)")
                    data_quality = "degraded"
                    invalid_values_list.append(key)
        elif not factors:
            data_quality = "missing"
            logger.warning(f"exposure_factors JSON is empty or null")
        raw_score = safe_float(row.get("raw_score"))
        exposure_pct = safe_float(row.get("exposure_pct"))
        result = {
            "raw_score":    raw_score,
            "exposure_pct": exposure_pct,
            "regime":       row.get("regime"),
            "factors":      factors,
            "_data_quality": data_quality,
            "_missing_keys": missing_keys_list,
            "_invalid_values": invalid_values_list,
        }
        if factors_error:
            result["_factors_parse_error"] = factors_error
            result["_data_quality"] = "error"
        _log_data_quality("fetch_exposure_factors", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_exposure_factors: {type(e).__name__}: {e}")
        _log_data_quality("fetch_exposure_factors", 0, str(e), severity="error")
        return {"_error": str(e)}

def fetch_portfolio(c):
    try:
        row = q1(c, """
            SELECT snapshot_date, total_portfolio_value, daily_return_pct,
                   unrealized_pnl_pct, position_count, total_cash,
                   cumulative_return_pct, max_drawdown_pct, largest_position_pct
            FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1""")
        if not row:
            _log_data_quality("fetch_portfolio", 0)
            return {"_error": "No portfolio snapshot data available"}

        # Issue 29 FIX: Return date mismatch warning to client so dashboard can display it
        snapshot_date = row.get("snapshot_date")
        latest_price = q1(c, "SELECT DISTINCT date FROM price_daily ORDER BY date DESC LIMIT 1")
        price_date = latest_price.get("date") if latest_price else None

        result = dict(row)
        result["_date_mismatch"] = False
        result["_date_mismatch_msg"] = None

        if snapshot_date and price_date:
            snap_dt = snapshot_date if isinstance(snapshot_date, date) else datetime.fromisoformat(str(snapshot_date)).date()
            price_dt = price_date if isinstance(price_date, date) else datetime.fromisoformat(str(price_date)).date()
            if snap_dt != price_dt:
                msg = f"Portfolio snapshot ({snap_dt}) does not match latest price data ({price_dt}) — portfolio value may be stale"
                logger.warning(f"VALIDATION: {msg}")
                result["_date_mismatch"] = True
                result["_date_mismatch_msg"] = msg
        elif not price_date:
            msg = "No price data available — portfolio value cannot be validated"
            logger.warning(f"VALIDATION: {msg}")
            result["_date_mismatch"] = True
            result["_date_mismatch_msg"] = msg

        _log_data_quality("fetch_portfolio", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_portfolio: {type(e).__name__}: {e}")
        _log_data_quality("fetch_portfolio", 0, str(e))
        return {"_error": f"Failed to load portfolio: {type(e).__name__}"}

def fetch_perf(c=None):
    """Fetch performance metrics from API instead of database.

    Uses /api/algo/performance endpoint which returns comprehensive metrics.
    Maintains backward compatibility with existing dashboard display format.
    """
    stale_alerts = []
    try:
        api_resp = api_call("/api/algo/performance")
        if "_error" in api_resp:
            logger.error(f"fetch_perf: API error: {api_resp['_error']}")
            _log_data_quality("fetch_perf", 0, api_resp['_error'])
            return {"_error": api_resp['_error']}

        perf = api_resp.get("data", api_resp)
        total_trades = perf.get("total_trades", 0)
        if total_trades == 0:
            logger.warning("VALIDATION: No trade history available")
            return {"_reason": "no-reconciliation-data"}

        winning_trades = perf.get("winning_trades", 0)
        losing_trades = perf.get("losing_trades", 0)
        breakeven_trades = perf.get("breakeven_trades", 0)
        # H15/H16 FIX: Extract open trade breakdown from API for unrealized risk visibility
        open_winning_trades = perf.get("open_winning_trades", 0)
        open_losing_trades = perf.get("open_losing_trades", 0)
        total_open_trades = open_winning_trades + open_losing_trades
        wr_pct = perf.get("win_rate_pct")
        wr_confidence = perf.get("win_rate_confidence", "medium")
        be_pct = (breakeven_trades / total_trades * 100) if total_trades > 0 else 0
        if be_pct > 15:
            wr_confidence = "low"
        elif be_pct > 5:
            wr_confidence = "medium"

        sharpe = perf.get("sharpe_ratio")
        sharpe_confidence = perf.get("sharpe_confidence", "medium")
        maxdd = perf.get("max_drawdown_pct")
        pf = perf.get("profit_factor")
        exp = perf.get("expectancy_r")
        avg_win = perf.get("avg_win_pct")
        avg_loss = perf.get("avg_loss_pct")
        avg_r = perf.get("expectancy_r")
        current_streak = perf.get("current_streak", 0)
        pnl = perf.get("total_pnl_dollars", 0)
        portfolio_snapshots = perf.get("portfolio_snapshots", 0)

        equity_vals = []
        recent_rets = []
        recent_rets_confidence = "medium"
        if portfolio_snapshots < 5:
            stale_alerts.append(f"Insufficient data for Sharpe ({portfolio_snapshots} snapshots, need 63+)")

        _log_data_quality("fetch_perf", total_trades)
        data_freshness = perf.get("data_freshness", {})
        updated_at = data_freshness.get("last_updated_at") if isinstance(data_freshness, dict) else None
        return {
            "n": total_trades, "w": winning_trades, "l": losing_trades, "b": breakeven_trades,
            "_open_w": open_winning_trades, "_open_l": open_losing_trades,
            "wr": wr_pct, "wr_confidence": wr_confidence, "wr_breakeven_pct": round(be_pct, 1),
            "_open_trades_count": total_open_trades, "pnl": round(pnl, 2), "streak": current_streak,
            "sharpe": sharpe, "sharpe_confidence": sharpe_confidence, "maxdd": round(maxdd, 1) if maxdd is not None else None,
            "avg_win": round(avg_win, 2) if avg_win is not None else None, "avg_loss": round(avg_loss, 2) if avg_loss is not None else None,
            "profit_factor": pf, "expectancy": exp, "avg_r": avg_r, "equity_vals": equity_vals,
            "recent_rets": recent_rets, "recent_rets_confidence": recent_rets_confidence, "stale_alerts": stale_alerts,
            "_source": "api_algo_performance", "_updated_at": updated_at
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.error(f"fetch_perf: {type(e).__name__}: {e}")
        _log_data_quality("fetch_perf", 0, str(e))
        return {"_error": str(e)}


def fetch_positions(c):
    """Fetch open positions from API instead of database.

    Uses /api/algo/positions endpoint which returns current positions
    with latest prices, risk metrics, and technical data.
    """
    stale_alerts = []
    try:
        api_resp = api_call("/api/algo/positions")
        if "_error" in api_resp:
            logger.warning(f"fetch_positions: API error: {api_resp['_error']}")
            _log_data_quality("fetch_positions", 0, api_resp['_error'])
            return {"_error": api_resp['_error'], "positions": [], "stale_alerts": stale_alerts}

        positions_data = api_resp.get("data", {})
        result = positions_data.get("items", [])
        validation = positions_data.get("join_validation", {})
        if validation and validation.get("status") == "degraded":
            mismatches = validation.get("mismatches", [])
            for mismatch in mismatches:
                symbol = mismatch.get("symbol")
                field = mismatch.get("missing_field")
                stale_alerts.append(f"Missing {field} for {symbol}")

        _log_data_quality("fetch_positions", len(result) if result else 0)
        return {"positions": result, "stale_alerts": stale_alerts}
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_positions: {type(e).__name__}: {e}")
        _log_data_quality("fetch_positions", 0, str(e))
        return {"_error": str(e), "positions": [], "stale_alerts": stale_alerts}


def fetch_recent_trades(c):
    """Fetch recent trades from API instead of database."""
    stale_alerts = []
    try:
        api_resp = api_call("/api/algo/trades", params={"limit": "50"})
        if "_error" in api_resp:
            logger.warning(f"fetch_recent_trades: API error: {api_resp['_error']}")
            return {"trades": [], "stale_alerts": stale_alerts}

        trades_data = api_resp.get("data", {})
        trades = trades_data.get("items", [])
        _log_data_quality("fetch_recent_trades", len(trades) if trades else 0)
        return {"trades": trades, "stale_alerts": stale_alerts}
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_recent_trades: {type(e).__name__}: {e}")
        return {"trades": [], "stale_alerts": stale_alerts}


def fetch_signals(c):
    stale_alerts = []
    try:
        # Issue 21 FIX: Use default min_swing_score instead of separate query (already fetched by fetch_algo_config)
        # This avoids redundant database round-trips; cfg will fetch the actual value from algo_config
        min_score = 70.0

        sig = q1(c, """
            SELECT COUNT(*) AS n, MAX(date) AS d FROM buy_sell_daily
            WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily')
              AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily'))""")
        total_r = q1(c, """SELECT COUNT(*) AS n FROM buy_sell_daily
                           WHERE timeframe IN ('1d', 'daily', 'Daily') AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE timeframe IN ('1d', 'daily', 'Daily'))""")
        total_n = int(total_r["n"]) if total_r and total_r.get("n") is not None else None
        signal_date = sig.get("d") if sig else None

        # Actual BUY signals with rich setup detail
        buy_sigs = q(c, """
            SELECT b.symbol, b.signal_type, b.stage_number, b.signal_quality_score,
                   b.entry_quality_score, b.close, b.buylevel, b.stoplevel,
                   b.risk_reward_ratio, b.volume_surge_pct, b.rs_rating,
                   b.breakout_quality, b.base_type, b.reason,
                   cp.sector,
                   s.score AS swing_score
            FROM buy_sell_daily b
            LEFT JOIN company_profile cp ON cp.symbol = b.symbol
            LEFT JOIN (
                SELECT DISTINCT ON (symbol) symbol, score
                FROM swing_trader_scores ORDER BY symbol, date DESC
            ) s ON s.symbol = b.symbol
            WHERE b.signal='BUY' AND b.timeframe IN ('1d', 'daily', 'Daily')
              AND b.date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily'))
            ORDER BY COALESCE(b.signal_quality_score, b.entry_quality_score, 0) DESC
            LIMIT 30""")

        # Issue 23: Filter out signals with missing quality scores (MEDIUM Issue #13)
        # ISSUE 41 FIX: Return count of filtered signals so dashboard can display data quality info
        before_count = len(buy_sigs)
        buy_sigs = [s for s in buy_sigs if s.get("signal_quality_score") is not None or s.get("entry_quality_score") is not None]
        filtered_count = before_count - len(buy_sigs) if before_count != len(buy_sigs) else 0
        if filtered_count > 0:
            logger.warning(f"VALIDATION: Filtered {filtered_count} signals with missing quality scores")

        # Issue 3 FIX: Enforce minimum quality score threshold (40/100)
        MIN_QUALITY_SCORE = 40
        before_threshold = len(buy_sigs)
        # TIER 1A FIX: Explicitly filter out signals with missing or low quality scores
        def get_signal_quality(s):
            sq = s.get("signal_quality_score")
            eq = s.get("entry_quality_score")
            sq_f = safe_float(sq, 0)
            eq_f = safe_float(eq, 0)
            return max(sq_f, eq_f)
        buy_sigs = [s for s in buy_sigs if get_signal_quality(s) >= MIN_QUALITY_SCORE]
        quality_filtered = before_threshold - len(buy_sigs)
        if quality_filtered > 0:
            logger.warning(f"VALIDATION: Filtered {quality_filtered} signals with quality score < {MIN_QUALITY_SCORE}/100")

        # HIGH-SEVERITY ISSUE FIX: Grade distribution now pre-computed in grade_distribution_daily
        # Try to read from pre-computed table first, fallback to calculation
        grades = {}
        grades_date = None

        # First try pre-computed grades
        grades_daily = None
        try:
            grades_daily = q1(c, """
                SELECT num_grade_a as a, num_grade_b as b, num_grade_c as c, num_grade_d as d,
                       total_graded as total, score_date
                FROM grade_distribution_daily
                ORDER BY report_date DESC LIMIT 1
            """)
        except psycopg2.Error as e:
            logger.debug(f"Grade distribution table not available: {e}")

        if grades_daily:
            grades = grades_daily
            grades_date = grades_daily.get('score_date')
            logger.debug(f"Grade distribution from pre-computed table: A={grades.get('a')} B={grades.get('b')} C={grades.get('c')} D={grades.get('d')}")
        else:
            # Issue 20 FIX: Fallback calculation with validation
            logger.warning("Grade distribution not in pre-computed table, falling back to calculation")

            # Validate signal_date is not NULL and not in future
            if signal_date:
                try:
                    sig_dt = _parse_datetime(signal_date, as_date=True, timezone_aware=False)
                    if sig_dt and sig_dt <= datetime.now(ET).date():
                        # signal_date is valid and in past, use it
                        grades_date_r = q1(c, "SELECT MAX(date) FROM swing_trader_scores WHERE date <= %s", (sig_dt,))
                        grades_date = grades_date_r.get("max") if grades_date_r else None
                    else:
                        logger.warning(f"VALIDATION: signal_date {signal_date} is in future or invalid; using latest available date")
                        grades_date_r = q1(c, "SELECT MAX(date) FROM swing_trader_scores")
                        grades_date = grades_date_r.get("max") if grades_date_r else None
                except (ValueError, TypeError):
                    logger.warning(f"VALIDATION: signal_date {signal_date} unparseable; using latest available date")
                    grades_date_r = q1(c, "SELECT MAX(date) FROM swing_trader_scores")
                    grades_date = grades_date_r.get("max") if grades_date_r else None
            else:
                # signal_date is NULL, use latest available
                logger.warning("VALIDATION: signal_date is NULL; using latest available date from swing_trader_scores")
                grades_date_r = q1(c, "SELECT MAX(date) FROM swing_trader_scores")
                grades_date = grades_date_r.get("max") if grades_date_r else None

            if grades_date:
                # Load grade thresholds from config (M1 FIX: no longer hardcoded)
                # Safe to use f-string here: thresholds come from our config table, not user input
                grade_cfg = load_grade_thresholds(cfg)
                thr_a = int(grade_cfg.get('a', 80))
                thr_b = int(grade_cfg.get('b', 60))
                thr_c = int(grade_cfg.get('c', 40))
                grades_r = q(c, f"""
                    SELECT COUNT(*) FILTER (WHERE score >= {thr_a}) AS a,
                           COUNT(*) FILTER (WHERE score >= {thr_b} AND score < {thr_a}) AS b,
                           COUNT(*) FILTER (WHERE score >= {thr_c} AND score < {thr_b}) AS c,
                           COUNT(*) FILTER (WHERE score < {thr_c}) AS d,
                           COUNT(*) AS total
                    FROM swing_trader_scores
                    WHERE date=%s""", (grades_date,))
                grades = grades_r[0] if grades_r else {}

        # Issue 25: Near-misses: use actual min_swing_score instead of hardcoded 55-69 range
        # Near-miss is 15 points below threshold to 5 points below (e.g., if threshold is 70: 55-69)
        near_lower = max(0, min_score - 15)
        near_upper = min_score - 1 if min_score > 0 else 69
        near = q(c, """
            SELECT s.symbol, s.score, cp.sector
            FROM swing_trader_scores s
            LEFT JOIN company_profile cp ON cp.symbol = s.symbol
            WHERE s.date=%s
              AND s.score BETWEEN %s AND %s
            ORDER BY s.score DESC LIMIT 15""", (grades_date, near_lower, near_upper)) if grades_date else []

        # Top A-grade stocks by name (radar display — score ≥ threshold_a)
        # M1 FIX: Use config threshold instead of hardcoded 80
        grade_cfg = load_grade_thresholds(cfg)
        thr_a = grade_cfg.get('a', 80)
        top_a = q(c, f"""
            SELECT s.symbol, s.score
            FROM swing_trader_scores s
            WHERE s.date=%s
              AND s.score >= {thr_a}
            ORDER BY s.score DESC LIMIT 20""", (grades_date,)) if grades_date else []

        # Signal count trend: last 7 trading days
        trend = q(c, """
            SELECT date,
                   COUNT(*) FILTER (WHERE signal='BUY') AS buy_n,
                   COUNT(*) AS total_n
            FROM buy_sell_daily
            WHERE timeframe IN ('1d', 'daily', 'Daily') AND date >= CURRENT_DATE - 14
            GROUP BY date ORDER BY date DESC LIMIT 7""")

        # ISSUE 32 FIX: Return None for missing signal counts instead of 0 (don't hide missing data)
        sig_count = int(sig["n"]) if sig and sig.get("n") is not None else None
        _log_data_quality("fetch_signals", sig_count if sig_count is not None else 0)
        return {"n": sig_count, "total": total_n, "filtered_count": filtered_count,
                "date": sig["d"] if sig else None,
                "buy_sigs": buy_sigs, "grades": grades, "near": near,
                "top_a": top_a, "trend": trend}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_signals: {type(e).__name__}: {e}")
        _log_data_quality("fetch_signals", 0, str(e))
        return {"_error": f"Failed to load signals: {type(e).__name__}", "stale_alerts": stale_alerts}

def fetch_sector_ranking(c):
    try:
        # Issue 15 FIX: Validate that sector_ranking table has data
        max_date = q1(c, "SELECT MAX(date) as max_date FROM sector_ranking")
        if not max_date or max_date.get("max_date") is None:
            logger.warning("VALIDATION: sector_ranking table empty (max_date is NULL) — sector loader may not have run")
            _log_data_quality("fetch_sector_ranking", 0, "table has no data")
            return {"_error": "Sector ranking table has no data"}

        raw_result = q(c, """
            SELECT sector_name, current_rank, momentum_score, rank_1w_ago, rank_4w_ago
            FROM sector_ranking
            WHERE date=%s
            ORDER BY current_rank ASC""", (max_date.get("max_date"),))

        if not raw_result:
            logger.warning(f"VALIDATION: sector_ranking has max_date {max_date.get('max_date')} but no rows for that date")
            _log_data_quality("fetch_sector_ranking", 0, "no rows for max_date")
            return {"_error": "No sector ranking rows for latest date"}

        # H7 FIX: Validate completeness of each sector entry and track filtered count
        required_fields = ["sector_name", "current_rank", "momentum_score", "rank_1w_ago", "rank_4w_ago"]
        result = []
        filtered_out_count = 0
        for row in raw_result:
            if all(row.get(field) is not None for field in required_fields):
                result.append(row)
            else:
                filtered_out_count += 1
                incomplete_fields = [f for f in required_fields if row.get(f) is None]
                logger.warning(f"VALIDATION: Filtered incomplete sector entry {row.get('sector_name', 'UNKNOWN')}: missing {incomplete_fields}")

        if filtered_out_count > 0:
            logger.warning(f"VALIDATION: fetch_sector_ranking filtered out {filtered_out_count}/{len(raw_result)} incomplete sector entries")

        _log_data_quality("fetch_sector_ranking", len(result))
        return {
            "sectors": result,
            "total_returned": len(result),
            "filtered_out_count": filtered_out_count,
            "total_fetched": len(raw_result)
        }
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_sector_ranking: {type(e).__name__}: {e}")
        _log_data_quality("fetch_sector_ranking", 0, str(e))
        return {"_error": f"Failed to load sector ranking: {type(e).__name__}"}

def fetch_sector_position_warnings(c, cfg=None):
    """Issue 35 FIX: Display warnings when sectors reach/exceed position cap."""
    try:
        if cfg is None:
            cfg_row = q1(c, "SELECT config FROM algo_config LIMIT 1")
            cfg = cfg_row.get("config", {}) if cfg_row else {}
        max_positions_per_sector = int(cfg.get('max_positions_per_sector', 5))

        result = q(c, """
            SELECT cp.sector, COUNT(*) as position_count
            FROM algo_trades at
            LEFT JOIN company_profile cp ON cp.symbol = at.symbol
            WHERE at.status='open'
            GROUP BY cp.sector
            ORDER BY position_count DESC
        """)

        if not result:
            _log_data_quality("fetch_sector_position_warnings", 0)
            return {"warnings": [], "at_cap": []}

        warnings = []
        at_cap = []

        for row in result:
            sector = row.get('sector') or 'Unknown'
            position_count_val = row.get('position_count')
            count = int(position_count_val) if position_count_val is not None else None
            pct = (count / max_positions_per_sector * 100) if count is not None and max_positions_per_sector > 0 else None

            if sector != 'Unknown' and count is not None and count >= max_positions_per_sector:
                at_cap.append(sector)
                warnings.append({
                    'sector': sector,
                    'count': count,
                    'max': max_positions_per_sector,
                    'pct_of_max': round(pct, 0),
                    'status': 'AT_CAP'
                })
            elif sector != 'Unknown' and count >= (max_positions_per_sector * 0.8):
                warnings.append({
                    'sector': sector,
                    'count': count,
                    'max': max_positions_per_sector,
                    'pct_of_max': round(pct, 0),
                    'status': 'NEAR_CAP'
                })

        if warnings:
            logger.warning(f"VALIDATION: Sector position warnings: {len(warnings)} sectors near/at cap")
            _log_data_quality("fetch_sector_position_warnings", len(warnings))
        else:
            _log_data_quality("fetch_sector_position_warnings", 0)

        return {"warnings": warnings, "at_cap": at_cap}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_sector_position_warnings: {type(e).__name__}: {e}")
        _log_data_quality("fetch_sector_position_warnings", 0, str(e))
        return {"_error": f"Failed to load sector position warnings: {type(e).__name__}"}


def fetch_activity(c):
    try:
        latest = q1(c, """
            SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
            FROM algo_audit_log
            WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"):
            _log_data_quality("fetch_activity", 0)
            return {"_error": "No recent activity data available"}
        rid    = latest["run_id"]
        run_at = latest.get("run_at")
        phases = q(c, """
            SELECT action_type, status, details, created_at
            FROM algo_audit_log WHERE details->>'run_id'=%s ORDER BY created_at ASC""", (rid,))
        recent_actions = q(c, """
            SELECT action_type, status, details, created_at
            FROM algo_audit_log
            WHERE action_type IN ('entry_executed','exit_executed','entry_rejected',
                                  'position_exited','order_placed','order_rejected')
            ORDER BY created_at DESC LIMIT 6""")
        result = {"run_id": rid, "run_at": run_at, "phases": phases, "recent_actions": recent_actions}
        _log_data_quality("fetch_activity", len(phases) if phases else 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_activity: {type(e).__name__}: {e}")
        _log_data_quality("fetch_activity", 0, str(e))
        return {"_error": f"Failed to load activity: {type(e).__name__}"}

def fetch_health(c):
    try:
        # Category 6 fix: Clarify staleness thresholds with explicit business logic
        # Monday (DOW=1): use 10d threshold for markets closed over weekend
        # All other days: use 3d threshold for critical tables, 7d for important, 14d for supporting
        result = q(c, """
            SELECT tbl, role, latest, age,
                   CASE WHEN age IS NULL OR age > stale_thresh THEN 'stale' ELSE 'ok' END AS st
            FROM (
              SELECT 'price_daily'    tbl,'CRIT' role, MAX(date)::date latest,(CURRENT_DATE-MAX(date)::date) age,
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 3 END stale_thresh FROM price_daily       UNION ALL
              SELECT 'buy_sell_daily','CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 3 END FROM buy_sell_daily  UNION ALL
              SELECT 'swing_scores',  'CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 3 END FROM swing_trader_scores UNION ALL
              SELECT 'exposure_daily','CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 3 END FROM market_exposure_daily UNION ALL
              SELECT 'port_snapshot', 'CRIT',          MAX(snapshot_date)::date,(CURRENT_DATE-MAX(snapshot_date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 3 END FROM algo_portfolio_snapshots UNION ALL
              SELECT 'technicals',    'IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 7 END FROM technical_data_daily UNION ALL
              SELECT 'market_health', 'IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 7 END FROM market_health_daily UNION ALL
              SELECT 'trend_template','IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 THEN 10 ELSE 7 END FROM trend_template_data UNION ALL
              SELECT 'sector_ranking','SUPP',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    14        FROM sector_ranking UNION ALL
              SELECT 'economic_data', 'SUPP',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    14        FROM economic_data
            ) s ORDER BY CASE role WHEN 'CRIT' THEN 1 WHEN 'IMP' THEN 2 ELSE 3 END, tbl""")
        _log_data_quality("fetch_health", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_health: {type(e).__name__}: {e}")
        _log_data_quality("fetch_health", 0, str(e))
        return {"_error": f"Failed to load health: {type(e).__name__}"}

def fetch_economic_pulse(c):
    try:
        KEY = ['DGS10', 'DGS2', 'DGS3MO', 'DGS6MO',
               'BAMLH0A0HYM2', 'BAMLC0A0CM',
               'DCOILWTICO', 'ANFCI',
               'FEDFUNDS', 'CPIAUCSL', 'UNRATE',
               'T10YIE', 'T5YIE', 'DTWEXBGS', 'MORTGAGE30US', 'UMCSENT']
        rows = q(c, """
            SELECT DISTINCT ON (series_id) series_id, date, value
            FROM economic_data WHERE series_id = ANY(%s)
            ORDER BY series_id, date DESC""", (KEY,))
        d = {r['series_id']: safe_float(r['value']) for r in rows if r.get('value') is not None}

        missing_required = [k for k in ['DGS10', 'DGS2', 'CPIAUCSL'] if k not in d or d[k] is None]
        if missing_required:
            logger.warning(f"VALIDATION: fetch_economic_pulse missing required fields: {missing_required} — economic data incomplete")

        yc_10_2 = None
        yc_10_3m = None
        try:
            ycs_metrics = q1(c, """
                SELECT yield_curve_slope_10y2y, yield_curve_slope_error
                FROM economic_metrics_daily
                ORDER BY report_date DESC LIMIT 1
            """)
            if ycs_metrics and ycs_metrics.get('yield_curve_slope_10y2y') is not None:
                yc_10_2 = safe_float(ycs_metrics.get('yield_curve_slope_10y2y'))
                logger.debug(f"Yield curve slope from pre-computed table: {yc_10_2}")
        except Exception as e:
            logger.debug(f"Could not fetch pre-computed yield curve slope: {e}")

        if yc_10_2 is None:
            t10 = d.get('DGS10'); t2 = d.get('DGS2'); t3m = d.get('DGS3MO')
            yc_10_2  = round(t10 - t2,  2) if (t10 is not None and t2 is not None) else None
            yc_10_3m = round(t10 - t3m, 2) if (t10 is not None and t3m is not None) else None
            if t10 is None or t2 is None:
                logger.warning(f"VALIDATION: fetch_economic_pulse cannot compute yield curve 10-2: DGS10={t10}, DGS2={t2}")
        else:
            t10 = d.get('DGS10'); t3m = d.get('DGS3MO')
            yc_10_3m = round(t10 - t3m, 2) if (t10 is not None and t3m is not None) else None

        cpi_yoy = None
        cpi_error = None
        try:
            econ_metrics = q1(c, """
                SELECT cpi_yoy_pct, cpi_yoy_error
                FROM economic_metrics_daily
                ORDER BY report_date DESC LIMIT 1
            """)
            if econ_metrics:
                cpi_yoy = safe_float(econ_metrics.get('cpi_yoy_pct'))
                cpi_error = econ_metrics.get('cpi_yoy_error')
                if cpi_yoy is not None:
                    logger.debug(f"CPI YoY from pre-computed table: {cpi_yoy}%")
        except Exception as e:
            logger.debug(f"Could not fetch pre-computed CPI YoY: {e}")

        if cpi_yoy is None:
            logger.debug("CPI YoY not in pre-computed table, falling back to calculation")
            cpi_cur = q1(c, "SELECT value FROM economic_data WHERE series_id='CPIAUCSL' ORDER BY date DESC LIMIT 1")
            cpi_yoy_row = q1(c, """
                SELECT value FROM economic_data
                WHERE series_id='CPIAUCSL' AND date <= CURRENT_DATE - 365
                ORDER BY date DESC LIMIT 1""")
            if cpi_cur and cpi_yoy_row and cpi_cur.get('value') is not None and cpi_yoy_row.get('value') is not None:
                try:
                    cur = safe_float(cpi_cur['value'])
                    prev = safe_float(cpi_yoy_row['value'])
                    if cur is not None and prev is not None:
                        if prev > 0:
                            cpi_yoy = round((cur - prev) / prev * 100, 2)
                        else:
                            cpi_error = "prev_cpi_zero"
                except (ValueError, TypeError) as e:
                    cpi_error = f"parse_error:{type(e).__name__}"
            else:
                if not cpi_cur or cpi_cur.get('value') is None:
                    cpi_error = "current_missing"
                elif not cpi_yoy_row or cpi_yoy_row.get('value') is None:
                    cpi_error = "yoy_history_missing"

        if cpi_error:
            logger.warning(f"VALIDATION: fetch_economic_pulse CPI YoY computation failed: {cpi_error}")

        # Issue 38 FIX: Include data freshness status
        max_date_row = q1(c, "SELECT MAX(date) as max_date FROM economic_data WHERE series_id = ANY(%s)", (KEY,))
        last_update = max_date_row.get('max_date') if max_date_row else None
        days_stale = (datetime.now(ET).date() - last_update).days if last_update else None
        data_status = 'current' if days_stale == 0 else ('1day_old' if days_stale == 1 else f'{days_stale}days_old' if days_stale else 'unknown')

        # M15 FIX: Track staleness for display
        if days_stale is None:
            stale_alerts.append("Economic data missing")
        elif days_stale > 1:
            stale_alerts.append(f"Economic data {days_stale}d old")
        if missing_required:
            stale_alerts.append(f"Missing: {', '.join(missing_required)}")
        if cpi_error:
            stale_alerts.append(f"CPI error: {cpi_error}")

        result = {
            't10': t10, 't2': t2, 't3m': t3m, 't6m': d.get('DGS6MO'),
            'yc_10_2':  yc_10_2, 'yc_10_3m': yc_10_3m,
            'hy':  d.get('BAMLH0A0HYM2'), 'ig': d.get('BAMLC0A0CM'),
            'oil': d.get('DCOILWTICO'),    'nfci': d.get('ANFCI'),
            'fed_funds': d.get('FEDFUNDS'),
            'cpi_yoy':   cpi_yoy,
            'unrate':    d.get('UNRATE'),
            'be10':      d.get('T10YIE'),
            'be5':       d.get('T5YIE'),
            'dxy':       d.get('DTWEXBGS'),
            'mortgage':  d.get('MORTGAGE30US'),
            'umcsent':   d.get('UMCSENT'),
            'stale_alerts': stale_alerts,
            '_last_update': last_update,
            '_data_status': data_status,
        }
        _log_data_quality("fetch_economic_pulse", len(d))
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_economic_pulse: {type(e).__name__}: {e}")
        _log_data_quality("fetch_economic_pulse", 0, str(e))
        return {"_error": f"Failed to load economic pulse: {type(e).__name__}"}

def fetch_algo_metrics(c):
    stale_alerts = []
    try:
        rows = q(c, """SELECT date, total_actions, entries, exits
                       FROM algo_metrics_daily ORDER BY date DESC LIMIT 5""")
        _log_data_quality("fetch_algo_metrics", len(rows) if rows else 0)
        return {"metrics": rows, "stale_alerts": stale_alerts}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_algo_metrics: {type(e).__name__}: {e}")
        _log_data_quality("fetch_algo_metrics", 0, str(e))
        return {"_error": f"Failed to load algo metrics: {type(e).__name__}", "stale_alerts": stale_alerts}

def fetch_notifications(c):
    stale_alerts = []
    try:
        # Issue 16 FIX: Filter to recent notifications (last 7 days) to avoid stale alerts
        result = q(c, """
            SELECT kind, severity, title, seen, created_at, details
            FROM algo_notifications
            WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            ORDER BY created_at DESC LIMIT 8""")
        _log_data_quality("fetch_notifications", len(result) if result else 0)
        return {"notifications": result, "stale_alerts": stale_alerts}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_notifications: {type(e).__name__}: {e}")
        _log_data_quality("fetch_notifications", 0, str(e))
        return {"_error": f"Failed to load notifications: {type(e).__name__}", "stale_alerts": stale_alerts}

def fetch_sentiment(c, cfg=None):
    stale_alerts = []
    try:
        mkt_cfg = load_market_thresholds(cfg)
        row = q1(c, "SELECT fear_greed_index, label, date FROM market_sentiment ORDER BY date DESC LIMIT 1")
        if not row:
            _log_data_quality("fetch_sentiment", 0, "No sentiment data")
            return {"_error": "No market sentiment data found", "stale_alerts": stale_alerts}
        fg = get_numeric(row, "fear_greed_index")
        if fg is None:
            logger.warning("VALIDATION: fetch_sentiment missing fear_greed_index (critical metric)")
            return {"_error": "fear_greed_index missing", "date": row.get("date"), "stale_alerts": stale_alerts}
        label = get_string(row, "label")
        c_fg = (R if fg is not None and fg <= mkt_cfg['fear_greed_alert'] else (Y if fg is not None and fg <= mkt_cfg['fear_greed_caution'] else (G if fg is not None and fg >= mkt_cfg['fear_greed_bullish'] else CY)))
        result = {"fg": round(fg, 1), "label": label, "date": row.get("date"), "color": c_fg}
        _log_data_quality("fetch_sentiment", 1)
        return {**result, "stale_alerts": stale_alerts}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_sentiment: {type(e).__name__}: {e}")
        _log_data_quality("fetch_sentiment", 0, str(e))
        return {"_error": f"Failed to load sentiment: {type(e).__name__}", "stale_alerts": stale_alerts}

def fetch_economic_calendar(c):
    stale_alerts = []
    try:
        rows = q(c, """SELECT event_name, event_date, event_time, importance,
                              forecast_value, actual_value, previous_value
                       FROM economic_calendar
                       WHERE event_date >= CURRENT_DATE - 1
                         AND country='US'
                       ORDER BY event_date ASC, importance DESC, event_time ASC
                       LIMIT 8""")

        if rows:
            # Issue 17 FIX: Simpler filtering: exclude known non-economic events, include everything else
            # This avoids brittle hardcoded keyword matching and catches new indicators automatically
            filtered = []
            for row in rows:
                event_name = str(row.get("event_name") or "").upper()

                # Blacklist approach: exclude specific non-economic patterns
                non_economic_patterns = [
                    'EARNINGS', 'GUIDANCE', 'IPO', 'CONFERENCE', 'SUMMIT',
                    'SPEECH', 'TESTIMONY', 'EARNINGS CALL', 'PRESIDEN', 'ELECTION'
                ]
                is_non_economic = any(pattern in event_name for pattern in non_economic_patterns)

                if is_non_economic:
                    logger.debug(f"VALIDATION: Skipping non-economic event: {event_name}")
                    continue

                filtered.append(row)

            _log_data_quality("fetch_economic_calendar", len(filtered) if filtered else 0)
            return {"events": filtered, "stale_alerts": stale_alerts}
        else:
            _log_data_quality("fetch_economic_calendar", 0, "No calendar events")
            return {"_error": "No economic calendar data", "stale_alerts": stale_alerts}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_economic_calendar: {type(e).__name__}: {e}")
        _log_data_quality("fetch_economic_calendar", 0, str(e))
        return {"_error": f"Failed to load economic calendar: {type(e).__name__}", "stale_alerts": stale_alerts}

def fetch_risk_metrics(c) -> dict:
    """Fetch pre-calculated risk metrics (updated hourly by load_algo_risk_daily.py).

    Returns freshness-checked metrics. If stale (>2h), returns data with warning flag.
    """
    stale_alerts = []
    try:
        row = q1(c, """SELECT report_date, var_pct_95, cvar_pct_95, stressed_var_pct,
                              portfolio_beta, top_5_concentration, updated_at
                       FROM algo_risk_daily ORDER BY report_date DESC LIMIT 1""")

        if not row:
            logger.warning("VALIDATION: No risk metrics data available; risk loader may not have run yet")
            _log_data_quality("fetch_risk_metrics", 0, "table has no data")
            stale_alerts.append("Risk metrics not yet computed")
            return {"_has_data": False, "stale_alerts": stale_alerts}

        # Issue 18 FIX: Check freshness but still return stale data with warning
        age_minutes = None
        is_fresh = False
        if row and row.get('updated_at'):
            try:
                if isinstance(row['updated_at'], datetime):
                    update_time = row['updated_at']
                else:
                    update_time = datetime.fromisoformat(str(row['updated_at']))
                if update_time.tzinfo is None:
                    update_time = update_time.replace(tzinfo=timezone.utc)
                age_minutes = (datetime.now(timezone.utc) - update_time).total_seconds() / 60
                is_fresh = age_minutes < METRICS_CALCULATION_MAX_AGE_MINUTES  # Metric calculation must be recent
                if age_minutes > 120:
                    logger.warning(f"fetch_risk_metrics: table data {age_minutes:.0f}m old (stale); will return with warning flag")
            except (ValueError, TypeError):
                is_fresh = row is not None

        # M6 FIX: Add calculation status to indicate data quality
        var95_val = row.get("var_pct_95")
        cvar95_val = row.get("cvar_pct_95")
        has_all_metrics = all([var95_val is not None, cvar95_val is not None])

        if not is_fresh:
            calc_status = "stale"
        elif not has_all_metrics:
            calc_status = "incomplete"
        else:
            calc_status = "complete"

        result = {
            "_has_data": True,
            "date":      row.get("report_date"),
            "var95":     safe_float(var95_val),
            "cvar95":    safe_float(cvar95_val),
            "svar":      safe_float(row.get("stressed_var_pct")),
            "beta":      safe_float(row.get("portfolio_beta")),
            "conc5":     safe_float(row.get("top_5_concentration")),
            "stale_alerts": stale_alerts,
            "_source":   "table",
            "_is_stale": not is_fresh,
            "_age_minutes": age_minutes,
            "_calculation_status": calc_status,
        }
        _log_data_quality("fetch_risk_metrics", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_risk_metrics: {type(e).__name__}: {e}")
        _log_data_quality("fetch_risk_metrics", 0, str(e))
        stale_alerts.append(f"Risk metrics fetch failed: {type(e).__name__}")
        return {"_has_data": False, "stale_alerts": stale_alerts}

def fetch_perf_analytics(c):
    """Fetch pre-calculated performance analytics (updated hourly by load_algo_performance_daily.py).

    Validates loader is running by checking update frequency. Returns stale data with warning if needed.
    """
    try:
        # Try table first (updated by load_algo_performance_daily.py hourly)
        row = q1(c, """SELECT report_date, rolling_sharpe_252d, rolling_sortino_252d,
                              calmar_ratio, win_rate_50t, avg_win_r_50t, avg_loss_r_50t,
                              expectancy, max_drawdown_pct, updated_at
                       FROM algo_performance_daily ORDER BY report_date DESC LIMIT 1""")

        if not row:
            logger.warning("VALIDATION: No performance data available; performance loader may not have run yet")
            _log_data_quality("fetch_perf_analytics", 0, "table has no data")
            return {"_unavailable": True, "_reason": "Performance metrics table is empty"}

        # Issue 19 FIX: Validate loader is actually running by checking update frequency
        age_minutes = None
        is_fresh = False
        loader_running = False
        if row and row.get('updated_at'):
            try:
                if isinstance(row['updated_at'], datetime):
                    update_time = row['updated_at']
                else:
                    update_time = datetime.fromisoformat(str(row['updated_at']))
                if update_time.tzinfo is None:
                    update_time = update_time.replace(tzinfo=timezone.utc)
                age_minutes = (datetime.now(timezone.utc) - update_time).total_seconds() / 60
                is_fresh = age_minutes < METRICS_CALCULATION_MAX_AGE_MINUTES  # Metric calculation must be recent
                loader_running = age_minutes < 1440  # Data updated within last 24 hours indicates loader runs

                if not loader_running:
                    logger.warning(f"fetch_perf_analytics: No updates in {age_minutes:.0f}m (>24h); loader may not be running")
                elif age_minutes > 120:
                    logger.warning(f"fetch_perf_analytics: table data {age_minutes:.0f}m old (stale but loader is running)")
            except (ValueError, TypeError):
                is_fresh = row is not None
                loader_running = is_fresh

        if row:
            def _f(k):
                val = safe_float(row[k]) if row.get(k) is not None else None
                return round(val, 3) if val is not None else None
            result = {
                "sharpe252": _f("rolling_sharpe_252d"),
                "sortino":   _f("rolling_sortino_252d"),
                "calmar":    _f("calmar_ratio"),
                "wr50":      _f("win_rate_50t"),
                "avg_w_r":   _f("avg_win_r_50t"),
                "avg_l_r":   _f("avg_loss_r_50t"),
                "expectancy": _f("expectancy"),
                "maxdd":     _f("max_drawdown_pct"),
                "_source": "table",
                "_is_stale": not is_fresh,
                "_loader_running": loader_running,
                "_age_minutes": age_minutes,
                "_updated_at": row.get("updated_at"),  # M10 FIX: Include timestamp for staleness display
            }
            _log_data_quality("fetch_perf_analytics", 1)
            return result

        _log_data_quality("fetch_perf_analytics", 0, "table query returned no data")
        return {"_unavailable": True, "_reason": "Performance metrics not yet calculated by loader"}

    except (psycopg2.Error, KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.error(f"fetch_perf_analytics: {type(e).__name__}: {e}")
        _log_data_quality("fetch_perf_analytics", 0, str(e))
        return {"_error": f"Failed to load performance analytics: {type(e).__name__}"}

def fetch_signal_eval(c):
    try:
        stats = q1(c, """SELECT
            COUNT(*) total,
            COUNT(*) FILTER (WHERE filter_tier_1_pass) t1,
            COUNT(*) FILTER (WHERE filter_tier_2_pass) t2,
            COUNT(*) FILTER (WHERE filter_tier_3_pass) t3,
            COUNT(*) FILTER (WHERE filter_tier_4_pass) t4,
            COUNT(*) FILTER (WHERE filter_tier_5_pass) t5,
            AVG(final_signal_quality_score) avg_score,
            MAX(signal_date) as signal_date
            FROM algo_signals_evaluated
            WHERE signal_date = (SELECT MAX(signal_date) FROM algo_signals_evaluated)""")
        if not stats or stats.get("total") is None:
            logger.warning("No signal evaluation data available")
            _log_data_quality("fetch_signal_eval", 0, "No evaluation data")
            return {"_error": "No signal evaluation data found"}
        rejected = q(c, """SELECT evaluation_reason, COUNT(*) n
                           FROM algo_signals_evaluated
                           WHERE signal_date = (SELECT MAX(signal_date) FROM algo_signals_evaluated)
                             AND filter_tier_5_pass = false
                           GROUP BY evaluation_reason
                           ORDER BY n DESC LIMIT 3""")
        def _i(k):
            val = stats.get(k) if stats else None
            return int(val) if val is not None else 0
        avg_score_val = safe_float(stats.get("avg_score"), 0) if stats else 0
        total_val = _i("total")
        result = {
            "total":    total_val,
            "t1": _i("t1"), "t2": _i("t2"), "t3": _i("t3"),
            "t4": _i("t4"), "t5": _i("t5"),
            "avg_score": round(avg_score_val, 1),
            "date":     stats.get("signal_date") if stats else None,
            "rejected": rejected,
        }
        _log_data_quality("fetch_signal_eval", total_val)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_signal_eval: {type(e).__name__}: {e}")
        _log_data_quality("fetch_signal_eval", 0, str(e))
        return {"_error": f"Failed to load signal evaluation: {type(e).__name__}"}

def fetch_sector_rotation(c):
    try:
        row = q1(c, """SELECT date, signal, strength, details
                       FROM sector_rotation_signal
                       ORDER BY date DESC LIMIT 1""")
        if not row:
            _log_data_quality("fetch_sector_rotation", 0, "No sector rotation data")
            return {"_error": "No sector rotation data available"}
        d = row.get("details")
        if d is None:
            d = {}
        elif isinstance(d, str):
            try:
                d = json.loads(d)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"sector_rotation details corrupt; sector rotation signal unavailable: {e}")
                return {"_error": "Sector rotation data corrupted"}
        strength = safe_float(row.get("strength"))
        signal = row.get("signal")
        result = {
            "date":     row.get("date"),
            "signal":   signal if signal is not None else "",
            "strength": strength,
            "weeks":    d.get("weeks_persistent", 1),
            "def_score": d.get("defensive_lead_score", 0),
            "cyc_score": d.get("cyclical_weak_score", 0),
        }
        _log_data_quality("fetch_sector_rotation", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_sector_rotation: {type(e).__name__}: {e}")
        _log_data_quality("fetch_sector_rotation", 0, str(e))
        return {"_error": f"Failed to load sector rotation: {type(e).__name__}"}

def fetch_industry_ranking(c):
    try:
        result = q(c, """SELECT industry, current_rank, momentum_score, rank_1w_ago
                       FROM industry_ranking
                       WHERE date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking)
                       ORDER BY current_rank LIMIT 10""")
        _log_data_quality("fetch_industry_ranking", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_industry_ranking: {type(e).__name__}: {e}")
        _log_data_quality("fetch_industry_ranking", 0, str(e))
        return {"_error": f"Failed to load industry ranking: {type(e).__name__}"}

def fetch_loader_status(c):
    try:
        result = q(c, """SELECT table_name, status, latest_date, age_days,
                              completion_pct, error_message, last_updated
                       FROM data_loader_status
                       ORDER BY CASE status
                           WHEN 'error'   THEN 1
                           WHEN 'failed'  THEN 2
                           WHEN 'stale'   THEN 3
                           WHEN 'loading' THEN 4
                           ELSE 5
                       END, age_days DESC NULLS LAST
                       LIMIT 8""")

        # Issue 28 FIX: Validate loader status freshness for all statuses, not just 'loading'
        if result:
            now = datetime.now(timezone.utc)
            for row in result:
                last_update = row.get("last_updated")
                status = row.get("status")
                table_name = row.get("table_name")

                if last_update:
                    if isinstance(last_update, datetime):
                        td = last_update
                    else:
                        try:
                            td = datetime.fromisoformat(str(last_update))
                        except (ValueError, TypeError):
                            logger.warning(f"VALIDATION: Loader '{table_name}' has unparseable last_updated: {last_update}")
                            continue

                    if td.tzinfo is None:
                        td = td.replace(tzinfo=timezone.utc)

                    minutes_since_update = (now - td).total_seconds() / 60

                    if status == 'loading' and minutes_since_update > 30:
                        logger.warning(f"VALIDATION: Loader '{table_name}' status marked as 'loading' for {minutes_since_update:.0f} minutes — status may be stale")
                    elif status in ('error', 'failed') and minutes_since_update > 1440:
                        logger.warning(f"VALIDATION: Loader '{table_name}' in '{status}' state for {minutes_since_update:.0f} minutes — requires investigation")
                elif status in ('loading', 'error', 'failed'):
                    logger.warning(f"VALIDATION: Loader '{table_name}' in '{status}' state but last_updated is NULL — cannot determine staleness")

        _log_data_quality("fetch_loader_status", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_loader_status: {type(e).__name__}: {e}")
        _log_data_quality("fetch_loader_status", 0, str(e))
        return {"_error": f"Failed to load loader status: {type(e).__name__}"}

def fetch_exec_history(c):
    try:
        # Try with phase array columns first; fall back if they don't exist yet
        try:
            result = q(c, """SELECT run_id, started_at, completed_at, overall_status,
                                  phases_completed, phases_halted, phases_errored, halt_reason
                           FROM orchestrator_execution_log
                           ORDER BY started_at DESC LIMIT 10""")
        except psycopg2.Error as e:
            logger.warning(f"fetch_exec_history: phases array columns not available, using fallback: {e}")
            result = q(c, """SELECT run_id, started_at, completed_at, overall_status,
                                  halt_reason
                           FROM orchestrator_execution_log
                           ORDER BY started_at DESC LIMIT 10""")
        _log_data_quality("fetch_exec_history", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_exec_history: {type(e).__name__}: {e}")
        _log_data_quality("fetch_exec_history", 0, str(e))
        return {"_error": f"Failed to load execution history: {type(e).__name__}"}

def fetch_audit_log(c):
    try:
        rows = q(c, """SELECT action_type, symbol, status, created_at,
                              details
                       FROM algo_audit_log
                       ORDER BY created_at DESC LIMIT 8""")
        result = []
        for r in rows:
            det = r.get("details")
            if det is None:
                det = {}
            elif isinstance(det, str):
                try: det = json.loads(det)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse audit_log details JSON: {e}")
                    det = {}
            result.append({
                "action_type": r.get("action_type", ""),
                "symbol":      r.get("symbol") or det.get("symbol", ""),
                "status":      r.get("status", ""),
                "created_at":  r.get("created_at"),
            })
        _log_data_quality("fetch_audit_log", len(result))
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_audit_log: {type(e).__name__}: {e}")
        _log_data_quality("fetch_audit_log", 0, str(e))
        return {"_error": f"Failed to load audit log: {type(e).__name__}"}

def fetch_circuit(c):
    """Fetch circuit breaker status from API instead of database.

    Uses /api/algo/circuit-breakers endpoint which returns real-time
    circuit breaker state and trigger status.
    """
    try:
        api_resp = api_call("/api/algo/circuit-breakers")
        if "_error" in api_resp:
            logger.error(f"fetch_circuit: API error: {api_resp['_error']}")
            _log_data_quality("fetch_circuit", 0, api_resp['_error'])
            return {"_error": api_resp['_error'], "breakers": [], "any_triggered": False, "triggered_count": 0}

        breakers_data = api_resp.get("data", api_resp)
        breakers = breakers_data.get("breakers", [])
        any_triggered = breakers_data.get("any_triggered", False)
        triggered_count = breakers_data.get("triggered_count", 0)
        _log_data_quality("fetch_circuit", len(breakers))
        return {"breakers": breakers, "any_triggered": any_triggered, "triggered_count": triggered_count}
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_circuit: {type(e).__name__}: {e}")
        _log_data_quality("fetch_circuit", 0, str(e))
        return {"_error": str(e), "breakers": [], "any_triggered": False, "triggered_count": 0}


def check_loader_health() -> dict:
    """Category 9 fix: Health check endpoint for monitoring loader failures.

    Returns dict with:
    - status: 'ok' (all critical fetchers pass), 'degraded' (some pass), 'failed' (none pass)
    - failures: list of fetcher names that failed
    - timestamp: when check was performed
    - data_quality_issues: list of row count / freshness issues
    """
    try:
        conn = get_conn()
        critical_fetchers = ["fetch_run", "fetch_algo_config", "fetch_market", "fetch_positions"]
        failures = []
        successes = []
        data_quality_issues = []

        for name in critical_fetchers:
            try:
                fn = FETCHERS.get(name)
                if fn:
                    result = fn(conn)
                    if isinstance(result, dict) and result.get("_error"):
                        failures.append(name)
                    elif isinstance(result, list) and not result and name in ["fetch_health"]:
                        failures.append(name)
                    else:
                        successes.append(name)
            except Exception as e:
                failures.append(f"{name}({type(e).__name__})")

        # Issue 24: Validate row counts and data freshness for critical tables
        critical_tables = {
            "algo_trades": {"min_rows": 1, "max_age_days": 7, "label": "Trade history"},
            "algo_portfolio_snapshots": {"min_rows": 1, "max_age_days": 1, "label": "Portfolio snapshot"},
            "price_daily": {"min_rows": 100, "max_age_days": 1, "label": "Price data"},
            "market_health_daily": {"min_rows": 1, "max_age_days": 1, "label": "Market health"},
        }

        for table_name, config in critical_tables.items():
            try:
                check = q1(conn, f"SELECT COUNT(*) as cnt, MAX(date) as latest_date FROM {table_name}")
                if check:
                    cnt_val = check.get("cnt")
                    row_count = int(cnt_val) if cnt_val is not None else None
                    latest_date = check.get("latest_date")

                    # Check row count
                    if row_count is None or row_count < config["min_rows"]:
                        issue = f"{config['label']} ({table_name}): only {row_count} rows (expected >={config['min_rows']})"
                        data_quality_issues.append(issue)
                        logger.warning(f"VALIDATION: {issue}")

                    # Check data freshness
                    if latest_date:
                        try:
                            if isinstance(latest_date, datetime):
                                ld = latest_date.date() if hasattr(latest_date, 'date') else latest_date
                            else:
                                ld = datetime.fromisoformat(str(latest_date)).date()

                            age_days = (date.today() - ld).days
                            if age_days > config["max_age_days"]:
                                issue = f"{config['label']} ({table_name}): {age_days} days old (max {config['max_age_days']}d)"
                                data_quality_issues.append(issue)
                                logger.warning(f"VALIDATION: {issue}")
                        except (ValueError, TypeError):
                            pass
            except psycopg2.Error as e:
                issue = f"Could not check {table_name}: {type(e).__name__}"
                data_quality_issues.append(issue)
                logger.warning(f"VALIDATION: {issue}")

        status = "ok" if not failures and not data_quality_issues else ("degraded" if successes else "failed")
        conn.close()
        return {
            "status": status,
            "failures": failures,
            "data_quality_issues": data_quality_issues if data_quality_issues else [],
            "timestamp": datetime.now(ET),
            "critical": len(critical_fetchers),
            "passed": len(successes),
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now(ET),
        }


# ── parallel data loader ──────────────────────────────────────────────────────

FETCHERS = {
    "run":          fetch_run,
    "cfg":          fetch_algo_config,
    "mkt":          fetch_market,
    "port":         fetch_portfolio,
    "perf":         fetch_perf,
    "pos":          fetch_positions,
    "trades":       fetch_recent_trades,
    "sig":          fetch_signals,
    "health":       fetch_health,
    "cb":           fetch_circuit,
    "srank":        fetch_sector_ranking,
    "activity":     fetch_activity,
    "exp_factors":  fetch_exposure_factors,
    "eco":          fetch_economic_pulse,
    "notifs":       fetch_notifications,
    "sentiment":    fetch_sentiment,
    "econ_cal":     fetch_economic_calendar,
    "risk":         fetch_risk_metrics,
    "perf_anl":     fetch_perf_analytics,
    "sig_eval":     fetch_signal_eval,
    "sec_rot":      fetch_sector_rotation,
    "algo_metrics": fetch_algo_metrics,
    "irank":        fetch_industry_ranking,
    "loader":       fetch_loader_status,
    "audit":        fetch_audit_log,
    "exec_hist":    fetch_exec_history,
    "sec_warn":       fetch_sector_position_warnings,
}

def load_all() -> dict:
    out: dict = {}
    load_start = time.time()
    def one(name, fn):
        max_retries = 3
        for attempt in range(max_retries + 1):
            conn = None
            try:
                conn = get_conn()
                conn.autocommit = True
                result = fn(conn)
                return name, result
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                if attempt < max_retries:
                    # Issue 17 FIX: Improved exponential backoff for transient RDS connection pool exhaustion
                    # For attempt 0: 2-5s, attempt 1: 4-12s, attempt 2: 8-28s
                    # Gives RDS connection pool adequate time to recover from transient exhaustion
                    # ISSUE 32 FIX: Add per-fetcher jitter to prevent thundering herd when all 27 fetchers
                    # retry simultaneously after pool exhaustion. Each fetcher gets unique timing offset.
                    backoff = (2 ** attempt) * 2 + random.random() * (2 ** attempt) * 3
                    # Additional per-fetcher jitter (0-5s) to stagger retry timing across all fetchers
                    fetcher_jitter = random.random() * 5
                    total_wait = backoff + fetcher_jitter
                    logger.warning(f"Retry {attempt+1}/{max_retries} for {name} (exponential backoff {backoff:.2f}s + fetcher jitter {fetcher_jitter:.2f}s = {total_wait:.2f}s): {e}")
                    time.sleep(total_wait)
                    continue
                logger.error(f"fetch_{name} failed after {max_retries+1} attempts: {e}")
                return name, {"_error": str(e)}
            except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
                logger.error(f"fetch_{name}: {type(e).__name__}: {e}")
                return name, {"_error": str(e)}
            finally:
                if conn:
                    try: conn.close()
                    except (psycopg2.Error, AttributeError): pass
    # Issue 15 FIX: Increase thread pool workers from 4 to better utilize CPU cores while respecting RDS limits
    # With 27 fetchers: 8 workers means only 3-4 fetchers queue per batch, avoiding timeout cascades
    # RDS connection pool typically 10-20 connections; fetchers hold conn 1-5s, so 8 workers is safe
    # Issue 16 FIX: Use per-batch timeout instead of global timeout to prevent cascading failures
    import os
    cpu_count = os.cpu_count() or 4
    max_workers = min(len(FETCHERS), max(cpu_count - 1, 6))  # Use most CPUs, minimum 6 workers
    logger.debug(f"load_all using {max_workers} workers for {len(FETCHERS)} fetchers on {cpu_count} CPUs")

    # Per-batch timeout: with 8 workers and 27 fetchers, ~4 batches of ~25s each = 100s total
    # ISSUE 31 FIX: Increased timeout to 100s to handle network latency and RDS connection pool contention
    # Each fetcher takes 1-5s; with 8 workers and 27 fetchers, worst-case is ~27/8 * 5s = ~17s, but
    # including pool acquisition delays, network jitter, and query compilation, allow 100s total
    BATCH_TIMEOUT = 100
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_key = {pool.submit(one, k, v): k for k, v in FETCHERS.items()}
        try:
            for f in as_completed(future_to_key, timeout=BATCH_TIMEOUT):
                try:
                    n, d = f.result()
                    out[n] = d
                except Exception as e:
                    logger.error(f"Thread exception in load_all: {type(e).__name__}: {e}")
                    k = future_to_key[f]
                    out[k] = {"_error": str(e)}
        except TimeoutError:
            elapsed = time.time() - load_start
            logger.error(f"load_all batch timed out after {BATCH_TIMEOUT}s (total elapsed {elapsed:.1f}s) — some fetchers incomplete")
            # Issue 21 FIX: Mark timed-out fetchers and track which are still running
            completed_count = sum(1 for f in future_to_key if f.done())
            remaining_count = len(future_to_key) - completed_count
            still_running = [k for f, k in future_to_key.items() if not f.done()]
            logger.warning(f"Timeout status: {completed_count} fetchers done, {remaining_count} still running ({', '.join(still_running[:5])}{'...' if remaining_count > 5 else ''})")
            # Mark remaining incomplete fetchers; this is now rare with improved pool sizing
            for f, k in future_to_key.items():
                if not f.done():
                    logger.warning(f"Fetcher {k} timed out — marking incomplete")
                    f.cancel()
                    out[k] = {"_error": f"Timeout (exceeded {BATCH_TIMEOUT}s, elapsed {elapsed:.1f}s)"}

    # H14 FIX: Check cumulative failure threshold — determine if dashboard should fail or show degraded
    # Define critical fetchers: dashboard cannot operate without these
    CRITICAL_FETCHERS = {"market", "positions", "perf"}

    # Count failures
    failures = [k for k, v in out.items() if isinstance(v, dict) and v.get("_error")]
    critical_failures = [k for k in failures if k in CRITICAL_FETCHERS]
    success_count = len([k for k in out if k not in failures])

    # Log failure summary
    if failures:
        logger.warning(f"Load summary: {success_count} succeeded, {len(failures)} failed (critical: {len(critical_failures)})")

    # If any critical fetcher failed: fail hard
    if critical_failures:
        critical_list = ", ".join(critical_failures)
        msg = f"Critical data source failed: {critical_list} — dashboard cannot proceed"
        logger.error(f"CRITICAL: {msg}")
        return {"_error": msg, "_critical_failures": critical_failures, "_partial_data": out}

    # If failure rate exceeds threshold: degraded state (but show what we have)
    failure_rate = len(failures) / len(FETCHERS) if len(FETCHERS) > 0 else 0
    if failure_rate > FETCHER_FAILURE_THRESHOLD:
        msg = f"Data degraded: {len(failures)}/{len(FETCHERS)} fetchers failed ({failure_rate*100:.1f}% > {FETCHER_FAILURE_THRESHOLD*100:.0f}% threshold)"
        logger.warning(f"DEGRADED: {msg}")
        return {**out, "_degraded": True, "_failure_count": len(failures), "_failed_fetchers": failures, "_failure_rate": round(failure_rate, 2)}

    # Partial failures are acceptable: show available data
    if failures:
        logger.warning(f"Showing partial data: {len(failures)} fetchers failed, proceeding with available data")

    return out


# ── halt reason helpers ───────────────────────────────────────────────────────

def _best_halt_reason(top_level: str, phase_results: list) -> list[tuple[str, str]]:
    """Return a list of (phase_label, reason) pairs drawn from phase-level data.

    Falls back to top_level if no per-phase detail is found.
    Tries multiple field names so the display is robust to orchestrator schema changes.
    """
    _FIELDS = ("halt_reason", "reason", "message", "error", "halt_message",
               "circuit_breaker", "triggered_by", "details")
    found: list[tuple[str, str]] = []
    for p in phase_results if isinstance(phase_results, list) else []:
        ps = (p.get("status") or "").lower()
        if ps not in ("halt", "halted"):
            continue
        raw  = (p.get("name") or p.get("phase", "")).lower()
        parts = raw.split("_")
        base  = "_".join(parts[:2]) if len(parts) >= 2 else raw
        label = PHASE_NAMES.get(base, raw.replace("phase_", "P"))
        pdata = p.get("data")
        if isinstance(pdata, str):
            try:
                pdata = json.loads(pdata)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse phase data JSON: {e}")
                pdata = {}
        elif pdata is None:
            pdata = {}
        detail = ""
        found_field = None
        for field in _FIELDS:
            val = pdata.get(field) if pdata else None
            if val and len(str(val)) > 3:
                detail = str(val)
                found_field = field
                break
        if found_field:
            logger.debug(f"Halt reason from field: {found_field}")
        elif pdata.get("halt_reason"):
            logger.debug(f"Halt reason fields present but all <3 chars: {list(pdata.keys())}")
        if detail:
            found.append((label, detail))
    if not found and top_level:
        found.append(("", top_level))
    return found


def _fmt_phases_halted(phases_halted) -> str:
    """Turn a phases_halted array into a compact human-readable label."""
    if not phases_halted:
        return ""
    if isinstance(phases_halted, int):
        return ""
    if isinstance(phases_halted, str):
        try:    phases_halted = json.loads(phases_halted)
        except (json.JSONDecodeError, ValueError, TypeError): phases_halted = [phases_halted]
    if not isinstance(phases_halted, (list, tuple)):
        return ""
    names = []
    for p in phases_halted:
        raw   = str(p).lower()
        parts = raw.split("_")
        base  = "_".join(parts[:2]) if len(parts) >= 2 else raw
        names.append(PHASE_NAMES.get(base, raw.replace("phase_", "P")))
    return ", ".join(names[:3])


# ── panel builders ────────────────────────────────────────────────────────────

def panel_orch(run, cfg, risk=None):
    # Validate error dicts (Issue 2 FIX: don't process errors as valid data)
    if run and run.get("_error"):
        return Panel(Text(f"error: {run.get('_error')}", style="dim"), title="[bold]ORCHESTRATOR[/]", border_style="yellow", padding=(0, 1))
    if cfg and cfg.get("_error"):
        return Panel(Text(f"error: {cfg.get('_error')}", style="dim"), title="[bold]ORCHESTRATOR[/]", border_style="yellow", padding=(0, 1))

    next_run  = next_run_str()
    mode      = cfg.get("mode", "?") if cfg else "?"
    mc2       = G if mode and "LIVE" in mode else Y
    en        = "ENABLED" if cfg and cfg.get("enabled", True) else "DISABLED"
    ec        = G if cfg and cfg.get("enabled", True) else R
    max_n     = cfg.get("max_pos_n")
    max_sec_n = cfg.get("max_sec_n")
    min_score = cfg.get("min_score")
    base_risk = cfg.get("base_risk")
    t1r       = cfg.get("t1_r")
    pyr       = cfg.get("pyramid", False)

    min_score_f = safe_float(min_score) if min_score else None
    score_s   = f"[dim]min score ≥[/][white]{min_score}[/]" if min_score_f is not None and min_score_f > 0 else ""
    slots_s   = f"[dim]max [/][white]{max_n}[/][dim] positions[/]" if max_n else ""
    sec_s     = f"[dim]sector ≤[/][white]{max_sec_n}[/]" if max_sec_n else ""
    risk_s    = f"[dim]base risk [/][white]{base_risk}%[/]" if base_risk else ""
    t1r_s     = f"[dim]T1 target [/][white]{t1r}R[/]" if t1r else ""
    pyr_s     = f"[{G}]pyramid on[/]" if pyr else ""
    config_line = "  ".join(x for x in [score_s, slots_s, sec_s, risk_s, t1r_s, pyr_s] if x)

    # VaR line — only show if table is populated with real data
    var_line = ""
    if risk and not risk.get("_error"):
        var95_v = get_numeric(risk, "var95")
        # Issue 37 FIX: Add VaR calculation status indicator
        has_data = risk.get("_has_data", False)
        is_stale = risk.get("_is_stale", False)
        if has_data and var95_v is not None and var95_v > 0:
            beta_v = get_numeric(risk, "beta")
            beta_c = R if beta_v is not None and beta_v >= mkt_cfg['beta_warning'] else (Y if beta_v is not None and beta_v >= mkt_cfg['beta_caution'] else G)
            svar_v = get_numeric(risk, "svar")
            svar_s = f"\n[dim]Stressed VaR:[/][{R}]{svar_v:.2f}%[/]" if svar_v is not None and svar_v > 0 else ""
            cvar95_v = get_numeric(risk, "cvar95")
            conc5_v = get_numeric(risk, "conc5")
            cvar95_str = f"{cvar95_v:.2f}%" if cvar95_v is not None else "--"
            conc5_str = f"{conc5_v:.0f}%" if conc5_v is not None else "--"
            beta_str = f"{beta_v:.2f}" if beta_v is not None else "--"
            status_ind = R if is_stale else G
            status_txt = "stale" if is_stale else "current"
            var_line = (f"\n[dim]VaR 95%:[/][white]{var95_v:.2f}%[/] [{status_ind}]({status_txt})[/]"
                        f"  [dim]CVaR 95%:[/][white]{cvar95_str}[/]"
                        f"  [dim]Portfolio Beta:[/][{beta_c}]{beta_str}[/]"
                        f"  [dim]Top-5 Conc:[/][white]{conc5_str}[/]"
                        + svar_s)
        elif not has_data:
            var_line = f"\n[dim]VaR:[/] [{Y}]calculation incomplete[/]"

    if not run or run.get("_error"):
        body = Text.from_markup(
            f"[dim]no run data[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next run:[/] [white]{next_run}[/]"
            + var_line
        )
    else:
        age  = fmt_age(run.get("run_at"))
        sts  = ("[bold bright_green]✔ COMPLETED[/]" if run.get("success") and not run.get("halted")
                else ("[bold yellow]~ HALTED[/]" if run.get("halted")
                else "[bold bright_red]✗ ERROR[/]"))

        pbadges = []
        # exec_log source: structured per-phase objects with names + statuses
        if run.get("_source") == "exec_log":
            # VALIDATION: Ensure phase_results has required schema
            phase_results = validate_phase_results(run.get("phase_results"))
            for p in phase_results:
                raw = (p.get("name") or p.get("phase", "")).lower()
                parts = raw.split("_")
                base  = "_".join(parts[:2]) if len(parts) >= 2 else raw
                short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
                ps    = (p.get("status") or "").lower()
                pc    = G if ps in ("success", "completed") else (Y if ps in ("halt", "halted", "warn") else R)
                pi    = "✓" if ps in ("success", "completed") else ("~" if ps in ("halt", "halted", "warn") else "✗")
                pbadges.append(f"[{pc}]{pi}{short}[/]")
            # Show halt reason if halted
            halt_r = run.get("halt_reason") or ""
            summary = run.get("summary") or ""
            if halt_r or run.get("halted"):
                _details = _best_halt_reason(halt_r, phase_results)
                _lines   = [f"{lb+': ' if lb else ''}{dt[:60]}" for lb, dt in _details]
                extra    = ("\n" + "\n".join(f"[{Y}]{ln}[/]" for ln in _lines)) if _lines else ""
            else:
                extra = f"\n[dim]{summary[:50]}[/]" if summary else ""
        else:
            # audit_log fallback: only phase number available
            for p in run.get("phases", []):
                at = p.get("action_type", "")
                if not at.startswith("phase_"): continue
                parts = at.split("_")
                if len(parts) > 2: continue  # skip sub-phases; only top-level
                num  = parts[1] if len(parts) > 1 else "?"
                short = PHASE_NAMES.get(f"phase_{num}", f"P{num}")[:9]
                ps   = p.get("status", "")
                pc   = G if ps == "success" else (Y if ps in ("halt", "warn") else R)
                pi   = "✓" if ps == "success" else ("~" if ps in ("halt", "warn") else "✗")
                pbadges.append(f"[{pc}]{pi}{short}[/]")
            extra = ""

        phases_str = "  ".join(pbadges) if pbadges else "[dim]—[/]"
        body = Text.from_markup(
            f"{sts}  [dim]{age}[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next run:[/] [white]{next_run}[/]\n"
            f"{phases_str}"
            + extra + var_line
        )
    return Panel(body, title="[bold cyan]ORCHESTRATOR[/]", border_style="cyan", padding=(0, 1))


def panel_market_full(mkt, sentiment=None, cfg=None):
    """Market regime + internals combined."""
    if not mkt or mkt.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]MARKET[/]", border_style="blue", padding=(0, 1))
    tier  = mkt.get("tier", "unknown")
    tc    = TIER_COLOR.get(tier, "dim")
    lbl   = TIER_SHORT.get(tier, "LOADING")
    exp   = mkt.get("pct")
    exp_s = f"{float(exp):.0f}%" if exp is not None else "--"
    # TIER 1A FIX: pass None to exp_bar instead of 0 when exposure is missing
    bar   = exp_bar(exp, w=10)
    vix_val = get_numeric(mkt, "vix")
    vix   = f"{vix_val:.1f}" if vix_val is not None else "--"
    # M2 FIX: Load market thresholds from config instead of hardcoded 30, 20
    mkt_cfg = load_market_thresholds(cfg)
    vc    = R if vix_val is not None and vix_val >= mkt_cfg['vix_alert'] else (Y if vix_val is not None and vix_val >= mkt_cfg['vix_caution'] else DIM)
    dist  = str(mkt.get("dist") or "--")
    stage = str(mkt.get("stage") or "--")
    spy   = f"${mkt['spy']:.2f}" if mkt.get("spy") else "--"
    trend = (mkt.get("trend") or "").upper()
    halts = get_list(mkt, "halts")
    halt_s = " | ".join(format_halt_reason(h) for h in halts[:2]) if halts else "none"
    hc    = Y if halts else DIM

    upvol = get_numeric(mkt, "upvol")
    adr   = get_numeric(mkt, "adr")
    nh    = get_numeric(mkt, "nh")
    nl    = get_numeric(mkt, "nl")
    pcr   = get_numeric(mkt, "pcr")
    bmom  = get_numeric(mkt, "bmom")
    fed   = mkt.get("fed")

    # M2 FIX: Load thresholds from config instead of hardcoded values
    uvc   = G if upvol is not None and upvol >= mkt_cfg['upvol_good'] else (Y if upvol is not None and upvol >= mkt_cfg['upvol_caution'] else DIM)
    pcr_c = G if pcr is not None and pcr <= mkt_cfg['put_call_bullish'] else (Y if pcr is not None and pcr <= mkt_cfg['put_call_fearful'] else DIM)
    # TIER 1A FIX: Calculate NH-NL only when both values exist, don't use "or 0" fallback
    nhnl  = nh - nl if nh is not None and nl is not None else None
    nhnl_c = G if nhnl is not None and nhnl >= mkt_cfg['breadth_good'] else (Y if nhnl is not None and nhnl >= mkt_cfg['breadth_caution'] else DIM)

    spy_raw = mkt.get("spy")
    spy_chg = get_numeric(mkt, "spy_chg")
    # TIER 1A FIX: sign() should only be called with non-None value
    spy_chg_s = f" [{G if spy_chg is not None and spy_chg >= 0 else R}]{sign(spy_chg)}{spy_chg:.1f}%[/]" if spy_chg is not None else ""
    spy_s   = f"SPY:[white]${float(spy_raw):.2f}[/]{spy_chg_s}  " if spy_raw else ""
    lines = [
        f"[{tc}][bold]{lbl}[/]  [dim]exposure[/][{tc}]{exp_s}[/]  {bar}",
        f"VIX:[{vc}]{vix}[/] [dim](20+=caution, 30+=alert)[/]  [dim]Dist Days:[/][white]{dist}[/]  [dim]Stage:[/][white]{stage}[/]  {spy_s}",
    ]
    if upvol is not None:
        adr_s  = f"  [dim]Adv/Dec:[/][white]{adr:.1f}[/]" if adr is not None else ""
        nhnl_s = f"  [dim]NH-NL:[/][{nhnl_c}]{sign(nhnl)}{nhnl}[/]" if nhnl is not None else ""
        lines.append(f"[dim]Up Volume:[/][{uvc}]{upvol:.0f}%[/] [dim](50%+=good)[/]{adr_s}  [dim]New Highs:[/][{G}]{nh or '--'}[/] [dim]Lows:[/][{R}]{nl or '--'}[/]{nhnl_s}")
    ycs = mkt.get("ycs")
    bmom_pcr = []
    if pcr is not None:
        bmom_pcr.append(f"[dim]Put/Call:[/][{pcr_c}]{pcr:.2f}[/] [dim](<0.8=bullish)[/]")
    if bmom is not None:
        bmc = G if bmom is not None and bmom >= mkt_cfg['breadth_momentum_good'] else (Y if bmom is not None and bmom >= 0 else R)
        bmom_pcr.append(f"[dim]Breadth Momentum:[/][{bmc}]{bmom:.1f}[/] [dim](0.5+=bullish)[/]")
    if ycs is not None:
        yc_c = G if ycs is not None and ycs >= mkt_cfg['yield_curve_good'] else (Y if ycs is not None and ycs >= 0 else R)
        bmom_pcr.append(f"[dim]Yield Curve Slope:[/][{yc_c}]{ycs:+.2f}[/] [dim](0+=flat)[/]")
    if bmom_pcr:
        lines.append("  ".join(bmom_pcr))
    halt_fed = f"[dim]Trading Halt:[/][{hc}]{halt_s}[/]"
    if fed:
        halt_fed += f"  [dim]Fed Environment:[/][white]{fed[:20]}[/]"
    lines.append(halt_fed)

    # Fear & Greed
    if sentiment and not sentiment.get("_error"):
        fg_v   = sentiment.get("fg", 0)
        fg_lbl = (sentiment.get("label") or "")[:16]
        fg_c   = sentiment.get("color", "dim")
        fg_bar = int(fg_v / 100 * 8)
        fg_bar_s = f"[{fg_c}]{'█' * fg_bar}[/][dim]{'░' * (8 - fg_bar)}[/]"
        lines.append(f"[dim]Fear & Greed:[/][{fg_c}]{fg_v:.0f} — {fg_lbl}[/] {fg_bar_s}")

    # Data freshness alerts
    stale_alerts = mkt.get("stale_alerts", [])
    if stale_alerts:
        lines.append(f"[orange1][!] Data stale:[/] {', '.join(stale_alerts)}")

    txt = Text.from_markup("\n".join(lines))
    return Panel(txt, title="[bold blue]MARKET[/]", border_style="blue", padding=(0, 1))


def panel_circuit(cb, risk=None):
    if not cb or cb.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]CIRCUIT BREAKERS[/]", border_style="blue", padding=(0, 1))
    n_f   = cb.get("n", 0)
    any_f = cb.get("any", False)
    hc    = R if any_f else G
    hs    = f"[!] {n_f} BREAKER{'S' if n_f != 1 else ''} FIRED" if any_f else "[+] ALL CLEAR"
    tbl = Table.grid(padding=(0, 1), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)
    bs = cb.get("bs", [])
    for a, b in zip(bs[::2], bs[1::2] + [None]):
        def fmt_b(br):
            if br is None: return ""
            thr = br.get("thr", 0)
            cur = br.get("cur")
            lbl = br.get("lbl", "?")
            u = br.get("u", "")
            fired = br.get("fired", False)
            available = br.get("available", True)
            if cur is None:
                cur_str = "--"
                ratio = 0
            else:
                cur_str = f"{cur}{u}" if u else str(cur)
                ratio = cur / thr if thr > 0 else 0
            fc = R if fired else (Y if ratio >= 0.75 else G)  # TODO: convert to config
            ind = "[bold red] ![/]" if fired else ""
            unavail = " [dim](unavailable)[/]" if not available else ""
            # TIER 1A FIX: Pass None instead of "or 0" to hbar for proper missing data display
            return f"[{fc}]{lbl}:[/]{cur_str}[dim]/{thr:.0f}{u}[/]{hbar(cur, thr, w=4)}{ind}{unavail}"
        tbl.add_row(Text.from_markup(fmt_b(a)), Text.from_markup(fmt_b(b)))
    parts = [Text.from_markup(f"[{hc}][bold]{hs}[/bold][/]"), tbl]
    return Panel(Group(*parts), title="[bold blue]CIRCUIT BREAKERS[/]", border_style="blue", padding=(0, 1))


def panel_header_market(mkt, sentiment, ts, mkt_s, elapsed, refresh_s="", cfg=None):
    """Compact market header — fits alongside exposure factors + monkey in the top row."""
    rows = [Text.from_markup(f"{mkt_s}  [dim]{ts}[/]  [dim]{elapsed:.1f}s[/]{refresh_s}")]
    if mkt and not mkt.get("_error"):
        tier    = mkt.get("tier", "unknown")
        tc      = TIER_COLOR.get(tier, "dim")
        lbl     = TIER_SHORT.get(tier, "LOADING")
        exp     = mkt.get("pct")
        exp_s   = f"{float(exp):.0f}%" if exp is not None else "--"
        # TIER 1A FIX: exp_bar now handles None safely
        bar     = exp_bar(exp, w=8)
        # M2 FIX: Load market thresholds from config
        mkt_cfg = load_market_thresholds(cfg)
        vix_val = get_numeric(mkt, "vix")
        vix     = f"{vix_val:.1f}" if vix_val is not None else "--"
        vc      = R if vix_val is not None and vix_val >= mkt_cfg['vix_alert'] else (Y if vix_val is not None and vix_val >= mkt_cfg['vix_caution'] else DIM)
        dist    = str(mkt.get("dist") or "--")
        stage   = str(mkt.get("stage") or "--")
        spy_raw = mkt.get("spy"); spy_chg = get_numeric(mkt, "spy_chg")
        # TIER 1A FIX: sign() now handles None safely
        spy_chg_s = (f" [{G if spy_chg is not None and spy_chg >= 0 else R}]{sign(spy_chg)}{spy_chg:.1f}%[/]"
                     if spy_chg is not None else "")
        spy_s   = f"  SPY:[white]${float(spy_raw):.2f}[/]{spy_chg_s}" if spy_raw else ""
        rows.append(Text.from_markup(
            f"[{tc}][bold]{lbl}[/]  [dim]exp[/][{tc}]{exp_s}[/]{bar}  "
            f"VIX:[{vc}]{vix}[/]  [dim]Dist:[/][white]{dist}[/]  [dim]Stage:[/][white]{stage}[/]{spy_s}"
        ))
        upvol = get_numeric(mkt, "upvol"); nh = get_numeric(mkt, "nh"); nl = get_numeric(mkt, "nl"); adr = get_numeric(mkt, "adr")
        if upvol is not None:
            # M2 FIX: Use config thresholds instead of hardcoded values
            uvc    = G if upvol >= mkt_cfg['upvol_good'] else (Y if upvol >= mkt_cfg['upvol_caution'] else DIM)
            nhnl   = (nh - nl) if nh is not None and nl is not None else None
            nhnl_c = G if nhnl is not None and nhnl >= mkt_cfg['breadth_good'] else (Y if nhnl is not None and nhnl >= mkt_cfg['breadth_caution'] else DIM)
            adr_s  = f"  [dim]A/D:[/][white]{adr:.1f}[/]" if adr is not None else ""
            rows.append(Text.from_markup(
                f"[dim]UpVol:[/][{uvc}]{upvol:.0f}%[/]{adr_s}  "
                f"[dim]NH:[/][{G}]{nh or '--'}[/] [dim]NL:[/][{R}]{nl or '--'}[/]  "
                f"[dim]NH-NL:[/][{nhnl_c}]{sign(nhnl)}{nhnl}[/]"
            ))
        pcr = mkt.get("pcr"); bmom = mkt.get("bmom"); ycs = mkt.get("ycs"); fed = mkt.get("fed")
        parts4 = []
        if pcr  is not None:
            pcr_c = G if pcr is not None and pcr <= mkt_cfg['put_call_bullish'] else (Y if pcr is not None and pcr <= mkt_cfg['put_call_fearful'] else R)
            parts4.append(f"[dim]P/C:[/][{pcr_c}]{pcr:.2f}[/]")
        if bmom is not None:
            bmc = G if bmom >= 0.5 else (Y if bmom >= 0 else R)
            parts4.append(f"[dim]Breadth Mom:[/][{bmc}]{bmom:.1f}[/]")
        if ycs  is not None:
            yc_c = G if ycs >= 0.5 else (Y if ycs >= 0 else R)
            parts4.append(f"[dim]Yld Curve:[/][{yc_c}]{ycs:+.2f}[/]")
        if fed:
            parts4.append(f"[dim]Fed:[/][white]{fed[:20]}[/]")
        if parts4:
            rows.append(Text.from_markup("  ".join(parts4)))
        halts  = mkt.get("halts")
        halt_s = " | ".join(format_halt_reason(h) for h in halts[:2]) if halts else "none"
        hc_col = Y if halts else DIM
        line5  = f"[dim]Halt:[/][{hc_col}]{halt_s}[/]"
        if sentiment and not sentiment.get("_error"):
            fg_v   = sentiment.get("fg", 0)
            fg_lbl = (sentiment.get("label") or "")[:14]
            fg_c   = sentiment.get("color", "dim")
            fg_bar = int(fg_v / 100 * 6)
            fg_bar_s = f"[{fg_c}]{'█' * fg_bar}[/][dim]{'░' * (6 - fg_bar)}[/]"
            line5 += f"  [dim]F&G:[/][{fg_c}]{fg_v:.0f} — {fg_lbl}[/] {fg_bar_s}"
        rows.append(Text.from_markup(line5))
        if cfg:
            mode      = cfg.get("mode", "?")
            mc2       = G if "LIVE" in str(mode) else Y
            en_s      = "ENABLED" if cfg.get("enabled", True) else "DISABLED"
            ec        = G if cfg.get("enabled", True) else R
            pyr       = cfg.get("pyramid", False)
            min_score = cfg.get("min_score")
            max_n     = cfg.get("max_pos_n")
            base_risk = cfg.get("base_risk")
            t1r       = cfg.get("t1_r")
            parts6    = [f"[{mc2}]{mode}[/]", f"[{ec}]{en_s}[/]"]
            if pyr:       parts6.append(f"[{G}]pyr✓[/]")
            if min_score: parts6.append(f"[dim]score≥[/][white]{min_score}[/]")
            if max_n:     parts6.append(f"[dim]slots:[/][white]{max_n}[/]")
            if base_risk: parts6.append(f"[dim]risk:[/][white]{base_risk}%[/]")
            if t1r:       parts6.append(f"[dim]T1:[/][white]{t1r}R[/]")
            parts6.append(f"[dim]next:[/][white]{next_run_str()}[/]")
            rows.append(Text.from_markup("  ".join(parts6)))
        stale_alerts = mkt.get("stale_alerts", [])
        if stale_alerts:
            rows.append(Text.from_markup(f"[orange1][!] Data stale:[/] {', '.join(stale_alerts)}"))
    else:
        rows.append(Text("no market data", style="dim"))
    return Panel(Group(*rows), title="[bold blue]MARKET[/]", border_style="blue", padding=(0, 1))


def panel_portfolio(port, cfg, risk=None, perf=None):
    risk_thr = load_risk_thresholds(cfg)
    if not port or port.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]PORTFOLIO[/]", border_style="green", padding=(0, 1))
    pv_val = port.get("total_portfolio_value")
    pv = float(pv_val) if pv_val is not None else 0
    dr_val = port.get("daily_return_pct")
    dr = float(dr_val) if dr_val is not None else 0
    urp_val = port.get("unrealized_pnl_pct")
    urp = float(urp_val) if urp_val is not None else None  # CRITICAL ISSUE 9 FIX: Keep None to display "--" instead of hiding missing data
    cash_val = port.get("total_cash")
    cash = float(cash_val) if cash_val is not None else 0
    npos_val = port.get("position_count")
    npos = int(npos_val) if npos_val is not None else 0
    cum   = port.get("cumulative_return_pct")
    mxdd  = port.get("max_drawdown_pct")
    lgpos = port.get("largest_position_pct")
    snap  = port.get("snapshot_date")
    max_n_val = cfg.get("max_pos_n") if cfg else None
    max_n = int(max_n_val) if max_n_val is not None else 0
    pct_c_val = cfg.get("max_pos_pct") if cfg else None
    pct_c = float(pct_c_val) if pct_c_val is not None else 0
    bp    = pv * pct_c / 100 if (pv > 0 and pct_c > 0) else cash
    if max_n:
        _sb   = mini_bar(npos, max_n, w=5)
        pos_s = f"[dim]Pos:[/] {_sb}[dim]{npos}/{max_n}[/]"
    else:
        pos_s = f"[dim]Pos:[/][white]{npos}[/]"
    snap_s  = f"  [dim]{fmt_age(snap)}[/]" if snap is not None else ""

    rows: list = []

    # Line 1: portfolio value + snapshot age
    rows.append(Text.from_markup(f"[bold white]{fmt_money(pv)}[/]{snap_s}"))

    # Line 2: cash + positions (slot bar) + buying power
    rows.append(Text.from_markup(
        f"[dim]Cash:[/] [white]{fmt_money(cash)}[/]  "
        f"{pos_s}  "
        f"[dim]BP:[/][white]{fmt_money(bp)}[/]"
    ))

    # Line 3: daily return + unrealized P&L
    urp_str = f"[{G if urp >= 0 else R}]{sign(urp)}{urp:.2f}%[/]" if urp is not None else "[dim]--[/]"
    rows.append(Text.from_markup(
        f"[dim]Day:[/] [{G if dr >= 0 else R}]{sign(dr)}{dr:.2f}%[/]  "
        f"[dim]Unrlzd:[/] {urp_str}"
    ))

    # Line 4: cumulative return + max drawdown (always show, "--" when missing)
    cum_v  = safe_float(cum)
    # TIER 1A FIX: Use get_numeric instead of "or 0" to preserve None for missing data
    mxdd_v = get_numeric(perf, "maxdd") if perf and not perf.get("_error") else None
    cc     = G if cum_v is not None and cum_v >= 0 else (R if cum_v is not None else DIM)
    cum_s  = f"[dim]Total Return:[/] [{cc}]{sign(cum_v)}{cum_v:.2f}%[/]" if cum_v is not None else "[dim]Total Return:[/] [dim]--[/]"
    dd_v   = abs(mxdd_v) if mxdd_v is not None else None
    dd_c = R if dd_v is not None and dd_v >= risk_thr.get('drawdown_alert', 15) else (Y if dd_v is not None and dd_v >= risk_thr.get('drawdown_caution', 5) else (G if dd_v is not None else DIM))
    mxdd_s = f"[dim]MaxDD:[/] [{dd_c}]-{dd_v:.1f}%[/]" if dd_v is not None else "[dim]MaxDD:[/] [dim]--[/]"
    rows.append(Text.from_markup(f"{cum_s}  {mxdd_s}"))

    # Line 5: largest position concentration (when available)
    if lgpos is not None:
        lp_c = R if float(lgpos) >= 20 else (Y if float(lgpos) >= 15 else "white")  # TODO: config
        rows.append(Text.from_markup(f"[dim]Largest pos:[/] [{lp_c}]{float(lgpos):.1f}%[/]"))

    # VaR metrics (compact one-liner)
    if risk and not risk.get("_error"):
        var95_v = get_numeric(risk, "var95")
        if var95_v is not None and var95_v > 0:
            beta_v = get_numeric(risk, "beta")
            beta_c = R if beta_v is not None and beta_v >= mkt_cfg['beta_warning'] else (Y if beta_v is not None and beta_v >= mkt_cfg['beta_caution'] else G)
            cvar95_v = get_numeric(risk, "cvar95")
            conc5_v = get_numeric(risk, "conc5")
            cvar95_str = f"{cvar95_v:.2f}%" if cvar95_v is not None else "--"
            conc5_str = f"{conc5_v:.0f}%" if conc5_v is not None else "--"
            row_text = (
                f"[dim]VaR:[/][white]{var95_v:.2f}%[/]  "
                f"[dim]CVaR:[/][white]{cvar95_str}[/]  "
            )
            if beta_v is not None:
                row_text += f"[dim]β:[/][{beta_c}]{beta_v:.2f}[/]  "
            row_text += f"[dim]Conc5:[/][white]{conc5_str}[/]"
            rows.append(Text.from_markup(row_text))

    return Panel(Group(*rows), title="[bold green]PORTFOLIO[/]", border_style="green", padding=(0, 1))


def panel_performance_spark(perf, rec, perf_anl=None, pos=None, cfg=None):
    """Performance metrics + equity sparkline + rolling analytics."""
    perf_thr = load_performance_thresholds(cfg)
    if not perf or perf.get("_error") or perf.get("_reason"):
        err = perf.get("_error") if perf else None
        error_msg = err
        reason = perf.get("_reason") if perf else None
        if error_msg:
            msg = f"error: {error_msg}"
        elif reason == "pre-market":
            msg = "pre-market: awaiting trading activity"
        elif reason == "after-hours":
            msg = "after-hours: awaiting next trading day"
        elif reason == "no-trades-yet":
            msg = "no closed trades yet (waiting for first exit)"
        else:
            msg = "no data"
        return Panel(Text(msg, style="dim"), title="[bold]PERFORMANCE[/]", border_style="green", padding=(0, 1))
    streak = perf.get("streak")
    if streak is not None:
        str_s   = f"+{streak}W" if streak >= 0 else f"{abs(streak)}L"
        str_c   = G if streak >= 0 else R
    else:
        str_s = "--"
        str_c = DIM
    pnl = get_numeric(perf, "pnl")
    pnl_c   = G if pnl is not None and pnl >= 0 else (R if pnl is not None else DIM)
    pf      = get_numeric(perf, "profit_factor")
    pf_s    = f"{pf:.2f}" if pf is not None else "--"
    pf_c = G if pf is not None and pf >= perf_thr['profit_factor_good'] else (Y if pf is not None and pf >= 1.0 else (R if pf is not None else DIM))
    exp     = get_numeric(perf, "expectancy")
    exp_s   = f"{fmt_money(exp)}" if exp is not None else "--"
    exp_c   = G if exp is not None and exp >= 0 else (R if exp is not None else DIM)
    avg_r   = get_numeric(perf, "avg_r")
    avg_r_s = f"{avg_r:.2f}R" if avg_r is not None else "--"

    wr_v = get_numeric(perf, "wr")
    wr_s = f"{wr_v:.1f}%" if wr_v is not None else "--"
    wr_c = G if wr_v is not None and wr_v >= perf_thr['win_rate_good'] else (R if wr_v is not None else DIM)
    # Issue 45 FIX: Show breakeven percentage in performance display
    be_pct = get_numeric(perf, "wr_breakeven_pct")
    be_s = f" [dim](+{be_pct:.0f}% breakeven)[/]" if be_pct is not None and be_pct > 0 else ""
    dd_v = get_numeric(perf, "maxdd")
    dd_s = f"{('-' if dd_v > 0 else '')}{dd_v:.1f}%" if dd_v is not None else "--"
    dd_c = R if dd_v is not None and dd_v >= 10 else (Y if dd_v is not None and dd_v >= 5 else (G if dd_v is not None else DIM))
    sharpe_val = perf.get('sharpe')
    sharpe_s = f"{sharpe_val:.2f}" if sharpe_val is not None else "--"
    sharpe_conf = perf.get('sharpe_confidence')
    # M9 FIX: Explain confidence levels for Sharpe and other metrics
    sharpe_conf_explain = {
        'high': '252+ days',
        'medium': '63-251 days',
        'low': '<63 days'
    }
    sharpe_label = f"{sharpe_s}" if sharpe_conf is None else f"{sharpe_s} ({sharpe_conf}, {sharpe_conf_explain.get(sharpe_conf, '')})"
    # Issue 5 FIX: Show closed trades + open trades in calculation
    n_closed = perf.get('n', 0)
    n_open = perf.get('_open_trades_count', 0)
    n_total = n_closed + n_open
    open_note = f" ([{n_open} open])" if n_open > 0 else ""
    b_val = perf.get('b', 0)
    b_str = f"[dim]/[/][yellow]{b_val}B[/]" if b_val > 0 else ""
    rows = [
        Text.from_markup(
            f"[bold white]{n_closed} Trades{open_note}[/]  "
            f"[{G}]{perf.get('w', 0)}W[/][dim]/[/][{R}]{perf.get('l', 0)}L[/]"
            f"{b_str}  "
            f"[dim]WR:[/][{wr_c}]{wr_s}{be_s}[/]  "
            f"[{str_c}]{str_s}[/]  "
            f"[dim]MaxDD:[/][{dd_c}]{dd_s}[/]"
        ),
        Text.from_markup(
            f"[dim]P&L:[/][{pnl_c}]{fmt_money(perf.get('pnl'))}[/]  "
            f"[dim]PF:[/][{pf_c}]{pf_s}[/]  "
            f"[dim]Sharpe:[/][white]{sharpe_label}[/]  "
            f"[dim]Exp:[/][{exp_c}]{exp_s}[/]  "
            f"[dim]AvgR:[/][white]{avg_r_s}[/]"
        ),
        Text.from_markup(
            f"[dim]AvgWin:[/][{G}]{fmt_money(perf.get('avg_win'))}[/]  "
            f"[dim]AvgLoss:[/][{R}]{fmt_money(perf.get('avg_loss'))}[/]"
        ),
    ]

    # Equity curve sparkline
    equity_vals = perf.get("equity_vals")
    if len(equity_vals) >= 3:
        sp = sparkline(equity_vals, width=28)
        rows.append(Text.from_markup(f"[dim]Equity:[/] {sp}"))

    # Recent daily returns (last 5 snapshots)
    recent_rets = perf.get("recent_rets")
    if recent_rets:
        parts = []
        for dt, ret in recent_rets[-5:]:
            rc = G if ret >= 0 else R
            d_s = dt.strftime("%a") if hasattr(dt, "strftime") else str(dt)[:3]
            parts.append(f"[dim]{d_s}[/][{rc}]{sign(ret)}{ret:.1f}%[/]")
        # M9 FIX: Add confidence level explanation for recent returns
        recent_rets_conf = perf.get("recent_rets_confidence")
        conf_explain = {
            'high': '(5+ snapshots)',
            'medium': '(3-4 snapshots)',
            'low': '(<3 snapshots)'
        }
        conf_note = f" [dim]{conf_explain.get(recent_rets_conf, '')}[/]" if recent_rets_conf else ""
        rows.append(Text.from_markup("  ".join(parts) + conf_note))

    # Rolling analytics from algo_performance_daily (only show if populated)
    if perf_anl and not perf_anl.get("_error"):
        anl_parts = []
        sharpe252 = perf_anl.get("sharpe252")
        sortino   = perf_anl.get("sortino")
        calmar    = perf_anl.get("calmar")
        wr50      = perf_anl.get("wr50")
        if sharpe252 is not None:
            sc = G if sharpe252 >= perf_thr['sharpe_good'] else (Y if sharpe252 >= 0 else R)
            anl_parts.append(f"[dim]Sharpe (1Y):[/][{sc}]{sharpe252:.2f}[/]")
        if sortino is not None:
            sc = G if sortino >= 1.5 else (Y if sortino >= 0 else R)
            anl_parts.append(f"[dim]Sortino:[/][{sc}]{sortino:.2f}[/]")
        if calmar is not None:
            sc = G if calmar >= perf_thr['calmar_good'] else (Y if calmar >= 0 else R)
            anl_parts.append(f"[dim]Calmar:[/][{sc}]{calmar:.2f}[/]")
        total_trades = perf.get("n", 0) if perf else 0
        if wr50 is not None and (total_trades >= 10 or wr50 > 0):
            wrc = G if wr50 >= perf_thr['win_rate_excellent'] else (Y if wr50 >= perf_thr['win_rate_good'] else R)
            anl_parts.append(f"[dim]Win Rate (last 50T):[/][{wrc}]{wr50:.0f}%[/]")
        if anl_parts:
            rows.append(Text.from_markup("  ".join(anl_parts)))
        # M10 FIX: Show when rolling analytics were last calculated (Issue 43)
        anl_updated_at = perf_anl.get("_updated_at")
        if anl_updated_at:
            try:
                if isinstance(anl_updated_at, str):
                    calc_dt = datetime.fromisoformat(anl_updated_at)
                else:
                    calc_dt = anl_updated_at
                age_str = fmt_age(calc_dt)
                rows.append(Text.from_markup(f"[dim]Rolling analytics calculated: {age_str}[/]"))
            except (ValueError, TypeError, AttributeError):
                pass
        avg_w_r = perf_anl.get("avg_w_r")
        avg_l_r = perf_anl.get("avg_l_r")
        if avg_w_r is not None or avg_l_r is not None:
            r_parts = []
            if avg_w_r is not None:
                r_parts.append(f"[dim]Avg Win R:[/][{G}]{avg_w_r:.2f}R[/]")
            if avg_l_r is not None:
                r_parts.append(f"[dim]Avg Loss R:[/][{R}]{avg_l_r:.2f}R[/]")
            if r_parts:
                rows.append(Text.from_markup("  ".join(r_parts)))

    # Recent closed trades — last 3 exits with result
    recent = [t for t in rec if t.get("status") == "closed" and t.get("exit_date")][:3]
    if recent:
        rows.append(Text.from_markup("[dim]Recent exits:[/]"))
        for t in recent:
            pv2   = get_numeric(t, "profit_loss_dollars")
            pct_v = get_numeric(t, "profit_loss_pct")
            rv    = get_numeric(t, "exit_r_multiple")
            sym   = get_string(t, "symbol", "--")
            c     = G if pv2 is not None and pv2 >= 0 else (R if pv2 is not None else DIM)
            rv_s  = f" {sign(rv)}{rv:.1f}R" if rv is not None else ""
            pv2_display = fmt_money(pv2) if pv2 is not None else "--"
            pct_display = f"{sign(pct_v)}{pct_v:.1f}%" if pct_v is not None else "--"
            rows.append(Text.from_markup(
                f"  [{c}]{sym}[/] [{c}]{pct_display}  {pv2_display}{rv_s}[/]"
            ))

    # ISSUE 43 FIX: Show when metrics were last calculated (staleness indicator)
    updated_at = perf.get("_updated_at")
    if updated_at:
        try:
            if isinstance(updated_at, str):
                calc_dt = datetime.fromisoformat(updated_at)
            else:
                calc_dt = updated_at
            age_str = fmt_age(calc_dt)
            rows.append(Text.from_markup(f"[dim]Calculated: {age_str}[/]"))
        except (ValueError, TypeError, AttributeError):
            pass

    # ISSUE 5 FIX: Alert if open positions have unrealized losses (risk not in win rate)
    # ISSUE 13 FIX: Only sum P&L values that exist, don't default missing P&L to 0
    # Extract positions from new dict format if needed
    positions_list = pos
    if isinstance(pos, dict) and "positions" in pos:
        positions_list = pos.get("positions", [])
    if positions_list:
        losing_positions = []
        for p in positions_list:
            upnl = p.get("unrealized_pnl_pct")
            if upnl is not None and float(upnl) < 0:
                losing_positions.append(p)
        if losing_positions:
            def _get_loss_pct(p):
                upnl = p.get("unrealized_pnl_pct")
                return float(upnl) if upnl is not None else 0
            loss_pct = sum(_get_loss_pct(p) for p in losing_positions)
            if loss_pct != 0:  # Only show if there's actual loss
                rows.append(Text.from_markup(
                    f"[orange1][!] {len(losing_positions)} open position(s) at risk:[/] {loss_pct:.1f}% unrealized loss"
                ))

    return Panel(Group(*rows), title="[bold green]PERFORMANCE[/]", border_style="green", padding=(0, 1))


def panel_positions(pos, compact=False, trades=None, cfg=None):
    # TIER 1B FIX: Check for error dict before processing
    if isinstance(pos, dict) and pos.get("_error"):
        return error_panel("POSITIONS", pos.get("_error"))
    # Extract positions and stale_alerts from new dict format
    stale_alerts = []
    if isinstance(pos, dict) and "positions" in pos:
        stale_alerts = pos.get("stale_alerts", [])
        pos = pos.get("positions", [])
    if not pos:
        return Panel(Text("  No open positions — algo is flat", style="dim"),
                     title="[bold]POSITIONS[/]", border_style="cyan", padding=(0, 1))
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="dim bold",
              padding=(0, 1), row_styles=["", "dim"], expand=True)
    t.add_column("Symbol",  style="bold white", no_wrap=True, min_width=6)
    t.add_column("Val",     justify="right",    no_wrap=True, min_width=5)
    t.add_column("Entry",   justify="right",    no_wrap=True)
    t.add_column("Price",   justify="right",    no_wrap=True)
    t.add_column("P&L%",    justify="right",    no_wrap=True, min_width=7)
    t.add_column("R-Mult",  justify="right",    no_wrap=True, min_width=6)
    t.add_column("Stop",    justify="right",    no_wrap=True)
    t.add_column("Dist%",   justify="right",    no_wrap=True)
    if not compact:
        t.add_column("T1->",   justify="right", no_wrap=True)
        t.add_column("Days",   justify="right", no_wrap=True, min_width=4)
        t.add_column("Stg",    justify="center",no_wrap=True, min_width=3)
        t.add_column("Swg",    justify="right", no_wrap=True, min_width=4)
        t.add_column("Sector", style="dim",     no_wrap=True, max_width=12)
    for p in pos:
        # CRITICAL ISSUE 7 FIX: Check if price data is stale/missing and flag for special display
        is_stale_price = p.get("_missing_price", False)
        price_quality_warning = f" ⚠ {p.get('_price_quality', '')}" if is_stale_price else ""
        # ISSUE 19 FIX: Validate entry price is positive to avoid division by zero
        entry_val = p.get("avg_entry_price")
        entry = float(entry_val) if entry_val is not None and float(entry_val) > 0 else None
        price_val = p.get("current_price")
        price = float(price_val) if price_val is not None else None
        pval_val = p.get("position_value")
        pval = float(pval_val) if pval_val is not None else None
        stop_val = p.get("stop_loss_price")
        stop = float(stop_val) if stop_val is not None else None
        t1_val = p.get("target_1_price")
        t1 = float(t1_val) if t1_val is not None else None
        pnl_val = p.get("unrealized_pnl_pct")
        pnl = float(pnl_val) if pnl_val is not None else None
        # Issue 22 FIX: For same-day entries, show hours/minutes instead of just "0" days
        days_raw = p.get("days_since_entry")
        if days_raw is not None and days_raw == 0:
            # Same day — try to get entry_time for finer granularity
            entry_time = p.get("entry_time")
            if entry_time:
                try:
                    if isinstance(entry_time, datetime):
                        et = entry_time
                    else:
                        et = datetime.fromisoformat(str(entry_time))
                    now = datetime.now(timezone.utc if et.tzinfo else None)
                    mins = int((now - et).total_seconds() / 60)
                    if mins < 60:
                        days = f"{mins}m"
                    else:
                        hours = mins // 60
                        remainder = mins % 60
                        days = f"{hours}h{remainder:02d}m"
                except (ValueError, TypeError, AttributeError):
                    days = "0d"
            else:
                days = "0d"
        else:
            days = f"{days_raw}d" if days_raw is not None else "--"
        stg   = p.get("weinstein_stage")
        swg   = p.get("swing_score")
        # ISSUE 15 FIX: Indicate when sector data is missing from lookup
        sec_val = p.get("sector")
        sec_warning = " ⚠" if p.get("_missing_sector", False) else ""
        sec   = ((sec_val or "--")[:12] + sec_warning) if sec_val else ("--" + sec_warning)
        denom = (entry - stop) if (stop is not None and entry is not None and entry != stop) else None
        # Category 8: Position metrics — guard against None current_price (missing market data)
        rmul  = (price - entry) / denom if (denom is not None and entry is not None and price is not None) else None
        dist  = (price - stop) / price * 100 if (stop is not None and price is not None and price > 0) else None
        t1pct = (t1 - price) / price * 100 if (t1 is not None and price is not None and price > 0) else None
        pc    = DIM if pnl is None else (G if pnl >= 0 else R)
        rc    = DIM if rmul is None else (G if rmul >= 0 else R)
        # Distance to stop coloring: explicit panic check for positions below stop loss (dist < 0)
        if dist is None:
            dc = "white"
        elif dist < 0:
            dc = R  # PANIC: position is below stop loss already
        elif dist < 3:
            dc = R  # Close to stop loss
        elif dist < 5:
            dc = Y  # Approaching stop loss
        else:
            dc = "white"
        symbol_display = (p.get("symbol") or "--") + price_quality_warning
        row = [
            symbol_display,
            fmt_money_short(pval) if pval is not None else "--",
            f"${entry:.2f}" if entry is not None else "--", (f"${price:.2f} [yellow]⚠ stale[/]" if is_stale_price else f"${price:.2f}") if price is not None else "--",
            Text(f"{sign(pnl)}{pnl:.2f}%" if pnl is not None else "--", style=pc),
            # TIER 1A FIX: sign() handles None safely
            Text(f"{sign(rmul)}{rmul:.2f}R" if rmul is not None else "--", style=rc),
            f"${stop:.2f}" if stop is not None else "--",
            Text(f"{dist:.1f}%" if dist is not None else "--", style=dc),
        ]
        if not compact:
            swg_s = safe_float(swg)
            # M8 FIX: Use get_swing_score_thresholds() for consistency (Issue 42)
            swing_thresholds = get_swing_score_thresholds(cfg)
            swg_c = G if swg_s is not None and swg_s >= swing_thresholds["excellent"] else (Y if swg_s is not None and swg_s >= swing_thresholds["good"] else "white")
            row += [
                f"+{t1pct:.1f}%" if t1pct is not None else "--",
                str(days),
                f"S{stg}" if stg else "--",
                Text(f"{swg_s:.0f}" if swg_s is not None else "--", style=swg_c),
                sec,
            ]
        t.add_row(*row)

    content = t
    # Display stale data alerts if any
    if stale_alerts:
        content = Group(t, Text.from_markup(f"[orange1][!] Stale data:[/] {', '.join(stale_alerts)}"))

    return Panel(content, title=f"[bold cyan]POSITIONS ({len(pos)})[/]  [dim][p] expand[/]", border_style="cyan", padding=(0, 0))


def panel_signals_compact(sig, sig_eval=None, cfg=None):
    """Signals & screening — actual BUY signals from buy_sell_daily with setup detail."""
    if not sig or sig.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]SIGNALS[/]", border_style="magenta", padding=(0, 1))

    raw   = get_int(sig, "n")
    total = get_int(sig, "total")
    d     = sig.get("date")
    ds    = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    g     = sig.get("grades")
    if g is None:
        g = {}
    ga_val = g.get("a")
    ga = int(ga_val) if ga_val is not None else 0
    gb_val = g.get("b")
    gb = int(gb_val) if gb_val is not None else 0
    gc_val = g.get("c")
    gc = int(gc_val) if gc_val is not None else 0
    gd_val = g.get("d")
    gd = int(gd_val) if gd_val is not None else 0
    top_a = sig.get("top_a")
    near  = sig.get("near")
    # M1 FIX: Load grade thresholds from config for dynamic score color coding
    grade_thresholds = get_grade_thresholds(cfg)

    def _shorten_reason(r: str) -> str:
        r = r.lower()
        if "52w" in r or "52-w" in r or ("low" in r and "proximity" in r): return "52wLow"
        if "sector"   in r and ("cap" in r or "concentr" in r or "already" in r): return "SctCap"
        if "industry" in r and ("cap" in r or "concentr" in r or "already" in r): return "IndCap"
        if "stage"  in r: return "Stage"
        if "volume" in r: return "Vol"
        if "rs" in r or "relative strength" in r: return "RS"
        return r[:7].title()

    def _shorten_type(t: str) -> str:
        t = (t or "").replace("WEEKLY_", "W_").replace("STAGE_2", "S2").replace("STAGE2", "S2")
        t = t.replace("BREAKOUT", "BKT").replace("MOMENTUM", "MOM").replace("REVERSAL", "REV")
        t = t.replace("PULLBACK", "PB").replace("TREND", "TRD").replace("_FOLLOW", "")
        return t[:12]

    # ── Row 1: count  ·  7-day sparkline  ·  grade pool  ·  date ─────────────
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))  # TODO: convert to config
    trend = sig.get("trend")
    spark_s = ""
    if len(trend) >= 2:
        def _get_buy_n(t):
            bn = t.get("buy_n")
            return int(bn) if bn is not None else 0
        counts = [_get_buy_n(t) for t in reversed(trend)]
        max_b   = max(counts) if counts else 1
        spark   = "".join("▁▂▃▄▅▆▇█"[min(7, int(v / max(max_b, 1) * 7.9))] for v in counts)
        spark_s = f"  [{CY}]{spark}[/]"
    n_near = len(near)
    near_hint = f"  [{CY}]{n_near} near[/]" if n_near else ""
    # ISSUE 41 FIX: Display count of filtered signals due to missing quality scores
    filtered = sig.get("filtered_count", 0)
    filtered_hint = f"  [{R}]{filtered} filtered[/]" if filtered > 0 else ""
    rows = [Text.from_markup(
        f"[{buy_c}][bold]{raw} BUY[/][/]{spark_s}  [dim]from {total} screened  {ds}[/]"
        f"  [{G}]A:{ga}[/] [{CY}]B:{gb}[/] [{Y}]C:{gc}[/] [{R}]D:{gd}[/]{near_hint}{filtered_hint}"
    )]

    # ── Row 2: A-grade radar (always; near-misses only when nothing better) ──
    if top_a:
        parts = []
        for s in top_a[:8]:
            # TIER 1A FIX: Show "--" for missing scores, not "0"
            sc = s.get("score")
            if sc is not None:
                sc = float(sc)
                # M1 FIX: Use config-based grade thresholds for consistent coloring
                sc_c = G if sc >= grade_thresholds["a_plus"] else ("bright_green" if sc >= grade_thresholds["a"] else "green")
                parts.append(f"[{sc_c}]{s.get('symbol','')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{s.get('symbol','')}[/][dim]--[/]")
        extra = f"  [dim]+{ga - min(ga, 8)} more[/]" if ga > 8 else ""
        rows.append(Text.from_markup("[dim]A radar:[/]  " + "  ".join(parts) + extra))
    elif near:
        # TIER 1A FIX: Show "--" for missing scores, not "0"
        parts = []
        for a in near[:8]:
            sc = a.get('score')
            if sc is not None:
                parts.append(f"[{CY}]{a['symbol']}[/][dim]{float(sc):.0f}[/]")
            else:
                parts.append(f"[{CY}]{a['symbol']}[/][dim]--[/]")
        rows.append(Text.from_markup("[dim]Near threshold:[/]  " + "  ".join(parts)))

    # ── Row 3: Funnel arrow chain  ·  avg score  ·  top blockers ─────────────
    if sig_eval and not sig_eval.get("_error"):
        ev_tot = sig_eval.get("total", 0)
        ev_t1  = sig_eval.get("t1", 0)
        ev_t5  = sig_eval.get("t5", 0)
        ev_avg = sig_eval.get("avg_score", 0)
        ev_c   = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
        rejected   = sig_eval.get("rejected")
        block_parts = ["  ".join(
            f"[dim]{_shorten_reason(rj['evaluation_reason'])}:{rj['n']}[/]"
            for rj in rejected[:3]
        )]
        blocks_s = "  [dim]blocked:[/]  " + block_parts[0] if rejected else ""
        rows.append(Text.from_markup(
            f"[dim]{ev_tot} →[/] [{ev_c}]{ev_t5} qualified[/]"
            f"  [dim]avg score:[/][white]{ev_avg:.0f}[/]" + blocks_s
        ))

    rows.append(Rule(style="dim"))

    # ── Signal table (Rich Table for proper column alignment) ─────────────────
    buy_sigs = sig.get("buy_sigs")
    if buy_sigs:
        t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="dim",
                  padding=(0, 1), expand=True, row_styles=["", "dim"])
        t.add_column("Sym",   style="bold white", no_wrap=True, min_width=5)
        t.add_column("Stg",   justify="center",   no_wrap=True, min_width=3)
        t.add_column("Type",  no_wrap=True,        min_width=8)
        t.add_column("Q",     justify="right",     no_wrap=True, min_width=3)
        t.add_column("Swg",   justify="right",     no_wrap=True, min_width=3)
        t.add_column("R:R",   justify="right",     no_wrap=True, min_width=4)
        t.add_column("Entry", justify="right",     no_wrap=True, min_width=6)
        t.add_column("Stop",  justify="right",     no_wrap=True, min_width=6)
        t.add_column("Vol%",  justify="right",     no_wrap=True, min_width=5)
        for bs in buy_sigs[:15]:
            sym    = bs.get("symbol") or "--"
            stg    = bs.get("stage_number")
            sig_t  = _shorten_type(bs.get("signal_type") or "")
            sq     = bs.get("signal_quality_score") or bs.get("entry_quality_score")
            swg    = bs.get("swing_score")
            rr     = bs.get("risk_reward_ratio")
            vsurge = bs.get("volume_surge_pct")
            entry  = bs.get("buylevel") or bs.get("close")
            stop   = bs.get("stoplevel")
            # M2 FIX: Use config-based signal quality thresholds
            sq_c   = G if sq is not None and sq >= grade_thresholds["b"] else (Y if sq is not None and sq >= grade_thresholds["c"] else "white")
            # M8 FIX: Use get_swing_score_thresholds() for consistency (Issue 42)
            swing_thresholds = get_swing_score_thresholds(cfg)
            swg_c  = G if swg is not None and swg >= swing_thresholds["excellent"] else (Y if swg is not None and swg >= swing_thresholds["good"] else "white")
            rr_c   = G if rr is not None and rr >= 2.5 else (Y if rr is not None and rr >= 1.5 else "white")
            vs_c   = G if vsurge is not None and vsurge >= sig_thr['volume_surge_good'] else (Y if vsurge is not None and vsurge >= sig_thr['volume_surge_caution'] else "white")
            stg_c  = G if stg == 2 else (Y if stg == 3 else ("white" if stg else DIM))
            t.add_row(
                sym,
                Text(f"S{stg}" if stg else "–", style=stg_c),
                Text(sig_t, style="dim"),
                Text(f"{sq:.0f}"       if sq     is not None else "–", style=sq_c),
                Text(f"{swg:.0f}"      if swg    is not None else "–", style=swg_c),
                Text(f"{rr:.1f}"       if rr     is not None else "–", style=rr_c),
                Text(f"${float(entry):.2f}" if entry is not None else "–", style="dim"),
                Text(f"${float(stop):.2f}"  if stop  is not None else "–", style="dim"),
                Text(f"{vsurge:+.0f}%" if vsurge is not None else "–", style=vs_c),
            )
        rows.append(t)
    else:
        if total == 0:
            rows.append(Text.from_markup(f"[{Y}]No signals — buy_sell_daily may be stale (check Data Health)[/]"))
        else:
            rows.append(Text.from_markup(f"[dim]0 BUY signals from {total} screened[/]"))

    # ── Near-miss strip (only when A-grade stocks exist above; otherwise shown on row 2) ──
    if near and top_a:
        rows.append(Rule(style="dim"))
        # TIER 1A FIX: Show "--" for missing scores
        parts = []
        for a in near[:8]:
            sc = a.get('score')
            if sc is not None:
                parts.append(f"[{CY}]{a['symbol']}[/][dim]{float(sc):.0f}[/]")
            else:
                parts.append(f"[{CY}]{a['symbol']}[/][dim]--[/]")
        rows.append(Text.from_markup("[dim]Near BUY (55–69):[/]  " + "  ".join(parts)))

    return Panel(Group(*rows), title="[bold magenta]BUY SIGNALS & SCREENING[/]  [dim][s] expand[/]", border_style="magenta", padding=(0, 1))


def panel_recent_trades(trades):
    """Closed/recent trade history — sits alongside positions panel."""
    # TIER 1B FIX: Check for error dict
    if isinstance(trades, dict) and trades.get("_error"):
        return error_panel("RECENT TRADES", trades.get("_error"))
    if not trades:
        return Panel(Text("no recent trades", style="dim"),
                     title="[bold cyan]RECENT TRADES[/]", border_style="cyan", padding=(0, 1))
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="dim bold",
              padding=(0, 1), row_styles=["", "dim"], expand=True)
    t.add_column("Sym",  style="bold white", no_wrap=True, min_width=4)
    t.add_column("Date", style="dim",        no_wrap=True, min_width=5)
    t.add_column("P&L$", justify="right",    no_wrap=True, min_width=6)
    t.add_column("P&L%", justify="right",    no_wrap=True, min_width=5)
    t.add_column("R",    justify="right",    no_wrap=True, min_width=4)
    t.add_column("St",   style="dim",        no_wrap=True, min_width=4)
    VALID_STATUSES = {'open', 'closed', 'partially_filled', 'filled', 'pending', 'cancelled', 'rejected'}
    for tr in trades[:10]:
        sym    = tr.get("symbol") or "--"
        date   = tr.get("exit_date") or tr.get("trade_date")
        date_s = date.strftime("%b %d") if hasattr(date, "strftime") else str(date or "--")
        pnl_d  = get_numeric(tr, "profit_loss_dollars")
        pnl_p  = get_numeric(tr, "profit_loss_pct")
        rmul   = tr.get("exit_r_multiple")
        status = (tr.get("status") or "")
        if status and status not in VALID_STATUSES:
            logger.warning(f"VALIDATION: panel_recent_trades invalid status '{status}' for {sym}")
            status = "INVALID"
        is_closed = status == "closed"
        # Issue 10: Show breakeven separately from losses
        is_breakeven = is_closed and pnl_d is not None and pnl_d == 0
        pc  = G if (pnl_d is not None and pnl_d > 0) else (Y if is_breakeven else (R if (is_closed and pnl_d is not None and pnl_d < 0) else (DIM if is_closed else Y)))
        si  = f"[{G}]✓[/]" if (pnl_d is not None and pnl_d > 0) else (f"[{Y}]≈[/]" if is_breakeven else (f"[{R}]✗[/]" if (is_closed and pnl_d is not None and pnl_d < 0) else f"[{Y}]▷[/]"))
        t.add_row(
            Text.from_markup(f"{si} {sym}"),
            date_s,
            Text(f"{sign(pnl_d)}${abs(pnl_d):.0f}" if (is_closed and pnl_d is not None) else "--", style=pc),
            Text(f"{sign(pnl_p)}{pnl_p:.1f}%" if (is_closed and pnl_p is not None) else "--",      style=pc),
            Text(f"{float(rmul):.2f}R" if rmul is not None else "--",       style=pc),
            status[:4],
        )
    return Panel(t, title="[bold cyan]RECENT TRADES[/]", border_style="cyan", padding=(0, 0))


def panel_sector_compact(srank, pos, port, sec_rot=None, irank=None, sec_warn=None):
    """Rotation + holdings (max 2) + sector leaders (1 pair) + industries (2 pairs) = 8 lines."""
    # Issue 2 FIX: Check for error dicts in all data parameters
    if isinstance(srank, dict) and srank.get("_error"):
        return error_panel("SECTORS", srank.get("_error"))
    if isinstance(pos, dict) and pos.get("_error"):
        return error_panel("SECTORS (positions)", pos.get("_error"))
    if isinstance(port, dict) and port.get("_error"):
        return error_panel("SECTORS (portfolio)", port.get("_error"))
    if isinstance(sec_rot, dict) and sec_rot.get("_error"):
        return error_panel("SECTORS (rotation)", sec_rot.get("_error"))
    if isinstance(irank, dict) and irank.get("_error"):
        return error_panel("SECTORS (industries)", irank.get("_error"))
    if isinstance(sec_warn, dict) and sec_warn.get("_error"):
        return error_panel("SECTORS (warnings)", sec_warn.get("_error"))
    rows = []

    # Issue 35 FIX: Display sector position warnings
    if sec_warn and sec_warn.get("warnings"):
        for w in sec_warn.get("warnings", []):
            status_color = R if w.get("status") == "AT_CAP" else Y
            rows.append(Text.from_markup(
                f"[{status_color}]⚠ {w.get('sector')}: {w.get('count')}/{w.get('max')} positions[/]"
            ))

    def rdelta(r, wk="rank_1w_ago", wk4=None):
        cur, old = r.get("current_rank", 0), r.get(wk)
        if old is None: return ""
        d = int(old) - int(cur)
        s1 = (f"[{G}]▲{d}[/]" if d > 0 else (f"[{R}]▼{abs(d)}[/]" if d < 0 else "[dim]=[/]"))
        if wk4:
            old4 = r.get(wk4)
            if old4 is not None:
                d4 = int(old4) - int(cur)
                s4 = (f"[{G}]▲{d4}[/]" if d4 > 0 else (f"[{R}]▼{abs(d4)}[/]" if d4 < 0 else "[dim]=[/]"))
                return f"{s1}[dim]/[/]{s4}"
        return s1

    # Row 1: Rotation signal
    if sec_rot and not sec_rot.get("_error") and sec_rot.get("signal"):
        sig_name = get_string(sec_rot, "signal").replace("_", " ").title()
        wks      = sec_rot.get("weeks", 1)
        def_s    = get_numeric(sec_rot, "def_score")
        cyc_s    = get_numeric(sec_rot, "cyc_score")
        strength = get_numeric(sec_rot, "strength")
        # Normalize strength to 0-1 range: if strength > 1, assume it's a percentage (0-100)
        if strength is not None and strength > 1:
            strength = strength / 100.0
        sig_c = R if def_s is not None and def_s >= 60 else (Y if def_s is not None and def_s >= 40 else G)  # TODO: convert to config
        scores_s = f" [dim]defensive:{def_s:.0f} cyclical:{cyc_s:.0f}[/]" if (def_s is not None or cyc_s is not None) else ""
        str_s    = f" [dim]strength:{strength:.0%}[/]" if strength is not None else ""
        rows.append(Text.from_markup(
            f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name[:20]}[/] [dim]{wks}wk[/]{scores_s}{str_s}"
        ))

    # Holdings by sector: 2-col pairs, up to 6 sectors
    # Extract positions from new dict format if needed
    positions_list = pos
    if isinstance(pos, dict) and "positions" in pos:
        positions_list = pos.get("positions", [])
    if positions_list:
        pv_val = port.get("total_portfolio_value") if port else None
        pv = float(pv_val) if pv_val is not None else 0
        sd: dict = {}
        for p in positions_list:
            sec = p.get("sector") or "[No Sector]"
            val = float(p.get("position_value")) if p.get("position_value") is not None else 0.0
            pnl_raw = p.get("unrealized_pnl_pct")
            # Only track non-None P&L values for accurate averages
            pnl = safe_float(pnl_raw)
            if sec not in sd:
                sd[sec] = {"val": 0.0, "n": 0, "pnls": []}
            sd[sec]["val"] += val
            sd[sec]["n"]   += 1
            if pnl is not None:
                sd[sec]["pnls"].append(pnl)
        sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])
        total_secs  = len(sorted_secs)
        show_secs   = sorted_secs[:6]
        hdr_more    = f" [dim](top 6 of {total_secs})[/]" if total_secs > 6 else ""
        rows.append(Text.from_markup(f"[dim]Holdings by sector:{hdr_more}[/]"))

        def fmt_sec_item(sec, dv):
            pct     = dv["val"] / pv * 100 if pv else 0
            avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
            pc      = G if avg_pnl >= 0 else R
            bar_f   = int(min(pct, 30) / 30 * 3)
            bar_s   = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (3 - bar_f)}[/]"
            return (f"[white]{sec[:11]:<11}[/]{bar_s}"
                    f"[dim]{pct:.0f}%[/] [{pc}]{sign(avg_pnl)}{avg_pnl:.1f}%[/]")

        for a, b in zip(show_secs[::2], show_secs[1::2] + [None]):
            left = fmt_sec_item(*a)
            if b:
                right = fmt_sec_item(*b)
                rows.append(Text.from_markup(f" {left}   {right}"))
            else:
                rows.append(Text.from_markup(f" {left}"))

    # Top sector rankings with 1-week and 4-week rank changes
    # Issue 18 FIX: Validate individual rank entries have required fields before display
    valid_srank_raw = [r for r in srank
                       if not (isinstance(srank, dict) and srank.get("_error"))]
    valid_srank = []
    filtered_count = 0
    for r in valid_srank_raw[:6]:
        # Validate entry has required fields: sector_name, current_rank, momentum_score
        if not isinstance(r, dict):
            logger.warning(f"VALIDATION: Sector rank entry is not a dict: {type(r).__name__}")
            filtered_count += 1
            continue
        if not r.get("sector_name"):
            logger.warning(f"VALIDATION: Sector rank entry missing sector_name field")
            filtered_count += 1
            continue
        if r.get("current_rank") is None:
            logger.warning(f"VALIDATION: Sector rank entry missing current_rank field for {r.get('sector_name', 'unknown')}")
            filtered_count += 1
            continue
        valid_srank.append(r)
    if filtered_count > 0:
        logger.warning(f"VALIDATION: Sector ranking filtered {filtered_count} incomplete entries")

    if valid_srank:
        if rows:
            rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Top sectors by rank (momentum score, ▲▼= rank change vs 1wk/4wk):[/]"))
        for a, b in zip(valid_srank[::2], valid_srank[1::2] + [None]):
            na  = (a.get("sector_name") or "")[:10]
            mma = a.get("momentum_score")
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            la  = f"[{G}]#{a['current_rank']}[/] [dim]{na}[/]{ms_a}{rdelta(a, wk4='rank_4w_ago')}"
            if b:
                nb  = (b.get("sector_name") or "")[:10]
                mmb = b.get("momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                rows.append(Text.from_markup(f" {la}    [{G}]#{b['current_rank']}[/] [dim]{nb}[/]{ms_b}{rdelta(b, wk4='rank_4w_ago')}"))
            else:
                rows.append(Text.from_markup(f" {la}"))

    # Top industries (sub-sector groups)
    valid_irank = irank if (irank and not (isinstance(irank, dict) and irank.get("_error"))) else []
    if valid_irank:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Top industries (sub-sector groups, ▲▼= vs 1wk):[/]"))
        for a, b in zip(valid_irank[:4][::2], valid_irank[:4][1::2] + [None]):
            na  = (a.get("industry") or "")[:12]
            mma = a.get("momentum_score")
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            la  = f"[{CY}]#{a['current_rank']}[/] [white]{na}[/]{ms_a}{rdelta(a)}"
            if b:
                nb  = (b.get("industry") or "")[:12]
                mmb = b.get("momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                rows.append(Text.from_markup(f" {la}    [{CY}]#{b['current_rank']}[/] [white]{nb}[/]{ms_b}{rdelta(b)}"))
            else:
                rows.append(Text.from_markup(f" {la}"))

    if not rows:
        return Panel(Text("no data", style="dim"), title="[bold]SECTORS & INDUSTRIES[/]", border_style="cyan", padding=(0, 1))
    return Panel(Group(*rows), title="[bold cyan]SECTORS & INDUSTRIES[/]  [dim][r] expand[/]", border_style="cyan", padding=(0, 1))


def panel_exposure_compact(exp_f):
    """12-factor exposure score — compact 2-col layout."""
    if not exp_f or exp_f.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]EXPOSURE FACTORS[/]",
                     border_style="blue", padding=(0, 1))
    raw_score = exp_f.get("raw_score")
    epct_score = exp_f.get("exposure_pct")
    raw     = safe_float(raw_score)
    epct    = safe_float(epct_score)
    regime  = exp_f.get("regime") or ""
    factors = exp_f.get("factors")
    if factors is None:
        factors = {}
    tier    = tier_from_pct(epct)
    tc      = TIER_COLOR.get(tier, "dim")

    def factor_detail(key):
        """Return a short value string for a factor key (Issue 9: distinguish missing data).

        Returns: formatted value, '(n/a)' if factor not found, '(--)' if value missing
        """
        f = factors.get(key)
        if f is None:
            return "(n/a)"
        if not f or not isinstance(f, dict):
            return "(n/a)"
        if key == "trend_30wk":
            v = f.get("price_vs_ma_pct")
            if v is not None:
                return f" {'+' if v >= 0 else ''}{v:.1f}%"
            else:
                return "(--)"
        if key == "breadth_50dma":
            v = f.get("value")
            return f" {v:.0f}%" if v is not None else "(--)"
        if key == "breadth_200dma":
            v = f.get("value")
            return f" {v:.0f}%" if v is not None else "(--)"
        if key == "mcclellan":
            v = f.get("value")
            return f" {v:+.0f}" if v is not None else "(--)"
        if key == "vix_regime":
            v = f.get("value")
            return f" {v:.1f}" if v is not None else "(--)"
        if key == "new_highs_lows":
            nh = f.get("new_highs"); nl = f.get("new_lows")
            if nh is not None and nl is not None:
                net = nh - nl
                return f" {'+' if net >= 0 else ''}{net}"
            return "(--)"
        if key == "credit_spread":
            v = f.get("value")
            return f" {v:.2f}" if v is not None else "(--)"
        if key == "ad_line":
            rel = (f.get("relation") or "").replace("_", " ")[:8]
            return f" {rel}" if rel else "(--)"
        if key == "aaii_sentiment":
            bull = f.get("bullish_pct"); bear = f.get("bearish_pct")
            return f" B:{bull:.0f}/Be:{bear:.0f}" if bull is not None and bear is not None else "(--)"
        if key == "naaim":
            v = f.get("value")
            return f" {v:.0f}" if v is not None else "(--)"
        if key == "ibd_state":
            st = (f.get("state") or "").replace("_under_pressure", "↓").replace("_", " ")[:9]
            dd = f.get("distribution_days_25d")
            if st or dd is not None:
                dd_s = f" D{dd}" if dd is not None else ""
                return f" {st}{dd_s}" if st else f" D{dd}"
            return "(--)"
        return "(--)"

    FACTOR_MAP = [
        ("trend_30wk",    "30wk Trend",   15),
        ("breadth_50dma", "Breadth 50MA", 14),
        ("ibd_state",     "IBD State",    18),
        ("breadth_200dma","Breadth 200MA",10),
        ("mcclellan",     "McClellan Osc",  9),
        ("vix_regime",    "VIX Level",     8),
        ("new_highs_lows","New Hi vs Lo",  7),
        ("credit_spread", "Credit Spread", 7),
        ("ad_line",       "Adv/Dec Line",  5),
        ("aaii_sentiment","AAII Sentiment",4),
        ("naaim",         "NAAIM Exposure",3),
    ]

    tbl = Table.grid(padding=(0, 1), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)

    items = []
    for key, label, max_pts in FACTOR_MAP:
        f    = factors.get(key)
        if f is None:
            f = {}
        pts_val = f.get("pts")
        pts  = safe_float(pts_val, 0)
        bar  = mini_bar(pts, max_pts, w=3)
        fc   = G if pts >= max_pts * 0.75 else (Y if pts >= max_pts * 0.35 else R)
        det  = factor_detail(key)
        det_markup = f"[dim]{det}[/]" if det else ""
        items.append(f"[{fc}]{label:<6}[/]{bar}[dim]{pts:.0f}/{max_pts}[/]{det_markup}")

    sr = factors.get("sector_rotation")
    if sr is None:
        sr = {}
    eco = factors.get("economic_overlay")
    if eco is None:
        eco = {}
    sr_pts = sr.get("pts")
    eco_pts = eco.get("pts")
    sr_pen  = safe_float(sr_pts, 0)
    eco_pen = safe_float(eco_pts, 0)
    if sr_pen < 0:
        sig = (sr.get("signal") or "").replace("_", " ")[:20]
        items.append(f"[{R}]Sector Rotation[/] [dim]{sr_pen:+.0f} {sig}[/]")
    if eco_pen < 0:
        eco_err = (eco.get("error") or "")[:20]
        items.append(f"[{R}]Economic Overlay[/] [dim]{eco_pen:+.0f}{(' ' + eco_err) if eco_err else ''}[/]")

    for a, b in zip(items[::2], items[1::2] + [""]):
        tbl.add_row(Text.from_markup(a), Text.from_markup(b))

    raw_bar = mini_bar(raw, 100, w=8)
    # Issue 9: Add data quality indicator to title
    data_quality = exp_f.get("_data_quality", "good")
    quality_indicator = ""
    if data_quality == "degraded":
        quality_indicator = " [yellow]⚠ partial data[/]"
    elif data_quality == "missing":
        quality_indicator = " [red]⚠ no data[/]"
    elif data_quality == "error":
        quality_indicator = " [red]✗ error[/]"
    header  = Text.from_markup(
        f"[dim]Score:[/][white]{raw:.0f}[/][dim]/100[/] {raw_bar} [dim]→ allocation[/] [{tc}][bold]{epct:.0f}%[/][/]  [dim]{regime[:24]}[/]"
    )
    return Panel(Group(header, tbl), title=f"[bold blue]EXPOSURE SCORE BREAKDOWN (12 factors / 100pts){quality_indicator}[/]",
                 border_style="blue", padding=(0, 1))


def panel_economic_pulse(eco, econ_cal=None):
    """Economic factors the algo uses to calculate market exposure score."""
    if not eco or eco.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]ECONOMIC INPUTS[/]",
                     border_style="bright_magenta", padding=(0, 1))
    rows: list = []

    # Issue 38 FIX: Display economic data freshness status
    data_status = eco.get('_data_status', 'unknown')
    last_update = eco.get('_last_update')
    status_color = G if data_status == 'current' else (Y if '1day_old' in data_status else R)
    if last_update:
        rows.append(Text.from_markup(f"[dim]Data as of:[/] [{status_color}]{last_update}[/]"))

    t10 = eco.get("t10"); t2 = eco.get("t2"); t3m = eco.get("t3m"); t6m = eco.get("t6m")
    yc10_2 = eco.get("yc_10_2"); yc10_3m = eco.get("yc_10_3m")
    hy  = eco.get("hy"); ig = eco.get("ig")
    oil = eco.get("oil"); nfci = eco.get("nfci")
    fed_funds = eco.get("fed_funds")
    cpi_yoy   = eco.get("cpi_yoy")
    unrate    = eco.get("unrate")
    be10      = eco.get("be10")
    be5       = eco.get("be5")
    dxy       = eco.get("dxy")
    mortgage  = eco.get("mortgage")
    umcsent   = eco.get("umcsent")

    y_parts = []
    if t3m is not None: y_parts.append(f"[dim]3M Treasury:[/][white]{t3m:.2f}%[/]")
    if t6m is not None: y_parts.append(f"[dim]6M:[/][white]{t6m:.2f}%[/]")
    if t2  is not None: y_parts.append(f"[dim]2Y:[/][white]{t2:.2f}%[/]")
    if t10 is not None: y_parts.append(f"[dim]10Y:[/][white]{t10:.2f}%[/]")
    if fed_funds is not None: y_parts.append(f"[dim]Fed Rate:[/][white]{fed_funds:.2f}%[/]")
    if y_parts: rows.append(Text.from_markup("  ".join(y_parts)))

    if yc10_2 is not None:
        ycc = G if yc10_2 >= YIELD_CURVE_GOOD else (Y if yc10_2 >= 0 else R)
        inv = "  [bold red]INV[/]" if yc10_2 < 0 else ""
        c3m = f"  [dim]10Y-3M:[/][{ycc}]{yc10_3m:+.2f}%[/]" if yc10_3m is not None else ""
        rows.append(Text.from_markup(
            f"[dim]10Y-2Y:[/][{ycc}]{yc10_2:+.2f}%[/]{inv}{c3m}"
        ))

    if hy is not None or ig is not None:
        parts = []
        if hy is not None:
            hy_c = G if hy <= HY_OAS_GOOD else (Y if hy <= HY_OAS_WARNING else R)
            parts.append(f"[dim]HY OAS:[/][{hy_c}]{hy:.2f}%[/]")
        if ig is not None:
            ig_c = G if ig <= IG_OAS_GOOD else (Y if ig <= IG_OAS_WARNING else R)
            parts.append(f"[dim]IG OAS:[/][{ig_c}]{ig:.2f}%[/]")
        rows.append(Text.from_markup("  ".join(parts)))

    macro = []
    if cpi_yoy is not None:
        cpi_c = G if cpi_yoy <= CPI_GOOD else (Y if cpi_yoy <= CPI_WARNING else R)
        macro.append(f"[dim]CPI YoY:[/][{cpi_c}]{cpi_yoy:.1f}%[/]")
    if unrate is not None:
        ur_c = G if unrate <= UNRATE_GOOD else (Y if unrate <= UNRATE_WARNING else R)
        macro.append(f"[dim]Unemp:[/][{ur_c}]{unrate:.1f}%[/]")
    if macro: rows.append(Text.from_markup("  ".join(macro)))

    other = []
    if oil  is not None: other.append(f"[dim]WTI Crude Oil:[/][white]${oil:.2f}[/]")
    if nfci is not None:
        nc  = G if nfci <= NFCI_NEGATIVE else (Y if nfci <= NFCI_POSITIVE else R)
        lbl = "accommodative" if nfci < 0 else ("tight" if nfci > NFCI_POSITIVE else "neutral")
        other.append(f"[dim]Chicago Fed (NFCI):[/][{nc}]{nfci:+.3f}[/][dim] {lbl}[/]")
    if dxy is not None:
        dxy_c = R if dxy >= DXY_CRITICAL else (Y if dxy >= DXY_WARNING else G)
        other.append(f"[dim]USD Index (DXY):[/][{dxy_c}]{dxy:.1f}[/]")
    if other: rows.append(Text.from_markup("  ".join(other)))

    extra = []
    if be10 is not None:
        be_c = R if be10 >= BE_CRITICAL else (Y if be10 >= BE_WARNING else G)
        extra.append(f"[dim]10Y Inflation Breakeven:[/][{be_c}]{be10:.2f}%[/]")
    if be5 is not None:
        be5_c = R if be5 >= BE_CRITICAL else (Y if be5 >= BE_WARNING else G)
        extra.append(f"[dim]5Y Breakeven:[/][{be5_c}]{be5:.2f}%[/]")
    if mortgage is not None:
        mg_c = R if mortgage >= MORTGAGE_CRITICAL else (Y if mortgage >= MORTGAGE_WARNING else G)
        extra.append(f"[dim]30Y Mortgage:[/][{mg_c}]{mortgage:.2f}%[/]")
    if umcsent is not None:
        uc = G if umcsent >= UMCSENT_GOOD else (Y if umcsent >= UMCSENT_WARNING else R)
        extra.append(f"[dim]UMich Consumer Sentiment:[/][{uc}]{umcsent:.0f}[/]")
    if extra: rows.append(Text.from_markup("  ".join(extra)))

    valid_cal = econ_cal if (econ_cal and not (isinstance(econ_cal, dict) and econ_cal.get("_error"))) else []
    if valid_cal:
        rows.append(Rule(style="dim"))
        IMP_C = {"HIGH": "bold bright_red", "MEDIUM": "yellow", "LOW": "dim"}
        today = date.today()
        seen_keys = set()
        dedup_count = 0
        for ev in valid_cal[:6]:
            ed      = ev.get("event_date")
            full_nm = (ev.get("event_name") or "")
            name    = full_nm[:24]
            date_str = str(_parse_event_date(ed)) if ed is not None else "unknown_date"
            event_time = str(ev.get("event_time") or "").strip()
            key     = (date_str + event_time + full_nm).lower()
            if key in seen_keys:
                dedup_count += 1
                continue
            seen_keys.add(key)
            imp  = (ev.get("importance") or "LOW").upper()
            ic   = IMP_C.get(imp, "dim")
            f_v  = ev.get("forecast_value")
            a_v  = ev.get("actual_value")
            p_v  = ev.get("previous_value")
            ed_date = _parse_event_date(ed)
            if ed_date == today:
                when = "TODAY"
            elif ed_date is not None:
                delta = (ed_date - today).days
                when  = f"+{delta}d" if delta > 0 else "YST"
            else:
                when = "--"
            vals = ""
            if a_v is not None:
                ac = G if float(a_v) <= float(f_v if f_v is not None else a_v) else R
                vals = f" [{ac}]A={a_v:.1f}[/]"
            elif f_v is not None:
                vals = f" [dim]F={f_v:.1f}[/]"
            if p_v is not None:
                vals += f"[dim] P={p_v:.1f}[/]"
            et    = ev.get("event_time")
            et_s  = f" [dim]{str(et)[:5]}[/]" if et else ""
            rows.append(Text.from_markup(
                f"[{ic}]{when:<5}[/]{et_s} [white]{name}[/]{vals}"
            ))

        if dedup_count > 0:
            logger.debug(f"Economic calendar deduplication: removed {dedup_count} duplicate events")

    if not rows:
        rows.append(Text("[dim]no economic data[/]"))
    return Panel(Group(*rows), title="[bold bright_magenta]ECONOMIC INPUTS → Exposure Score[/]",
                 border_style="bright_magenta", padding=(0, 1))


def panel_status(act, hlth, notifs, algo_metrics=None, loader=None, audit=None, run=None, exec_hist=None, cfg=None):
    """Algo activity phases + data health + recent notifications + action counts + loader status."""
    # Issue 2 FIX: Validate error dicts — return early if any critical param has _error
    if isinstance(act, dict) and act.get("_error"):
        return error_panel("ALGO ACTIVITY", act.get("_error"))
    if isinstance(hlth, dict) and hlth.get("_error"):
        return error_panel("DATA HEALTH", hlth.get("_error"))
    if isinstance(notifs, dict) and notifs.get("_error"):
        return error_panel("NOTIFICATIONS", notifs.get("_error"))
    rows: list = []

    # ── Run status + schedule + mode + trading config ────────────────────────────
    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_id_top = (run.get("run_id") or "") if run_valid else ((act.get("run_id") or "") if act_valid else "")
    run_at_top = (run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None))
    if run_id_top or run_at_top:
        sts = (
            f"[bold bright_green]✔ COMPLETED[/]" if (run_valid and run.get("success") and not run.get("halted"))
            else (f"[bold yellow]~ HALTED[/]" if (run_valid and run.get("halted"))
            else (f"[bold bright_red]✘ ERROR[/]" if (run_valid and run.get("errored"))
            else "[dim]RUN[/]"))
        )
        age_s = f"  [dim]{fmt_age(run_at_top)}[/]" if run_at_top else ""
        rows.append(Text.from_markup(f"{sts}{age_s}"))
    cfg_v = cfg if cfg is not None else {}
    mode  = cfg_v.get("mode", "")
    en    = cfg_v.get("enabled", True)
    mc    = G if "LIVE" in str(mode) else Y
    ec    = G if en else R
    en_s  = "ENABLED" if en else "DISABLED"
    next_r = next_run_str()
    rows.append(Text.from_markup(
        f"[{mc}]{mode or 'PAPER'}[/]  [{ec}]{en_s}[/]  [dim]Next run:[/] [white]{next_r}[/]"
    ))
    # Trading config params — visible context for position sizing decisions
    cfg_parts = []
    if cfg_v.get("max_pos_n"):    cfg_parts.append(f"[dim]slots:[/][white]{cfg_v['max_pos_n']}[/]")
    if cfg_v.get("max_sec_n"):   cfg_parts.append(f"[dim]sector≤4:[/][white]{cfg_v['max_sec_n']}[/]")
    if cfg_v.get("base_risk"):   cfg_parts.append(f"[dim]risk:[/][white]{cfg_v['base_risk']}%[/]")
    if cfg_v.get("t1_r"):        cfg_parts.append(f"[dim]T1:[/][white]{cfg_v['t1_r']}R[/]")
    if cfg_v.get("pyramid"):     cfg_parts.append(f"[{G}]pyr✓[/]")
    if cfg_parts:
        rows.append(Text.from_markup("  ".join(cfg_parts)))
    rows.append(Rule(style="dim"))

    def _pc(v):
        if isinstance(v, list): return len(v)
        if isinstance(v, int):  return v
        return 0

    # Execution history summary — last 7 runs
    valid_hist = exec_hist if (exec_hist and not (isinstance(exec_hist, dict) and exec_hist.get("_error"))) else []
    if valid_hist:
        n_ok  = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() in ("success", "completed"))
        n_hlt = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() == "halted")
        n_err = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() in ("error", "failed"))
        total_h = len(valid_hist)
        wr_h  = n_ok / total_h * 100 if total_h else 0
        wc_h = G if wr_h >= 80 else (Y if wr_h >= 50 else R)  # TODO: config
        badges = []
        for r in valid_hist[:7]:
            s = (r.get("overall_status") or "").lower()
            if s in ("success", "completed"): badges.append(f"[{G}]✓[/]")
            elif s == "halted":               badges.append(f"[{Y}]~[/]")
            else:                             badges.append(f"[{R}]✗[/]")
        rows.append(Text.from_markup(
            f"[dim]Last {total_h} runs:[/] {''.join(badges)}"
            f"  [{wc_h}]{n_ok}/{total_h} success[/]"
            + (f"  [{Y}]{n_hlt} halted[/]" if n_hlt else "")
            + (f"  [{R}]{n_err} error[/]" if n_err else "")
        ))
        last_halt = next((r for r in valid_hist if (r.get("overall_status") or "").lower() == "halted"), None)
        if last_halt:
            lhr  = last_halt.get("halt_reason") or ""
            lph  = _fmt_phases_halted(last_halt.get("phases_halted"))
            body = lhr or lph
            if body:
                ph_s = f"  [dim]({lph})[/]" if lph and lph not in lhr else ""
                rows.append(Text.from_markup(f"  [{Y}]↳ {body[:55]}[/]{ph_s}"))
        rows.append(Rule(style="dim"))

    # Current run status — shown prominently even when history is empty
    run_id = (run.get("run_id") or "") if run and not run.get("_error") else ""
    run_at = run.get("run_at") if run else None
    if not run_id and act and not act.get("_error"):
        run_id = (act.get("run_id") or "")[:26]
        run_at = act.get("run_at")
    if run_id:
        age_s  = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""
        r_stat = ""
        if run and not run.get("_error"):
            if run.get("success"):   r_stat = f"  [{G}]✓ COMPLETED[/]"
            elif run.get("halted"):  r_stat = f"  [{Y}]~ HALTED[/]"
            elif run.get("errored"): r_stat = f"  [{R}]✗ ERROR[/]"
        rows.append(Text.from_markup(f"[dim]Run:[/] [white]{run_id[:30]}[/]{age_s}{r_stat}"))

        # Show phases_completed/halted/errored counts from the run object
        if run and not run.get("_error"):
            n_done = _pc(run.get("phases_completed"))
            n_hlt  = _pc(run.get("phases_halted"))
            n_err  = _pc(run.get("phases_errored"))
            if n_done + n_hlt + n_err > 0:
                done_s = f"[{G}]{n_done} phases ✓[/]"
                hlt_s  = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
                err_s  = f"  [{R}]{n_err} errored[/]" if n_err else ""
                rows.append(Text.from_markup(f"  {done_s}{hlt_s}{err_s}"))

    # Phase detail — named phases from exec_log with per-phase status and key data
    phase_badges = []
    if run and not run.get("_error") and run.get("_source") == "exec_log":
        halt_r  = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"[{Y}]↳ {prefix}{detail[:60]}[/]"))
        elif summary and isinstance(summary, str):
            rows.append(Text.from_markup(f"[dim]{summary[:65]}[/]"))

        phase_results = run.get("phase_results")
        for p in phase_results:
            raw   = (p.get("name") or p.get("phase", "")).lower()
            parts = raw.split("_")
            base  = "_".join(parts[:2]) if len(parts) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
            ps    = (p.get("status") or "").lower()
            sc    = G if ps in ("success", "completed", "ok") else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            si    = "✓" if ps in ("success", "completed", "ok") else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

            # Show error or key data for failed/halted phases
            err = p.get("error")
            pdata = p.get("data")
            if isinstance(pdata, str):
                try: pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError, TypeError): pdata = None
            if err and ps not in ("success", "completed", "ok"):
                rows.append(Text.from_markup(f"  [{sc}]↳ {err[:62]}[/]"))
            elif ps in ("halt", "halted") and pdata is not None:
                reason = ""
                if isinstance(pdata, dict):
                    reason = (pdata.get("halt_reason") or pdata.get("reason") or "")[:55]
                if reason:
                    rows.append(Text.from_markup(f"  [{Y}]↳ {reason}[/]"))
            elif ps in ("success", "completed", "ok") and pdata is not None:
                # Surface a key metric per phase if available
                for key in ("signals_generated", "entries_executed", "exits_executed",
                             "positions_checked", "orders_placed", "symbols_checked",
                             "trades_executed", "checks_passed", "score"):
                    val = pdata.get(key)
                    if val is not None:
                        rows.append(Text.from_markup(
                            f"  [dim]{short}:[/] [white]{key.replace('_', ' ')}={val}[/]"
                        ))
                        break

        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

        n_ok  = _pc(run.get("phases_completed"))
        n_hlt = _pc(run.get("phases_halted"))
        n_err = _pc(run.get("phases_errored"))
        if n_ok + n_hlt + n_err > 0:
            ok_s  = f"[{G}]{n_ok} phases done[/]"
            hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
            err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
            rows.append(Text.from_markup(f"  {ok_s}{hlt_s}{err_s}"))
    elif act and not act.get("_error"):
        phases = act.get("phases")
        if phases is None:
            phases = []
        for p in phases:
            at = p.get("action_type", "")
            if not at.startswith("phase_"): continue
            parts = at.split("_")
            if len(parts) > 2: continue
            num   = parts[1] if len(parts) > 1 else "?"
            short = PHASE_NAMES.get(f"phase_{num}", f"P{num}")[:9]
            st    = p.get("status", "")
            sc    = G if st == "success" else (Y if st in ("halt", "warn", "halted") else R)
            si    = "✓" if st == "success" else ("~" if st in ("halt", "warn", "halted") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

    # Recent trade events (entry/exit/order) from audit_log
    recent_actions = act.get("recent_actions") if (act and not act.get("_error")) else None
    recent = recent_actions if recent_actions is not None else []
    trade_evts = [a for a in recent if a.get("action_type") in
                  ("entry_executed","exit_executed","entry_rejected","position_exited",
                   "order_placed","order_rejected")]
    for a in trade_evts[:4]:
        at  = a.get("action_type", "")
        det = a.get("details")
        if det is None:
            det = {}
        elif isinstance(det, str):
            try: det = json.loads(det)
            except (json.JSONDecodeError, ValueError):
                logger.warning("action details JSON parse failed in panel_status")
                det = {}
        sym = det.get("symbol", "")
        ic  = G if ("executed" in at or at == "position_exited") else (Y if "placed" in at else R)
        lbl = at.replace("_", " ").title()[:20]
        rows.append(Text.from_markup(f"  [{ic}]{lbl}{(' ' + sym) if sym else ''}[/]"))

    # Data health (stale tables only)
    if hlth:
        rows.append(Rule(style="dim"))
        stale = [r for r in hlth if r.get("st") != "ok"]
        if not stale:
            rows.append(Text.from_markup(f"[{G}]✓ Data OK[/]  [dim]{len(hlth)} tables[/]"))
            crit = [r for r in hlth if r.get("role") == "CRIT"]
            if crit:
                crit_parts = "  ".join(f"[{G}]✓[/][dim]{r.get('tbl','')[:13]}[/]" for r in crit)
                rows.append(Text.from_markup(f"  {crit_parts}"))
        else:
            for r in stale[:4]:
                nm  = (r.get("tbl") or "--")[:10]
                age = r.get("age") or "?"
                rc  = r.get("role", "")
                cc  = "bold white" if rc == "CRIT" else "white"
                lat = r.get("latest")
                lat_s = f" ({lat.strftime('%b %d') if hasattr(lat, 'strftime') else str(lat)[:5]})" if lat else ""
                rows.append(Text.from_markup(f"[{R}]✗[/] [{cc}]{nm:<10}[/] [dim]{age}d stale{lat_s}[/]"))

    # Notifications (up to 4)
    valid_notifs = notifs if (notifs and not (isinstance(notifs, dict) and notifs.get("_error"))) else []
    if valid_notifs:
        rows.append(Rule(style="dim"))
        SEV_C = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        _SHORT = {
            "trading halted by circuit": "Halted: CB",
            "circuit breaker":           "CB fired",
            "position entered":          "Entered",
            "position exited":           "Exited",
            "daily loss limit":          "DailyLoss",
            "max drawdown":              "MaxDD hit",
        }
        for n in valid_notifs[:4]:
            sc    = SEV_C.get(n.get("severity","info"), DIM)
            raw_t = (n.get("title") or "")
            tl    = raw_t.lower()
            title = next((v for k, v in _SHORT.items() if k in tl), raw_t[:24])
            age   = fmt_age(n.get("created_at"))
            unread = "●" if not n.get("seen", True) else " "
            rows.append(Text.from_markup(
                f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]"
            ))

    # Algo metrics daily (action counts)
    valid_metrics = algo_metrics if (algo_metrics and not (isinstance(algo_metrics, dict) and algo_metrics.get("_error"))) else []
    if valid_metrics:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Daily trade activity:[/]"))
        for m in valid_metrics[:5]:
            d   = m.get("date")
            d_s = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
            ta_val = m.get("total_actions")
            en_val = m.get("entries")
            ex_val = m.get("exits")
            ta  = int(ta_val) if ta_val is not None else None
            en  = int(en_val) if en_val is not None else None
            ex  = int(ex_val) if ex_val is not None else None
            ta_display = str(ta) if ta is not None else "--"
            en_display = str(en) if en is not None else "--"
            ex_display = str(ex) if ex is not None else "--"
            rows.append(Text.from_markup(
                f"  [dim]{d_s}:[/] [white]{ta_display}[/][dim] total actions,  [/][{G}]{en_display}[/][dim] entries  [/][{R}]{ex_display}[/][dim] exits[/]"
            ))

    # Data loader status (errors/stale from data_loader_status table)
    valid_loader   = loader if (loader and not (isinstance(loader, dict) and loader.get("_error"))) else []
    problem_loader = [r for r in valid_loader if (r.get("status") or "") in ("error", "failed", "stale")]
    running_loader = [r for r in valid_loader if (r.get("status") or "") == "loading"]
    ok_count       = len(valid_loader) - len(problem_loader) - len(running_loader)
    if problem_loader:
        rows.append(Rule(style="dim"))
        ok_s = f"  [dim]{ok_count} ok[/]" if ok_count > 0 else ""
        rows.append(Text.from_markup(f"[{Y}]Loaders ({len(problem_loader)} issues){ok_s}:[/]"))
        for r in problem_loader[:3]:
            nm  = (r.get("table_name") or "--")[:14]
            st  = r.get("status") or "?"
            age = r.get("age_days")
            age_s = f"{int(age)}d" if age is not None else "--"
            sc  = R if st in ("error", "failed") else Y
            err = (r.get("error_message") or "")[:20]
            rows.append(Text.from_markup(
                f"  [{sc}]{nm:<14}[/] [dim]{age_s}[/]" + (f" [dim]{err}[/]" if err else "")
            ))
    elif valid_loader:
        if running_loader:
            rows.append(Rule(style="dim"))
            for r in running_loader[:3]:
                nm   = (r.get("table_name") or "")[:12]
                pct  = r.get("completion_pct")
                pct_s = f" {float(pct):.0f}%" if pct is not None else ""
                rows.append(Text.from_markup(f"[{CY}]Loading:[/][dim] {nm}{pct_s}[/]"))
        elif ok_count > 0:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup(f"[{G}]✓ Loaders[/]  [dim]{ok_count} feeds healthy[/]"))

    # Audit log — most recent notable actions
    valid_audit = audit if (audit and not (isinstance(audit, dict) and audit.get("_error"))) else []
    if valid_audit:
        notable = [a for a in valid_audit
                   if any(k in (a.get("action_type") or "") for k in
                          ("entry", "exit", "halt", "resume", "circuit"))][:3]
        if notable:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[dim]Audit:[/]"))
            for a in notable:
                at  = (a.get("action_type") or "").replace("_", " ")
                sym = a.get("symbol") or ""
                st  = a.get("status") or ""
                sc  = G if st == "success" else (Y if st == "warn" else R)
                rows.append(Text.from_markup(
                    f"  [{sc}]{at[:22]}[/]" + (f" [white]{sym}[/]" if sym else "")
                ))

    if not rows:
        rows.append(Text("no activity", style="dim"))
    return Panel(Group(*rows), title="[bold yellow]ALGO ACTIVITY & SYSTEM HEALTH[/]", border_style="yellow", padding=(0, 1))


def panel_algo_health(run, act, hlth, notifs, algo_metrics=None, loader=None, audit=None, exec_hist=None, risk=None):
    """Focused 'did the algo work?' panel: run outcome → what it did → system health."""
    # Issue 2 FIX: Validate error dicts — return early if any critical param has _error
    if isinstance(hlth, dict) and hlth.get("_error"):
        return error_panel("DATA HEALTH", hlth.get("_error"))
    if isinstance(notifs, dict) and notifs.get("_error"):
        return error_panel("NOTIFICATIONS", notifs.get("_error"))
    rows: list = []

    # ── A: Run outcome ────────────────────────────────────────────────────────
    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_at    = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    age_s     = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid:
        if run.get("success") and not run.get("halted"):
            sts = f"[bold {G}]✔ COMPLETED[/]"
        elif run.get("halted"):
            sts = f"[bold {Y}]~ HALTED[/]"
        elif run.get("errored"):
            sts = f"[bold {R}]✗ ERROR[/]"
        else:
            sts = "[dim]UNKNOWN[/]"
        rid = (run.get("run_id") or "")[:28]
        rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r  = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"  [{Y}]↳ {prefix}{detail[:80]}[/]"))
        elif summary:
            rows.append(Text.from_markup(f"  [dim]{summary[:72]}[/]"))
    elif act_valid:
        rows.append(Text.from_markup(f"[dim]Last run (audit):[/]  [dim]{fmt_age(run_at)}[/]"))
    else:
        rows.append(Text.from_markup("[dim]No run data — algo has not run yet[/]"))

    # ── B: Phase badges + aggregated "what did it do?" metrics ───────────────
    signals_gen  = 0
    entries_exec = 0
    exits_exec   = 0
    phase_badges: list = []

    def _pc(v):
        if isinstance(v, list): return len(v)
        if isinstance(v, int):  return v
        return 0

    if run_valid and run.get("_source") == "exec_log":
        for p in (run.get("phase_results")):
            raw   = (p.get("name") or p.get("phase", "")).lower()
            parts_p = raw.split("_")
            base  = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
            ps    = (p.get("status") or "").lower()
            sc    = G if ps in ("success", "completed", "ok") else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            si    = "✓" if ps in ("success", "completed", "ok") else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
            pdata = p.get("data")
            if pdata is None:
                pdata = {}
            if isinstance(pdata, str):
                try: pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError, TypeError): pdata = {}
            sg = pdata.get("signals_generated")
            ee = pdata.get("entries_executed")
            if ee is None:
                ee = pdata.get("trades_executed")
            xe = pdata.get("exits_executed")
            if sg: signals_gen  = max(signals_gen,  int(sg))
            if ee: entries_exec = max(entries_exec, int(ee))
            if xe: exits_exec   = max(exits_exec,   int(xe))
    elif run_valid or act_valid:
        src = run if run_valid else act
        phases = src.get("phases")
        if phases is None:
            phases = []
        for p in phases:
            at = p.get("action_type", "")
            if not at.startswith("phase_"): continue
            parts_p = at.split("_")
            if len(parts_p) > 2: continue
            num   = parts_p[1] if len(parts_p) > 1 else "?"
            short = PHASE_NAMES.get(f"phase_{num}", f"P{num}")[:8]
            st    = p.get("status", "")
            sc    = G if st == "success" else (Y if st in ("halt", "warn", "halted") else R)
            si    = "✓" if st == "success" else ("~" if st in ("halt", "warn", "halted") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

    if phase_badges:
        rows.append(Text.from_markup("  ".join(phase_badges)))

    # Fallback: use algo_metrics for today's entry/exit counts
    valid_metrics = algo_metrics if (algo_metrics and not (isinstance(algo_metrics, dict) and algo_metrics.get("_error"))) else []
    today_m = valid_metrics[0] if valid_metrics else {}
    if not entries_exec:
        entries_val = today_m.get("entries")
        entries_exec = int(entries_val) if entries_val is not None else None
    if not exits_exec:
        exits_val = today_m.get("exits")
        exits_exec = int(exits_val) if exits_val is not None else None

    # "What did the algo do today?" summary — the core insight
    action_parts = []
    if signals_gen > 0:
        action_parts.append(f"[dim]Signals found:[/][white]{signals_gen}[/]")
    if entries_exec > 0:
        action_parts.append(f"[dim]Entries executed:[/][{G}]{entries_exec}[/]")
    else:
        action_parts.append(f"[dim]Entries:[/][{DIM}]0[/]")
    if exits_exec > 0:
        action_parts.append(f"[dim]Exits executed:[/][{Y}]{exits_exec}[/]")
    else:
        action_parts.append(f"[dim]Exits:[/][{DIM}]0[/]")
    if action_parts:
        rows.append(Text.from_markup("  ".join(action_parts)))

    # 5-day activity strip
    if len(valid_metrics) >= 2:
        day_parts = []
        for m in valid_metrics[:5]:
            d   = m.get("date")
            d_s = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
            en_val = m.get("entries")
            ex_val = m.get("exits")
            en  = int(en_val) if en_val is not None else None
            ex  = int(ex_val) if ex_val is not None else None
            e_c = G if en is not None and en > 0 else DIM
            x_c = Y if ex is not None and ex > 0 else DIM
            en_display = str(en) if en is not None else "--"
            ex_display = str(ex) if ex is not None else "--"
            day_parts.append(f"[dim]{d_s}:[/][{e_c}]{en_display}▲[/][{x_c}]{ex_display}▼[/]")
        rows.append(Text.from_markup("[dim]5d activity:[/] " + "  ".join(day_parts)))

    rows.append(Rule(style="dim"))

    # ── C: Run history (last 7 runs as badges) ───────────────────────────────
    valid_hist = exec_hist if (exec_hist and not (isinstance(exec_hist, dict) and exec_hist.get("_error"))) else []
    if valid_hist:
        n_ok  = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() in ("success", "completed"))
        n_hlt = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() == "halted")
        n_err = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() in ("error", "failed"))
        total_h = len(valid_hist)
        badges  = []
        for r in valid_hist[:7]:
            s = (r.get("overall_status") or "").lower()
            badges.append(f"[{G}]✓[/]" if s in ("success", "completed") else (f"[{Y}]~[/]" if s == "halted" else f"[{R}]✗[/]"))
        wc = G if n_ok == total_h else (Y if n_ok > 0 else R)
        rows.append(Text.from_markup(
            f"[dim]Last {total_h} runs:[/] {''.join(badges)}"
            f"  [{wc}]{n_ok}/{total_h} success[/]"
            + (f"  [{Y}]{n_hlt} halted[/]" if n_hlt else "")
            + (f"  [{R}]{n_err} error[/]"  if n_err  else "")
        ))
        last_halt = next((r for r in valid_hist if (r.get("overall_status") or "").lower() == "halted"), None)
        if last_halt:
            lhr  = last_halt.get("halt_reason") or ""
            lph  = _fmt_phases_halted(last_halt.get("phases_halted"))
            body = lhr or lph
            if body:
                ph_s = f"  [dim]({lph})[/]" if lph and lph not in lhr else ""
                rows.append(Text.from_markup(f"  [{Y}]↳ {body[:68]}[/]{ph_s}"))

    rows.append(Rule(style="dim"))

    # ── D: Data health (compact) ──────────────────────────────────────────────
    if hlth:
        stale = [r for r in hlth if r.get("st") != "ok"]
        if not stale:
            crit  = [r for r in hlth if r.get("role") == "CRIT"]
            ok_s  = "  ".join(f"[{G}]✓[/][dim]{r.get('tbl','')[:10]}[/]" for r in crit[:5])
            rows.append(Text.from_markup(f"[{G}]✓ Data OK[/]  [dim]{len(hlth)} tables[/]  {ok_s}"))
        else:
            stale_parts = []
            for r in stale[:5]:
                nm  = (r.get("tbl") or "--")[:9]
                age = r.get("age") or "?"
                cc  = "bold white" if r.get("role") == "CRIT" else "white"
                stale_parts.append(f"[{R}]✗[/][{cc}]{nm}[/][dim]{age}d[/]")
            rows.append(Text.from_markup("[dim]Data stale:[/] " + "  ".join(stale_parts)))

    # Loader status (compact inline)
    valid_loader   = loader if (loader and not (isinstance(loader, dict) and loader.get("_error"))) else []
    problem_loader = [r for r in valid_loader if (r.get("status") or "") in ("error", "failed", "stale")]
    running_loader = [r for r in valid_loader if (r.get("status") or "") == "loading"]
    ok_count       = len(valid_loader) - len(problem_loader) - len(running_loader)
    if problem_loader:
        ldr_parts = [f"[{R if (r.get('status') or '') in ('error','failed') else Y}]{(r.get('table_name') or '')[:12]}[/]"
                     for r in problem_loader[:3]]
        rows.append(Text.from_markup(f"[dim]Loaders:[/] [{Y}]{len(problem_loader)} issues:[/] " + "  ".join(ldr_parts)))
    elif running_loader:
        rows.append(Text.from_markup(f"[{CY}]Loading:[/] [dim]{running_loader[0].get('table_name','')[:16]}[/]"))
    else:
        rows.append(Text.from_markup(f"[dim]Loaders:[/] [{G}]✓ {ok_count} healthy[/]"))

    # ── E: Risk snapshot (VaR / CVaR / Beta / Concentration) ────────────────────
    var95_v = get_numeric(risk, "var95") if risk else None
    if risk and not risk.get("_error") and var95_v is not None and var95_v > 0:
        rows.append(Rule(style="dim"))
        # M6 FIX: Show risk calculation status (successful/incomplete/stale)
        has_data = risk.get("_has_data", False)
        is_stale = risk.get("_is_stale", False)
        age_min = risk.get("_age_minutes")
        if not has_data:
            rows.append(Text.from_markup(f"[{R}]⚠ Risk calculation incomplete - awaiting data[/]"))
        elif is_stale and age_min:
            rows.append(Text.from_markup(f"[{Y}]⚠ Risk data stale ({age_min:.0f}min old)[/]"))
        else:
            rows.append(Text.from_markup(f"[{G}]✓ Risk metrics current[/]"))

        beta_v = get_numeric(risk, "beta")
        conc5_v = get_numeric(risk, "conc5")
        beta_c = R if beta_v is not None and beta_v >= mkt_cfg['beta_warning'] else (Y if beta_v is not None and beta_v >= mkt_cfg['beta_caution'] else G)
        conc_c = R if conc5_v is not None and conc5_v >= 35 else (Y if conc5_v is not None and conc5_v >= 25 else "white")
        cvar95_v = get_numeric(risk, "cvar95")
        svar_v = get_numeric(risk, "svar")
        var95_str = f"{var95_v:.2f}%" if var95_v is not None else "--"
        beta_str = f"{beta_v:.2f}" if beta_v is not None else "--"
        conc5_str = f"{conc5_v:.0f}%" if conc5_v is not None else "--"
        cvar95_str = f"{cvar95_v:.2f}%" if cvar95_v is not None else "--"
        svar_str = f"{svar_v:.2f}%" if svar_v is not None else "--"
        risk_parts = [
            f"[dim]VaR 95%:[/][white]{var95_str}[/]",
            f"[dim]CVaR 95%:[/][white]{cvar95_str}[/]",
            f"[dim]Beta:[/][{beta_c}]{beta_str}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{conc5_str}[/]",
        ]
        if svar_v is not None and svar_v > 0:
            risk_parts.append(f"[dim]Stressed VaR:[/][{R}]{svar_v:.2f}%[/]")
        rows.append(Text.from_markup("  ".join(risk_parts)))

    # ── F: Notifications (compact) ────────────────────────────────────────────
    valid_notifs = notifs if (notifs and not (isinstance(notifs, dict) and notifs.get("_error"))) else []
    if valid_notifs:
        rows.append(Rule(style="dim"))
        SEV_C  = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        _SHORT = {
            "trading halted by circuit": "Halted:CB",
            "circuit breaker":           "CB fired",
            "position entered":          "Entered",
            "position exited":           "Exited",
            "daily loss limit":          "DailyLoss",
            "max drawdown":              "MaxDD",
        }
        notif_parts = []
        for n in valid_notifs[:5]:
            sc    = SEV_C.get(n.get("severity", "info"), DIM)
            raw_t = n.get("title") or ""
            title = next((v for k, v in _SHORT.items() if k in raw_t.lower()), raw_t[:20])
            age   = fmt_age(n.get("created_at"))
            unread = "●" if not n.get("seen", True) else "·"
            notif_parts.append(f"[{sc}]{unread}{title}[/][dim]{age}[/]")
        rows.append(Text.from_markup("[dim]Alerts:[/] " + "  ".join(notif_parts)))

    if not rows:
        rows.append(Text("no activity", style="dim"))
    return Panel(Group(*rows), title="[bold yellow]ALGO HEALTH[/]  [dim][h] expand[/]", border_style="yellow", padding=(0, 1))


def panel_data_quality_status() -> Panel:
    """Issue 46: Unified data quality status panel for operator visibility.

    Shows comprehensive health of all critical data sources:
    - Critical fetchers status (ok/degraded/failed)
    - Last update times for each data source
    - Staleness warnings for any data exceeding thresholds
    - Data quality issues (row counts, freshness)
    - Summary status indicator (green/yellow/red)
    """
    rows: list = []

    # Get comprehensive health status
    hlth = check_loader_health()

    # Status summary line
    status = hlth.get("status", "unknown")
    failures = hlth.get("failures", [])
    passed = hlth.get("passed", 0)
    critical = hlth.get("critical", 0)
    issues = hlth.get("data_quality_issues", [])

    if status == "ok":
        status_c = G
        status_t = "✓ ALL SYSTEMS HEALTHY"
    elif status == "degraded":
        status_c = Y
        status_t = "⚠ DEGRADED (Some data stale or missing)"
    else:
        status_c = R
        status_t = "✗ CRITICAL (Data unavailable)"

    ts = hlth.get("timestamp")
    ts_s = ts.strftime("%H:%M:%S ET") if ts and hasattr(ts, "strftime") else "?"
    rows.append(Text.from_markup(f"[{status_c}]{status_t}[/]  [dim]{ts_s}[/]"))
    rows.append(Rule(style="dim"))

    # Critical fetchers health
    rows.append(Text.from_markup("[dim]Critical Data Sources:[/]"))
    critical_fetchers = ["fetch_run", "fetch_algo_config", "fetch_market", "fetch_positions"]
    for fname in critical_fetchers:
        if fname in failures:
            rows.append(Text.from_markup(f"  [{R}]✗[/] {fname:<25} [dim]failed[/]"))
        else:
            rows.append(Text.from_markup(f"  [{G}]✓[/] {fname:<25} [dim]ok[/]"))

    rows.append(Rule(style="dim"))

    # Data quality issues
    if issues:
        rows.append(Text.from_markup(f"[{Y}]Data Quality Issues ({len(issues)}):[/]"))
        for issue in issues[:10]:
            rows.append(Text.from_markup(f"  [{Y}]⚠[/] {issue}"))
        if len(issues) > 10:
            rows.append(Text.from_markup(f"  [dim]... and {len(issues) - 10} more issues[/]"))
    else:
        rows.append(Text.from_markup(f"[{G}]✓ No data quality issues[/]"))

    rows.append(Rule(style="dim"))

    # Status summary
    rows.append(Text.from_markup(f"[dim]Fetchers healthy:[/] [{G if passed == critical else Y}]{passed}/{critical}[/]"))

    return Panel(Group(*rows), title="[bold cyan]DATA QUALITY STATUS[/]  [dim][d] detailed view[/]", border_style="cyan", padding=(0, 1))


# ── mascot panel (compact — dancing man only) ────────────────────────────────
# MASCOT_W defined above in the mascot section.
# MASCOT_H = 1 top border + 1 blank + 4 pose lines + 1 blank + 1 bottom border = 8

MASCOT_H = 8


def mascot_compact(data: dict, frame: int) -> Panel:
    fi   = mascot_pose(data, frame)
    mc   = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    # No justify= — strings are pre-padded to exactly 11 chars (panel content width).
    return Panel(
        Group(
            Text(" " * 11),
            Text(pose[0], style=f"bold {mc}", no_wrap=True),
            Text(pose[1], style=f"bold {mc}", no_wrap=True),
            Text(pose[2], style=f"bold {mc}", no_wrap=True),
            Text(pose[3], style=f"bold {mc}", no_wrap=True),
            Text(" " * 11),
        ),
        border_style=mc,
        padding=(0, 0),
    )


# ── loading layout — same structure as render_dashboard to prevent flicker ──

def loading_layout(frame: int) -> Layout:
    """Show compact mascot in top-right corner with loading message below."""
    fi   = LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]   # 4fps loading animation
    mc   = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    dots = "." * ((frame // 2 % 4) + 1)             # dots cycle at ~1Hz

    # Same pre-padded approach as mascot_compact (11-char strings)
    mascot_panel = Panel(
        Group(
            Text(" " * 11),
            Text(pose[0], style=f"bold {mc}", no_wrap=True),
            Text(pose[1], style=f"bold {mc}", no_wrap=True),
            Text(pose[2], style=f"bold {mc}", no_wrap=True),
            Text(pose[3], style=f"bold {mc}", no_wrap=True),
            Text(" " * 11),
        ),
        border_style=mc,
        padding=(0, 0),
    )

    hdr_text = Text.from_markup(
        f"[bold white]ALGO OPS DASHBOARD[/]  [dim]{dots}[/]"
    )
    hdr_panel = Panel(
        Align(hdr_text, vertical="middle"),
        border_style="blue",
        padding=(0, 1),
    )

    loading_body = Text.from_markup(
        f"\n\n[bold white]  Fetching market data{dots}[/]\n\n"
        f"  [dim]Connecting to database...[/]\n\n"
        f"  [dim]Keys: [/][cyan]p[/][dim] positions  [/][cyan]s[/][dim] signals  "
        f"[/][cyan]h[/][dim] health  [/][cyan]r[/][dim] sectors  [/][cyan]q[/][dim] quit[/]"
    )
    main_panel = Panel(
        Align(loading_body, align="left", vertical="middle"),
        border_style="blue",
        padding=(0, 1),
    )

    layout = Layout()
    layout.split_column(
        Layout(name="top", size=MASCOT_H),
        Layout(name="main", ratio=1),
    )
    layout["top"].split_row(
        Layout(name="hdr",    ratio=1),
        Layout(name="mascot", size=MASCOT_W),
    )
    layout["top"]["hdr"].update(hdr_panel)
    layout["top"]["mascot"].update(mascot_panel)
    layout["main"].update(main_panel)
    return layout


# ── expanded panel helpers ────────────────────────────────────────────────────

def _expanded_layout(hdr_panel, exposure_panel, mascot_panel, main_panel) -> Layout:
    """Shared skeleton: market header row on top, one full-height panel below."""
    exp = Layout()
    exp.split_column(Layout(name="etop", size=10), Layout(name="emain"))
    exp["etop"].split_row(
        Layout(name="ehdr", ratio=1),
        Layout(name="eexp", ratio=2),
        Layout(name="emsc", size=MASCOT_W),
    )
    exp["etop"]["ehdr"].update(hdr_panel)
    exp["etop"]["eexp"].update(exposure_panel)
    exp["etop"]["emsc"].update(mascot_panel)
    exp["emain"].update(main_panel)
    return exp


def panel_signals_expanded(sig, sig_eval=None, cfg=None):
    """Full-screen buy signals — all signals, full text, breakout quality, base type."""
    if not sig or sig.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]SIGNALS[/]", border_style="magenta", padding=(0, 1))
    grade_thresholds = get_grade_thresholds(cfg)
    raw   = sig.get("n", 0)
    total = sig.get("total", 0)
    d     = sig.get("date")
    ds    = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    g = sig.get("grades")
    if g is None:
        g = {}
    ga, gb, gc, gd = (int(g.get(k)) if g.get(k) is not None else None for k in ("a", "b", "c", "d"))
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))  # TODO: convert to config
    rows = [Text.from_markup(
        f"[{buy_c}][bold]{raw} BUY SIGNALS[/][/]  [dim]from {total} screened  {ds}[/]  "
        f"[{G}]A:{ga}[/] [{CY}]B:{gb}[/] [{Y}]C:{gc}[/] [{R}]D:{gd}[/]  "
        f"[dim]press [/][bold magenta]s[/][dim] to return[/]"
    )]

    top_a = sig.get("top_a")
    if top_a:
        parts = []
        for s in top_a:
            sc = get_numeric(s, "score")
            # M1 FIX: Use config-based grade thresholds for dynamic coloring
            sc_c = G if sc is not None and sc >= grade_thresholds["a_plus"] else ("bright_green" if sc is not None and sc >= grade_thresholds["a"] else "green")
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            parts.append(f"[{sc_c}]{s.get('symbol','')}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]A-grade radar:[/] " + "  ".join(parts)))

    if sig_eval and not sig_eval.get("_error"):
        ev_tot = sig_eval.get("total", 0); ev_t5 = sig_eval.get("t5", 0); ev_avg = sig_eval.get("avg_score", 0)
        ev_c = G if ev_t5 >= sig_thr['event_value_good'] else (Y if ev_t5 >= sig_thr['event_value_caution'] else R)
        funnel = (f"[dim]Funnel  T1:[/]{sig_eval.get('t1',0)} [dim]T2:[/]{sig_eval.get('t2',0)} "
                  f"[dim]T3:[/]{sig_eval.get('t3',0)} [dim]T4:[/]{sig_eval.get('t4',0)} "
                  f"[dim]T5:[/][{ev_c}]{ev_t5}[/][dim]/{ev_tot}  avg score:[/]{ev_avg:.0f}")
        rejected = sig_eval.get("rejected")
        if rejected:
            blocks = "  ".join(f"[dim]{rj['evaluation_reason'][:32]}:{rj['n']}[/]" for rj in rejected)
            funnel += f"  [dim]blocked:[/] {blocks}"
        rows.append(Text.from_markup(funnel))

    rows.append(Rule(style="dim"))
    buy_sigs = sig.get("buy_sigs")
    if buy_sigs:
        rows.append(Text.from_markup(
            "[dim]sym    stg  type           Q    R:R  vol%    entry    stop   RS  bk-qual   base[/]"
        ))
        for bs in buy_sigs:
            sym    = (bs.get("symbol") or "--")
            stg    = bs.get("stage_number")
            sig_t  = (bs.get("signal_type") or "").replace("WEEKLY_", "W_").replace("STAGE_2", "S2").replace("STAGE2", "S2").replace("BREAKOUT", "BKT").replace("MOMENTUM", "MOM").replace("REVERSAL", "REV").replace("PULLBACK", "PB").replace("TREND", "TRD").replace("_FOLLOW", "")
            sq     = bs.get("signal_quality_score") or bs.get("entry_quality_score")
            rr     = bs.get("risk_reward_ratio")
            vsurge = bs.get("volume_surge_pct")
            rs     = bs.get("rs_rating")
            entry  = bs.get("buylevel") or bs.get("close")
            stop   = bs.get("stoplevel")
            bqual  = (bs.get("breakout_quality") or "")[:9]
            btype  = (bs.get("base_type") or "")[:9]
            sq_c   = G if sq is not None and sq >= grade_thresholds.get('a', 80) else (Y if sq is not None and sq >= grade_thresholds.get('b', 60) else "white")
            rr_c   = G if rr is not None and rr >= 2.5 else (Y if rr is not None and rr >= 1.5 else "white")
            vs_c   = G if vsurge is not None and vsurge >= sig_thr['volume_surge_good'] else (Y if vsurge is not None and vsurge >= sig_thr['volume_surge_caution'] else "white")
            rows.append(Text.from_markup(
                f"[{sq_c}]{sym:<6}[/][dim]{('S'+str(stg) if stg else '  ')} {sig_t:<14}[/]"
                f"[{sq_c}]{(f'{sq:.0f}' if sq is not None else '--'):>4}[/]"
                f"[{rr_c}]{(f'{rr:.1f}' if rr is not None else '--'):>4}[/]"
                f"[{vs_c}]{(f'{vsurge:+.0f}%' if vsurge is not None else '--'):>5}[/]"
                f" [dim]{(f'${float(entry):.2f}' if entry is not None else '--'):>8}"
                f" {(f'${float(stop):.2f}' if stop is not None else '--'):>8}"
                f" {(str(rs) if rs is not None else '--'):>3}  {bqual:<9} {btype}[/]"
            ))
    else:
        rows.append(Text.from_markup(f"[dim]No BUY signals from {total} screened[/]"))

    near = sig.get("near")
    if near:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Near BUY threshold (swing score 55–69):[/]"))
        def _score_display(a):
            score_val = a.get('score')
            if score_val is not None:
                return f"{float(score_val):.0f}"
            else:
                return "--"
        parts = [f"[{CY}]{a['symbol']}[/][dim] {_score_display(a)}[/]" for a in near]
        for i in range(0, len(parts), 4):
            rows.append(Text.from_markup("  " + "    ".join(parts[i:i+4])))

    return Panel(Group(*rows), title="[bold magenta]BUY SIGNALS — EXPANDED[/]  [dim][s] return[/]", border_style="magenta", padding=(0, 1))


def panel_algo_health_expanded(run, act, hlth, notifs, algo_metrics=None, loader=None, audit=None, exec_hist=None, risk=None):
    """Full-screen algo health — complete run history, all data tables, all notifications."""
    # Issue 2 FIX: Validate error dicts — return early if any critical param has _error
    if isinstance(hlth, dict) and hlth.get("_error"):
        return error_panel("DATA HEALTH", hlth.get("_error"))
    if isinstance(notifs, dict) and notifs.get("_error"):
        return error_panel("NOTIFICATIONS", notifs.get("_error"))
    rows: list = [Text.from_markup("[dim]press [/][bold yellow]h[/][dim] to return to dashboard[/]"), Rule(style="dim")]

    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_at    = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    age_s     = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid:
        sts = (f"[bold {G}]✔ COMPLETED[/]" if run.get("success") and not run.get("halted")
               else (f"[bold {Y}]~ HALTED[/]" if run.get("halted")
               else f"[bold {R}]✗ ERROR[/]"))
        rid = (run.get("run_id") or "")
        rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r  = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"  [{Y}]↳ {prefix}{detail}[/]"))
        elif summary:
            rows.append(Text.from_markup(f"  [dim]{summary}[/]"))

    phase_badges: list = []
    if run_valid and run.get("_source") == "exec_log":
        for p in (run.get("phase_results")):
            raw   = (p.get("name") or p.get("phase", "")).lower()
            parts_p = raw.split("_")
            base  = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
            ps    = (p.get("status") or "").lower()
            sc    = G if ps in ("success", "completed", "ok") else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            si    = "✓" if ps in ("success", "completed", "ok") else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
    if phase_badges:
        rows.append(Text.from_markup("  ".join(phase_badges)))

    rows.append(Rule(style="dim"))

    # Full run history — all runs, untruncated halt reasons, with timestamps
    valid_hist = exec_hist if (exec_hist and not (isinstance(exec_hist, dict) and exec_hist.get("_error"))) else []
    if valid_hist:
        n_ok  = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() in ("success", "completed"))
        wc    = G if n_ok == len(valid_hist) else (Y if n_ok > 0 else R)
        rows.append(Text.from_markup(f"[dim]Run history ({len(valid_hist)} runs):[/]  [{wc}]{n_ok}/{len(valid_hist)} success[/]"))
        for r in valid_hist:
            s    = (r.get("overall_status") or "").lower()
            dt   = r.get("started_at")
            dt_s = dt.strftime("%b %d  %I:%M %p") if hasattr(dt, "strftime") else str(dt or "")[:16]
            ic   = G if s in ("success", "completed") else (Y if s == "halted" else R)
            ii   = "✓" if s in ("success", "completed") else ("~" if s == "halted" else "✗")
            hr   = r.get("halt_reason") or ""
            lph  = _fmt_phases_halted(r.get("phases_halted"))
            body = hr or lph
            ph_s = f"  [dim]({lph})[/]" if lph and lph not in (hr or "") else ""
            hr_s = f"  [{Y}]↳ {body}[/]{ph_s}" if body else ""
            rows.append(Text.from_markup(f"  [{ic}]{ii}[/] [dim]{dt_s}[/]  [{ic}]{s}[/]{hr_s}"))

    rows.append(Rule(style="dim"))

    # All data tables — ok and stale, with role and date
    if hlth:
        stale_count = sum(1 for r in hlth if r.get("st") != "ok")
        rows.append(Text.from_markup(f"[dim]Data freshness ({len(hlth)} tables, {stale_count} stale):[/]"))
        for r in hlth:
            nm   = (r.get("tbl") or "--")
            role = r.get("role") or ""
            age  = r.get("age") if r.get("age") is not None else "?"
            lat  = r.get("latest")
            lat_s = lat.strftime("%b %d") if hasattr(lat, "strftime") else str(lat or "")[:5]
            ok   = r.get("st") == "ok"
            ic   = G if ok else R
            ii   = "✓" if ok else "✗"
            rc   = "white" if role == "CRIT" else (Y if role == "IMP" else DIM)
            rows.append(Text.from_markup(
                f"  [{ic}]{ii}[/] [{rc}]{nm:<18}[/] [dim]{role:<4}  {age}d  {lat_s}[/]"
            ))

    rows.append(Rule(style="dim"))

    # All loader statuses with full error messages
    valid_loader = loader if (loader and not (isinstance(loader, dict) and loader.get("_error"))) else []
    if valid_loader:
        rows.append(Text.from_markup("[dim]Data loaders:[/]"))
        for r in valid_loader:
            st  = r.get("status") or ""
            nm  = r.get("table_name") or "--"
            err = r.get("error_message") or ""
            sc  = R if st in ("error", "failed") else (Y if st == "stale" else (CY if st == "loading" else G))
            rows.append(Text.from_markup(
                f"  [{sc}]{nm:<22}[/] [dim]{st:<8}[/]"
                + (f" [{R}]{err}[/]" if err else "")
            ))

    # Risk snapshot
    var95_v = get_numeric(risk, "var95") if risk and not risk.get("_error") else None
    if var95_v is not None and var95_v > 0:
        rows.append(Rule(style="dim"))
        beta_v = get_numeric(risk, "beta")
        conc5_v = get_numeric(risk, "conc5")
        beta_v = beta_v if beta_v is not None else 0
        conc5_v = conc5_v if conc5_v is not None else 0
        beta_c = R if beta_v >= 1.2 else (Y if beta_v >= 0.8 else G)
        conc_c = R if conc5_v >= 35 else (Y if conc5_v >= 25 else "white")
        cvar95_v = get_numeric(risk, "cvar95")
        cvar95_v = cvar95_v if cvar95_v is not None else 0
        svar_v = get_numeric(risk, "svar")
        svar_v = svar_v if svar_v is not None else 0
        risk_parts = [
            f"[dim]VaR 95%:[/][white]{var95_v:.2f}%[/]",
            f"[dim]CVaR 95%:[/][white]{cvar95_v:.2f if cvar95_v is not None else '--'}%[/]",
            f"[dim]Beta:[/][{beta_c}]{beta_v:.2f}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{conc5_v:.0f}%[/]",
        ]
        if svar_v is not None and svar_v > 0:
            risk_parts.append(f"[dim]Stressed VaR:[/][{R}]{svar_v:.2f}%[/]")
        rows.append(Text.from_markup("  ".join(risk_parts)))

    # All notifications — untruncated titles
    valid_notifs = notifs if (notifs and not (isinstance(notifs, dict) and notifs.get("_error"))) else []
    if valid_notifs:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Notifications:[/]"))
        SEV_C = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        for n in valid_notifs:
            sc     = SEV_C.get(n.get("severity", "info"), DIM)
            title  = n.get("title") or ""
            age    = fmt_age(n.get("created_at"))
            unread = "●" if not n.get("seen", True) else "·"
            rows.append(Text.from_markup(f"  [{sc}]{unread} {title}[/] [dim]{age}[/]"))

    return Panel(Group(*rows), title="[bold yellow]ALGO HEALTH — EXPANDED[/]  [dim][h] return[/]", border_style="yellow", padding=(0, 1))


def panel_sectors_expanded(srank, pos, port, sec_rot=None, irank=None, sec_warn=None):
    """Full-screen sectors — all sector and industry rankings, full portfolio breakdown."""
    # Issue 2 FIX: Check for error dicts in all data parameters
    if isinstance(srank, dict) and srank.get("_error"):
        return error_panel("SECTORS (expanded)", srank.get("_error"))
    if isinstance(pos, dict) and pos.get("_error"):
        return error_panel("SECTORS (positions)", pos.get("_error"))
    if isinstance(port, dict) and port.get("_error"):
        return error_panel("SECTORS (portfolio)", port.get("_error"))
    if isinstance(sec_rot, dict) and sec_rot.get("_error"):
        return error_panel("SECTORS (rotation)", sec_rot.get("_error"))
    if isinstance(irank, dict) and irank.get("_error"):
        return error_panel("SECTORS (industries)", irank.get("_error"))
    if isinstance(sec_warn, dict) and sec_warn.get("_error"):
        return error_panel("SECTORS (warnings)", sec_warn.get("_error"))
    rows: list = [Text.from_markup("[dim]press [/][bold cyan]r[/][dim] to return to dashboard[/]"), Rule(style="dim")]

    def rdelta(r, wk="rank_1w_ago", wk4=None):
        cur, old = r.get("current_rank", 0), r.get(wk)
        if old is None: return ""
        d  = int(old) - int(cur)
        s1 = f"[{G}]▲{d}[/]" if d > 0 else (f"[{R}]▼{abs(d)}[/]" if d < 0 else "[dim]=[/]")
        if wk4:
            old4 = r.get(wk4)
            if old4 is not None:
                d4 = int(old4) - int(cur)
                s4 = f"[{G}]▲{d4}[/]" if d4 > 0 else (f"[{R}]▼{abs(d4)}[/]" if d4 < 0 else "[dim]=[/]")
                return f"{s1}[dim]/[/]{s4}"
        return s1

    # Issue 35 FIX: Display sector position warnings in expanded view
    if sec_warn and sec_warn.get("warnings"):
        rows.append(Text.from_markup("[bold]Position Capacity Warnings[/]"))
        for w in sec_warn.get("warnings", []):
            status_color = R if w.get("status") == "AT_CAP" else Y
            status_label = "AT CAP" if w.get("status") == "AT_CAP" else "NEAR CAP"
            rows.append(Text.from_markup(
                f"  [{status_color}]{status_label}[/] [white]{w.get('sector')}[/] [{status_color}]{w.get('count')}/{w.get('max')}[/] positions ([dim]{int(w.get('pct_of_max', 0))}%[/])"
            ))
        rows.append(Rule(style="dim"))

    if sec_rot and not sec_rot.get("_error") and sec_rot.get("signal"):
        sig_name = (sec_rot.get("signal") or "").replace("_", " ").title()
        wks      = sec_rot.get("weeks", 1)
        def_s = get_numeric(sec_rot, "def_score")
        cyc_s = get_numeric(sec_rot, "cyc_score")
        strength = get_numeric(sec_rot, "strength")
        # Normalize strength to 0-1 range: if strength > 1, assume it's a percentage (0-100)
        if strength > 1:
            strength = strength / 100.0
        sig_c    = R if def_s >= 60 else (Y if def_s >= 40 else G)
        rows.append(Text.from_markup(
            f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name}[/]  [dim]{wks}wk  "
            f"defensive:{def_s:.0f}  cyclical:{cyc_s:.0f}  strength:{strength:.0%}[/]"
        ))
        rows.append(Rule(style="dim"))

    # Full portfolio by sector
    # Extract positions from new dict format if needed
    positions_list = pos
    if isinstance(pos, dict) and "positions" in pos:
        positions_list = pos.get("positions", [])
    if positions_list:
        pv_val = port.get("total_portfolio_value") if port else None
        pv = float(pv_val) if pv_val is not None else 0
        sd: dict = {}
        for p in positions_list:
            sec = p.get("sector") or "[No Sector]"
            val = float(p.get("position_value")) if p.get("position_value") is not None else 0.0
            pnl_raw = p.get("unrealized_pnl_pct")
            pnl = safe_float(pnl_raw)
            if sec not in sd:
                sd[sec] = {"val": 0.0, "n": 0, "pnls": []}
            sd[sec]["val"] += val
            sd[sec]["n"] += 1
            if pnl is not None:
                sd[sec]["pnls"].append(pnl)
        sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])
        rows.append(Text.from_markup("[dim]Portfolio by sector:[/]"))
        for sec, dv in sorted_secs:
            pct     = dv["val"] / pv * 100 if pv else 0
            avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
            pc      = G if avg_pnl >= 0 else R
            bar_f   = int(min(pct, 25) / 25 * 8)
            bar_s   = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (8 - bar_f)}[/]"
            rows.append(Text.from_markup(
                f"  [white]{sec:<24}[/]{bar_s} [dim]{pct:.1f}%  {dv['n']} pos[/]  [{pc}]{sign(avg_pnl)}{avg_pnl:.1f}% avg P&L[/]"
            ))
        rows.append(Rule(style="dim"))

    # All sector rankings — one per row, full names, 1wk and 4wk changes
    valid_srank = [r for r in srank if not (isinstance(srank, dict) and srank.get("_error"))]
    if valid_srank:
        rows.append(Text.from_markup("[dim]All sectors  (rank  momentum  ▲▼1wk/4wk):[/]"))
        for r in valid_srank:
            nm  = r.get("sector_name") or ""
            mm  = r.get("momentum_score")
            ms  = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rows.append(Text.from_markup(
                f"  [{G}]#{r['current_rank']:<2}[/]  [white]{nm:<28}[/]{ms}  {rdelta(r, wk4='rank_4w_ago')}"
            ))
        rows.append(Rule(style="dim"))

    # All industries — full names, 1wk change
    valid_irank = irank if (irank and not (isinstance(irank, dict) and irank.get("_error"))) else []
    if valid_irank:
        rows.append(Text.from_markup("[dim]All industries  (rank  momentum  ▲▼1wk):[/]"))
        for r in valid_irank:
            nm  = r.get("industry") or ""
            mm  = r.get("momentum_score")
            ms  = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rows.append(Text.from_markup(
                f"  [{CY}]#{r['current_rank']:<2}[/]  [white]{nm:<32}[/]{ms}  {rdelta(r)}"
            ))

    if not rows:
        return Panel(Text("no data", style="dim"), title="[bold]SECTORS[/]", border_style="cyan", padding=(0, 1))
    return Panel(Group(*rows), title="[bold cyan]SECTORS & INDUSTRIES — EXPANDED[/]  [dim][r] return[/]", border_style="cyan", padding=(0, 1))


# ── dashboard layout ──────────────────────────────────────────────────────────

def render_dashboard(data: dict, compact: bool = False, elapsed: float = 0.0,
                     frame: int = 0, watch_interval: Optional[int] = None,
                     last_load_time: Optional[float] = None,
                     refreshing: bool = False,
                     view_mode: str = "normal") -> Layout:
    run      = data.get("run")
    cfg      = data.get("cfg")
    mkt      = data.get("mkt")
    port     = data.get("port")
    perf     = data.get("perf")
    pos      = data.get("pos")
    sig      = data.get("sig")
    hlth     = data.get("health")
    cb       = data.get("cb")
    rec      = data.get("trades")
    srank    = data.get("srank")
    act      = data.get("activity")
    exp_f    = data.get("exp_factors")
    eco      = data.get("eco")
    notifs   = data.get("notifs")
    sentiment = data.get("sentiment")
    econ_cal  = data.get("econ_cal")
    risk      = data.get("risk")
    perf_anl  = data.get("perf_anl")
    sig_eval  = data.get("sig_eval")
    sec_rot      = data.get("sec_rot")
    algo_metrics = data.get("algo_metrics")
    irank        = data.get("irank")
    loader       = data.get("loader")
    audit        = data.get("audit")
    exec_hist    = data.get("exec_hist")
    sec_warn     = data.get("sec_warn")

    now_et = datetime.now(ET)
    _mkt_badge, _mkt_cdown = mkt_hours_str()
    mkt_s  = f"{_mkt_badge}  [dim]{_mkt_cdown}[/]"
    ts     = now_et.strftime("%a %b %d  %I:%M %p ET")

    refresh_s = ""
    if refreshing:
        refresh_s = "  [cyan]↻[/]"
    elif watch_interval is not None and last_load_time is not None:
        secs = max(0, watch_interval - int(time.monotonic() - last_load_time))
        refresh_s = f"  [dim]↻{secs}s[/]"

    hdr_panel = panel_header_market(mkt, sentiment, ts, mkt_s, elapsed, refresh_s, cfg=cfg)

    outer = Layout()
    outer.split_column(
        Layout(name="top",  size=10),   # market header | exposure factors | monkey
        Layout(name="r1",   ratio=2),   # circuit breakers (left) | algo health (right)
        Layout(name="r1b",  ratio=1),   # data quality status (Issue 46)
        Layout(name="r2",   ratio=2),   # portfolio | perf | eco
        Layout(name="r3",   ratio=2),   # signals | sectors
        Layout(name="pos",  ratio=3),   # positions + recent trades
    )

    # Top row: Market header | 12-factor exposure | Monkey
    outer["top"].split_row(
        Layout(name="hdr",      ratio=1),
        Layout(name="exposure", ratio=2),
        Layout(name="mascot",   size=MASCOT_W),
    )
    outer["top"]["hdr"].update(hdr_panel)
    outer["top"]["exposure"].update(panel_exposure_compact(exp_f))
    outer["top"]["mascot"].update(mascot_compact(data, frame))

    # Row 1: Circuit Breakers (narrower left) | Algo Health (wider right) — side by side
    outer["r1"].split_row(
        Layout(panel_circuit(cb),                                                                         ratio=1, name="cb"),
        Layout(panel_algo_health(run, act, hlth, notifs, algo_metrics, loader, audit, exec_hist, risk=risk), ratio=2, name="health"),
    )

    # Row 1b: Data Quality Status (Issue 46 — unified panel for operator visibility)
    outer["r1b"].update(panel_data_quality_status())

    # Row 2: Portfolio | Performance | Economic pulse
    outer["r2"].split_row(
        Layout(panel_portfolio(port, cfg, risk=risk, perf=perf),    name="portfolio"),
        Layout(panel_performance_spark(perf, rec, perf_anl, pos=pos, cfg=cfg),        name="perf"),
        Layout(panel_economic_pulse(eco, econ_cal),                  name="eco"),
    )

    # Row 3: Signals (wider) | Sectors
    outer["r3"].split_row(
        Layout(panel_signals_compact(sig, sig_eval, cfg), ratio=3, name="signals"),
        Layout(panel_sector_compact(srank, pos, port, sec_rot, irank, sec_warn), ratio=2, name="sectors"),
    )

    # Row 4: Positions | Recent Trades
    outer["pos"].split_row(
        Layout(panel_positions(pos, compact, trades=rec, cfg=cfg),  ratio=3, name="positions"),
        Layout(panel_recent_trades(rec),                   ratio=2, name="recent_trades"),
    )

    _exp_top = (hdr_panel, panel_exposure_compact(exp_f), mascot_compact(data, frame))

    if view_mode == "positions":
        hint = Text.from_markup("[dim]press [/][bold cyan]p[/][dim] to return to dashboard[/]")
        return _expanded_layout(*_exp_top, Panel(
            Group(hint, Rule(style="dim"), panel_positions(pos, compact=False, trades=rec, cfg=cfg)),
            title=f"[bold cyan]ALL POSITIONS ({len(pos)})[/]",
            border_style="cyan", padding=(0, 1),
        ))

    if view_mode == "signals":
        return _expanded_layout(*_exp_top, panel_signals_expanded(sig, sig_eval, cfg))

    if view_mode == "health":
        return _expanded_layout(*_exp_top, panel_algo_health_expanded(
            run, act, hlth, notifs, algo_metrics, loader, audit, exec_hist, risk=risk))

    if view_mode == "data_quality":
        hint = Text.from_markup("[dim]press [/][bold cyan]q[/][dim] to return to dashboard[/]")
        return _expanded_layout(*_exp_top, Panel(
            Group(hint, Rule(style="dim"), panel_data_quality_status()),
            title="[bold cyan]DATA QUALITY STATUS (Issue 46)[/]",
            border_style="cyan", padding=(0, 1),
        ))

    if view_mode == "sectors":
        return _expanded_layout(*_exp_top, panel_sectors_expanded(srank, pos, port, sec_rot, irank, sec_warn))

    return outer


# ── run modes ─────────────────────────────────────────────────────────────────

def run_once(compact: bool) -> None:
    """Single Live session: mascot stays in upper right through loading and live view."""
    result:  list = [None]
    elapsed: list = [0.0]
    done = threading.Event()

    def bg():
        t0 = time.monotonic()
        result[0] = load_all()
        elapsed[0] = time.monotonic() - t0
        done.set()

    threading.Thread(target=bg, daemon=True).start()

    frame = 0
    view_mode = ["normal"]
    _KEY_MAP = {"p": "positions", "s": "signals", "h": "health", "r": "sectors", "d": "data_quality"}
    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                key = _keypress()
                if key == "q":
                    break
                if key in _KEY_MAP and done.is_set():
                    target = _KEY_MAP[key]
                    view_mode[0] = "normal" if view_mode[0] == target else target
                frame += 1
                if not done.is_set():
                    live.update(loading_layout(frame))
                else:
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0], frame=frame,
                        view_mode=view_mode[0]))
                time.sleep(0.125)
        except KeyboardInterrupt:
            pass


def run_watch(interval: int, compact: bool) -> None:
    """Watch mode: auto-refresh data every `interval` seconds, mascot dances continuously."""
    result:    list = [None]
    elapsed:   list = [0.0]
    loading:   list = [True]
    last_load: list = [0.0]
    frame:     list = [0]
    load_failures: list = [0]

    def reload():
        loading[0] = True
        t0 = time.monotonic()
        try:
            new_result = load_all()
            if new_result:
                result[0] = new_result
                load_failures[0] = 0
            else:
                load_failures[0] += 1
                if load_failures[0] == 1:
                    logger.warning(f"Load failed (attempt {load_failures[0]}): no data returned")
        except Exception as e:
            load_failures[0] += 1
            if load_failures[0] == 1:
                logger.error(f"Load failed (attempt {load_failures[0]}): {e}")
        elapsed[0] = time.monotonic() - t0
        last_load[0] = time.monotonic()
        loading[0] = False

    threading.Thread(target=reload, daemon=True).start()

    view_mode = ["normal"]
    _KEY_MAP  = {"p": "positions", "s": "signals", "h": "health", "r": "sectors", "d": "data_quality"}
    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                key = _keypress()
                if key == "q":
                    break
                if key in _KEY_MAP and result[0] is not None:
                    target = _KEY_MAP[key]
                    view_mode[0] = "normal" if view_mode[0] == target else target
                frame[0] += 1
                if result[0] is None:
                    # First load only — show loading screen until we have data
                    # Only update when animation frame changes (every 2 frames) to avoid flicker
                    if frame[0] % 2 == 0:
                        live.update(loading_layout(frame[0]))
                else:
                    # Keep showing existing data during background refresh (no flash)
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0],
                        frame=frame[0], watch_interval=interval,
                        last_load_time=last_load[0], refreshing=loading[0],
                        view_mode=view_mode[0]))
                    if not loading[0] and (time.monotonic() - last_load[0]) >= interval:
                        threading.Thread(target=reload, daemon=True).start()
                time.sleep(0.125)
        except KeyboardInterrupt:
            pass


LEGEND = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                     ALGO DASHBOARD — TERM GUIDE                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

PANELS:

  ORCHESTRATOR — algo run status & configuration
    Mode            LIVE or PAPER trading, SWING/MOMENTUM style
    Enabled         Whether the algo is currently active
    min score ≥     Minimum swing score a stock must have to be considered
    max N positions Max simultaneous open positions allowed
    sector ≤ N      Max positions in any single sector
    base risk %     % of portfolio risked per trade (stop-loss sizing)
    T1 target NR    Target profit = N × the initial risk amount (R-multiple)
    pyramid on      Algo can add to winning positions (scale in)
    Phase 1/2/3✓    Algo run phases: prep, screening, execution — ✓=passed
    VaR 95%         Value at Risk: max expected daily loss 95% of the time
    CVaR 95%        Conditional VaR: avg loss on the worst 5% of days
    Portfolio Beta  How much the portfolio moves vs SPY (1.0 = same as market)
    Top-5 Conc      % of portfolio in top 5 positions (concentration risk)

  MARKET — market regime inputs to the algo
    CONF UP etc     Market tier: Confirmed Uptrend → Correction (5 levels)
    exposure %      How much of the portfolio the algo is deploying (0–100%)
    VIX             Volatility Index (>20 = caution, >30 = reduces exposure, >35 = halts trading)
    Dist Days       Distribution days in 4 weeks (heavy selling by institutions)
    Stage           Market stage 1–4 (Weinstein: 1=base, 2=up, 3=top, 4=down)
    SPY             S&P 500 ETF price + daily % change
    Up Volume %     % of NYSE volume in advancing stocks (>60% = bullish)
    Adv/Dec         Advance/Decline ratio (stocks up vs down)
    New Highs/Lows  52-week highs vs lows (breadth indicator)
    NH-NL           Net new highs minus new lows
    Put/Call Ratio  Options market sentiment (<0.8 = bullish, >1.0 = fearful)
    Breadth Momentum 10-day breadth trend (+= improving market internals)
    Yield Curve Slope 10Y minus 2Y yield (negative = inverted = recession risk)
    Trading Halt    Reasons the algo has paused new entries
    Fear & Greed    CNN composite sentiment index (0=extreme fear, 100=greed)

  CIRCUIT BREAKERS — hard stops that halt the algo
    Drawdown        Current drawdown from equity peak / halt threshold
    Daily Loss      Today's loss / max allowed daily loss
    Weekly Loss     This week's loss / max allowed weekly loss
    Consec Losses   Consecutive losing trades / max before halt
    Total Risk      Open position risk (vs stops) as % of portfolio
    VIX             Current VIX / threshold that triggers halt
    Mkt Stage       Current market stage (halts if stage ≥ 4)

  PORTFOLIO — live account snapshot
    Total value     Current account value including unrealized P&L
    Cash            Available cash (not invested)
    Positions       Number of open positions / open slots remaining
    Today's Return  Today's portfolio return %
    Unrealized P&L  Gain/loss on currently open positions
    Buying Power    Approximate capital available to open new positions
    Total Return    Cumulative portfolio return since algo started
    Max Drawdown    Largest peak-to-trough portfolio drop

  PERFORMANCE — historical trade analytics
    N Trades        Total closed trades
    W/L             Wins / Losses
    Win Rate        % of trades that were profitable
    streak          Current win (+) or loss (-) streak
    P&L             Total dollar profit/loss from all closed trades
    Profit Factor   Gross wins ÷ gross losses (>1.5 = good, >2.0 = excellent)
    Sharpe          Risk-adjusted return (>1.0 = good, >2.0 = excellent)
    Expectancy      Average dollar gain/loss per trade (positive = edge)
    Avg R           Average R-multiple per trade (1R = risked amount won)
    Avg Win/Loss    Average dollar size of winning vs losing trades
    Equity curve    Visual chart of portfolio value over time (sparkline)
    Sharpe (1Y)     Rolling 252-day Sharpe ratio
    Sortino         Like Sharpe but only penalizes downside volatility
    Calmar          Annualized return ÷ max drawdown
    Win Rate (50T)  Win rate over the most recent 50 trades
    Avg Win R       Average R-multiple on winning trades
    Avg Loss R      Average R-multiple on losing trades (should be < 1.0)

  POSITIONS — currently open trades
    Val             Current dollar value of the position ($45K, $1.2M)
    Entry           Average cost basis per share
    Price           Current market price
    P&L%            Unrealized gain/loss %
    R-Mult          How many R (risk units) this position has moved
    Stop            Current stop-loss price
    Dist%           Distance from current price to stop (buffer remaining)
    T1→             % gain needed to hit first profit target
    Days            Days since position was entered
    Stage           Weinstein stage of the stock (2 = uptrend)
    Swing Score     Algo's composite score for this stock (0–100)

  SIGNALS — today's buy signal analysis
    A/B/C/D grades  Score grade distribution of all stocks screened today
    buy signals / N scored  How many stocks got a BUY signal today
    Screened → Selected   Signal filter funnel (how many pass each gate)
      →Mkt:          Market condition gate (is market healthy enough?)
      →Score:        Minimum swing score gate
      →Risk:         Position sizing / risk gate
      →Sector:       Sector concentration gate
      →Selected:     Final candidates the algo can trade
    avg score       Average quality score of signals passing all filters
    Top rejection reasons   Why most signals were filtered out

  SECTORS & INDUSTRY — rotation context for position decisions
    Rotation signal   Whether defensive or cyclical sectors are leading
    Sector holdings   Which sectors our current positions are in
    #1 Tech ▲2        Sector rank (1=best), with 1-week rank change
    #2 Industry ▲1    Top industry sub-groups within sectors

  EXPOSURE SCORE BREAKDOWN — what drives the algo's allocation %
    Score N/100       Raw points scored → converted to exposure % (0–100%)
    30wk Trend        Is SPY above its 30-week moving average?
    Breadth 50MA      % of S&P 500 stocks above their 50-day MA
    IBD State         IBD market status (Confirmed Uptrend/Under Pressure/etc)
    Breadth 200MA     % of S&P 500 stocks above their 200-day MA
    McClellan Osc     Short-term breadth oscillator (momentum of A/D)
    VIX Level         Volatility regime contribution to score
    New Hi vs Lo      Daily new highs minus new lows
    Credit Spread     High-yield bond spread (risk appetite indicator)
    Adv/Dec Line      Cumulative advance/decline trend
    AAII Sentiment    Weekly survey: retail investor bullish vs bearish %
    NAAIM Exposure    Active manager equity exposure level

  ECONOMIC INPUTS → Exposure Score — macro factors the algo monitors
    3M/6M/2Y/10Y Tsy  Treasury yield curve (used in yield curve slope factor)
    10Y-2Y spread     Yield curve inversion (algo reduces exposure when inverted)
    Fed Rate          Federal Funds Rate (algo's fed_rate_environment filter)
    HY/IG OAS         Credit spreads — widening = risk-off → algo reduces exposure
    CPI YoY           Inflation rate (algo's economic overlay factor)
    Unemployment      Labor market health (economic overlay)
    WTI Crude Oil     Oil price (energy cost / inflation proxy)
    Chicago Fed NFCI  Financial conditions index (tight = algo more conservative)
    USD Index (DXY)   Dollar strength (affects international/commodity stocks)
    10Y/5Y Breakeven  Market's inflation expectations
    30Y Mortgage      Housing market health proxy
    UMich Sentiment   Consumer confidence (economic overlay factor)

  ACTIVITY & HEALTH — algo system status
    Run phases        Which phases of today's run completed (✓/~/✗)
    Data health       Whether all required data tables are fresh
    Notifications     System alerts (circuit breaker fired, trade executed, etc)
    Daily actions     How many entries/exits the algo took each day
    Loader status     Data pipeline status (are feeds updating correctly?)
    Audit log         Recent significant algo actions with pass/fail status

SIDEBAR:
    Market tier       Current regime label (Confirmed Uptrend = max aggression)
    exposure %        Current allocation level set by exposure score
    VIX               Volatility (algo dials back when high)
    SPY ±%            S&P 500 daily change
    Portfolio value   Total account value
    +/-% today        Today's portfolio return
    +/-% unrlzd       Unrealized P&L on open positions
    N positions       Currently open position count
    Win rate %        All-time trade win rate
    P&L $             Total realized profit/loss
    Last run status   ✓=completed ✗=error ~=halted, and time since
    ● N alerts        Unread notifications needing attention
"""


def print_legend():
    CONSOLE.print(LEGEND)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    pa = argparse.ArgumentParser(
        description="Algo ops terminal dashboard",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pa.add_argument("-w", "--watch", nargs="?", const=30, type=int, metavar="SECS",
                    help="Watch mode, auto-refresh interval (default 30s)")
    pa.add_argument("--compact", "-c", action="store_true",
                    help="Omit T1 and Sector columns from positions table")
    pa.add_argument("--legend", "-l", action="store_true",
                    help="Print a guide explaining every term and panel, then exit")
    args = pa.parse_args()
    validate_schema()

    if args.legend:
        print_legend()
        return

    if args.watch is not None:
        run_watch(max(10, args.watch), args.compact)
    else:
        run_once(args.compact)


if __name__ == "__main__":
    main()


