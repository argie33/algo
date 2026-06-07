#!/usr/bin/env python3
"""
Algo Ops Terminal Dashboard  --  single-pane morning brief.

Usage:
  python scripts/algo_dashboard.py            # live view (mascot dances, Ctrl+C to exit)
  python scripts/algo_dashboard.py -w         # watch mode, auto-refresh every 30s
  python scripts/algo_dashboard.py -w 60      # watch mode, refresh every 60s
  python scripts/algo_dashboard.py --compact  # narrow positions table
"""

import argparse
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

if sys.platform == "win32":
    os.system("chcp 65001 > nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

try:
    import psycopg2, psycopg2.extras
except ImportError:
    sys.exit("pip install psycopg2-binary")

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

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"

# ── mascot ────────────────────────────────────────────────────────────────────
# Each line is exactly 5 visible chars — consistent width prevents wobble
MASCOT_FRAMES = [
    (" \\o/ ", "  |  ", " / \\ "),   # 0  groove
    (" \\o/ ", "  |  ", "  /\\ "),   # 1  sway right
    (" /o\\ ", " /|  ", " /|  "),   # 2  lean left
    (" \\o\\ ", "  |  ", " /|  "),   # 3  sway left
    (" \\o/ ", " \\|/ ", " | | "),   # 4  star jump
    ("  o  ", "  |  ", " / \\ "),   # 5  rest
    ("  o/ ", "  |\\ ", " /   "),   # 6  stumble (warning)
    (" _o_ ", "  |  ", "  /\\ "),   # 7  freeze (correction)
]
MASCOT_COLORS = [
    "bright_green", "green", "bright_cyan", "cyan",
    "bright_yellow", "white", "yellow", "bright_red",
]
LOAD_SEQ = [0, 1, 2, 3, 1, 0, 2, 3]


def mascot_pose(data: dict, frame: int) -> int:
    cb   = data.get("cb") or {}
    mkt  = data.get("mkt") or {}
    tier = mkt.get("tier", "unknown")
    if cb.get("any"):
        return [6, 7][frame % 2]
    tier_ranges: Dict[str, List[int]] = {
        "confirmed_uptrend": [0, 1, 2, 3],
        "healthy_uptrend":   [0, 1, 2],
        "pressure":          [1, 3, 4],
        "caution":           [4, 5, 6],
        "correction":        [6, 7, 5],
    }
    r = tier_ranges.get(tier, [0, 1, 2, 3])
    return r[frame % len(r)]


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_conn():
    miss = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.environ.get(k)]
    if miss:
        sys.exit(f"Missing env vars: {', '.join(miss)}")
    return psycopg2.connect(
        host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        dbname=os.environ["DB_NAME"], connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
        options="-c statement_timeout=8000",
    )

def q(c, sql, p=None):
    with c.cursor() as cur:
        cur.execute(sql, p or ())
        return [dict(r) for r in cur.fetchall()]

def q1(c, sql, p=None):
    rows = q(c, sql, p)
    return rows[0] if rows else None


# ── formatters ────────────────────────────────────────────────────────────────

def fmt_age(ts):
    from datetime import date as _date
    if ts is None: return "--"
    if isinstance(ts, str): ts = datetime.fromisoformat(ts)
    if isinstance(ts, _date) and not isinstance(ts, datetime):
        ts = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
    if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
    m = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
    if m < 60:   return f"{m}m ago"
    if m < 1440: return f"{m // 60}h{m % 60:02d}m ago"
    return f"{m // 1440}d ago"

def fmt_money(v):
    if v is None: return "--"
    v = float(v)
    if abs(v) >= 1e6: return f"${v / 1e6:.2f}M"
    if abs(v) >= 1e3: return f"${v:,.0f}"
    return f"${v:.2f}"

def grade(s):
    s = float(s)
    if s >= 90: return "A+"
    if s >= 80: return "A"
    if s >= 70: return "B"
    if s >= 60: return "C"
    return "D"

def tier_from_pct(p) -> str:
    if p is None: return "unknown"
    p = float(p)
    if p >= 80: return "confirmed_uptrend"
    if p >= 60: return "healthy_uptrend"
    if p >= 40: return "pressure"
    if p >= 20: return "caution"
    return "correction"

def is_open() -> bool:
    n = datetime.now(ET)
    if n.weekday() >= 5: return False
    t = n.hour * 60 + n.minute
    return 570 <= t <= 960

def next_run_str() -> str:
    from datetime import timedelta
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

def hbar(cur, thr, w=6):
    r = min(float(cur) / float(thr), 1.0) if thr and float(thr) > 0 else 0
    f = int(r * w)
    c = R if r >= 1 else (Y if r >= 0.75 else G)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def exp_bar(pct, w=12):
    f = int(min(float(pct or 0), 100) / 100 * w)
    tc = TIER_COLOR.get(tier_from_pct(pct), "dim")
    return f"[{tc}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"

def mini_bar(pts, max_pts, w=5):
    r = min(float(pts or 0) / float(max_pts or 1), 1.0)
    f = int(r * w)
    c = G if r >= 0.75 else (Y if r >= 0.35 else R)
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


# ── fetchers ──────────────────────────────────────────────────────────────────

