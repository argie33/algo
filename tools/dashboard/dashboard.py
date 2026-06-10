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
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

def _log_data_quality(source: str, count: int, error: Optional[str] = None):
    """Log data fetch results: distinguishes 'empty' (no rows but no error) from 'failed' (error occurred).

    Log levels:
    - ERROR: fetch failed due to database/parsing error
    - WARNING: fetch succeeded but returned 0 rows (may indicate problem or expected state)
    - DEBUG: fetch succeeded with data
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
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

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
}

TIER_SHORT = {
    "confirmed_uptrend": "CONF UP",
    "healthy_uptrend":   "HLTH UP",
    "pressure":          "PRESSURE",
    "caution":           "CAUTION",
    "correction":        "CORRECT",
}

GRADE_A_PLUS = 90
GRADE_A = 80
GRADE_B = 70
GRADE_C = 60

HBAR_CRITICAL = 1.0
HBAR_WARNING = 0.75

MINIBAR_HIGH = 0.75
MINIBAR_MED = 0.35

TIER_THRESHOLD_CONFIRMED = 80
TIER_THRESHOLD_HEALTHY = 60
TIER_THRESHOLD_PRESSURE = 40
TIER_THRESHOLD_CAUTION = 20

YIELD_CURVE_GOOD = 0.5
IG_OAS_GOOD = 1.0
IG_OAS_WARNING = 2.0
HY_OAS_GOOD = 3.5
HY_OAS_WARNING = 6.0
CPI_GOOD = 2.5
CPI_WARNING = 4.0
UNRATE_GOOD = 4.5
UNRATE_WARNING = 6.0
NFCI_NEGATIVE = -0.3
NFCI_POSITIVE = 0.3
DXY_WARNING = 100
DXY_CRITICAL = 110
BE_CRITICAL = 3.0
BE_WARNING = 2.5
MORTGAGE_WARNING = 6.0
MORTGAGE_CRITICAL = 7.0
UMCSENT_GOOD = 80
UMCSENT_WARNING = 60

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
    if (data.get("cb") or {}).get("any"):
        # Panic dance: mostly LOAD_SEQ energy, freeze face appears once per 20 poses (~5%)
        seq = [4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 7]
        return seq[(frame // 2) % len(seq)]
    return LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db_credentials() -> dict:
    """Fetch DB credentials: try env vars first, then AWS Secrets Manager."""
    env_creds = {
        "host": os.environ.get("DB_HOST"),
        "user": os.environ.get("DB_USER"),
        "password": os.environ.get("DB_PASSWORD"),
        "dbname": os.environ.get("DB_NAME"),
        "port": int(os.environ.get("DB_PORT", 5432)),
    }

    # If env vars are complete, use them
    if all([env_creds["host"], env_creds["user"], env_creds["password"], env_creds["dbname"]]):
        return env_creds

    # Otherwise try AWS Secrets Manager
    if boto3:
        try:
            client = boto3.client("secretsmanager", region_name="us-east-1")
            secret_name = os.environ.get("DB_SECRET_NAME", "algo-db-credentials")
            response = client.get_secret_value(SecretId=secret_name)
            secret_dict = json.loads(response.get("SecretString", "{}"))
            return {
                "host": secret_dict.get("host"),
                "user": secret_dict.get("username"),
                "password": secret_dict.get("password"),
                "dbname": secret_dict.get("dbname"),
                "port": secret_dict.get("port", 5432),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch credentials from Secrets Manager: {e}. Using env vars.")

    return env_creds

def get_conn() -> psycopg2.extensions.connection:
    creds = _get_db_credentials()
    miss = [k for k, v in creds.items() if not v]
    if miss:
        sys.exit(f"Missing DB credentials: {', '.join(miss)}")
    return psycopg2.connect(
        host=creds["host"], port=creds["port"],
        user=creds["user"], password=creds["password"],
        dbname=creds["dbname"], connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
        options="-c statement_timeout=30000",
    )

def q(c: psycopg2.extensions.connection, sql: str, p: Optional[tuple] = None) -> List[Dict]:
    with c.cursor() as cur:
        cur.execute(sql, p or ())
        return [r if isinstance(r, dict) else dict(r) for r in cur.fetchall()]

def q1(c: psycopg2.extensions.connection, sql: str, p: Optional[tuple] = None) -> Optional[Dict]:
    rows = q(c, sql, p)
    return rows[0] if rows else None

def validate_schema() -> None:
    try:
        conn = get_conn()
        critical_checks = [
            ("algo_positions", ["avg_entry_price", "current_price", "stop_loss_price"]),
            ("algo_portfolio_snapshots", ["total_portfolio_value", "daily_return_pct"]),
            ("algo_trades", ["profit_loss_dollars", "exit_date", "status"]),
            ("price_daily", ["close"]),
        ]
        for table, cols in critical_checks:
            result = q1(conn, f"""
                SELECT COUNT(*) as col_count FROM information_schema.columns
                WHERE table_name = %s AND column_name = ANY(%s)
            """, (table, cols))
            if result and result.get("col_count") != len(cols):
                logger.error(f"Schema validation failed: {table} missing columns {cols}")
                sys.exit(f"Database schema error: {table} missing required columns")

            # Also verify critical tables have data
            row_count = q1(conn, f"SELECT COUNT(*) as cnt FROM {table}")
            if row_count and row_count.get("cnt") == 0:
                logger.warning(f"Schema validation: {table} exists but is EMPTY (no rows)")

        conn.close()
        logger.info("Database schema validation passed")
    except (psycopg2.Error, KeyError) as e:
        logger.error(f"Schema validation failed: {e}")
        sys.exit(f"Database connection/schema error: {e}")


# ── formatters ────────────────────────────────────────────────────────────────

def fmt_age(ts: any) -> str:
    if ts is None: return "--"
    try:
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                return "--"
        if isinstance(ts, date) and not isinstance(ts, datetime):
            ts = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        m = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
        if m < 60:   return f"{m}m ago"
        if m < 1440: return f"{m // 60}h{m % 60:02d}m ago"
        return f"{m // 1440}d ago"
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"fmt_age error parsing {ts!r}: {e}")
        return "--"

def fmt_money(v: any) -> str:
    if v is None: return "--"
    v = float(v)
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6: return f"{s}${av / 1e6:.2f}M"
    if av >= 1e3: return f"{s}${av:,.0f}"
    return f"{s}${av:.2f}"

def fmt_money_short(v: any) -> str:
    """Compact dollar format: $45K, $1.2M, $850 — for narrow table columns."""
    if v is None: return "--"
    v = float(v)
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6: return f"{s}${av/1e6:.1f}M"
    if av >= 1e3: return f"{s}${av/1e3:.0f}K"
    return f"{s}${av:.0f}"

def grade(s: float) -> str:
    s = float(s)
    if s >= GRADE_A_PLUS: return "A+"
    if s >= GRADE_A: return "A"
    if s >= GRADE_B: return "B"
    if s >= GRADE_C: return "C"
    return "D"

def tier_from_pct(p: Optional[float]) -> str:
    if p is None: return "unknown"
    p = float(p)
    if p >= TIER_THRESHOLD_CONFIRMED: return "confirmed_uptrend"
    if p >= TIER_THRESHOLD_HEALTHY: return "healthy_uptrend"
    if p >= TIER_THRESHOLD_PRESSURE: return "pressure"
    if p >= TIER_THRESHOLD_CAUTION: return "caution"
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
    r = min(float(cur) / float(thr), 1.0) if thr and float(thr) > 0 else 0
    f = int(r * w)
    c = R if r >= HBAR_CRITICAL else (Y if r >= HBAR_WARNING else G)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def exp_bar(pct, w=12):
    f = int(min(float(pct or 0), 100) / 100 * w)
    tc = TIER_COLOR.get(tier_from_pct(pct), "dim")
    return f"[{tc}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def mini_bar(pts: Optional[float], max_pts: Optional[float], w: int = 5) -> str:
    r = min(float(pts or 0) / float(max_pts or 1), 1.0)
    f = int(r * w)
    c = G if r >= MINIBAR_HIGH else (Y if r >= MINIBAR_MED else R)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def sign(v) -> str:
    return "+" if float(v) >= 0 else ""

def sparkline(values: list, width: int = 24) -> str:
    vals = [v for v in (values or []) if v is not None and float(v) > 0]
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

def _parse_event_date(ed: any) -> Optional[date]:
    """Parse event date from various formats (always returns naive date, handling timezone-aware inputs).

    Converts all datetime inputs to UTC before extracting the date to ensure consistent
    date boundaries regardless of input timezone.
    """
    if ed is None:
        return None
    try:
        if isinstance(ed, str):
            return datetime.strptime(ed[:10], "%Y-%m-%d").date()
        elif isinstance(ed, datetime):
            if ed.tzinfo is not None:
                ed = ed.astimezone(timezone.utc)
            return ed.date()
        elif isinstance(ed, date):
            return ed
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning(f"Failed to parse event_date: {ed} (type: {type(ed).__name__}): {e}")
    return None


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
            pr = row.get("phase_results") or []
            if isinstance(pr, str):
                try: pr = json.loads(pr)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase_results JSON: {e}")
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
                "phases_completed": row.get("phases_completed") or [],
                "phases_halted":    row.get("phases_halted") or [],
                "phases_errored":   row.get("phases_errored") or [],
                "phase_results":    pr,
                "_source": "exec_log",
            }
            _log_data_quality("fetch_run", 1)
            return result
        _log_data_quality("fetch_run", 0)
        return {}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_run (exec_log): {type(e).__name__}: {e}")
        _log_data_quality("fetch_run", 0, str(e))
        return {}

    # Fallback: reconstruct from algo_audit_log
    try:
        latest = q1(c, """
            SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
            FROM algo_audit_log WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"):
            _log_data_quality("fetch_run", 0)
            return {}
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
        return {}

def fetch_algo_config(c):
    try:
        keys = ["enable_algo", "execution_mode", "max_position_size_pct",
                "max_positions", "max_positions_per_sector", "min_swing_score",
                "alpaca_paper_trading", "base_risk_pct", "t1_target_r_multiple",
                "pyramid_enabled"]
        rows = q(c, "SELECT key, value FROM algo_config WHERE key=ANY(%s)", (keys,))
        d = {r["key"]: r["value"] for r in rows}
        paper  = d.get("alpaca_paper_trading", "false").lower() == "true"
        mode   = d.get("execution_mode", "unknown").upper()
        mode_s = f"{mode}/PAPER" if paper else mode
        _log_data_quality("fetch_algo_config", 1)
        return {
            "enabled":      d.get("enable_algo", "true").lower() == "true",
            "mode":         mode_s,
            "max_pos_pct":  d.get("max_position_size_pct"),
            "max_pos_n":    d.get("max_positions"),
            "max_sec_n":    d.get("max_positions_per_sector"),
            "min_score":    d.get("min_swing_score"),
            "base_risk":    d.get("base_risk_pct"),
            "t1_r":         d.get("t1_target_r_multiple"),
            "pyramid":      d.get("pyramid_enabled", "false").lower() == "true",
        }
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_algo_config: {type(e).__name__}: {e}")
        _log_data_quality("fetch_algo_config", 0, str(e))
        return {}

def fetch_market(c):
    try:
        exp  = q1(c, "SELECT exposure_pct, halt_reasons, date FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
        h    = q1(c, """SELECT market_stage, vix_level, distribution_days_4w,
                               spy_close, market_trend, up_volume_percent,
                               advance_decline_ratio, new_highs_count, new_lows_count,
                               put_call_ratio, yield_curve_slope, breadth_momentum_10d,
                               fed_rate_environment, date
                        FROM market_health_daily ORDER BY date DESC LIMIT 1""")
        pct   = float(exp.get("exposure_pct")) if exp and exp.get("exposure_pct") is not None else None
        halts = exp.get("halt_reasons") or [] if exp else []
        if isinstance(halts, str):
            try: halts = json.loads(halts)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse halt_reasons JSON: {e}")
                halts = [halts] if halts else []

        # Check data freshness (should be from today or recent trading day)
        exp_age = None
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

        vix_row = q1(c, "SELECT vix_level FROM market_health_daily WHERE vix_level IS NOT NULL AND vix_level > 0 ORDER BY date DESC LIMIT 1")
        vix_v   = vix_row.get("vix_level") if vix_row else None
        def _f(key): return float(h[key]) if h and h.get(key) is not None else None
        def _i(key): return int(h[key])   if h and h.get(key) is not None else None
        spy_v = _f("spy_close")
        spy_chg = None
        spy_rows = q(c, "SELECT close, date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 2")
        spy_age = None
        if len(spy_rows) >= 2:
            close0 = spy_rows[0].get("close")
            close1 = spy_rows[1].get("close")
            if close0 is not None and close1 is not None:
                cur_spy  = float(close0)
                prev_spy = float(close1)
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
        elif len(spy_rows) == 1 and spy_v is None:
            close0 = spy_rows[0].get("close")
            if close0 is not None:
                spy_v = float(close0)
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
        if not fed_val or fed_val in ("unknown", "Unknown"): fed_val = None

        # Log staleness if data is old and track for dashboard display
        stale_alerts = []
        if exp_age is not None and exp_age > 1:
            logger.warning(f"Market exposure data is {exp_age} days old")
            stale_alerts.append(f"Exposure {exp_age}d old")
        if spy_age is not None and spy_age > 1:
            logger.warning(f"SPY price data is {spy_age} days old")
            stale_alerts.append(f"SPY {spy_age}d old")

        _log_data_quality("fetch_market", 1)
        return {
            "pct":   pct,
            "tier":  tier_from_pct(pct),
            "halts": halts,
            "vix":     float(vix_v) if vix_v is not None else None,
            "dist":    _i("distribution_days_4w"),
            "stage":   _i("market_stage"),
            "spy":     spy_v,
            "spy_chg": spy_chg,
            "spy_age": spy_age,
            "exp_age": exp_age,
            "stale_alerts": stale_alerts,
            "trend":   h.get("market_trend") if h else None,
            "upvol": _f("up_volume_percent"),
            "adr":   _f("advance_decline_ratio"),
            "nh":    _i("new_highs_count"),
            "nl":    _i("new_lows_count"),
            "pcr":   _f("put_call_ratio"),
            "ycs":   _f("yield_curve_slope"),
            "bmom":  _f("breadth_momentum_10d"),
            "fed":   fed_val,
        }
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_market: {type(e).__name__}: {e}")
        _log_data_quality("fetch_market", 0, str(e))
        return {}

def fetch_exposure_factors(c):
    try:
        row = q1(c, """SELECT raw_score, exposure_pct, regime, factors
                       FROM market_exposure_daily ORDER BY date DESC LIMIT 1""")
        if not row:
            _log_data_quality("fetch_exposure_factors", 0)
            return {}
        factors = row.get("factors") or {}
        factors_error = None
        if isinstance(factors, str):
            try: factors = json.loads(factors)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse exposure factors JSON: {e}")
                factors_error = str(e)
                factors = {}
        result = {
            "raw_score":    float(row.get("raw_score") or 0),
            "exposure_pct": float(row.get("exposure_pct") or 0),
            "regime":       row.get("regime"),
            "factors":      factors,
        }
        if factors_error:
            result["_factors_parse_error"] = factors_error
        _log_data_quality("fetch_exposure_factors", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_exposure_factors: {type(e).__name__}: {e}")
        _log_data_quality("fetch_exposure_factors", 0, str(e))
        return {}

def fetch_portfolio(c):
    try:
        row = q1(c, """
            SELECT snapshot_date, total_portfolio_value, daily_return_pct,
                   unrealized_pnl_pct, position_count, total_cash,
                   cumulative_return_pct, max_drawdown_pct, largest_position_pct
            FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1""")
        result = dict(row or {})
        _log_data_quality("fetch_portfolio", 1 if row else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_portfolio: {type(e).__name__}: {e}")
        _log_data_quality("fetch_portfolio", 0, str(e))
        return {}

def fetch_perf(c):
    try:
        trades = q(c, """SELECT profit_loss_dollars, exit_r_multiple, profit_loss_pct
                         FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL
                         ORDER BY exit_date ASC""")
        if not trades:
            _log_data_quality("fetch_perf", 0)
            return {}
        wins      = [t for t in trades if t.get("profit_loss_dollars") is not None and float(t.get("profit_loss_dollars")) > 0]
        losses    = [t for t in trades if t.get("profit_loss_dollars") is not None and float(t.get("profit_loss_dollars")) < 0]
        breakeven = [t for t in trades if t.get("profit_loss_dollars") is not None and float(t.get("profit_loss_dollars")) == 0]
        pnl       = sum(float(t.get("profit_loss_dollars")) for t in trades if t.get("profit_loss_dollars") is not None)
        counted_trades = len(wins) + len(losses) + len(breakeven)
        wr        = len(wins) / counted_trades * 100 if counted_trades > 0 else 0
        streak = 0
        for t in reversed(trades):
            w = float(t.get("profit_loss_dollars") or 0) > 0
            if streak >= 0 and w:       streak += 1
            elif streak <= 0 and not w: streak -= 1
            else: break
        snaps = q(c, """SELECT daily_return_pct, total_portfolio_value
                        FROM algo_portfolio_snapshots ORDER BY snapshot_date ASC""")
        sharpe = None
        maxdd  = 0.0
        equity_vals = [float(s.get("total_portfolio_value") or 0)
                       for s in snaps if s.get("total_portfolio_value") is not None]
        if len(snaps) >= 10:
            rets = [float(s.get("daily_return_pct") or 0) / 100 for s in snaps if s.get("daily_return_pct") is not None]
            if len(rets) > 1:
                mn = statistics.mean(rets)
                sd = statistics.stdev(rets)
                if sd > 0: sharpe = round(mn / sd * (252 ** 0.5), 2)
            pk = 0.0
            for s in snaps:
                v = float(s.get("total_portfolio_value") or 0)
                if v > pk: pk = v
                if pk > 0: maxdd = max(maxdd, (pk - v) / pk * 100)
        win_amt   = [float(t.get("profit_loss_dollars")) for t in wins if t.get("profit_loss_dollars") is not None]
        loss_amt  = [abs(float(t.get("profit_loss_dollars"))) for t in losses if t.get("profit_loss_dollars") is not None]
        avg_win   = statistics.mean(win_amt)  if win_amt  else 0.0
        avg_loss  = statistics.mean(loss_amt) if loss_amt else 0.0
        gw = sum(win_amt); gl = sum(loss_amt)
        pf = round(gw / gl, 2) if gl > 0 else None
        exp = round(wr / 100 * avg_win - (1 - wr / 100) * avg_loss, 2) if trades else 0.0
        avg_r_vals = [float(t["exit_r_multiple"]) for t in trades if t.get("exit_r_multiple") is not None]
        avg_r = round(statistics.mean(avg_r_vals), 2) if avg_r_vals else None
        recent_rets = [(s.get("snapshot_date"), float(s.get("daily_return_pct") or 0))
                       for s in snaps[-7:] if s.get("snapshot_date") and s.get("daily_return_pct") is not None]
        _log_data_quality("fetch_perf", len(trades))
        return {"n": len(trades), "w": len(wins), "l": len(losses), "b": len(breakeven),
                "wr": round(wr, 1), "pnl": round(pnl, 2), "streak": streak,
                "sharpe": sharpe, "maxdd": round(maxdd, 1),
                "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
                "profit_factor": pf, "expectancy": exp, "avg_r": avg_r,
                "equity_vals": equity_vals, "recent_rets": recent_rets}
    except (psycopg2.Error, KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.error(f"fetch_perf: {type(e).__name__}: {e}")
        _log_data_quality("fetch_perf", 0, str(e))
        return {}

def fetch_positions(c):
    """Fetch open positions from algo_trades (single source of truth).

    Data derivation:
    - algo_trades WHERE status IN ('open','filled','partially_filled','active')
    - Latest price from price_daily for ONLY the open positions (not all symbols)
    - Trade metadata (stop, targets) from the trade record
    - Technical/fundamental data from supporting tables

    This eliminates sync issues that occur when algo_positions table
    drifts from algo_trades. Positions are now computed, not stored separately.

    Validation: Logs if algo_trades table is empty (no historical trades at all).
    """
    try:
        # Validation: check if algo_trades table has any data at all
        trade_check = q1(c, "SELECT COUNT(*) as n FROM algo_trades")
        total_trades = int(trade_check.get("n")) if trade_check and trade_check.get("n") is not None else 0
        if total_trades == 0:
            logger.warning("VALIDATION: algo_trades table is EMPTY - no historical trades found")
            _log_data_quality("fetch_positions", 0, "algo_trades table is empty")
            return []

        result = q(c, """
            WITH open_trades AS (
                -- All trades with active positions (source of truth)
                SELECT DISTINCT ON (symbol)
                    symbol, trade_id, entry_quantity, entry_price,
                    stop_loss_price, target_1_price, target_2_price, target_3_price,
                    trade_date, entry_time
                FROM algo_trades
                WHERE status IN ('open', 'filled', 'partially_filled', 'active')
                    AND exit_date IS NULL
                ORDER BY symbol, trade_date DESC
            ),
            latest_prices AS (
                -- Only get prices for open position symbols (not all 10k+ symbols)
                SELECT DISTINCT ON (symbol) symbol, close as current_price
                FROM price_daily
                WHERE symbol IN (SELECT DISTINCT symbol FROM open_trades)
                ORDER BY symbol, date DESC
            ),
            trend AS (
                SELECT DISTINCT ON (symbol) symbol, weinstein_stage
                FROM trend_template_data
                WHERE symbol IN (SELECT DISTINCT symbol FROM open_trades)
                ORDER BY symbol, date DESC
            ),
            swings AS (
                SELECT DISTINCT ON (symbol) symbol, score AS swing_score
                FROM swing_trader_scores
                WHERE symbol IN (SELECT DISTINCT symbol FROM open_trades)
                ORDER BY symbol, date DESC
            ),
            days_held AS (
                SELECT symbol,
                    (CURRENT_DATE - entry_time::date)::INT as days_since_entry
                FROM open_trades
            )
            SELECT
                ot.symbol,
                ot.entry_price as avg_entry_price,
                COALESCE(lp.current_price, ot.entry_price) as current_price,
                CASE
                    WHEN ot.entry_price > 0
                    THEN (((COALESCE(lp.current_price, ot.entry_price) - ot.entry_price) / ot.entry_price) * 100)
                    ELSE 0
                END as unrealized_pnl_pct,
                (ot.entry_quantity * COALESCE(lp.current_price, ot.entry_price))::DECIMAL(14,2) as position_value,
                dh.days_since_entry,
                ot.stop_loss_price,
                ot.target_1_price,
                t.weinstein_stage,
                cp.sector,
                s.swing_score
            FROM open_trades ot
            LEFT JOIN latest_prices lp ON ot.symbol = lp.symbol
            LEFT JOIN trend t ON ot.symbol = t.symbol
            LEFT JOIN company_profile cp ON cp.ticker = ot.symbol
            LEFT JOIN swings s ON ot.symbol = s.symbol
            LEFT JOIN days_held dh ON ot.symbol = dh.symbol
            ORDER BY position_value DESC""")
        _log_data_quality("fetch_positions", len(result) if result else 0)
        return result
    except psycopg2.Error as e:
        err_msg = str(e)
        error_detail = None
        if "does not exist" in err_msg:
            if "trend_template_data" in err_msg:
                error_detail = "Missing or renamed table trend_template_data (check column: weinstein_stage)"
            elif "company_profile" in err_msg:
                error_detail = "Missing or renamed table company_profile (check columns: sector, ticker)"
            elif "swing_trader_scores" in err_msg:
                error_detail = "Missing or renamed table swing_trader_scores (check column: score)"
            else:
                error_detail = f"Missing table in query. {err_msg}"
        elif "column" in err_msg and "does not exist" in err_msg:
            error_detail = f"Column name mismatch (check: weinstein_stage, sector, score). {err_msg}"
        else:
            error_detail = f"{type(e).__name__}: {err_msg}"
        logger.error(f"fetch_positions: {error_detail}")
        _log_data_quality("fetch_positions", 0, err_msg)
        return []
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_positions: {type(e).__name__}: {e}")
        _log_data_quality("fetch_positions", 0, str(e))
        return []

def fetch_recent_trades(c):
    try:
        result = q(c, """
            SELECT symbol, trade_date, exit_date, status,
                   profit_loss_dollars, profit_loss_pct, exit_r_multiple
            FROM algo_trades ORDER BY COALESCE(exit_date, trade_date) DESC LIMIT 10""")
        _log_data_quality("fetch_recent_trades", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_recent_trades: {type(e).__name__}: {e}")
        _log_data_quality("fetch_recent_trades", 0, str(e))
        return []

def fetch_signals(c):
    try:
        sig = q1(c, """
            SELECT COUNT(*) AS n, MAX(date) AS d FROM buy_sell_daily
            WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily')
              AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily'))""")
        total_r = q1(c, """SELECT COUNT(*) AS n FROM buy_sell_daily
                           WHERE timeframe IN ('1d', 'daily', 'Daily') AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE timeframe IN ('1d', 'daily', 'Daily'))""")
        total_n = int(total_r["n"] or 0) if total_r else 0

        # Actual BUY signals with rich setup detail
        buy_sigs = q(c, """
            SELECT b.symbol, b.signal_type, b.stage_number, b.signal_quality_score,
                   b.entry_quality_score, b.close, b.buylevel, b.stoplevel,
                   b.risk_reward_ratio, b.volume_surge_pct, b.rs_rating,
                   b.breakout_quality, b.base_type, b.reason,
                   cp.sector,
                   s.score AS swing_score
            FROM buy_sell_daily b
            LEFT JOIN company_profile cp ON cp.ticker = b.symbol
            LEFT JOIN (
                SELECT DISTINCT ON (symbol) symbol, score
                FROM swing_trader_scores ORDER BY symbol, date DESC
            ) s ON s.symbol = b.symbol
            WHERE b.signal='BUY' AND b.timeframe IN ('1d', 'daily', 'Daily')
              AND b.date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily'))
            ORDER BY COALESCE(b.signal_quality_score, b.entry_quality_score, 0) DESC
            LIMIT 30""")

        grades_r = q(c, """
            SELECT COUNT(*) FILTER (WHERE score >= 80) AS a,
                   COUNT(*) FILTER (WHERE score >= 60 AND score < 80) AS b,
                   COUNT(*) FILTER (WHERE score >= 40 AND score < 60) AS c,
                   COUNT(*) FILTER (WHERE score < 40) AS d,
                   COUNT(*) AS total
            FROM swing_trader_scores
            WHERE date=(SELECT MAX(date) FROM swing_trader_scores)""")
        grades = grades_r[0] if grades_r else {}

        # Near-misses: scored stocks close to BUY threshold
        near = q(c, """
            SELECT s.symbol, s.score, cp.sector
            FROM swing_trader_scores s
            LEFT JOIN company_profile cp ON cp.ticker = s.symbol
            WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
              AND s.score BETWEEN 55 AND 69
            ORDER BY s.score DESC LIMIT 15""")

        # Top A-grade stocks by name (radar display — score ≥ 80)
        top_a = q(c, """
            SELECT s.symbol, s.score
            FROM swing_trader_scores s
            WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
              AND s.score >= 80
            ORDER BY s.score DESC LIMIT 20""")

        # Signal count trend: last 7 trading days
        trend = q(c, """
            SELECT date,
                   COUNT(*) FILTER (WHERE signal='BUY') AS buy_n,
                   COUNT(*) AS total_n
            FROM buy_sell_daily
            WHERE timeframe IN ('1d', 'daily', 'Daily') AND date >= CURRENT_DATE - 14
            GROUP BY date ORDER BY date DESC LIMIT 7""")

        _log_data_quality("fetch_signals", int(sig["n"] or 0) if sig else 0)
        return {"n": int(sig["n"] or 0) if sig else 0, "total": total_n,
                "date": sig["d"] if sig else None,
                "buy_sigs": buy_sigs, "grades": grades, "near": near,
                "top_a": top_a, "trend": trend}
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_signals: {type(e).__name__}: {e}")
        _log_data_quality("fetch_signals", 0, str(e))
        return {}

def fetch_sector_ranking(c):
    try:
        result = q(c, """
            SELECT sector_name, current_rank, momentum_score, rank_1w_ago, rank_4w_ago
            FROM sector_ranking
            WHERE date=(SELECT MAX(date) FROM sector_ranking)
            ORDER BY current_rank ASC""")
        _log_data_quality("fetch_sector_ranking", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_sector_ranking: {type(e).__name__}: {e}")
        _log_data_quality("fetch_sector_ranking", 0, str(e))
        return []

def fetch_activity(c):
    try:
        latest = q1(c, """
            SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
            FROM algo_audit_log
            WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"):
            _log_data_quality("fetch_activity", 0)
            return {}
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
        return {}

def fetch_health(c):
    try:
        result = q(c, """
            SELECT tbl, role, latest, age,
                   CASE WHEN age IS NULL OR age > stale_thresh THEN 'stale' ELSE 'ok' END AS st
            FROM (
              SELECT 'price_daily'    tbl,'CRIT' role, MAX(date)::date latest,(CURRENT_DATE-MAX(date)::date) age,
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(date)::date)<=2 THEN 10 ELSE 3 END stale_thresh FROM price_daily       UNION ALL
              SELECT 'buy_sell_daily','CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(date)::date)<=2 THEN 10 ELSE 3 END FROM buy_sell_daily  UNION ALL
              SELECT 'swing_scores',  'CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(date)::date)<=2 THEN 10 ELSE 3 END FROM swing_trader_scores UNION ALL
              SELECT 'exposure_daily','CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(date)::date)<=2 THEN 10 ELSE 3 END FROM market_exposure_daily UNION ALL
              SELECT 'port_snapshot', 'CRIT',          MAX(snapshot_date)::date,(CURRENT_DATE-MAX(snapshot_date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(snapshot_date)::date)<=2 THEN 10 ELSE 3 END FROM algo_portfolio_snapshots UNION ALL
              SELECT 'technicals',    'IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(date)::date)<=2 THEN 10 ELSE 3 END FROM technical_data_daily UNION ALL
              SELECT 'market_health', 'IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(date)::date)<=2 THEN 10 ELSE 7 END FROM market_health_daily UNION ALL
              SELECT 'trend_template','IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),
                     CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=1 AND (CURRENT_DATE-MAX(date)::date)<=2 THEN 10 ELSE 7 END FROM trend_template_data UNION ALL
              SELECT 'sector_ranking','SUPP',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    14        FROM sector_ranking UNION ALL
              SELECT 'economic_data', 'SUPP',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    14        FROM economic_data
            ) s ORDER BY CASE role WHEN 'CRIT' THEN 1 WHEN 'IMP' THEN 2 ELSE 3 END, tbl""")
        _log_data_quality("fetch_health", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_health: {type(e).__name__}: {e}")
        _log_data_quality("fetch_health", 0, str(e))
        return []

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
        d = {r['series_id']: float(r['value']) for r in rows if r.get('value') is not None}
        t10 = d.get('DGS10'); t2 = d.get('DGS2'); t3m = d.get('DGS3MO')
        yc_10_2  = round(t10 - t2,  2) if t10 is not None and t2  is not None else None
        yc_10_3m = round(t10 - t3m, 2) if t10 is not None and t3m is not None else None

        # CPI YoY: need 12-month-old value
        cpi_yoy = None
        cpi_rows = q(c, """
            SELECT value FROM economic_data WHERE series_id='CPIAUCSL'
            ORDER BY date DESC LIMIT 14""")
        if len(cpi_rows) >= 13:
            cur_val  = cpi_rows[0].get('value')
            prev_val = cpi_rows[12].get('value')
            if cur_val is not None and prev_val is not None:
                cur_cpi  = float(cur_val)
                prev_cpi = float(prev_val)
                if prev_cpi > 0:
                    cpi_yoy = round((cur_cpi - prev_cpi) / prev_cpi * 100, 2)

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
        }
        _log_data_quality("fetch_economic_pulse", len(d))
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_economic_pulse: {type(e).__name__}: {e}")
        _log_data_quality("fetch_economic_pulse", 0, str(e))
        return {}

def fetch_algo_metrics(c):
    try:
        rows = q(c, """SELECT date, total_actions, entries, exits
                       FROM algo_metrics_daily ORDER BY date DESC LIMIT 5""")
        _log_data_quality("fetch_algo_metrics", len(rows) if rows else 0)
        return rows
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_algo_metrics: {type(e).__name__}: {e}")
        _log_data_quality("fetch_algo_metrics", 0, str(e))
        return []

def fetch_notifications(c):
    try:
        result = q(c, """
            SELECT kind, severity, title, seen, created_at, details
            FROM algo_notifications
            ORDER BY created_at DESC LIMIT 8""")
        _log_data_quality("fetch_notifications", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_notifications: {type(e).__name__}: {e}")
        _log_data_quality("fetch_notifications", 0, str(e))
        return []

def fetch_sentiment(c):
    try:
        row = q1(c, "SELECT fear_greed_index, label, date FROM market_sentiment ORDER BY date DESC LIMIT 1")
        if not row:
            _log_data_quality("fetch_sentiment", 0)
            return {}
        fg = float(row.get("fear_greed_index") or 0)
        label = row.get("label") or ""
        c_fg  = (R if fg <= 25 else (Y if fg <= 45 else (G if fg >= 75 else CY)))
        result = {"fg": round(fg, 1), "label": label, "date": row.get("date"), "color": c_fg}
        _log_data_quality("fetch_sentiment", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_sentiment: {type(e).__name__}: {e}")
        _log_data_quality("fetch_sentiment", 0, str(e))
        return {}

def fetch_economic_calendar(c):
    try:
        rows = q(c, """SELECT event_name, event_date, event_time, importance,
                              forecast_value, actual_value, previous_value
                       FROM economic_calendar
                       WHERE event_date >= CURRENT_DATE - 1
                         AND country='US'
                       ORDER BY event_date ASC, importance DESC, event_time ASC
                       LIMIT 8""")
        _log_data_quality("fetch_economic_calendar", len(rows) if rows else 0)
        return rows
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_economic_calendar: {type(e).__name__}: {e}")
        _log_data_quality("fetch_economic_calendar", 0, str(e))
        return []

def fetch_risk_metrics(c) -> dict:
    try:
        row = q1(c, """SELECT report_date, var_pct_95, cvar_pct_95, stressed_var_pct,
                              portfolio_beta, top_5_concentration
                       FROM algo_risk_daily ORDER BY report_date DESC LIMIT 1""")
        if not row:
            logger.warning("No risk metrics data available; risk loader may not have run yet")
            _log_data_quality("fetch_risk_metrics", 0)
            return {"_has_data": False}
        result = {
            "_has_data": True,
            "date":      row.get("report_date"),
            "var95":     float(row.get("var_pct_95")) if row.get("var_pct_95") is not None else None,
            "cvar95":    float(row.get("cvar_pct_95")) if row.get("cvar_pct_95") is not None else None,
            "svar":      float(row.get("stressed_var_pct")) if row.get("stressed_var_pct") is not None else None,
            "beta":      float(row.get("portfolio_beta")) if row.get("portfolio_beta") is not None else None,
            "conc5":     float(row.get("top_5_concentration")) if row.get("top_5_concentration") is not None else None,
        }
        _log_data_quality("fetch_risk_metrics", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_risk_metrics: {type(e).__name__}: {e}")
        _log_data_quality("fetch_risk_metrics", 0, str(e))
        return {"_has_data": False}

def fetch_perf_analytics(c):
    try:
        row = q1(c, """SELECT report_date, rolling_sharpe_252d, rolling_sortino_252d,
                              calmar_ratio, win_rate_50t, avg_win_r_50t, avg_loss_r_50t,
                              expectancy, max_drawdown_pct
                       FROM algo_performance_daily ORDER BY report_date DESC LIMIT 1""")
        if not row:
            _log_data_quality("fetch_perf_analytics", 0)
            return {}
        def _f(k): return round(float(row[k]), 3) if row.get(k) is not None else None
        result = {
            "sharpe252": _f("rolling_sharpe_252d"),
            "sortino":   _f("rolling_sortino_252d"),
            "calmar":    _f("calmar_ratio"),
            "wr50":      _f("win_rate_50t"),
            "avg_w_r":   _f("avg_win_r_50t"),
            "avg_l_r":   _f("avg_loss_r_50t"),
            "expectancy": _f("expectancy"),
            "maxdd":     _f("max_drawdown_pct"),
        }
        _log_data_quality("fetch_perf_analytics", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.error(f"fetch_perf_analytics: {type(e).__name__}: {e}")
        _log_data_quality("fetch_perf_analytics", 0, str(e))
        return {}

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
            _log_data_quality("fetch_signal_eval", 0)
            return {}
        rejected = q(c, """SELECT evaluation_reason, COUNT(*) n
                           FROM algo_signals_evaluated
                           WHERE signal_date = (SELECT MAX(signal_date) FROM algo_signals_evaluated)
                             AND filter_tier_5_pass = false
                           GROUP BY evaluation_reason
                           ORDER BY n DESC LIMIT 3""")
        def _i(k): return int(stats.get(k)) if stats and stats.get(k) is not None else 0
        avg_score_val = float(stats.get("avg_score")) if stats and stats.get("avg_score") is not None else 0
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
        return {}

def fetch_sector_rotation(c):
    try:
        row = q1(c, """SELECT date, signal, strength, details
                       FROM sector_rotation_signal
                       ORDER BY date DESC LIMIT 1""")
        if not row:
            _log_data_quality("fetch_sector_rotation", 0)
            return {}
        d = row.get("details") or {}
        if isinstance(d, str):
            try: d = json.loads(d)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse sector_rotation details JSON: {e}")
                d = {}
        result = {
            "date":     row.get("date"),
            "signal":   row.get("signal") or "",
            "strength": float(row.get("strength") or 0),
            "weeks":    d.get("weeks_persistent", 1),
            "def_score": d.get("defensive_lead_score", 0),
            "cyc_score": d.get("cyclical_weak_score", 0),
        }
        _log_data_quality("fetch_sector_rotation", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_sector_rotation: {type(e).__name__}: {e}")
        _log_data_quality("fetch_sector_rotation", 0, str(e))
        return {}

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
        return []

def fetch_loader_status(c):
    try:
        result = q(c, """SELECT table_name, status, latest_date, age_days,
                              completion_pct, error_message
                       FROM data_loader_status
                       ORDER BY CASE status
                           WHEN 'error'   THEN 1
                           WHEN 'failed'  THEN 2
                           WHEN 'stale'   THEN 3
                           WHEN 'loading' THEN 4
                           ELSE 5
                       END, age_days DESC NULLS LAST
                       LIMIT 8""")
        _log_data_quality("fetch_loader_status", len(result) if result else 0)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_loader_status: {type(e).__name__}: {e}")
        _log_data_quality("fetch_loader_status", 0, str(e))
        return []

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
        return []

def fetch_audit_log(c):
    try:
        rows = q(c, """SELECT action_type, symbol, status, created_at,
                              details
                       FROM algo_audit_log
                       ORDER BY created_at DESC LIMIT 8""")
        result = []
        for r in rows:
            det = r.get("details") or {}
            if isinstance(det, str):
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
        return []

def fetch_circuit(c):
    try:
        # Load circuit breaker thresholds from config
        config_keys = ["halt_drawdown_pct", "max_daily_loss_pct", "max_consecutive_losses",
                       "max_total_risk_pct", "vix_max_threshold", "max_weekly_loss_pct"]
        rows = q(c, "SELECT key, value FROM algo_config WHERE key=ANY(%s)", (config_keys,))
        cfg = {r["key"]: float(r["value"]) for r in rows if r.get("value") is not None}

        # Validation: Log if any circuit breaker keys are missing from config
        missing_keys = [k for k in config_keys if k not in cfg]
        if missing_keys:
            logger.warning(f"VALIDATION: Circuit breaker config MISSING KEYS: {missing_keys} "
                         f"(will use hardcoded defaults - may be incorrect)")

        snaps = q(c, "SELECT total_portfolio_value, daily_return_pct FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 30")
        lat   = snaps[0] if snaps else {}
        # Safely calculate peak value
        snap_vals = [float(s.get("total_portfolio_value")) for s in snaps if s.get("total_portfolio_value") is not None]
        pk    = max(snap_vals, default=0) if snap_vals else 0
        cur_v = float(lat.get("total_portfolio_value")) if lat and lat.get("total_portfolio_value") is not None else 0
        dd    = (pk - cur_v) / pk * 100 if pk > 0 else 0
        daily_ret = lat.get("daily_return_pct") if lat and lat.get("daily_return_pct") is not None else 0
        dl    = max(0.0, -float(daily_ret))
        # Weekly loss: sum of last 7 days, only include non-None values
        week_rets = [float(s.get("daily_return_pct")) for s in snaps[:7] if s.get("daily_return_pct") is not None]
        wl    = max(0.0, -sum(week_rets)) if week_rets else 0
        trades = q(c, "SELECT profit_loss_dollars FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL ORDER BY exit_date DESC LIMIT 20")
        consec = 0
        for t in trades:
            pnl = t.get("profit_loss_dollars")
            if pnl is not None and float(pnl) < 0: consec += 1
            else: break
        h     = q1(c, "SELECT market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1")
        vix_r = q1(c, "SELECT vix_level FROM market_health_daily WHERE vix_level IS NOT NULL AND vix_level > 0 ORDER BY date DESC LIMIT 1")
        vix_v = vix_r.get("vix_level") if vix_r else None
        vix   = float(vix_v) if vix_v is not None else 0.0
        stage = int(h.get("market_stage") or 1) if h else 1
        rr    = q1(c, """
            WITH open_trades AS (
                SELECT DISTINCT ON (symbol) symbol, entry_quantity, stop_loss_price
                FROM algo_trades WHERE status IN ('open', 'filled', 'partially_filled', 'active')
                  AND exit_date IS NULL
                ORDER BY symbol, trade_date DESC
            ),
            latest_prices AS (
                SELECT DISTINCT ON (symbol) symbol, close as current_price
                FROM price_daily ORDER BY symbol, date DESC
            )
            SELECT SUM(GREATEST(lp.current_price - ot.stop_loss_price, 0) * ot.entry_quantity) AS risk,
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1) AS pv
            FROM open_trades ot LEFT JOIN latest_prices lp ON ot.symbol = lp.symbol""")
        # Properly handle None risk and pv values
        risk_val = float(rr.get("risk")) if rr and rr.get("risk") is not None else 0.0
        pv_val = float(rr.get("pv")) if rr and rr.get("pv") is not None else 0.0
        rp = risk_val / max(pv_val, 1) * 100 if pv_val > 0 else 0

        # Threshold helper: tracks which values came from config vs defaults
        defaults_used = {}
        def th(k, d):
            if k not in cfg:
                defaults_used[k] = d
            return cfg.get(k, d)

        bs = [
            {"lbl": "Drawdown",     "cur": round(dd, 1),      "thr": th("halt_drawdown_pct", 20),     "u": "%"},
            {"lbl": "Daily Loss",   "cur": round(dl, 1),      "thr": th("max_daily_loss_pct", 2),     "u": "%"},
            {"lbl": "Weekly Loss",  "cur": round(wl, 1),      "thr": th("max_weekly_loss_pct", 5),    "u": "%"},
            {"lbl": "Consec Loss",  "cur": float(consec),     "thr": th("max_consecutive_losses", 3), "u": ""},
            {"lbl": "Total Risk",   "cur": round(rp, 1),      "thr": th("max_total_risk_pct", 4),     "u": "%"},
            {"lbl": "VIX",          "cur": round(vix, 1),     "thr": th("vix_max_threshold", 35),     "u": ""},
            {"lbl": "Mkt Stage",    "cur": float(stage),      "thr": 4,                                "u": ""},
        ]

        # Log which thresholds used defaults (indicates stale/incomplete config)
        if defaults_used:
            logger.warning(f"VALIDATION: Circuit breaker using DEFAULT thresholds (config incomplete): "
                         f"{', '.join(f'{k}={v}' for k, v in defaults_used.items())}")
        for b in bs: b["fired"] = b["cur"] >= b["thr"]
        n_fired = sum(1 for b in bs if b["fired"])
        if n_fired > 0:
            logger.warning(f"Circuit breaker triggered: {n_fired} breaker(s) fired")
        result = {"bs": bs, "any": any(b["fired"] for b in bs), "n": n_fired}
        _log_data_quality("fetch_circuit", 1)
        return result
    except (psycopg2.Error, KeyError, TypeError, ValueError) as e:
        logger.error(f"fetch_circuit: {type(e).__name__}: {e}")
        _log_data_quality("fetch_circuit", 0, str(e))
        return {}


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
}

def load_all() -> dict:
    out: dict = {}
    def one(name, fn):
        max_retries = 2
        for attempt in range(max_retries + 1):
            conn = None
            try:
                conn = get_conn()
                conn.autocommit = True
                result = fn(conn)
                return name, result
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                if attempt < max_retries:
                    logger.warning(f"Retry {attempt+1}/{max_retries} for {name}: {e}")
                    time.sleep(0.5 * (attempt + 1))
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
    max_workers = min(4, max(1, len(FETCHERS) // 3))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_key = {pool.submit(one, k, v): k for k, v in FETCHERS.items()}
        for f in as_completed(future_to_key):
            try:
                n, d = f.result()
                out[n] = d
            except Exception as e:
                logger.error(f"Thread exception in load_all: {type(e).__name__}: {e}")
                k = future_to_key[f]
                out[k] = {"_error": str(e)}
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
    for p in (phase_results or []):
        ps = (p.get("status") or "").lower()
        if ps not in ("halt", "halted"):
            continue
        raw  = (p.get("name") or p.get("phase", "")).lower()
        parts = raw.split("_")
        base  = "_".join(parts[:2]) if len(parts) >= 2 else raw
        label = PHASE_NAMES.get(base, raw.replace("phase_", "P"))
        pdata = p.get("data") or {}
        if isinstance(pdata, str):
            try:    pdata = json.loads(pdata)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse phase data JSON: {e}")
                pdata = {}
        detail = next(
            (str(pdata[k]) for k in _FIELDS
             if pdata.get(k) and len(str(pdata.get(k))) > 3),
            ""
        )
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
    next_run  = next_run_str()
    mode      = cfg.get("mode", "?")
    mc2       = G if "LIVE" in mode else Y
    en        = "ENABLED" if cfg.get("enabled", True) else "DISABLED"
    ec        = G if cfg.get("enabled", True) else R
    max_n     = cfg.get("max_pos_n")
    max_sec_n = cfg.get("max_sec_n")
    min_score = cfg.get("min_score")
    base_risk = cfg.get("base_risk")
    t1r       = cfg.get("t1_r")
    pyr       = cfg.get("pyramid", False)

    score_s   = f"[dim]min score ≥[/][white]{min_score}[/]" if min_score and float(min_score) > 0 else ""
    slots_s   = f"[dim]max [/][white]{max_n}[/][dim] positions[/]" if max_n else ""
    sec_s     = f"[dim]sector ≤[/][white]{max_sec_n}[/]" if max_sec_n else ""
    risk_s    = f"[dim]base risk [/][white]{base_risk}%[/]" if base_risk else ""
    t1r_s     = f"[dim]T1 target [/][white]{t1r}R[/]" if t1r else ""
    pyr_s     = f"[{G}]pyramid on[/]" if pyr else ""
    config_line = "  ".join(x for x in [score_s, slots_s, sec_s, risk_s, t1r_s, pyr_s] if x)

    # VaR line — only show if table is populated with real data
    var_line = ""
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        beta_c = R if (risk.get("beta") or 0) >= 1.2 else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        svar_v = float(risk.get("svar") or 0)
        svar_s = f"\n[dim]Stressed VaR:[/][{R}]{svar_v:.2f}%[/]" if svar_v > 0 else ""
        var95_v = float(risk.get("var95") or 0)
        cvar95_v = float(risk.get("cvar95") or 0)
        beta_v = float(risk.get("beta") or 0)
        conc5_v = float(risk.get("conc5") or 0)
        var_line = (f"\n[dim]VaR 95%:[/][white]{var95_v:.2f}%[/]"
                    f"  [dim]CVaR 95%:[/][white]{cvar95_v:.2f}%[/]"
                    f"  [dim]Portfolio Beta:[/][{beta_c}]{beta_v:.2f}[/]"
                    f"  [dim]Top-5 Conc:[/][white]{conc5_v:.0f}%[/]"
                    + svar_s)

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
            for p in (run.get("phase_results") or []):
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
                _details = _best_halt_reason(halt_r, run.get("phase_results"))
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


def panel_market_full(mkt, sentiment=None):
    """Market regime + internals combined."""
    if not mkt or mkt.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]MARKET[/]", border_style="blue", padding=(0, 1))
    tier  = mkt.get("tier", "unknown")
    tc    = TIER_COLOR.get(tier, "dim")
    lbl   = TIER_SHORT.get(tier, "LOADING")
    exp   = mkt.get("pct")
    exp_s = f"{float(exp):.0f}%" if exp is not None else "--"
    bar   = exp_bar(exp or 0, w=10)
    vix   = f"{mkt['vix']:.1f}" if mkt.get("vix") is not None else "--"
    vc    = R if (mkt.get("vix") or 0) >= 30 else (Y if (mkt.get("vix") or 0) >= 20 else G)
    dist  = str(mkt.get("dist") or "--")
    stage = str(mkt.get("stage") or "--")
    spy   = f"${mkt['spy']:.2f}" if mkt.get("spy") else "--"
    trend = (mkt.get("trend") or "").upper()
    halts = mkt.get("halts") or []
    halt_s = " ".join(str(h)[:16] for h in halts[:2]) if halts else "none"
    hc    = Y if halts else DIM

    upvol = mkt.get("upvol")
    adr   = mkt.get("adr")
    nh    = mkt.get("nh")
    nl    = mkt.get("nl")
    pcr   = mkt.get("pcr")
    bmom  = mkt.get("bmom")
    fed   = mkt.get("fed")

    uvc   = G if (upvol or 0) >= 60 else (Y if (upvol or 0) >= 50 else R)
    pcr_c = G if (pcr or 99) <= 0.8 else (Y if (pcr or 99) <= 1.0 else R)
    nhnl  = (nh or 0) - (nl or 0)
    nhnl_c = G if nhnl >= 50 else (Y if nhnl >= 0 else R)

    spy_raw = mkt.get("spy")
    spy_chg = mkt.get("spy_chg")
    spy_chg_s = f" [{G if (spy_chg or 0) >= 0 else R}]{sign(spy_chg or 0)}{spy_chg:.1f}%[/]" if spy_chg is not None else ""
    spy_s   = f"SPY:[white]${float(spy_raw):.2f}[/]{spy_chg_s}  " if spy_raw else ""
    lines = [
        f"[{tc}][bold]{lbl}[/]  [dim]exposure[/][{tc}]{exp_s}[/]  {bar}",
        f"VIX:[{vc}]{vix}[/]  [dim]Dist Days:[/][white]{dist}[/]  [dim]Stage:[/][white]{stage}[/]  {spy_s}",
    ]
    if upvol is not None:
        adr_s  = f"  [dim]Adv/Dec:[/][white]{adr:.1f}[/]" if adr is not None else ""
        nhnl_s = f"  [dim]NH-NL:[/][{nhnl_c}]{sign(nhnl)}{nhnl}[/]" if nh is not None else ""
        lines.append(f"[dim]Up Volume:[/][{uvc}]{upvol:.0f}%[/]{adr_s}  [dim]New Highs:[/][{G}]{nh or '--'}[/] [dim]Lows:[/][{R}]{nl or '--'}[/]{nhnl_s}")
    ycs = mkt.get("ycs")
    bmom_pcr = []
    if pcr is not None:
        bmom_pcr.append(f"[dim]Put/Call:[/][{pcr_c}]{pcr:.2f}[/]")
    if bmom is not None:
        bmc = G if bmom >= 0.5 else (Y if bmom >= 0 else R)
        bmom_pcr.append(f"[dim]Breadth Momentum:[/][{bmc}]{bmom:.1f}[/]")
    if ycs is not None:
        yc_c = G if ycs >= 0.5 else (Y if ycs >= 0 else R)
        bmom_pcr.append(f"[dim]Yield Curve Slope:[/][{yc_c}]{ycs:+.2f}[/]")
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
            cur = br.get("cur", 0)
            lbl = br.get("lbl", "?")
            u = br.get("u", "")
            fired = br.get("fired", False)
            ratio = cur / thr if thr > 0 else 0
            fc = R if fired else (Y if ratio >= 0.75 else G)
            ind = "[bold red] ![/]" if fired else ""
            return f"[{fc}]{lbl}:[/]{cur}{u}[dim]/{thr:.0f}{u}[/]{hbar(cur, thr, w=4)}{ind}"
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
        bar     = exp_bar(exp or 0, w=8)
        vix     = f"{mkt['vix']:.1f}" if mkt.get("vix") is not None else "--"
        vc      = R if (mkt.get("vix") or 0) >= 30 else (Y if (mkt.get("vix") or 0) >= 20 else G)
        dist    = str(mkt.get("dist") or "--")
        stage   = str(mkt.get("stage") or "--")
        spy_raw = mkt.get("spy"); spy_chg = mkt.get("spy_chg")
        spy_chg_s = (f" [{G if (spy_chg or 0) >= 0 else R}]{sign(spy_chg or 0)}{spy_chg:.1f}%[/]"
                     if spy_chg is not None else "")
        spy_s   = f"  SPY:[white]${float(spy_raw):.2f}[/]{spy_chg_s}" if spy_raw else ""
        rows.append(Text.from_markup(
            f"[{tc}][bold]{lbl}[/]  [dim]exp[/][{tc}]{exp_s}[/]{bar}  "
            f"VIX:[{vc}]{vix}[/]  [dim]Dist:[/][white]{dist}[/]  [dim]Stage:[/][white]{stage}[/]{spy_s}"
        ))
        upvol = mkt.get("upvol"); nh = mkt.get("nh"); nl = mkt.get("nl"); adr = mkt.get("adr")
        if upvol is not None:
            uvc    = G if upvol >= 60 else (Y if upvol >= 50 else R)
            nhnl   = (nh or 0) - (nl or 0)
            nhnl_c = G if nhnl >= 50 else (Y if nhnl >= 0 else R)
            adr_s  = f"  [dim]A/D:[/][white]{adr:.1f}[/]" if adr is not None else ""
            rows.append(Text.from_markup(
                f"[dim]UpVol:[/][{uvc}]{upvol:.0f}%[/]{adr_s}  "
                f"[dim]NH:[/][{G}]{nh or '--'}[/] [dim]NL:[/][{R}]{nl or '--'}[/]  "
                f"[dim]NH-NL:[/][{nhnl_c}]{sign(nhnl)}{nhnl}[/]"
            ))
        pcr = mkt.get("pcr"); bmom = mkt.get("bmom"); ycs = mkt.get("ycs"); fed = mkt.get("fed")
        parts4 = []
        if pcr  is not None:
            pcr_c = G if pcr <= 0.8 else (Y if pcr <= 1.0 else R)
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
        halts  = mkt.get("halts") or []
        halt_s = " ".join(str(h)[:14] for h in halts[:2]) if halts else "none"
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
    else:
        rows.append(Text("no market data", style="dim"))
    return Panel(Group(*rows), title="[bold blue]MARKET[/]", border_style="blue", padding=(0, 1))


def panel_portfolio(port, cfg, risk=None, perf=None):
    if not port or port.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]PORTFOLIO[/]", border_style="green", padding=(0, 1))
    pv    = float(port.get("total_portfolio_value")) if port.get("total_portfolio_value") is not None else 0
    dr    = float(port.get("daily_return_pct")) if port.get("daily_return_pct") is not None else 0
    urp   = float(port.get("unrealized_pnl_pct")) if port.get("unrealized_pnl_pct") is not None else 0
    cash  = float(port.get("total_cash")) if port.get("total_cash") is not None else 0
    npos  = int(port.get("position_count")) if port.get("position_count") is not None else 0
    cum   = port.get("cumulative_return_pct")
    mxdd  = port.get("max_drawdown_pct")
    lgpos = port.get("largest_position_pct")
    snap  = port.get("snapshot_date")
    max_n = int(cfg.get("max_pos_n")) if cfg and cfg.get("max_pos_n") is not None else 0
    pct_c = float(cfg.get("max_pos_pct")) if cfg and cfg.get("max_pos_pct") is not None else 0
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
    rows.append(Text.from_markup(
        f"[dim]Day:[/] [{G if dr >= 0 else R}]{sign(dr)}{dr:.2f}%[/]  "
        f"[dim]Unrlzd:[/] [{G if urp >= 0 else R}]{sign(urp)}{urp:.2f}%[/]"
    ))

    # Line 4: cumulative return + max drawdown (always show, "--" when missing)
    cum_v  = float(cum) if cum is not None else None
    mxdd_v = float(mxdd) if mxdd is not None else (
        float((perf or {}).get("maxdd") or 0) if perf and not perf.get("_error") else None)
    cc     = G if (cum_v or 0) >= 0 else R
    cum_s  = f"[dim]Total Return:[/] [{cc}]{sign(cum_v or 0)}{cum_v:.2f}%[/]" if cum_v is not None else "[dim]Total Return:[/] [dim]--[/]"
    dd_v   = abs(mxdd_v) if mxdd_v is not None else None
    dd_c   = R if (dd_v or 0) >= 15 else (Y if (dd_v or 0) >= 5 else G)
    mxdd_s = f"[dim]MaxDD:[/] [{dd_c}]-{dd_v:.1f}%[/]" if dd_v is not None else "[dim]MaxDD:[/] [dim]--[/]"
    rows.append(Text.from_markup(f"{cum_s}  {mxdd_s}"))

    # Line 5: largest position concentration (when available)
    if lgpos is not None:
        lp_c = R if float(lgpos) >= 20 else (Y if float(lgpos) >= 15 else "white")
        rows.append(Text.from_markup(f"[dim]Largest pos:[/] [{lp_c}]{float(lgpos):.1f}%[/]"))

    # VaR metrics (compact one-liner)
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        beta_c = R if (risk.get("beta") or 0) >= 1.2 else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        var95_v = float(risk.get("var95") or 0)
        cvar95_v = float(risk.get("cvar95") or 0)
        beta_v = float(risk.get("beta") or 0)
        conc5_v = float(risk.get("conc5") or 0)
        rows.append(Text.from_markup(
            f"[dim]VaR:[/][white]{var95_v:.2f}%[/]  "
            f"[dim]CVaR:[/][white]{cvar95_v:.2f}%[/]  "
            f"[dim]β:[/][{beta_c}]{beta_v:.2f}[/]  "
            f"[dim]Conc5:[/][white]{conc5_v:.0f}%[/]"
        ))

    return Panel(Group(*rows), title="[bold green]PORTFOLIO[/]", border_style="green", padding=(0, 1))


def panel_performance_spark(perf, rec, perf_anl=None):
    """Performance metrics + equity sparkline + rolling analytics."""
    if not perf or perf.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]PERFORMANCE[/]", border_style="green", padding=(0, 1))
    streak  = perf.get("streak") or 0
    str_s   = f"+{streak}W" if streak >= 0 else f"{abs(streak)}L"
    str_c   = G if streak >= 0 else R
    pnl_c   = G if (perf.get("pnl") or 0) >= 0 else R
    pf      = perf.get("profit_factor")
    pf_s    = f"{pf:.2f}" if pf is not None else "--"
    pf_c    = G if (pf or 0) >= 1.5 else (Y if (pf or 0) >= 1.0 else R)
    exp     = perf.get("expectancy") or 0
    exp_c   = G if exp >= 0 else R
    avg_r   = perf.get("avg_r")
    avg_r_s = f"{avg_r:.2f}R" if avg_r is not None else "--"

    wr_v = perf.get('wr') or 0
    dd_v = perf.get('maxdd') or 0
    dd_c = R if dd_v >= 10 else (Y if dd_v >= 5 else G)
    rows = [
        Text.from_markup(
            f"[bold white]{perf.get('n', 0)} Trades[/]  "
            f"[{G}]{perf.get('w', 0)}W[/][dim]/[/][{R}]{perf.get('l', 0)}L[/]  "
            f"[dim]WR:[/][{G if wr_v >= 50 else R}]{wr_v}%[/]  "
            f"[{str_c}]{str_s}[/]  "
            f"[dim]MaxDD:[/][{dd_c}]{('-' if dd_v > 0 else '')}{dd_v:.1f}%[/]"
        ),
        Text.from_markup(
            f"[dim]P&L:[/][{pnl_c}]{fmt_money(perf.get('pnl'))}[/]  "
            f"[dim]PF:[/][{pf_c}]{pf_s}[/]  "
            f"[dim]Sharpe:[/][white]{perf.get('sharpe') or '--'}[/]  "
            f"[dim]Exp:[/][{exp_c}]{fmt_money(exp)}[/]  "
            f"[dim]AvgR:[/][white]{avg_r_s}[/]"
        ),
        Text.from_markup(
            f"[dim]AvgWin:[/][{G}]{fmt_money(perf.get('avg_win'))}[/]  "
            f"[dim]AvgLoss:[/][{R}]{fmt_money(perf.get('avg_loss'))}[/]"
        ),
    ]

    # Equity curve sparkline
    equity_vals = perf.get("equity_vals") or []
    if len(equity_vals) >= 3:
        sp = sparkline(equity_vals, width=28)
        rows.append(Text.from_markup(f"[dim]Equity:[/] {sp}"))

    # Recent daily returns (last 5 snapshots)
    recent_rets = perf.get("recent_rets") or []
    if recent_rets:
        parts = []
        for dt, ret in recent_rets[-5:]:
            rc = G if ret >= 0 else R
            d_s = dt.strftime("%a") if hasattr(dt, "strftime") else str(dt)[:3]
            parts.append(f"[dim]{d_s}[/][{rc}]{sign(ret)}{ret:.1f}%[/]")
        rows.append(Text.from_markup("  ".join(parts)))

    # Rolling analytics from algo_performance_daily (only show if populated)
    if perf_anl and not perf_anl.get("_error"):
        anl_parts = []
        sharpe252 = perf_anl.get("sharpe252")
        sortino   = perf_anl.get("sortino")
        calmar    = perf_anl.get("calmar")
        wr50      = perf_anl.get("wr50")
        if sharpe252 is not None:
            sc = G if sharpe252 >= 1.0 else (Y if sharpe252 >= 0 else R)
            anl_parts.append(f"[dim]Sharpe (1Y):[/][{sc}]{sharpe252:.2f}[/]")
        if sortino is not None:
            sc = G if sortino >= 1.5 else (Y if sortino >= 0 else R)
            anl_parts.append(f"[dim]Sortino:[/][{sc}]{sortino:.2f}[/]")
        if calmar is not None:
            sc = G if calmar >= 0.5 else (Y if calmar >= 0 else R)
            anl_parts.append(f"[dim]Calmar:[/][{sc}]{calmar:.2f}[/]")
        total_trades = perf.get("n", 0) if perf else 0
        if wr50 is not None and (total_trades >= 10 or wr50 > 0):
            wrc = G if wr50 >= 55 else (Y if wr50 >= 45 else R)
            anl_parts.append(f"[dim]Win Rate (last 50T):[/][{wrc}]{wr50:.0f}%[/]")
        if anl_parts:
            rows.append(Text.from_markup("  ".join(anl_parts)))
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
            pv2   = float(t.get("profit_loss_dollars") or 0)
            pct_v = float(t.get("profit_loss_pct") or 0)
            rv    = float(t.get("exit_r_multiple") or 0) if t.get("exit_r_multiple") else None
            sym   = t.get("symbol") or "--"
            c     = G if pv2 >= 0 else R
            rv_s  = f" {sign(rv)}{rv:.1f}R" if rv is not None else ""
            rows.append(Text.from_markup(
                f"  [{c}]{sym}[/] [{c}]{sign(pct_v)}{pct_v:.1f}%  {fmt_money(pv2)}{rv_s}[/]"
            ))

    return Panel(Group(*rows), title="[bold green]PERFORMANCE[/]", border_style="green", padding=(0, 1))


def panel_positions(pos, compact=False, trades=None):
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
        entry = float(p.get("avg_entry_price")) if p.get("avg_entry_price") is not None else None
        price = float(p.get("current_price"))   if p.get("current_price") is not None else None
        pval  = float(p.get("position_value")) if p.get("position_value") is not None else None
        stop  = float(p.get("stop_loss_price")) if p.get("stop_loss_price") is not None else None
        t1    = float(p.get("target_1_price")) if p.get("target_1_price") is not None else None
        pnl   = float(p.get("unrealized_pnl_pct") or 0)
        days  = p.get("days_since_entry") or "--"
        stg   = p.get("weinstein_stage")
        swg   = p.get("swing_score")
        sec   = (p.get("sector") or "--")[:12]
        denom = (entry - stop) if (stop is not None and entry is not None and entry != stop) else None
        rmul  = (price - entry) / denom if (denom is not None and entry is not None) else None
        dist  = (price - stop) / price * 100 if (stop is not None and price is not None and price > 0) else None
        t1pct = (t1 - price) / price * 100 if (t1 is not None and price is not None and price > 0) else None
        pc    = G if pnl >= 0 else R
        rc    = G if (rmul is not None and rmul >= 0) else R
        dc    = R if (dist is not None and dist < 3) else (Y if (dist is not None and dist < 5) else "white")
        row = [
            p.get("symbol") or "--",
            fmt_money_short(pval) if pval is not None else "--",
            f"${entry:.2f}" if entry is not None else "--", f"${price:.2f}" if price is not None else "--",
            Text(f"{sign(pnl)}{pnl:.2f}%", style=pc),
            Text(f"{sign(rmul or 0)}{rmul:.2f}R" if rmul is not None else "--", style=rc),
            f"${stop:.2f}" if stop is not None else "--",
            Text(f"{dist:.1f}%" if dist is not None else "--", style=dc),
        ]
        if not compact:
            swg_s = float(swg) if swg is not None else None
            swg_c = G if (swg_s or 0) >= 80 else (Y if (swg_s or 0) >= 60 else "white")
            row += [
                f"+{t1pct:.1f}%" if t1pct is not None else "--",
                str(days),
                f"S{stg}" if stg else "--",
                Text(f"{swg_s:.0f}" if swg_s is not None else "--", style=swg_c),
                sec,
            ]
        t.add_row(*row)

    content = t

    return Panel(content, title=f"[bold cyan]POSITIONS ({len(pos)})[/]  [dim][p] expand[/]", border_style="cyan", padding=(0, 0))


def panel_signals_compact(sig, sig_eval=None):
    """Signals & screening — actual BUY signals from buy_sell_daily with setup detail."""
    if not sig or sig.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]SIGNALS[/]", border_style="magenta", padding=(0, 1))

    raw   = sig.get("n", 0)
    total = sig.get("total", 0)
    d     = sig.get("date")
    ds    = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    g     = sig.get("grades") or {}
    ga, gb, gc, gd = (int(g.get(k) or 0) for k in ("a", "b", "c", "d"))
    top_a = sig.get("top_a") or []
    near  = sig.get("near")  or []

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
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))
    trend = sig.get("trend") or []
    spark_s = ""
    if len(trend) >= 2:
        counts  = [int(t.get("buy_n") or 0) for t in reversed(trend)]
        max_b   = max(counts) if counts else 1
        spark   = "".join("▁▂▃▄▅▆▇█"[min(7, int(v / max(max_b, 1) * 7.9))] for v in counts)
        spark_s = f"  [{CY}]{spark}[/]"
    n_near = len(near)
    near_hint = f"  [{CY}]{n_near} near[/]" if n_near else ""
    rows = [Text.from_markup(
        f"[{buy_c}][bold]{raw} BUY[/][/]{spark_s}  [dim]from {total} screened  {ds}[/]"
        f"  [{G}]A:{ga}[/] [{CY}]B:{gb}[/] [{Y}]C:{gc}[/] [{R}]D:{gd}[/]{near_hint}"
    )]

    # ── Row 2: A-grade radar (always; near-misses only when nothing better) ──
    if top_a:
        parts = []
        for s in top_a[:8]:
            sc   = float(s.get("score") or 0)
            sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
            parts.append(f"[{sc_c}]{s.get('symbol','')}[/][dim]{sc:.0f}[/]")
        extra = f"  [dim]+{ga - min(ga, 8)} more[/]" if ga > 8 else ""
        rows.append(Text.from_markup("[dim]A radar:[/]  " + "  ".join(parts) + extra))
    elif near:
        parts = [f"[{CY}]{a['symbol']}[/][dim]{float(a.get('score') or 0):.0f}[/]" for a in near[:8]]
        rows.append(Text.from_markup("[dim]Near threshold:[/]  " + "  ".join(parts)))

    # ── Row 3: Funnel arrow chain  ·  avg score  ·  top blockers ─────────────
    if sig_eval and not sig_eval.get("_error"):
        ev_tot = sig_eval.get("total", 0)
        ev_t1  = sig_eval.get("t1", 0)
        ev_t5  = sig_eval.get("t5", 0)
        ev_avg = sig_eval.get("avg_score", 0)
        ev_c   = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
        rejected   = sig_eval.get("rejected") or []
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
    buy_sigs = sig.get("buy_sigs") or []
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
            sq_c   = G if (sq  or 0) >= 70 else (Y if (sq  or 0) >= 50 else "white")
            swg_c  = G if (swg or 0) >= 80 else (Y if (swg or 0) >= 60 else "white")
            rr_c   = G if (rr  or 0) >= 2.5 else (Y if (rr  or 0) >= 1.5 else "white")
            vs_c   = G if (vsurge or 0) >= 50 else (Y if (vsurge or 0) >= 20 else "white")
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
        parts = [f"[{CY}]{a['symbol']}[/][dim]{float(a.get('score') or 0):.0f}[/]" for a in near[:8]]
        rows.append(Text.from_markup("[dim]Near BUY (55–69):[/]  " + "  ".join(parts)))

    return Panel(Group(*rows), title="[bold magenta]BUY SIGNALS & SCREENING[/]  [dim][s] expand[/]", border_style="magenta", padding=(0, 1))


def panel_recent_trades(trades):
    """Closed/recent trade history — sits alongside positions panel."""
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
    for tr in trades[:10]:
        sym    = tr.get("symbol") or "--"
        date   = tr.get("exit_date") or tr.get("trade_date")
        date_s = date.strftime("%b %d") if hasattr(date, "strftime") else str(date or "--")
        pnl_d  = float(tr.get("profit_loss_dollars") or 0)
        pnl_p  = float(tr.get("profit_loss_pct") or 0)
        rmul   = tr.get("exit_r_multiple")
        status = (tr.get("status") or "")
        is_closed = status == "closed"
        pc  = G if pnl_d > 0 else (R if is_closed else Y)
        si  = f"[{G}]✓[/]" if pnl_d > 0 else (f"[{R}]✗[/]" if is_closed else f"[{Y}]▷[/]")
        t.add_row(
            Text.from_markup(f"{si} {sym}"),
            date_s,
            Text(f"{sign(pnl_d)}${abs(pnl_d):.0f}" if is_closed else "--", style=pc),
            Text(f"{sign(pnl_p)}{pnl_p:.1f}%" if is_closed else "--",      style=pc),
            Text(f"{float(rmul):.2f}R" if rmul is not None else "--",       style=pc),
            status[:4],
        )
    return Panel(t, title="[bold cyan]RECENT TRADES[/]", border_style="cyan", padding=(0, 0))


def panel_sector_compact(srank, pos, port, sec_rot=None, irank=None):
    """Rotation + holdings (max 2) + sector leaders (1 pair) + industries (2 pairs) = 8 lines."""
    rows = []

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
        sig_name = (sec_rot.get("signal") or "").replace("_", " ").title()
        wks      = sec_rot.get("weeks", 1)
        def_s    = float(sec_rot.get("def_score") or 0)
        cyc_s    = float(sec_rot.get("cyc_score") or 0)
        strength = float(sec_rot.get("strength") or 0)
        sig_c    = R if def_s >= 60 else (Y if def_s >= 40 else G)
        scores_s = f" [dim]defensive:{def_s:.0f} cyclical:{cyc_s:.0f}[/]" if def_s or cyc_s else ""
        str_s    = f" [dim]strength:{strength:.0%}[/]" if strength else ""
        rows.append(Text.from_markup(
            f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name[:20]}[/] [dim]{wks}wk[/]{scores_s}{str_s}"
        ))

    # Holdings by sector: 2-col pairs, up to 6 sectors
    if pos:
        pv = float(port.get("total_portfolio_value")) if port and port.get("total_portfolio_value") is not None else 0
        sd: dict = {}
        for p in pos:
            sec = p.get("sector") or "[No Sector]"
            val = float(p.get("position_value")) if p.get("position_value") is not None else 0.0
            pnl_raw = p.get("unrealized_pnl_pct")
            # Only track non-None P&L values for accurate averages
            pnl = float(pnl_raw) if pnl_raw is not None else None
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
    valid_srank = [r for r in (srank or [])
                   if not (isinstance(srank, dict) and srank.get("_error"))][:6]
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


def panel_economic_pulse(eco, econ_cal=None):
    """Economic factors the algo uses to calculate market exposure score."""
    if not eco or eco.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]ECONOMIC INPUTS[/]",
                     border_style="bright_magenta", padding=(0, 1))
    rows: list = []

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

    # Treasury yields (short to long) + Fed Funds Rate
    y_parts = []
    if t3m is not None: y_parts.append(f"[dim]3M Treasury:[/][white]{t3m:.2f}%[/]")
    if t6m is not None: y_parts.append(f"[dim]6M:[/][white]{t6m:.2f}%[/]")
    if t2  is not None: y_parts.append(f"[dim]2Y:[/][white]{t2:.2f}%[/]")
    if t10 is not None: y_parts.append(f"[dim]10Y:[/][white]{t10:.2f}%[/]")
    if fed_funds is not None: y_parts.append(f"[dim]Fed Rate:[/][white]{fed_funds:.2f}%[/]")
    if y_parts: rows.append(Text.from_markup("  ".join(y_parts)))

    # Yield curve
    if yc10_2 is not None:
        ycc = G if yc10_2 >= YIELD_CURVE_GOOD else (Y if yc10_2 >= 0 else R)
        inv = "  [bold red]INV[/]" if yc10_2 < 0 else ""
        c3m = f"  [dim]10Y-3M:[/][{ycc}]{yc10_3m:+.2f}%[/]" if yc10_3m is not None else ""
        rows.append(Text.from_markup(
            f"[dim]10Y-2Y:[/][{ycc}]{yc10_2:+.2f}%[/]{inv}{c3m}"
        ))

    # Credit spreads
    if hy is not None or ig is not None:
        parts = []
        if hy is not None:
            hy_c = G if hy <= HY_OAS_GOOD else (Y if hy <= HY_OAS_WARNING else R)
            parts.append(f"[dim]HY OAS:[/][{hy_c}]{hy:.2f}%[/]")
        if ig is not None:
            ig_c = G if ig <= IG_OAS_GOOD else (Y if ig <= IG_OAS_WARNING else R)
            parts.append(f"[dim]IG OAS:[/][{ig_c}]{ig:.2f}%[/]")
        rows.append(Text.from_markup("  ".join(parts)))

    # Macro: CPI YoY, unemployment, NFCI, oil
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

    # Inflation breakevens + consumer sentiment + mortgage rates
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

    # Economic calendar (upcoming events)
    valid_cal = econ_cal if (econ_cal and not (isinstance(econ_cal, dict) and econ_cal.get("_error"))) else []
    if valid_cal:
        rows.append(Rule(style="dim"))
        IMP_C = {"HIGH": "bold bright_red", "MEDIUM": "yellow", "LOW": "dim"}
        today = date.today()
        seen_keys = set()
        for ev in valid_cal[:6]:
            ed      = ev.get("event_date")
            full_nm = (ev.get("event_name") or "")
            name    = full_nm[:24]
            key     = (str(ed) + full_nm[:24]).lower()
            if key in seen_keys: continue
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

    if not rows:
        rows.append(Text("[dim]no economic data[/]"))
    return Panel(Group(*rows), title="[bold bright_magenta]ECONOMIC INPUTS → Exposure Score[/]",
                 border_style="bright_magenta", padding=(0, 1))


def panel_exposure_compact(exp_f):
    """12-factor exposure score — compact 2-col layout."""
    if not exp_f or exp_f.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]EXPOSURE FACTORS[/]",
                     border_style="blue", padding=(0, 1))
    raw     = float(exp_f.get("raw_score") or 0)
    epct    = float(exp_f.get("exposure_pct") or 0)
    regime  = exp_f.get("regime") or ""
    factors = exp_f.get("factors") or {}
    tier    = tier_from_pct(epct)
    tc      = TIER_COLOR.get(tier, "dim")

    def factor_detail(key):
        """Return a short value string for a factor key."""
        f = factors.get(key) or {}
        if not f: return ""
        if key == "trend_30wk":
            v = f.get("price_vs_ma_pct")
            return f" {'+' if (v or 0) >= 0 else ''}{v:.1f}%" if v is not None else ""
        if key == "breadth_50dma":
            v = f.get("value")
            return f" {v:.0f}%" if v is not None else ""
        if key == "breadth_200dma":
            v = f.get("value")
            return f" {v:.0f}%" if v is not None else ""
        if key == "mcclellan":
            v = f.get("value")
            return f" {v:+.0f}" if v is not None else ""
        if key == "vix_regime":
            v = f.get("value")
            return f" {v:.1f}" if v is not None else ""
        if key == "new_highs_lows":
            nh = f.get("new_highs", 0); nl = f.get("new_lows", 0)
            net = (nh or 0) - (nl or 0)
            return f" {'+' if net >= 0 else ''}{net}"
        if key == "credit_spread":
            v = f.get("value")
            return f" {v:.2f}" if v is not None else ""
        if key == "ad_line":
            rel = (f.get("relation") or "").replace("_", " ")[:8]
            return f" {rel}" if rel else ""
        if key == "aaii_sentiment":
            bull = f.get("bullish_pct"); bear = f.get("bearish_pct")
            return f" B:{bull:.0f}/Be:{bear:.0f}" if bull is not None and bear is not None else ""
        if key == "naaim":
            v = f.get("value")
            return f" {v:.0f}" if v is not None else ""
        if key == "ibd_state":
            st = (f.get("state") or "").replace("_under_pressure", "↓").replace("_", " ")[:9]
            dd = f.get("distribution_days_25d")
            dd_s = f" D{dd}" if dd is not None else ""
            return f" {st}{dd_s}"
        return ""

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
        f    = factors.get(key) or {}
        pts  = float(f.get("pts") or 0)
        bar  = mini_bar(pts, max_pts, w=3)
        fc   = G if pts >= max_pts * 0.75 else (Y if pts >= max_pts * 0.35 else R)
        det  = factor_detail(key)
        det_markup = f"[dim]{det}[/]" if det else ""
        items.append(f"[{fc}]{label:<6}[/]{bar}[dim]{pts:.0f}/{max_pts}[/]{det_markup}")

    sr  = factors.get("sector_rotation") or {}
    eco = factors.get("economic_overlay") or {}
    sr_pen  = float(sr.get("pts") or 0)
    eco_pen = float(eco.get("pts") or 0)
    if sr_pen < 0:
        sig = (sr.get("signal") or "").replace("_", " ")[:20]
        items.append(f"[{R}]Sector Rotation[/] [dim]{sr_pen:+.0f} {sig}[/]")
    if eco_pen < 0:
        eco_err = (eco.get("error") or "")[:20]
        items.append(f"[{R}]Economic Overlay[/] [dim]{eco_pen:+.0f}{(' ' + eco_err) if eco_err else ''}[/]")

    for a, b in zip(items[::2], items[1::2] + [""]):
        tbl.add_row(Text.from_markup(a), Text.from_markup(b))

    raw_bar = mini_bar(raw, 100, w=8)
    header  = Text.from_markup(
        f"[dim]Score:[/][white]{raw:.0f}[/][dim]/100[/] {raw_bar} [dim]→ allocation[/] [{tc}][bold]{epct:.0f}%[/][/]  [dim]{regime[:24]}[/]"
    )
    return Panel(Group(header, tbl), title="[bold blue]EXPOSURE SCORE BREAKDOWN (12 factors / 100pts)[/]",
                 border_style="blue", padding=(0, 1))


def panel_status(act, hlth, notifs, algo_metrics=None, loader=None, audit=None, run=None, exec_hist=None, cfg=None):
    """Algo activity phases + data health + recent notifications + action counts + loader status."""
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
    cfg_v = cfg or {}
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
        wc_h  = G if wr_h >= 80 else (Y if wr_h >= 50 else R)
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

        phase_results = run.get("phase_results") or []
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
            err = p.get("error") or ""
            pdata = p.get("data") or {}
            if isinstance(pdata, str):
                try: pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError, TypeError): pdata = {}
            if err and ps not in ("success", "completed", "ok"):
                rows.append(Text.from_markup(f"  [{sc}]↳ {err[:62]}[/]"))
            elif ps in ("halt", "halted") and pdata:
                reason = (pdata.get("halt_reason") or pdata.get("reason") or "")[:55]
                if reason:
                    rows.append(Text.from_markup(f"  [{Y}]↳ {reason}[/]"))
            elif ps in ("success", "completed", "ok") and pdata:
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
        for p in (act.get("phases") or []):
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
    recent = (act.get("recent_actions") or []) if (act and not act.get("_error")) else []
    trade_evts = [a for a in recent if a.get("action_type") in
                  ("entry_executed","exit_executed","entry_rejected","position_exited",
                   "order_placed","order_rejected")]
    for a in trade_evts[:4]:
        at  = a.get("action_type", "")
        det = a.get("details") or {}
        if isinstance(det, str):
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
            ta  = int(m.get("total_actions") or 0)
            en  = int(m.get("entries") or 0)
            ex  = int(m.get("exits") or 0)
            rows.append(Text.from_markup(
                f"  [dim]{d_s}:[/] [white]{ta}[/][dim] total actions,  [/][{G}]{en}[/][dim] entries  [/][{R}]{ex}[/][dim] exits[/]"
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
        for p in (run.get("phase_results") or []):
            raw   = (p.get("name") or p.get("phase", "")).lower()
            parts_p = raw.split("_")
            base  = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
            ps    = (p.get("status") or "").lower()
            sc    = G if ps in ("success", "completed", "ok") else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            si    = "✓" if ps in ("success", "completed", "ok") else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
            pdata = p.get("data") or {}
            if isinstance(pdata, str):
                try: pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError, TypeError): pdata = {}
            sg = pdata.get("signals_generated")
            ee = pdata.get("entries_executed") or pdata.get("trades_executed")
            xe = pdata.get("exits_executed")
            if sg: signals_gen  = max(signals_gen,  int(sg))
            if ee: entries_exec = max(entries_exec, int(ee))
            if xe: exits_exec   = max(exits_exec,   int(xe))
    elif run_valid or act_valid:
        src = run if run_valid else act
        for p in (src.get("phases") or []):
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
    if not entries_exec: entries_exec = int(today_m.get("entries") or 0)
    if not exits_exec:   exits_exec   = int(today_m.get("exits")   or 0)

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
            en  = int(m.get("entries") or 0)
            ex  = int(m.get("exits")   or 0)
            e_c = G if en > 0 else DIM
            x_c = Y if ex > 0 else DIM
            day_parts.append(f"[dim]{d_s}:[/][{e_c}]{en}▲[/][{x_c}]{ex}▼[/]")
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
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        rows.append(Rule(style="dim"))
        beta_v = float(risk.get("beta") or 0)
        conc5_v = float(risk.get("conc5") or 0)
        beta_c = R if beta_v >= 1.2 else (Y if beta_v >= 0.8 else G)
        conc_c = R if conc5_v >= 35 else (Y if conc5_v >= 25 else "white")
        var95_v = float(risk.get("var95") or 0)
        cvar95_v = float(risk.get("cvar95") or 0)
        svar_v = float(risk.get("svar") or 0)
        risk_parts = [
            f"[dim]VaR 95%:[/][white]{var95_v:.2f}%[/]",
            f"[dim]CVaR 95%:[/][white]{cvar95_v:.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{beta_v:.2f}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{conc5_v:.0f}%[/]",
        ]
        if svar_v > 0:
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


# ── loading layout — mascot compact in top-right ──────────────────────────────

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


def panel_signals_expanded(sig, sig_eval=None):
    """Full-screen buy signals — all signals, full text, breakout quality, base type."""
    if not sig or sig.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]SIGNALS[/]", border_style="magenta", padding=(0, 1))
    raw   = sig.get("n", 0)
    total = sig.get("total", 0)
    d     = sig.get("date")
    ds    = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    g     = sig.get("grades") or {}
    ga, gb, gc, gd = (int(g.get(k) or 0) for k in ("a", "b", "c", "d"))
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))
    rows = [Text.from_markup(
        f"[{buy_c}][bold]{raw} BUY SIGNALS[/][/]  [dim]from {total} screened  {ds}[/]  "
        f"[{G}]A:{ga}[/] [{CY}]B:{gb}[/] [{Y}]C:{gc}[/] [{R}]D:{gd}[/]  "
        f"[dim]press [/][bold magenta]s[/][dim] to return[/]"
    )]

    top_a = sig.get("top_a") or []
    if top_a:
        parts = []
        for s in top_a:
            sc_c = G if float(s.get("score") or 0) >= 90 else ("bright_green" if float(s.get("score") or 0) >= 85 else "green")
            parts.append(f"[{sc_c}]{s.get('symbol','')}[/][dim]{float(s.get('score') or 0):.0f}[/]")
        rows.append(Text.from_markup("[dim]A-grade radar:[/] " + "  ".join(parts)))

    if sig_eval and not sig_eval.get("_error"):
        ev_tot = sig_eval.get("total", 0); ev_t5 = sig_eval.get("t5", 0); ev_avg = sig_eval.get("avg_score", 0)
        ev_c = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
        funnel = (f"[dim]Funnel  T1:[/]{sig_eval.get('t1',0)} [dim]T2:[/]{sig_eval.get('t2',0)} "
                  f"[dim]T3:[/]{sig_eval.get('t3',0)} [dim]T4:[/]{sig_eval.get('t4',0)} "
                  f"[dim]T5:[/][{ev_c}]{ev_t5}[/][dim]/{ev_tot}  avg score:[/]{ev_avg:.0f}")
        rejected = sig_eval.get("rejected") or []
        if rejected:
            blocks = "  ".join(f"[dim]{rj['evaluation_reason'][:32]}:{rj['n']}[/]" for rj in rejected)
            funnel += f"  [dim]blocked:[/] {blocks}"
        rows.append(Text.from_markup(funnel))

    rows.append(Rule(style="dim"))
    buy_sigs = sig.get("buy_sigs") or []
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
            sq_c   = G if (sq or 0) >= 70 else (Y if (sq or 0) >= 50 else "white")
            rr_c   = G if (rr or 0) >= 2.5 else (Y if (rr or 0) >= 1.5 else "white")
            vs_c   = G if (vsurge or 0) >= 50 else (Y if (vsurge or 0) >= 20 else "white")
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

    near = sig.get("near") or []
    if near:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Near BUY threshold (swing score 55–69):[/]"))
        parts = [f"[{CY}]{a['symbol']}[/][dim] {float(a.get('score') or 0):.0f}[/]" for a in near]
        for i in range(0, len(parts), 4):
            rows.append(Text.from_markup("  " + "    ".join(parts[i:i+4])))

    return Panel(Group(*rows), title="[bold magenta]BUY SIGNALS — EXPANDED[/]  [dim][s] return[/]", border_style="magenta", padding=(0, 1))


def panel_algo_health_expanded(run, act, hlth, notifs, algo_metrics=None, loader=None, audit=None, exec_hist=None, risk=None):
    """Full-screen algo health — complete run history, all data tables, all notifications."""
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
        for p in (run.get("phase_results") or []):
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
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        rows.append(Rule(style="dim"))
        beta_v = float(risk.get("beta") or 0)
        conc5_v = float(risk.get("conc5") or 0)
        beta_c = R if beta_v >= 1.2 else (Y if beta_v >= 0.8 else G)
        conc_c = R if conc5_v >= 35 else (Y if conc5_v >= 25 else "white")
        var95_v = float(risk.get("var95") or 0)
        cvar95_v = float(risk.get("cvar95") or 0)
        svar_v = float(risk.get("svar") or 0)
        risk_parts = [
            f"[dim]VaR 95%:[/][white]{var95_v:.2f}%[/]",
            f"[dim]CVaR 95%:[/][white]{cvar95_v:.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{beta_v:.2f}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{conc5_v:.0f}%[/]",
        ]
        if svar_v > 0:
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


def panel_sectors_expanded(srank, pos, port, sec_rot=None, irank=None):
    """Full-screen sectors — all sector and industry rankings, full portfolio breakdown."""
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

    if sec_rot and not sec_rot.get("_error") and sec_rot.get("signal"):
        sig_name = (sec_rot.get("signal") or "").replace("_", " ").title()
        wks      = sec_rot.get("weeks", 1)
        def_s    = float(sec_rot.get("def_score") or 0)
        cyc_s    = float(sec_rot.get("cyc_score") or 0)
        strength = float(sec_rot.get("strength") or 0)
        sig_c    = R if def_s >= 60 else (Y if def_s >= 40 else G)
        rows.append(Text.from_markup(
            f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name}[/]  [dim]{wks}wk  "
            f"defensive:{def_s:.0f}  cyclical:{cyc_s:.0f}  strength:{strength:.0%}[/]"
        ))
        rows.append(Rule(style="dim"))

    # Full portfolio by sector
    if pos:
        pv = float(port.get("total_portfolio_value")) if port and port.get("total_portfolio_value") is not None else 0
        sd: dict = {}
        for p in pos:
            sec = p.get("sector") or "[No Sector]"
            val = float(p.get("position_value")) if p.get("position_value") is not None else 0.0
            pnl_raw = p.get("unrealized_pnl_pct")
            pnl = float(pnl_raw) if pnl_raw is not None else None
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
    valid_srank = [r for r in (srank or []) if not (isinstance(srank, dict) and srank.get("_error"))]
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
    run      = data.get("run")         or {}
    cfg      = data.get("cfg")         or {}
    mkt      = data.get("mkt")         or {}
    port     = data.get("port")        or {}
    perf     = data.get("perf")        or {}
    pos      = data.get("pos")         or []
    sig      = data.get("sig")         or {}
    hlth     = data.get("health")      or []
    cb       = data.get("cb")          or {}
    rec      = data.get("trades")      or []
    srank    = data.get("srank")       or []
    act      = data.get("activity")    or {}
    exp_f    = data.get("exp_factors") or {}
    eco      = data.get("eco")         or {}
    notifs   = data.get("notifs")      or []
    sentiment = data.get("sentiment")  or {}
    econ_cal  = data.get("econ_cal")   or []
    risk      = data.get("risk")       or {}
    perf_anl  = data.get("perf_anl")   or {}
    sig_eval  = data.get("sig_eval")   or {}
    sec_rot      = data.get("sec_rot")       or {}
    algo_metrics = data.get("algo_metrics")  or []
    irank        = data.get("irank")         or []
    loader       = data.get("loader")        or []
    audit        = data.get("audit")         or []
    exec_hist    = data.get("exec_hist")     or []

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

    # Row 2: Portfolio | Performance | Economic pulse
    outer["r2"].split_row(
        Layout(panel_portfolio(port, cfg, risk=risk, perf=perf),    name="portfolio"),
        Layout(panel_performance_spark(perf, rec, perf_anl),        name="perf"),
        Layout(panel_economic_pulse(eco, econ_cal),                  name="eco"),
    )

    # Row 3: Signals (wider) | Sectors
    outer["r3"].split_row(
        Layout(panel_signals_compact(sig, sig_eval), ratio=3, name="signals"),
        Layout(panel_sector_compact(srank, pos, port, sec_rot, irank), ratio=2, name="sectors"),
    )

    # Row 4: Positions | Recent Trades
    outer["pos"].split_row(
        Layout(panel_positions(pos, compact, trades=rec),  ratio=3, name="positions"),
        Layout(panel_recent_trades(rec),                   ratio=2, name="recent_trades"),
    )

    _exp_top = (hdr_panel, panel_exposure_compact(exp_f), mascot_compact(data, frame))

    if view_mode == "positions":
        hint = Text.from_markup("[dim]press [/][bold cyan]p[/][dim] to return to dashboard[/]")
        return _expanded_layout(*_exp_top, Panel(
            Group(hint, Rule(style="dim"), panel_positions(pos, compact=False, trades=rec)),
            title=f"[bold cyan]ALL POSITIONS ({len(pos or [])})[/]",
            border_style="cyan", padding=(0, 1),
        ))

    if view_mode == "signals":
        return _expanded_layout(*_exp_top, panel_signals_expanded(sig, sig_eval))

    if view_mode == "health":
        return _expanded_layout(*_exp_top, panel_algo_health_expanded(
            run, act, hlth, notifs, algo_metrics, loader, audit, exec_hist, risk=risk))

    if view_mode == "sectors":
        return _expanded_layout(*_exp_top, panel_sectors_expanded(srank, pos, port, sec_rot, irank))

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
    _KEY_MAP = {"p": "positions", "s": "signals", "h": "health", "r": "sectors"}
    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                key = _keypress()
                if key == "q":
                    break
                if key in _KEY_MAP:
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

    def reload():
        loading[0] = True
        t0 = time.monotonic()
        result[0] = load_all()
        elapsed[0] = time.monotonic() - t0
        last_load[0] = time.monotonic()
        loading[0] = False

    threading.Thread(target=reload, daemon=True).start()

    view_mode = ["normal"]
    _KEY_MAP  = {"p": "positions", "s": "signals", "h": "health", "r": "sectors"}
    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                key = _keypress()
                if key == "q":
                    break
                if key in _KEY_MAP:
                    target = _KEY_MAP[key]
                    view_mode[0] = "normal" if view_mode[0] == target else target
                frame[0] += 1
                if result[0] is None:
                    # First load only — show loading screen until we have data
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