def fetch_run(c):
    try:
        latest = q1(c, """
            SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
            FROM algo_audit_log WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"): return {}
        rid = latest["run_id"]
        phases = q(c, """SELECT action_type, status FROM algo_audit_log
                         WHERE details->>'run_id'=%s ORDER BY created_at ASC""", (rid,))
        halted  = any(p["status"] == "halt"  for p in phases)
        errored = any(p["status"] == "error" for p in phases)
        return {"run_id": rid, "run_at": latest["run_at"],
                "success": bool(phases) and not errored, "halted": halted, "phases": phases}
    except Exception as e:
        return {"_error": str(e)}

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
    except Exception as e:
        return {"_error": str(e)}

def fetch_market(c):
    try:
        exp  = q1(c, "SELECT exposure_pct, halt_reasons FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
        h    = q1(c, """SELECT market_stage, vix_level, distribution_days_4w,
                               spy_close, market_trend, up_volume_percent,
                               advance_decline_ratio, new_highs_count, new_lows_count,
                               put_call_ratio, yield_curve_slope, breadth_momentum_10d,
                               fed_rate_environment
                        FROM market_health_daily ORDER BY date DESC LIMIT 1""")
        pct   = float(exp["exposure_pct"] or 0) if exp else None
        halts = exp.get("halt_reasons") or [] if exp else []
        if isinstance(halts, str):
            try: halts = json.loads(halts)
            except: halts = [halts] if halts else []
        vix_row = q1(c, "SELECT vix_level FROM market_health_daily WHERE vix_level IS NOT NULL AND vix_level > 0 ORDER BY date DESC LIMIT 1")
        vix_v   = vix_row.get("vix_level") if vix_row else None
        def _f(key): return float(h[key]) if h and h.get(key) is not None else None
        def _i(key): return int(h[key])   if h and h.get(key) is not None else None
        spy_v = _f("spy_close")
        if spy_v is None:
            spy_r = q1(c, "SELECT close FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
            if spy_r: spy_v = float(spy_r["close"])
        fed_val = h.get("fed_rate_environment") if h else None
        if not fed_val or fed_val in ("unknown", "Unknown"): fed_val = None
        return {
            "pct":   pct,
            "tier":  tier_from_pct(pct),
            "halts": halts,
            "vix":   float(vix_v) if vix_v is not None else None,
            "dist":  _i("distribution_days_4w"),
            "stage": _i("market_stage"),
            "spy":   spy_v,
            "trend": h.get("market_trend") if h else None,
            "upvol": _f("up_volume_percent"),
            "adr":   _f("advance_decline_ratio"),
            "nh":    _i("new_highs_count"),
            "nl":    _i("new_lows_count"),
            "pcr":   _f("put_call_ratio"),
            "ycs":   _f("yield_curve_slope"),
            "bmom":  _f("breadth_momentum_10d"),
            "fed":   fed_val,
        }
    except Exception as e:
        return {"_error": str(e)}

def fetch_exposure_factors(c):
    try:
        row = q1(c, """SELECT raw_score, exposure_pct, regime, factors
                       FROM market_exposure_daily ORDER BY date DESC LIMIT 1""")
        if not row: return {}
        factors = row.get("factors") or {}
        if isinstance(factors, str):
            try: factors = json.loads(factors)
            except: factors = {}
        return {
            "raw_score":    float(row.get("raw_score") or 0),
            "exposure_pct": float(row.get("exposure_pct") or 0),
            "regime":       row.get("regime"),
            "factors":      factors,
        }
    except Exception as e:
        return {"_error": str(e)}

def fetch_portfolio(c):
    try:
        return dict(q1(c, """
            SELECT snapshot_date, total_portfolio_value, daily_return_pct,
                   unrealized_pnl_pct, position_count, total_cash
            FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1""") or {})
    except Exception as e:
        return {"_error": str(e)}

def fetch_perf(c):
    try:
        trades = q(c, """SELECT profit_loss_dollars, exit_r_multiple, profit_loss_pct
                         FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL
                         ORDER BY exit_date ASC""")
        if not trades: return {}
        wins   = [t for t in trades if float(t.get("profit_loss_dollars") or 0) > 0]
        losses = [t for t in trades if float(t.get("profit_loss_dollars") or 0) <= 0]
        pnl    = sum(float(t.get("profit_loss_dollars") or 0) for t in trades)
        wr     = len(wins) / len(trades) * 100 if trades else 0
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
        win_amt   = [float(t.get("profit_loss_dollars") or 0) for t in wins]
        loss_amt  = [abs(float(t.get("profit_loss_dollars") or 0)) for t in losses]
        avg_win   = statistics.mean(win_amt)  if win_amt  else 0.0
        avg_loss  = statistics.mean(loss_amt) if loss_amt else 0.0
        gw = sum(win_amt); gl = sum(loss_amt)
        pf = round(gw / gl, 2) if gl > 0 else None
        exp = round(wr / 100 * avg_win - (1 - wr / 100) * avg_loss, 2) if trades else 0.0
        avg_r_vals = [float(t["exit_r_multiple"]) for t in trades if t.get("exit_r_multiple") is not None]
        avg_r = round(statistics.mean(avg_r_vals), 2) if avg_r_vals else None
        return {"n": len(trades), "w": len(wins), "l": len(losses),
                "wr": round(wr, 1), "pnl": round(pnl, 2), "streak": streak,
                "sharpe": sharpe, "maxdd": round(maxdd, 1),
                "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
                "profit_factor": pf, "expectancy": exp, "avg_r": avg_r,
                "equity_vals": equity_vals}
    except Exception as e:
        return {"_error": str(e)}

def fetch_positions(c):
    try:
        return q(c, """
            WITH lt AS (
                SELECT DISTINCT ON (symbol) symbol, stop_loss_price, target_1_price
                FROM algo_trades WHERE status='open' ORDER BY symbol, trade_date DESC
            ),
            ltt AS (
                SELECT DISTINCT ON (symbol) symbol, weinstein_stage
                FROM trend_template_data ORDER BY symbol, date DESC
            ),
            lss AS (
                SELECT DISTINCT ON (symbol) symbol, score AS swing_score
                FROM swing_trader_scores ORDER BY symbol, date DESC
            )
            SELECT p.symbol, p.avg_entry_price, p.current_price,
                   p.unrealized_pnl_pct, p.position_value, p.days_since_entry,
                   lt.stop_loss_price, lt.target_1_price,
                   ltt.weinstein_stage, cp.sector, lss.swing_score
            FROM algo_positions p
            LEFT JOIN lt  ON lt.symbol  = p.symbol
            LEFT JOIN ltt ON ltt.symbol = p.symbol
            LEFT JOIN company_profile cp ON cp.ticker = p.symbol
            LEFT JOIN lss ON lss.symbol = p.symbol
            WHERE p.status = 'open' ORDER BY p.position_value DESC""")
    except:
        return []

def fetch_recent_trades(c):
    try:
        return q(c, """
            SELECT symbol, trade_date, exit_date, status,
                   profit_loss_dollars, profit_loss_pct, exit_r_multiple
            FROM algo_trades ORDER BY COALESCE(exit_date, trade_date) DESC LIMIT 5""")
    except:
        return []

def fetch_signals(c):
    try:
        sig = q1(c, """
            SELECT COUNT(*) AS n, MAX(date) AS d FROM buy_sell_daily
            WHERE signal='BUY' AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY')""")
        total_r = q1(c, "SELECT COUNT(*) AS n FROM buy_sell_daily WHERE date=(SELECT MAX(date) FROM buy_sell_daily)")
        total_n = int(total_r["n"] or 0) if total_r else 0
        top = q(c, """
            SELECT s.symbol, s.score, cp.sector
            FROM swing_trader_scores s
            LEFT JOIN company_profile cp ON cp.ticker = s.symbol
            WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
            ORDER BY s.score DESC LIMIT 10""")
        grades_r = q(c, """
            SELECT COUNT(*) FILTER (WHERE score >= 80) AS a,
                   COUNT(*) FILTER (WHERE score >= 60 AND score < 80) AS b,
                   COUNT(*) FILTER (WHERE score >= 40 AND score < 60) AS c,
                   COUNT(*) FILTER (WHERE score < 40) AS d,
                   COUNT(*) AS total
            FROM swing_trader_scores
            WHERE date=(SELECT MAX(date) FROM swing_trader_scores)""")
        grades = grades_r[0] if grades_r else {}
        near = q(c, """
            SELECT s.symbol, s.score, cp.sector
            FROM swing_trader_scores s
            LEFT JOIN company_profile cp ON cp.ticker = s.symbol
            WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
              AND s.score BETWEEN 55 AND 69
            ORDER BY s.score DESC LIMIT 6""")
        return {"n": int(sig["n"] or 0) if sig else 0, "total": total_n,
                "date": sig["d"] if sig else None,
                "top": top, "pass": [s for s in top if float(s.get("score") or 0) >= 60],
                "grades": grades, "near": near}
    except Exception as e:
        return {"_error": str(e)}

def fetch_sector_ranking(c):
    try:
        return q(c, """
            SELECT sector_name, current_rank, momentum_score, rank_1w_ago, rank_4w_ago
            FROM sector_ranking
            WHERE date=(SELECT MAX(date) FROM sector_ranking)
            ORDER BY current_rank ASC""")
    except Exception as e:
        return {"_error": str(e)}

def fetch_activity(c):
    try:
        latest = q1(c, """
            SELECT details->>'run_id' AS run_id FROM algo_audit_log
            WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"): return {}
        rid = latest["run_id"]
        phases = q(c, """
            SELECT action_type, status, details, created_at
            FROM algo_audit_log WHERE details->>'run_id'=%s ORDER BY created_at ASC""", (rid,))
        recent_actions = q(c, """
            SELECT action_type, status, details, created_at
            FROM algo_audit_log
            WHERE action_type IN ('entry_executed','exit_executed','entry_rejected',
                                  'position_exited','order_placed','order_rejected')
            ORDER BY created_at DESC LIMIT 6""")
        return {"run_id": rid, "phases": phases, "recent_actions": recent_actions}
    except Exception as e:
        return {"_error": str(e)}

def fetch_health(c):
    try:
        return q(c, """
            SELECT tbl, role, latest, age,
                   CASE WHEN age IS NULL OR age > stale THEN 'stale' ELSE 'ok' END AS st
            FROM (
              SELECT 'price_daily'    tbl,'CRIT' role, MAX(date)::date latest,(CURRENT_DATE-MAX(date)::date) age,3  stale FROM price_daily       UNION ALL
              SELECT 'buy_sell_daily','CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    3         FROM buy_sell_daily  UNION ALL
              SELECT 'swing_scores',  'CRIT',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    3         FROM swing_trader_scores UNION ALL
              SELECT 'technicals',    'IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    3         FROM technical_data_daily UNION ALL
              SELECT 'market_health', 'IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    7         FROM market_health_daily UNION ALL
              SELECT 'trend_template','IMP',           MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    7         FROM trend_template_data UNION ALL
              SELECT 'sector_ranking','SUPP',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    14        FROM sector_ranking UNION ALL
              SELECT 'economic_data', 'SUPP',          MAX(date)::date,       (CURRENT_DATE-MAX(date)::date),    14        FROM economic_data
            ) s ORDER BY CASE role WHEN 'CRIT' THEN 1 WHEN 'IMP' THEN 2 ELSE 3 END, tbl""")
    except:
        return []

def fetch_economic_pulse(c):
    try:
        KEY = ['DGS10', 'DGS2', 'DGS3MO', 'DGS6MO',
               'BAMLH0A0HYM2', 'BAMLC0A0CM',
               'DCOILWTICO', 'ANFCI',
               'FEDFUNDS', 'CPIAUCSL', 'UNRATE']
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
            cur_cpi  = float(cpi_rows[0]['value'])  if cpi_rows[0].get('value')  else None
            prev_cpi = float(cpi_rows[12]['value']) if cpi_rows[12].get('value') else None
            if cur_cpi and prev_cpi and prev_cpi > 0:
                cpi_yoy = round((cur_cpi - prev_cpi) / prev_cpi * 100, 2)

        return {
            't10': t10, 't2': t2, 't3m': t3m, 't6m': d.get('DGS6MO'),
            'yc_10_2':  yc_10_2, 'yc_10_3m': yc_10_3m,
            'hy':  d.get('BAMLH0A0HYM2'), 'ig': d.get('BAMLC0A0CM'),
            'oil': d.get('DCOILWTICO'),    'nfci': d.get('ANFCI'),
            'fed_funds': d.get('FEDFUNDS'),
            'cpi_yoy':   cpi_yoy,
            'unrate':    d.get('UNRATE'),
        }
    except Exception as e:
        return {"_error": str(e)}

def fetch_algo_metrics(c):
    try:
        rows = q(c, """SELECT date, total_actions, entries, exits
                       FROM algo_metrics_daily ORDER BY date DESC LIMIT 5""")
        return rows
    except Exception as e:
        return {"_error": str(e)}

def fetch_notifications(c):
    try:
        return q(c, """
            SELECT kind, severity, title, seen, created_at, details
            FROM algo_notifications
            ORDER BY created_at DESC LIMIT 8""")
    except Exception as e:
        return {"_error": str(e)}

def fetch_sentiment(c):
    try:
        row = q1(c, "SELECT fear_greed_index, label, date FROM market_sentiment ORDER BY date DESC LIMIT 1")
        if not row: return {}
        fg = float(row.get("fear_greed_index") or 0)
        label = row.get("label") or ""
        c_fg  = (R if fg <= 25 else (Y if fg <= 45 else (G if fg >= 75 else CY)))
        return {"fg": round(fg, 1), "label": label, "date": row.get("date"), "color": c_fg}
    except Exception as e:
        return {"_error": str(e)}

def fetch_economic_calendar(c):
    try:
        rows = q(c, """SELECT event_name, event_date, event_time, importance,
                              forecast_value, actual_value, previous_value
                       FROM economic_calendar
                       WHERE event_date >= CURRENT_DATE - 1
                         AND country='US'
                       ORDER BY event_date ASC, importance DESC, event_time ASC
                       LIMIT 8""")
        return rows
    except Exception as e:
        return {"_error": str(e)}

def fetch_risk_metrics(c):
    try:
        row = q1(c, """SELECT report_date, var_pct_95, cvar_pct_95, stressed_var_pct,
                              portfolio_beta, top_5_concentration
                       FROM algo_risk_daily ORDER BY report_date DESC LIMIT 1""")
        if not row: return {}
        return {
            "date":      row.get("report_date"),
            "var95":     float(row.get("var_pct_95")         or 0),
            "cvar95":    float(row.get("cvar_pct_95")        or 0),
            "svar":      float(row.get("stressed_var_pct")   or 0),
            "beta":      float(row.get("portfolio_beta")     or 0),
            "conc5":     float(row.get("top_5_concentration") or 0),
        }
    except Exception as e:
        return {"_error": str(e)}

def fetch_perf_analytics(c):
    try:
        row = q1(c, """SELECT report_date, rolling_sharpe_252d, rolling_sortino_252d,
                              calmar_ratio, win_rate_50t, avg_win_r_50t, avg_loss_r_50t,
                              expectancy, max_drawdown_pct
                       FROM algo_performance_daily ORDER BY report_date DESC LIMIT 1""")
        if not row: return {}
        def _f(k): return round(float(row[k]), 3) if row.get(k) is not None else None
        return {
            "sharpe252": _f("rolling_sharpe_252d"),
            "sortino":   _f("rolling_sortino_252d"),
            "calmar":    _f("calmar_ratio"),
            "wr50":      _f("win_rate_50t"),
            "avg_w_r":   _f("avg_win_r_50t"),
            "avg_l_r":   _f("avg_loss_r_50t"),
            "expectancy": _f("expectancy"),
            "maxdd":     _f("max_drawdown_pct"),
        }
    except Exception as e:
        return {"_error": str(e)}

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
        rejected = q(c, """SELECT evaluation_reason, COUNT(*) n
                           FROM algo_signals_evaluated
                           WHERE signal_date = (SELECT MAX(signal_date) FROM algo_signals_evaluated)
                             AND filter_tier_5_pass = false
                           GROUP BY evaluation_reason
                           ORDER BY n DESC LIMIT 3""")
        return {
            "total":    int(stats.get("total") or 0) if stats else 0,
            "t5":       int(stats.get("t5") or 0) if stats else 0,
            "avg_score": round(float(stats.get("avg_score") or 0), 1) if stats else 0,
            "date":     stats.get("signal_date") if stats else None,
            "rejected": rejected,
        }
    except Exception as e:
        return {"_error": str(e)}

def fetch_sector_rotation(c):
    try:
        row = q1(c, """SELECT date, signal, strength, details
                       FROM sector_rotation_signal
                       ORDER BY date DESC LIMIT 1""")
        if not row: return {}
        d = row.get("details") or {}
        if isinstance(d, str):
            import json as _j
            try: d = _j.loads(d)
            except: d = {}
        return {
            "date":     row.get("date"),
            "signal":   row.get("signal") or "",
            "strength": float(row.get("strength") or 0),
            "weeks":    d.get("weeks_persistent", 1),
            "def_score": d.get("defensive_lead_score", 0),
            "cyc_score": d.get("cyclical_weak_score", 0),
        }
    except Exception as e:
        return {"_error": str(e)}

def fetch_industry_ranking(c):
    try:
        return q(c, """SELECT industry, current_rank, momentum_score, rank_1w_ago
                       FROM industry_ranking
                       WHERE date_recorded >= CURRENT_DATE - 5
                       ORDER BY current_rank LIMIT 10""")
    except Exception as e:
        return {"_error": str(e)}

def fetch_circuit(c):
    try:
        cfg = {r["key"]: float(r["value"]) for r in q(c,
            "SELECT key, value FROM algo_config WHERE key=ANY(%s)",
            (["halt_drawdown_pct", "max_daily_loss_pct", "max_consecutive_losses",
              "max_total_risk_pct", "vix_max_threshold", "max_weekly_loss_pct"],))}
        snaps = q(c, "SELECT total_portfolio_value, daily_return_pct FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 30")
        lat   = snaps[0] if snaps else {}
        pk    = max((float(s.get("total_portfolio_value") or 0) for s in snaps), default=0)
        cur_v = float(lat.get("total_portfolio_value") or 0)
        dd    = (pk - cur_v) / pk * 100 if pk > 0 else 0
        dl    = max(0.0, -float(lat.get("daily_return_pct") or 0))
        wl    = max(0.0, -sum(float(s.get("daily_return_pct") or 0) for s in snaps[:5]))
        trades = q(c, "SELECT profit_loss_dollars FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL ORDER BY exit_date DESC LIMIT 20")
        consec = 0
        for t in trades:
            if float(t.get("profit_loss_dollars") or 0) < 0: consec += 1
            else: break
        h     = q1(c, "SELECT market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1")
        vix_r = q1(c, "SELECT vix_level FROM market_health_daily WHERE vix_level IS NOT NULL AND vix_level > 0 ORDER BY date DESC LIMIT 1")
        vix_v = vix_r.get("vix_level") if vix_r else None
        vix   = float(vix_v) if vix_v is not None else 0.0
        stage = int(h.get("market_stage") or 1) if h else 1
        rr    = q1(c, """
            WITH lt AS (
                SELECT DISTINCT ON (symbol) symbol, stop_loss_price
                FROM algo_trades WHERE status='open' ORDER BY symbol, trade_date DESC
            )
            SELECT SUM(GREATEST(p.current_price - lt.stop_loss_price, 0) * p.quantity) AS risk,
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1) AS pv
            FROM algo_positions p LEFT JOIN lt ON lt.symbol = p.symbol WHERE p.status='open'""")
        rp = float(rr["risk"] or 0) / float(rr["pv"] or 1) * 100 if rr and rr.get("risk") and rr.get("pv") else 0
        def th(k, d): return cfg.get(k, d)
        bs = [
            {"lbl": "Drawdown",  "cur": round(dd, 1),    "thr": th("halt_drawdown_pct", 20),     "u": "%"},
            {"lbl": "Daily",     "cur": round(dl, 1),    "thr": th("max_daily_loss_pct", 2),     "u": "%"},
            {"lbl": "Weekly",    "cur": round(wl, 1),    "thr": th("max_weekly_loss_pct", 5),    "u": "%"},
            {"lbl": "CnsLoss",   "cur": consec,           "thr": th("max_consecutive_losses", 3), "u": ""},
            {"lbl": "TotalRisk", "cur": round(rp, 1),    "thr": th("max_total_risk_pct", 4),     "u": "%"},
            {"lbl": "VIX",       "cur": round(vix, 1),   "thr": th("vix_max_threshold", 35),     "u": ""},
            {"lbl": "Stage",     "cur": stage,            "thr": 4,                                "u": ""},
        ]
        for b in bs: b["fired"] = float(b["cur"]) >= float(b["thr"])
        return {"bs": bs, "any": any(b["fired"] for b in bs), "n": sum(1 for b in bs if b["fired"])}
    except Exception as e:
        return {"_error": str(e)}


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
}

def load_all() -> dict:
    out: dict = {}
    def one(name, fn):
        conn = None
        try:
            conn = get_conn()
            conn.autocommit = True
            return name, fn(conn)
        except Exception as e:
            return name, {"_error": str(e)}
        finally:
            if conn:
                try: conn.close()
                except: pass
    with ThreadPoolExecutor(max_workers=len(FETCHERS)) as pool:
        for f in as_completed({pool.submit(one, k, v): k for k, v in FETCHERS.items()}):
            n, d = f.result()
            out[n] = d
    return out


# ── panel builders ────────────────────────────────────────────────────────────

def panel_orch(run, cfg, risk=None):
    next_run  = next_run_str()
    mode      = cfg.get("mode", "?")
    mc2       = G if "LIVE" in mode else Y
    en        = "ENABLED" if cfg.get("enabled", True) else "DISABLED"
    ec        = G if cfg.get("enabled", True) else R
    max_n     = cfg.get("max_pos_n")
    min_score = cfg.get("min_score")
    base_risk = cfg.get("base_risk")
    t1r       = cfg.get("t1_r")
    pyr       = cfg.get("pyramid", False)

    score_s   = f"[dim]score≥[/][white]{min_score}[/]" if min_score and float(min_score) > 0 else ""
    slots_s   = f"[dim]max[/][white]{max_n}[/][dim]p[/]" if max_n else ""
    risk_s    = f"[dim]risk[/][white]{base_risk}%[/]" if base_risk else ""
    t1r_s     = f"[dim]T1@[/][white]{t1r}R[/]" if t1r else ""
    pyr_s     = f"[{G}]🔺pyr[/]" if pyr else ""
    config_line = "  ".join(x for x in [score_s, slots_s, risk_s, t1r_s, pyr_s] if x)

    # VaR line
    var_line = ""
    if risk and not risk.get("_error") and risk.get("var95"):
        beta_c = R if (risk.get("beta") or 0) >= 1.2 else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        var_line = (f"\n[dim]VaR95:[/][white]{risk['var95']:.2f}%[/]  "
                    f"[dim]CVaR:[/][white]{risk['cvar95']:.2f}%[/]  "
                    f"[dim]β:[/][{beta_c}]{risk['beta']:.2f}[/]  "
                    f"[dim]Top5:[/][white]{risk['conc5']:.0f}%[/]")

    if not run or run.get("_error"):
        body = Text.from_markup(
            f"[dim]no run data[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next:[/] [white]{next_run}[/]"
            + var_line
        )
    else:
        age  = fmt_age(run.get("run_at"))
        sts  = ("[bold bright_green]✔ COMPLETED[/]" if run.get("success") and not run.get("halted")
                else ("[bold yellow]~ HALTED[/]" if run.get("halted")
                else "[bold bright_red]✗ ERROR[/]"))
        rid  = str(run.get("run_id") or "")[:24]
        pbadges = []
        for p in run.get("phases", []):
            at = p.get("action_type", "")
            if not at.startswith("phase_"): continue
            num = at.split("_")[1] if "_" in at else "?"
            ps  = p.get("status", "")
            pc  = G if ps == "success" else (Y if ps in ("halt", "warn") else R)
            pi  = "+" if ps == "success" else ("~" if ps in ("halt", "warn") else "x")
            pbadges.append(f"[{pc}]P{num}{pi}[/]")
        phases_str = " ".join(pbadges) if pbadges else "[dim]—[/]"
        body = Text.from_markup(
            f"{sts}  [dim]{age}[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next:[/] [white]{next_run}[/]  {phases_str}"
            + var_line
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
    spy_s   = f"SPY:[white]${float(spy_raw):.2f}[/]  " if spy_raw else ""
    trend_s = f"[dim]{trend[:8]}[/]" if trend else ""
    lines = [
        f"[{tc}][bold]{lbl}[/]  [dim]alloc[/][{tc}]{exp_s}[/]  {bar}",
        f"VIX:[{vc}]{vix}[/]  D:[white]{dist}[/]  S[white]{stage}[/]  {spy_s}{trend_s}",
    ]
    if upvol is not None:
        adr_s  = f"  AD:[white]{adr:.1f}[/]" if adr is not None else ""
        nhnl_s = f"  ΔNH:[{nhnl_c}]{sign(nhnl)}{nhnl}[/]" if nh is not None else ""
        lines.append(f"[dim]UV:[/][{uvc}]{upvol:.0f}%[/]{adr_s}  NH:[{G}]{nh or '--'}[/] NL:[{R}]{nl or '--'}[/]{nhnl_s}")
    bmom_pcr = []
    if pcr is not None:
        bmom_pcr.append(f"[dim]P/C:[/][{pcr_c}]{pcr:.2f}[/]")
    if bmom is not None:
        bmc = G if bmom >= 0.5 else (Y if bmom >= 0 else R)
        bmom_pcr.append(f"[dim]BrdMom:[/][{bmc}]{bmom:.1f}[/]")
    if bmom_pcr:
        lines.append("  ".join(bmom_pcr))
    halt_fed = f"[dim]Halt:[/][{hc}]{halt_s}[/]"
    if fed:
        halt_fed += f"  [dim]Fed:[/][white]{fed[:14]}[/]"
    lines.append(halt_fed)

    # Fear & Greed
    if sentiment and not sentiment.get("_error"):
        fg_v   = sentiment.get("fg", 0)
        fg_lbl = (sentiment.get("label") or "")[:14]
        fg_c   = sentiment.get("color", "dim")
        fg_bar = int(fg_v / 100 * 8)
        fg_bar_s = f"[{fg_c}]{'█' * fg_bar}[/][dim]{'░' * (8 - fg_bar)}[/]"
        lines.append(f"[dim]F&G:[/][{fg_c}]{fg_v:.0f} {fg_lbl}[/] {fg_bar_s}")

    txt = Text.from_markup("\n".join(lines))
    return Panel(txt, title="[bold blue]MARKET[/]", border_style="blue", padding=(0, 1))


def panel_circuit(cb):
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
            fc  = R if br["fired"] else (Y if float(br["thr"]) > 0 and float(br["cur"]) / float(br["thr"]) >= 0.75 else G)
            ind = "[bold red] ![/]" if br["fired"] else ""
            return f"[{fc}]{br['lbl']}:[/]{br['cur']}{br['u']}[dim]/{br['thr']:.0f}{br['u']}[/]{hbar(br['cur'], br['thr'], w=4)}{ind}"
        tbl.add_row(Text.from_markup(fmt_b(a)), Text.from_markup(fmt_b(b)))
    return Panel(Group(Text.from_markup(f"[{hc}][bold]{hs}[/bold][/]"), tbl),
                 title="[bold blue]CIRCUIT BREAKERS[/]", border_style="blue", padding=(0, 1))


def panel_portfolio(port, cfg):
    if not port or port.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]PORTFOLIO[/]", border_style="green", padding=(0, 1))
    pv    = float(port.get("total_portfolio_value") or 0)
    dr    = float(port.get("daily_return_pct") or 0)
    urp   = float(port.get("unrealized_pnl_pct") or 0)
    cash  = float(port.get("total_cash") or 0)
    npos  = int(port.get("position_count") or 0)
    max_n = int(cfg.get("max_pos_n") or 0) if cfg else 0
    pct_c = float(cfg.get("max_pos_pct") or 0) if cfg else 0
    bp    = pv * pct_c / 100 if (pv and pct_c) else cash
    slots = max_n - npos if max_n else None
    slots_s = f"  [dim]slots:[/][white]{slots}[/]" if slots is not None else ""
    txt   = Text.from_markup(
        f"[bold white]{fmt_money(pv)}[/]\n"
        f"[dim]Cash:[/] [white]{fmt_money(cash)}[/]  [dim]Pos:[/][white]{npos}[/]{slots_s}\n"
        f"[dim]Today:[/]   [{G if dr  >= 0 else R}]{sign(dr)}{dr:.2f}%[/]\n"
        f"[dim]Unrlzd:[/]  [{G if urp >= 0 else R}]{sign(urp)}{urp:.2f}%[/]\n"
        f"[dim]BuyPwr:[/]  [white]{fmt_money(bp)}[/]"
    )
    return Panel(txt, title="[bold green]PORTFOLIO[/]", border_style="green", padding=(0, 1))


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

    rows = [Text.from_markup(
        f"[bold white]{perf.get('n', 0)}T[/]  "
        f"[{G}]{perf.get('w', 0)}W[/][dim]/[/][{R}]{perf.get('l', 0)}L[/]  "
        f"[dim]WR:[/][{G if (perf.get('wr') or 0) >= 50 else R}]{perf.get('wr', '--')}%[/]  "
        f"[{str_c}]{str_s}[/]\n"
        f"[dim]P&L:[/][{pnl_c}]{fmt_money(perf.get('pnl'))}[/]  "
        f"[dim]PF:[/][{pf_c}]{pf_s}[/]  "
        f"[dim]Shp:[/][white]{perf.get('sharpe') or '--'}[/]  "
        f"[dim]DD:[/][white]{perf.get('maxdd', '--')}%[/]\n"
        f"[dim]Exp:[/][{exp_c}]{fmt_money(exp)}[/]  "
        f"[dim]R:[/][white]{avg_r_s}[/]  "
        f"[dim]W:[/][{G}]{fmt_money(perf.get('avg_win'))}[/]  "
        f"[dim]L:[/][{R}]{fmt_money(perf.get('avg_loss'))}[/]"
    )]

    # Equity sparkline
    eq_vals = perf.get("equity_vals") or []
    if len(eq_vals) >= 5:
        spark = sparkline(eq_vals, width=24)
        first_v = next((v for v in eq_vals if v > 0), None)
        if first_v:
            total_rtn = (eq_vals[-1] - first_v) / first_v * 100
            rc = G if total_rtn >= 0 else R
            rows.append(Text.from_markup(
                f"{spark} [{rc}]{sign(total_rtn)}{total_rtn:.1f}%[/]"
            ))

    # Rolling analytics from algo_performance_daily
    if perf_anl and not perf_anl.get("_error"):
        anl_parts = []
        sharpe252 = perf_anl.get("sharpe252")
        sortino   = perf_anl.get("sortino")
        calmar    = perf_anl.get("calmar")
        wr50      = perf_anl.get("wr50")
        if sharpe252 is not None:
            sc = G if sharpe252 >= 1.0 else (Y if sharpe252 >= 0 else R)
            anl_parts.append(f"[dim]Shp252:[/][{sc}]{sharpe252:.2f}[/]")
        if sortino is not None:
            sc = G if sortino >= 1.5 else (Y if sortino >= 0 else R)
            anl_parts.append(f"[dim]Srt:[/][{sc}]{sortino:.2f}[/]")
        if calmar is not None:
            sc = G if calmar >= 0.5 else (Y if calmar >= 0 else R)
            anl_parts.append(f"[dim]Cal:[/][{sc}]{calmar:.2f}[/]")
        total_trades = perf.get("n", 0) if perf else 0
        if wr50 is not None and (total_trades >= 10 or wr50 > 0):
            wrc = G if wr50 >= 55 else (Y if wr50 >= 45 else R)
            anl_parts.append(f"[dim]WR50T:[/][{wrc}]{wr50:.0f}%[/]")
        if anl_parts:
            rows.append(Text.from_markup("  ".join(anl_parts)))

    # Recent trades (open, pending, closed)
    recent = [t for t in rec if t.get("status") in ("closed", "pending", "pending_new")][:3]
    if recent:
        rows.append(Text.from_markup("[dim]Recent:[/]"))
        for t in recent:
            st   = t.get("status", "")
            pv2  = float(t.get("profit_loss_dollars") or 0)
            pct_v = float(t.get("profit_loss_pct") or 0)
            rv   = float(t.get("exit_r_multiple") or 0) if t.get("exit_r_multiple") else None
            sym  = t.get("symbol") or "--"
            if st in ("pending", "pending_new"):
                rows.append(Text.from_markup(f"  [{Y}]{sym} PENDING[/]"))
            else:
                c = G if pv2 >= 0 else R
                rv_s = f" {sign(rv)}{rv:.1f}R" if rv is not None else ""
                rows.append(Text.from_markup(
                    f"  [{c}]{sym} {sign(pct_v)}{pct_v:.1f}%{rv_s}[/]"
                ))

    return Panel(Group(*rows), title="[bold green]PERFORMANCE[/]", border_style="green", padding=(0, 1))


def panel_positions(pos, compact=False, trades=None):
    if not pos:
        return Panel(Text("  No open positions — algo is flat", style="dim"),
                     title="[bold]POSITIONS[/]", border_style="cyan", padding=(0, 1))
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="dim bold",
              padding=(0, 1), row_styles=["", "dim"], expand=True)
    t.add_column("Symbol",  style="bold white", no_wrap=True, min_width=6)
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
        entry = float(p.get("avg_entry_price") or 0)
        price = float(p.get("current_price")   or 0)
        stop  = float(p.get("stop_loss_price") or 0) if p.get("stop_loss_price") else None
        t1    = float(p.get("target_1_price")  or 0) if p.get("target_1_price")  else None
        pnl   = float(p.get("unrealized_pnl_pct") or 0)
        days  = p.get("days_since_entry") or "--"
        stg   = p.get("weinstein_stage")
        swg   = p.get("swing_score")
        sec   = (p.get("sector") or "--")[:12]
        rmul  = (price - entry) / (entry - stop)   if (stop and entry > stop) else None
        dist  = (price - stop)  / price * 100        if (stop and price)        else None
        t1pct = (t1 - price)    / price * 100         if (t1 and price)         else None
        pc    = G if pnl >= 0        else R
        rc    = G if (rmul or 0) >= 0 else R
        dc    = R if (dist or 99) < 3 else (Y if (dist or 99) < 5 else "white")
        row = [
            p.get("symbol") or "--",
            f"${entry:.2f}", f"${price:.2f}",
            Text(f"{sign(pnl)}{pnl:.2f}%", style=pc),
            Text(f"{sign(rmul or 0)}{rmul:.2f}R" if rmul is not None else "--", style=rc),
            f"${stop:.2f}" if stop else "--",
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

    # Pending/queued trades below open positions
    pending = [tr for tr in (trades or [])
               if tr.get("status") in ("pending", "pending_new", "rejected")] if trades else []
    if pending:
        pend_rows = [Text.from_markup("[dim]Queued / Recent:[/]")]
        for tr in pending[:4]:
            st  = tr.get("status", "")
            sym = tr.get("symbol") or "--"
            td  = tr.get("trade_date")
            age_s = fmt_age(td) if td else "--"
            if st == "rejected":
                pend_rows.append(Text.from_markup(f"  [{R}]✗ {sym}[/] [dim]{age_s} rejected[/]"))
            else:
                pend_rows.append(Text.from_markup(f"  [{Y}]▷ {sym}[/] [dim]{age_s} {st}[/]"))
        content = Group(t, *pend_rows)
    else:
        content = t

    return Panel(content, title=f"[bold cyan]POSITIONS ({len(pos)})[/]", border_style="cyan", padding=(0, 0))


def panel_signals_compact(sig, sig_eval=None):
    """Signals & breadth — compact (top 10 scores in 2-col grid)."""
    if not sig or sig.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]SIGNALS[/]", border_style="magenta", padding=(0, 1))
    raw   = sig.get("n", 0)
    total = sig.get("total", 0)
    top   = sig.get("top", [])[:10]
    d     = sig.get("date")
    ds    = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    pct_s = f"{raw / total * 100:.1f}%" if total > 0 else "--"
    g     = sig.get("grades") or {}
    ga, gb, gc, gd, gt = (int(g.get(k) or 0) for k in ("a","b","c","d","total"))
    if gt == 0: gt = 1
    near  = sig.get("near") or []

    # Signal evaluation stats
    eval_line = ""
    if sig_eval and not sig_eval.get("_error"):
        ev_tot = sig_eval.get("total", 0)
        ev_t5  = sig_eval.get("t5", 0)
        ev_avg = sig_eval.get("avg_score", 0)
        ev_c   = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
        eval_line = f"\n[dim]Eval:[/][white]{ev_tot}[/][dim] scnd, [/][{ev_c}]{ev_t5}[/][dim] pass T5, avg {ev_avg:.0f}[/]"

    rows = [
        Text.from_markup(
            f"[dim]{ds}[/]  [bold white]{raw}[/][dim] BUY/{total} ({pct_s})[/]\n"
            f"[{G}]A:{ga}[/]  [{CY}]B:{gb}[/]  [{Y}]C:{gc}[/]  [{R}]D:{gd}[/]  [dim]/{gt}[/]"
            + eval_line
        ),
        Rule(style="dim"),
    ]
    for a, b in zip(top[::2], top[1::2] + [None]):
        sa = float(a.get("score") or 0)
        ca = G if sa >= 80 else CY
        left = f"[{ca}]{grade(sa)} {a['symbol']:<5} {sa:.0f}[/]"
        if b:
            sb = float(b.get("score") or 0)
            cb2 = G if sb >= 80 else CY
            right = f"[{cb2}]{grade(sb)} {b['symbol']:<5} {sb:.0f}[/]"
            rows.append(Text.from_markup(f"  {left}  {right}"))
        else:
            rows.append(Text.from_markup(f"  {left}"))

    if near:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Watch (55-69):[/]"))
        for a, b in zip(near[::2], near[1::2] + [None]):
            sa = float(a.get("score") or 0)
            left = f"[{Y}]{a['symbol']:<5} {sa:.0f}[/]"
            if b:
                sb = float(b.get("score") or 0)
                rows.append(Text.from_markup(f"  {left}  [{Y}]{b['symbol']:<5} {sb:.0f}[/]"))
            else:
                rows.append(Text.from_markup(f"  {left}"))

    return Panel(Group(*rows), title="[bold magenta]SIGNALS[/]", border_style="magenta", padding=(0, 1))


def panel_sector_compact(srank, pos, port, sec_rot=None, irank=None):
    """Rotation + holdings (top 3) + top industries — fits 8 content lines."""
    rows = []

    # Row 1: Rotation signal
    if sec_rot and not sec_rot.get("_error") and sec_rot.get("signal"):
        sig_name = (sec_rot.get("signal") or "").replace("_", " ")
        wks   = sec_rot.get("weeks", 1)
        def_s = sec_rot.get("def_score", 0)
        sig_c = R if def_s >= 60 else (Y if def_s >= 40 else G)
        rows.append(Text.from_markup(
            f"[dim]Rotation:[/] [{sig_c}]{sig_name}[/] [dim]{wks}wk[/]"
        ))
        rows.append(Rule(style="dim"))

    # Rows 2-4: Holdings by sector (top 3, no header label)
    if pos:
        pv = float(port.get("total_portfolio_value") or 0)
        sd: dict = {}
        for p in pos:
            sec = p.get("sector") or "Unknown"
            val = float(p.get("position_value") or 0)
            pnl = float(p.get("unrealized_pnl_pct") or 0)
            if sec not in sd:
                sd[sec] = {"val": 0.0, "n": 0, "pnls": []}
            sd[sec]["val"] += val
            sd[sec]["n"]   += 1
            sd[sec]["pnls"].append(pnl)
        for sec, d in sorted(sd.items(), key=lambda x: -x[1]["val"])[:3]:
            pct     = d["val"] / pv * 100 if pv else 0
            avg_pnl = sum(d["pnls"]) / len(d["pnls"]) if d["pnls"] else 0
            pc      = G if avg_pnl >= 0 else R
            bar_f   = int(min(pct, 25) / 25 * 4)
            bar     = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (4 - bar_f)}[/]"
            rows.append(Text.from_markup(
                f"  [white]{sec[:12]:<12}[/] {bar} [dim]{d['n']}p {pct:.0f}%[/] [{pc}]{sign(avg_pnl)}{avg_pnl:.1f}%[/]"
            ))
        rows.append(Rule(style="dim"))

    # Row 5-7: Top industries (compact pairs, 2 per line)
    valid_irank = irank if (irank and not (isinstance(irank, dict) and irank.get("_error"))) else []
    if valid_irank:
        def idelta(r):
            cur, old = r.get("current_rank", 0), r.get("rank_1w_ago")
            if old is None: return ""
            d = int(old) - int(cur)
            if d > 0:   return f"[{G}]▲{d}[/]"
            if d < 0:   return f"[{R}]▼{abs(d)}[/]"
            return "[dim]=[/]"
        rows.append(Text.from_markup(f"[{CY}]Industries:[/]"))
        items = valid_irank[:4]
        for a, b in zip(items[::2], items[1::2] + [None]):
            na = (a.get("industry") or "")[:9]
            la = f"[{CY}]#{a['current_rank']}[/][white]{na}[/]{idelta(a)}"
            if b:
                nb = (b.get("industry") or "")[:9]
                rows.append(Text.from_markup(f" {la}  [{CY}]#{b['current_rank']}[/][white]{nb}[/]{idelta(b)}"))
            else:
                rows.append(Text.from_markup(f" {la}"))
    elif srank and not (isinstance(srank, dict) and srank.get("_error")):
        # Fallback: sector ranking top 3 if no industry data
        rows.append(Text.from_markup(f"[{G}]Sec Leaders:[/]"))
        for r in srank[:3]:
            nm = (r.get("sector_name") or "--")[:17]
            rows.append(Text.from_markup(f"  [{G}]#{r.get('current_rank'):<2}[/] [white]{nm}[/]"))

    if not rows:
        return Panel(Text("no data", style="dim"), title="[bold]SECTORS[/]", border_style="cyan", padding=(0, 1))
    return Panel(Group(*rows), title="[bold cyan]SECTORS[/]", border_style="cyan", padding=(0, 1))


def panel_economic_pulse(eco, econ_cal=None):
    """Yields, curve, credit, macro indicators + upcoming calendar events."""
    if not eco or eco.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]ECONOMIC[/]",
                     border_style="bright_magenta", padding=(0, 1))
    rows: list = []

    t10 = eco.get("t10"); t2 = eco.get("t2"); t3m = eco.get("t3m")
    yc10_2 = eco.get("yc_10_2"); yc10_3m = eco.get("yc_10_3m")
    hy  = eco.get("hy"); ig = eco.get("ig")
    oil = eco.get("oil"); nfci = eco.get("nfci")
    fed_funds = eco.get("fed_funds")
    cpi_yoy   = eco.get("cpi_yoy")
    unrate    = eco.get("unrate")

    # Treasury yields
    y_parts = []
    if t3m is not None: y_parts.append(f"[dim]3M:[/][white]{t3m:.2f}%[/]")
    if t2  is not None: y_parts.append(f"[dim]2Y:[/][white]{t2:.2f}%[/]")
    if t10 is not None: y_parts.append(f"[dim]10Y:[/][white]{t10:.2f}%[/]")
    if fed_funds is not None: y_parts.append(f"[dim]FFR:[/][white]{fed_funds:.2f}%[/]")
    if y_parts: rows.append(Text.from_markup("  ".join(y_parts)))

    # Yield curve
    if yc10_2 is not None:
        ycc = G if yc10_2 >= 0.5 else (Y if yc10_2 >= 0 else R)
        inv = "  [bold red]INV[/]" if yc10_2 < 0 else ""
        c3m = f"  [dim]10Y-3M:[/][{ycc}]{yc10_3m:+.2f}%[/]" if yc10_3m is not None else ""
        rows.append(Text.from_markup(
            f"[dim]10Y-2Y:[/][{ycc}]{yc10_2:+.2f}%[/]{inv}{c3m}"
        ))

    # Credit spreads
    if hy is not None or ig is not None:
        parts = []
        if hy is not None:
            hy_c = G if hy <= 3.5 else (Y if hy <= 6.0 else R)
            parts.append(f"[dim]HY OAS:[/][{hy_c}]{hy:.2f}%[/]")
        if ig is not None:
            ig_c = G if ig <= 1.0 else (Y if ig <= 2.0 else R)
            parts.append(f"[dim]IG OAS:[/][{ig_c}]{ig:.2f}%[/]")
        rows.append(Text.from_markup("  ".join(parts)))

    # Macro: CPI YoY, unemployment, NFCI, oil
    macro = []
    if cpi_yoy is not None:
        cpi_c = G if cpi_yoy <= 2.5 else (Y if cpi_yoy <= 4.0 else R)
        macro.append(f"[dim]CPI YoY:[/][{cpi_c}]{cpi_yoy:.1f}%[/]")
    if unrate is not None:
        ur_c = G if unrate <= 4.5 else (Y if unrate <= 6.0 else R)
        macro.append(f"[dim]Unemp:[/][{ur_c}]{unrate:.1f}%[/]")
    if macro: rows.append(Text.from_markup("  ".join(macro)))

    other = []
    if oil  is not None: other.append(f"[dim]WTI:[/][white]${oil:.2f}[/]")
    if nfci is not None:
        nc  = G if nfci <= -0.3 else (Y if nfci <= 0.3 else R)
        lbl = "accom." if nfci < 0 else ("tight" if nfci > 0.3 else "neut.")
        other.append(f"[dim]NFCI:[/][{nc}]{nfci:+.3f}[/][dim] {lbl}[/]")
    if other: rows.append(Text.from_markup("  ".join(other)))

    # Economic calendar (upcoming events)
    valid_cal = econ_cal if (econ_cal and not (isinstance(econ_cal, dict) and econ_cal.get("_error"))) else []
    if valid_cal:
        rows.append(Rule(style="dim"))
        IMP_C = {"HIGH": "bold bright_red", "MEDIUM": "yellow", "LOW": "dim"}
        from datetime import date
        today = date.today()
        seen_keys = set()
        for ev in valid_cal[:6]:
            ed      = ev.get("event_date")
            full_nm = (ev.get("event_name") or "")
            name    = full_nm[:24]
            key     = (str(ed) + full_nm[:18]).lower()
            if key in seen_keys: continue
            if any(key.startswith(k[:len(key)]) or k.startswith(key) for k in seen_keys): continue
            seen_keys.add(key)
            imp  = (ev.get("importance") or "LOW").upper()
            ic   = IMP_C.get(imp, "dim")
            f_v  = ev.get("forecast_value")
            a_v  = ev.get("actual_value")
            p_v  = ev.get("previous_value")
            if ed == today:
                when = "TODAY"
            elif ed is not None:
                delta = (ed - today).days
                when  = f"+{delta}d" if delta > 0 else "YST"
            else:
                when = "--"
            vals = ""
            if a_v is not None:
                ac = G if float(a_v) <= float(f_v or a_v) else R
                vals = f" [{ac}]A={a_v:.1f}[/]"
            elif f_v is not None:
                vals = f" [dim]F={f_v:.1f}[/]"
            if p_v is not None:
                vals += f"[dim] P={p_v:.1f}[/]"
            rows.append(Text.from_markup(
                f"[{ic}]{when:<5}[/] [white]{name}[/]{vals}"
            ))

    if not rows:
        rows.append(Text("[dim]no economic data[/]"))
    return Panel(Group(*rows), title="[bold bright_magenta]ECONOMIC[/]",
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
        ("trend_30wk",    "Tr30wk", 15),
        ("breadth_50dma", "Br50MA", 14),
        ("ibd_state",     "IBD",    18),
        ("breadth_200dma","Br200M", 10),
        ("mcclellan",     "McClln",  9),
        ("vix_regime",    "VIX",     8),
        ("new_highs_lows","NHNL",    7),
        ("credit_spread", "Credit",  7),
        ("ad_line",       "A/D",     5),
        ("aaii_sentiment","AAII",    4),
        ("naaim",         "NAAIM",   3),
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
        sig = (sr.get("signal") or "").replace("_", " ")[:16]
        items.append(f"[{R}]SctRot[/] [dim]{sr_pen:+.0f} {sig}[/]")
    if eco_pen < 0:
        eco_err = (eco.get("error") or "")[:16]
        items.append(f"[{R}]EcoOvl[/] [dim]{eco_pen:+.0f}{(' ' + eco_err) if eco_err else ''}[/]")

    for a, b in zip(items[::2], items[1::2] + [""]):
        tbl.add_row(Text.from_markup(a), Text.from_markup(b))

    raw_bar = mini_bar(raw, 100, w=8)
    header  = Text.from_markup(
        f"[dim]Raw:[/][white]{raw:.0f}[/]/100 {raw_bar} [{tc}][bold]{epct:.0f}%[/][/]  [dim]{regime[:24]}[/]"
    )
    return Panel(Group(header, tbl), title="[bold blue]EXPOSURE FACTORS[/]",
                 border_style="blue", padding=(0, 1))


def panel_status(act, hlth, notifs, algo_metrics=None):
    """Algo activity phases + data health + recent notifications + action counts."""
    rows: list = []

    # Activity phases
    if act and not act.get("_error"):
        rid    = (act.get("run_id") or "")[:26]
        phases = act.get("phases") or []
        recent = act.get("recent_actions") or []
        if rid:
            rows.append(Text.from_markup(f"[dim]Run:[/] [white]{rid}[/]"))
        phase_badges = []
        for p in phases:
            at = p.get("action_type", "")
            if not at.startswith("phase_"): continue
            parts = at.split("_")
            num = parts[1] if len(parts) > 1 else "?"
            st  = p.get("status", "")
            sc  = G if st == "success" else (Y if st in ("halt","warn","halted") else R)
            si  = "+" if st == "success" else ("~" if st in ("halt","warn","halted") else "!")
            phase_badges.append(f"[{sc}]{si}P{num}[/]")
        if phase_badges:
            rows.append(Text.from_markup(" ".join(phase_badges)))

        trade_evts = [a for a in recent if a.get("action_type") in
                      ("entry_executed","exit_executed","entry_rejected","position_exited")]
        for a in trade_evts[:3]:
            at  = a.get("action_type", "")
            det = a.get("details") or {}
            if isinstance(det, str):
                try: det = json.loads(det)
                except: det = {}
            sym = det.get("symbol", "")
            ic  = G if "executed" in at else R
            lbl = at.replace("_", " ").title()[:20]
            rows.append(Text.from_markup(f"  [{ic}]{lbl}{(' ' + sym) if sym else ''}[/]"))

    # Data health (stale tables only)
    if hlth:
        rows.append(Rule(style="dim"))
        stale = [r for r in hlth if r.get("st") != "ok"]
        if not stale:
            all_ok_txt = "  ".join(
                f"[{G}]✓[/][dim]{r.get('tbl','')[:8]}[/]" for r in hlth[:4]
            )
            rows.append(Text.from_markup(f"[{G}]✓ Data OK[/]  [dim]{len(hlth)} tables[/]"))
        else:
            for r in stale[:4]:
                nm  = (r.get("tbl") or "--")[:14]
                age = r.get("age") or "?"
                rc  = r.get("role", "")
                cc  = "bold white" if rc == "CRIT" else "white"
                rows.append(Text.from_markup(f"[{R}]✗[/] [{cc}]{nm:<14}[/] [dim]{age}d stale[/]"))

    # Notifications (up to 4)
    valid_notifs = notifs if (notifs and not (isinstance(notifs, dict) and notifs.get("_error"))) else []
    if valid_notifs:
        rows.append(Rule(style="dim"))
        SEV_C = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        for n in valid_notifs[:4]:
            sc    = SEV_C.get(n.get("severity","info"), DIM)
            title = (n.get("title") or "")[:32]
            age   = fmt_age(n.get("created_at"))
            unread = "●" if not n.get("seen", True) else " "
            rows.append(Text.from_markup(
                f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]"
            ))

    # Algo metrics daily (action counts)
    valid_metrics = algo_metrics if (algo_metrics and not (isinstance(algo_metrics, dict) and algo_metrics.get("_error"))) else []
    if valid_metrics:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Daily actions:[/]"))
        for m in valid_metrics[:3]:
            d   = m.get("date")
            d_s = d.strftime("%m/%d") if hasattr(d, "strftime") else str(d or "--")
            ta  = int(m.get("total_actions") or 0)
            en  = int(m.get("entries") or 0)
            ex  = int(m.get("exits") or 0)
            rows.append(Text.from_markup(
                f"  [dim]{d_s}:[/] [white]{ta}[/][dim] acts, [/][{G}]{en}[/][dim]E [/][{R}]{ex}[/][dim]X[/]"
            ))

    if not rows:
        rows.append(Text("no activity", style="dim"))
    return Panel(Group(*rows), title="[bold yellow]ACTIVITY & HEALTH[/]", border_style="yellow", padding=(0, 1))


# ── mascot sidebar ────────────────────────────────────────────────────────────

def mascot_sidebar(data: dict, frame: int, secs_to_refresh: Optional[int] = None) -> Panel:
    fi   = mascot_pose(data, frame)
    mc   = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    cb   = data.get("cb") or {}
    mkt  = data.get("mkt") or {}
    tier = mkt.get("tier", "unknown")
    tc   = TIER_COLOR.get(tier, "dim")
    lbl  = TIER_SHORT.get(tier, "LOADING")
    exp_s = f"{float(mkt.get('pct') or 0):.0f}%" if mkt.get("pct") is not None else "--"
    vix_v = mkt.get("vix")
    vix_s = f"VIX {vix_v:.1f}" if vix_v is not None else ""

    if cb.get("any"):
        n_cb = cb.get("n", 0)
        body = Text.from_markup(
            f"\n[bold {mc}]{pose[0]}[/]\n"
            f"[bold {mc}]{pose[1]}[/]\n"
            f"[bold {mc}]{pose[2]}[/]\n\n"
            f"[bold bright_red]⚠ CB FIRED[/]\n"
            f"[{R}]{n_cb} breaker{'s' if n_cb != 1 else ''}[/]"
            + (f"\n\n[dim]↻ {secs_to_refresh}s[/]" if secs_to_refresh is not None else "")
        )
    else:
        refresh = f"\n\n[dim]↻ {secs_to_refresh}s[/]" if secs_to_refresh is not None else ""
        vix_line = f"\n[{tc}]{vix_s}[/]" if vix_s else ""
        body = Text.from_markup(
            f"\n[bold {mc}]{pose[0]}[/]\n"
            f"[bold {mc}]{pose[1]}[/]\n"
            f"[bold {mc}]{pose[2]}[/]\n\n"
            f"[{tc}]{lbl}[/]\n"
            f"[dim]{exp_s}[/]"
            + vix_line + refresh
        )
    return Panel(
        Align(body, align="center"),
        title="[bold white]ALGO[/]",
        border_style=mc,
        padding=(0, 0),
    )


# ── loading layout — mascot always in upper right ─────────────────────────────

def loading_layout(frame: int) -> Layout:
    """Show mascot in sidebar + loading message in main — same structure as full dashboard."""
    fi   = LOAD_SEQ[frame % len(LOAD_SEQ)]
    mc   = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    dots = "." * ((frame % 4) + 1)

    sidebar_body = Text.from_markup(
        f"\n[bold {mc}]{pose[0]}[/]\n"
        f"[bold {mc}]{pose[1]}[/]\n"
        f"[bold {mc}]{pose[2]}[/]\n\n"
        f"[dim]Loading{dots}[/]"
    )
    sidebar = Panel(
        Align(sidebar_body, align="center"),
        title="[bold white]ALGO[/]",
        border_style=mc,
        padding=(0, 0),
    )

    loading_body = Text.from_markup(
        f"\n\n\n[bold white]  ALGO OPS DASHBOARD[/]\n\n"
        f"  [dim]Fetching market data{dots}[/]\n\n"
        f"  [dim]Connecting to database...[/]"
    )
    main = Panel(
        Align(loading_body, align="left", vertical="middle"),
        border_style="blue",
        padding=(0, 1),
    )

    layout = Layout()
    layout.split_row(
        Layout(name="main",    ratio=1),
        Layout(name="sidebar", size=18),
    )
    layout["main"].update(main)
    layout["sidebar"].update(sidebar)
    return layout


# ── dashboard layout ──────────────────────────────────────────────────────────

def render_dashboard(data: dict, compact: bool = False, elapsed: float = 0.0,
                     frame: int = 0, watch_interval: Optional[int] = None,
                     last_load_time: Optional[float] = None) -> Layout:
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

    now_et = datetime.now(ET)
    mkt_s  = "[bold bright_green]● OPEN[/]" if is_open() else "[dim]● CLOSED[/]"
    ts     = now_et.strftime("%a %b %d  %I:%M %p ET")
    secs: Optional[int] = None
    if watch_interval is not None and last_load_time is not None:
        secs = max(0, watch_interval - int(time.monotonic() - last_load_time))

    # Outer split: main content | mascot sidebar
    outer = Layout()
    outer.split_row(
        Layout(name="main",    ratio=1),
        Layout(name="sidebar", size=18),
    )

    # Main content: header + 5 rows using ratio splits (adapts to terminal height)
    main = Layout()
    main.split_column(
        Layout(name="hdr",  size=1),
        Layout(name="r1",   ratio=1),
        Layout(name="r2",   ratio=1),
        Layout(name="pos",  ratio=2),  # positions gets 2x height
        Layout(name="r3",   ratio=1),
        Layout(name="r4",   ratio=1),
    )

    cb_fired = cb.get("any", False)
    cb_n     = cb.get("n", 0)
    fired_names = [b["lbl"] for b in (cb.get("bs") or []) if b.get("fired")]
    if cb_fired:
        fired_str = " · ".join(fired_names)
        hdr_rule = Rule(
            f"[bold bright_red]⚠ CB FIRED: {fired_str}[/]  {mkt_s}  [dim]{ts}[/]  [dim]{elapsed:.1f}s[/]",
            style="bright_red"
        )
    else:
        hdr_rule = Rule(
            f"[bold white]ALGO OPS DASHBOARD[/]  {mkt_s}  [dim]{ts}[/]  [dim]{elapsed:.1f}s[/]",
            style="blue"
        )
    main["hdr"].update(hdr_rule)

    # Row 1: Orchestrator | Market (full: regime + internals) | Circuit Breakers
    main["r1"].split_row(
        Layout(panel_orch(run, cfg, risk),              name="orch"),
        Layout(panel_market_full(mkt, sentiment),       name="market"),
        Layout(panel_circuit(cb),                       name="circuit"),
    )

    # Row 2: Portfolio | Performance + sparkline | Economic pulse
    main["r2"].split_row(
        Layout(panel_portfolio(port, cfg),                          name="portfolio"),
        Layout(panel_performance_spark(perf, rec, perf_anl),       name="perf"),
        Layout(panel_economic_pulse(eco, econ_cal),                 name="eco"),
    )

    # Row 3: Positions (full width, 2x height) — includes pending trades
    main["pos"].update(panel_positions(pos, compact, trades=rec))

    # Row 4: Signals | Sectors (exposure + ranking)
    main["r3"].split_row(
        Layout(panel_signals_compact(sig, sig_eval),             name="signals"),
        Layout(panel_sector_compact(srank, pos, port, sec_rot, irank),  name="sectors"),
    )

    # Row 5: Exposure factors | Activity + health + notifications
    main["r4"].split_row(
        Layout(panel_exposure_compact(exp_f), name="exposure"),
        Layout(panel_status(act, hlth, notifs, algo_metrics), name="status"),
    )

    outer["main"].update(main)
    outer["sidebar"].update(mascot_sidebar({"cb": cb, "mkt": mkt}, frame, secs))
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
    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                frame += 1
                if not done.is_set():
                    live.update(loading_layout(frame))
                else:
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0], frame=frame))
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

    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                frame[0] += 1
                if loading[0] or result[0] is None:
                    live.update(loading_layout(frame[0]))
                else:
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0],
                        frame=frame[0], watch_interval=interval,
                        last_load_time=last_load[0]))
                    if not loading[0] and (time.monotonic() - last_load[0]) >= interval:
                        threading.Thread(target=reload, daemon=True).start()
                time.sleep(0.125)
        except KeyboardInterrupt:
            pass


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
    args = pa.parse_args()

    if args.watch is not None:
        run_watch(max(10, args.watch), args.compact)
    else:
        run_once(args.compact)


if __name__ == "__main__":
    main()
