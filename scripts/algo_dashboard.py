#!/usr/bin/env python3
"""
Algo Ops Terminal Dashboard  --  single-pane morning brief.

Usage:
  python scripts/algo_dashboard.py            # one-shot (mascot dances while loading)
  python scripts/algo_dashboard.py -w         # watch mode, refresh every 30s (mascot dances continuously)
  python scripts/algo_dashboard.py -w 60      # watch mode, refresh every 60s
  python scripts/algo_dashboard.py --compact  # skip T1/Sector columns in positions
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
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

# Windows: switch console to UTF-8 before any other output
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

# ── globals ──────────────────────────────────────────────────────────────────
ET     = ZoneInfo("America/New_York")
CONSOLE = Console(force_terminal=True, legacy_windows=False, highlight=False)

G  = "bright_green"
R  = "bright_red"
Y  = "yellow"
CY = "cyan"
DIM = "dim"

TIER_COLOR = {
    "confirmed_uptrend": "bright_green",
    "healthy_uptrend":   "green",
    "pressure":          "yellow",
    "caution":           "orange1",
    "correction":        "bright_red",
}

# Mascot dances at 8fps in watch mode. Pose reflects market state.
MASCOT_FRAMES = [
    (" \\o/ ", "  |  ", " / \\ "),   # 0 uptrend groove
    ("  o/  ", " /|  ", "  |\\  "),  # 1 side lean
    (" /o\\ ", "  |  ", " \\/ "),    # 2 windmill
    (" \\o_ ", " /|  ", "  |\\ "),   # 3 freeze
    (" / \\ ", "  |  ", " \\o/ "),   # 4 headstand (correction)
    ("  o\\ ", "  |\\ ", " /   "),   # 5 stumble (circuit breaker)
]
MASCOT_COLORS = [
    "bright_green", "green", "bright_yellow",
    "bright_magenta", "bright_cyan", "bright_red",
]

# Mascot always dances; animation range reflects market state
def mascot_pose(data, frame):
    cb   = data.get("cb") or {}
    mkt  = data.get("mkt") or {}
    tier = mkt.get("tier", "unknown")
    if cb.get("any"):
        return 4 + (frame % 2)          # stumble/headstand when breaker fired
    tier_ranges = {
        "confirmed_uptrend": [0, 1],    # bounce between happy frames
        "healthy_uptrend":   [0, 1],
        "pressure":          [1, 2, 3], # windmill + freeze cycle
        "caution":           [2, 3],
        "correction":        [3, 4],
    }
    r = tier_ranges.get(tier, [0, 1, 2])
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
    if ts is None: return "--"
    if isinstance(ts, str): ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:   ts = ts.replace(tzinfo=timezone.utc)
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

def tier_from_pct(p):
    if p is None: return "unknown"
    p = float(p)
    if p >= 80: return "confirmed_uptrend"
    if p >= 60: return "healthy_uptrend"
    if p >= 40: return "pressure"
    if p >= 20: return "caution"
    return "correction"

def is_open():
    n = datetime.now(ET)
    if n.weekday() >= 5: return False
    t = n.hour * 60 + n.minute
    return 570 <= t <= 960

def next_run_str():
    """Return human string for next algo execution (2 AM morning prep or 9:30 AM orchestrator)."""
    from datetime import timedelta
    now = datetime.now(ET)
    wd  = now.weekday()      # 0=Mon … 4=Fri, 5=Sat, 6=Sun
    t   = now.hour * 60 + now.minute

    def fmt(dt):
        diff = dt - now
        mins = int(diff.total_seconds() / 60)
        if mins < 60:  return f"in {mins}m"
        if mins < 1440: return f"in {mins//60}h{mins%60:02d}m"
        return f"{dt.strftime('%a %I:%M %p')}"

    def next_weekday(dt, offset=0):
        d = dt + timedelta(days=offset)
        while d.weekday() >= 5: d += timedelta(days=1)
        return d

    if wd < 5:  # weekday
        if t < 2*60:        # before 2 AM → morning prep today
            target = now.replace(hour=2, minute=0, second=0, microsecond=0)
            return f"morning prep {fmt(target)}"
        if t < 9*60+30:     # before 9:30 AM → orchestrator today
            target = now.replace(hour=9, minute=30, second=0, microsecond=0)
            return f"orchestrator {fmt(target)}"
        # After 9:30 AM → morning prep next business day
        tomorrow = next_weekday(now, 1)
        target = tomorrow.replace(hour=2, minute=0, second=0, microsecond=0)
        return f"morning prep {fmt(target)}"
    else:  # weekend
        monday = next_weekday(now, 1)
        target = monday.replace(hour=2, minute=0, second=0, microsecond=0)
        return f"morning prep {fmt(target)}"

def hbar(cur, thr, w=8):
    r = min(float(cur) / float(thr), 1.0) if thr and float(thr) > 0 else 0
    f = int(r * w)
    c = R if r >= 1 else (Y if r >= 0.75 else G)
    return f"[{c}]{'#' * f}[/][dim]{'.' * (w - f)}[/]"

def exp_bar(pct, w=10):
    f = int(min(float(pct or 0), 100) / 100 * w)
    return "#" * f + "." * (w - f)


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
                "max_open_positions", "min_score_threshold"]
        rows = q(c, "SELECT key, value FROM algo_config WHERE key=ANY(%s)", (keys,))
        d = {r["key"]: r["value"] for r in rows}
        return {
            "enabled":     d.get("enable_algo", "true").lower() == "true",
            "mode":        d.get("execution_mode", "unknown").upper(),
            "max_pos_pct": d.get("max_position_size_pct"),
            "max_pos_n":   d.get("max_open_positions"),
            "min_score":   d.get("min_score_threshold"),
        }
    except Exception as e:
        return {"_error": str(e)}

def fetch_market(c):
    try:
        exp   = q1(c, "SELECT exposure_pct, halt_reasons FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
        h     = q1(c, "SELECT market_stage, vix_level, distribution_days_4w FROM market_health_daily ORDER BY date DESC LIMIT 1")
        pct   = float(exp["exposure_pct"] or 0) if exp else None
        halts = exp.get("halt_reasons") or [] if exp else []
        if isinstance(halts, str):
            try: halts = json.loads(halts)
            except: halts = [halts] if halts else []
        vix_v = h.get("vix_level") if h else None
        return {
            "pct":   pct,
            "tier":  tier_from_pct(pct),
            "halts": halts,
            "vix":   float(vix_v) if (vix_v is not None and float(vix_v) > 0) else None,
            "dist":  h.get("distribution_days_4w") if h else None,
            "stage": h.get("market_stage") if h else None,
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
        snaps = q(c, "SELECT daily_return_pct, total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date ASC")
        sharpe = None
        maxdd  = 0.0
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
        win_amt  = [float(t.get("profit_loss_dollars") or 0) for t in wins]
        loss_amt = [abs(float(t.get("profit_loss_dollars") or 0)) for t in losses]
        avg_win  = statistics.mean(win_amt)  if win_amt  else 0.0
        avg_loss = statistics.mean(loss_amt) if loss_amt else 0.0
        gross_wins  = sum(win_amt)
        gross_losses = sum(loss_amt)
        pf = round(gross_wins / gross_losses, 2) if gross_losses > 0 else None
        lr = 1 - wr / 100
        expectancy = round(wr / 100 * avg_win - lr * avg_loss, 2) if trades else 0.0
        avg_r = []
        for t in trades:
            rv = t.get("exit_r_multiple")
            if rv is not None:
                try: avg_r.append(float(rv))
                except: pass
        avg_r_val = round(statistics.mean(avg_r), 2) if avg_r else None
        return {"n": len(trades), "w": len(wins), "l": len(losses),
                "wr": round(wr, 1), "pnl": round(pnl, 2), "streak": streak,
                "sharpe": sharpe, "maxdd": round(maxdd, 1),
                "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
                "profit_factor": pf, "expectancy": expectancy, "avg_r": avg_r_val}
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
            )
            SELECT p.symbol, p.avg_entry_price, p.current_price,
                   p.unrealized_pnl_pct, p.position_value, p.days_since_entry,
                   lt.stop_loss_price, lt.target_1_price,
                   ltt.weinstein_stage, cp.sector
            FROM algo_positions p
            LEFT JOIN lt  ON lt.symbol  = p.symbol
            LEFT JOIN ltt ON ltt.symbol = p.symbol
            LEFT JOIN company_profile cp ON cp.ticker = p.symbol
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
            SELECT COUNT(*) AS n, MAX(date) AS d
            FROM buy_sell_daily
            WHERE signal='BUY'
              AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY')""")
        total_r = q1(c, "SELECT COUNT(*) AS n FROM buy_sell_daily WHERE date=(SELECT MAX(date) FROM buy_sell_daily)")
        total_n = int(total_r["n"] or 0) if total_r else 0
        top = q(c, """
            SELECT s.symbol, s.score, cp.sector
            FROM swing_trader_scores s
            LEFT JOIN company_profile cp ON cp.ticker = s.symbol
            WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
            ORDER BY s.score DESC LIMIT 12""")
        # Score grade distribution across full universe
        grades_r = q(c, """
            SELECT
              COUNT(*) FILTER (WHERE score >= 80) AS a,
              COUNT(*) FILTER (WHERE score >= 60 AND score < 80) AS b,
              COUNT(*) FILTER (WHERE score >= 40 AND score < 60) AS c,
              COUNT(*) FILTER (WHERE score < 40) AS d,
              COUNT(*) AS total
            FROM swing_trader_scores
            WHERE date=(SELECT MAX(date) FROM swing_trader_scores)""")
        grades = grades_r[0] if grades_r else {}
        # Near-threshold watchlist (score 55-69, just below or just above min threshold ~60)
        near = q(c, """
            SELECT s.symbol, s.score, cp.sector
            FROM swing_trader_scores s
            LEFT JOIN company_profile cp ON cp.ticker = s.symbol
            WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
              AND s.score BETWEEN 55 AND 69
            ORDER BY s.score DESC LIMIT 8""")
        return {"n": int(sig["n"] or 0) if sig else 0,
                "total": total_n,
                "date": sig["d"] if sig else None,
                "top": top,
                "pass": [s for s in top if float(s.get("score") or 0) >= 60],
                "grades": grades,
                "near": near}
    except Exception as e:
        return {"_error": str(e)}

def fetch_sector_ranking(c):
    try:
        return q(c, """
            SELECT sector_name, current_rank, momentum_score, rank_1w_ago, rank_4w_ago, stock_count
            FROM sector_ranking
            WHERE date=(SELECT MAX(date) FROM sector_ranking)
            ORDER BY current_rank ASC""")
    except Exception as e:
        return {"_error": str(e)}

def fetch_activity(c):
    """Get last run activity detail from audit log: what actually happened."""
    try:
        latest = q1(c, """
            SELECT details->>'run_id' AS run_id FROM algo_audit_log
            WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"):
            return {}
        rid = latest["run_id"]
        phases = q(c, """
            SELECT action_type, status, details, created_at
            FROM algo_audit_log WHERE details->>'run_id'=%s ORDER BY created_at ASC""", (rid,))
        # Pull last 10 trade actions (entries + exits) regardless of run
        recent_actions = q(c, """
            SELECT action_type, status, details, created_at
            FROM algo_audit_log
            WHERE action_type IN ('entry_executed','exit_executed','entry_rejected',
                                  'position_exited','order_placed','order_rejected')
            ORDER BY created_at DESC LIMIT 10""")
        # Count by type across last run
        counts = {}
        for p in phases:
            at = p.get("action_type", "")
            counts[at] = counts.get(at, 0) + 1
        return {"run_id": rid, "phases": phases, "counts": counts, "recent_actions": recent_actions}
    except Exception as e:
        return {"_error": str(e)}

def fetch_health(c):
    try:
        return q(c, """
            SELECT tbl, role, latest, age,
                   CASE WHEN age IS NULL OR age > stale THEN 'stale' ELSE 'ok' END AS st
            FROM (
              SELECT 'price_daily'     tbl,'CRIT' role, MAX(date)::date latest, (CURRENT_DATE-MAX(date)::date) age, 3  stale FROM price_daily      UNION ALL
              SELECT 'buy_sell_daily', 'CRIT',          MAX(date)::date,        (CURRENT_DATE-MAX(date)::date),      3         FROM buy_sell_daily  UNION ALL
              SELECT 'swing_scores',   'CRIT',          MAX(date)::date,        (CURRENT_DATE-MAX(date)::date),      3         FROM swing_trader_scores UNION ALL
              SELECT 'technicals',     'IMP',           MAX(date)::date,        (CURRENT_DATE-MAX(date)::date),      3         FROM technical_data_daily UNION ALL
              SELECT 'market_health',  'IMP',           MAX(date)::date,        (CURRENT_DATE-MAX(date)::date),      7         FROM market_health_daily UNION ALL
              SELECT 'trend_template', 'IMP',           MAX(date)::date,        (CURRENT_DATE-MAX(date)::date),      7         FROM trend_template_data UNION ALL
              SELECT 'sector_ranking', 'SUPP',          MAX(date)::date,        (CURRENT_DATE-MAX(date)::date),      14        FROM sector_ranking UNION ALL
              SELECT 'economic_data',  'SUPP',          MAX(date)::date,        (CURRENT_DATE-MAX(date)::date),      14        FROM economic_data
            ) s ORDER BY CASE role WHEN 'CRIT' THEN 1 WHEN 'IMP' THEN 2 ELSE 3 END, tbl""")
    except:
        return []

def fetch_circuit(c):
    try:
        cfg = {r["key"]: float(r["value"]) for r in q(c,
            "SELECT key, value FROM algo_config WHERE key=ANY(%s)",
            (["halt_drawdown_pct", "max_daily_loss_pct", "max_consecutive_losses",
              "max_total_risk_pct", "vix_max_threshold", "max_weekly_loss_pct"],))}
        snaps = q(c, "SELECT total_portfolio_value, daily_return_pct FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 30")
        lat   = snaps[0] if snaps else {}
        pk    = max((float(s.get("total_portfolio_value") or 0) for s in snaps), default=0)
        cur   = float(lat.get("total_portfolio_value") or 0)
        dd    = (pk - cur) / pk * 100 if pk > 0 else 0
        dl    = max(0.0, -float(lat.get("daily_return_pct") or 0))
        wl    = max(0.0, -sum(float(s.get("daily_return_pct") or 0) for s in snaps[:5]))
        trades = q(c, "SELECT profit_loss_dollars FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL ORDER BY exit_date DESC LIMIT 20")
        consec = 0
        for t in trades:
            if float(t.get("profit_loss_dollars") or 0) < 0: consec += 1
            else: break
        h     = q1(c, "SELECT vix_level, market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1")
        vix_v = h.get("vix_level") if h else None
        vix   = float(vix_v) if (vix_v is not None and float(vix_v) > 0) else 0.0
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
            {"lbl": "Drawdown",  "cur": round(dd, 1),    "thr": th("halt_drawdown_pct", 20),    "u": "%"},
            {"lbl": "Daily",     "cur": round(dl, 1),    "thr": th("max_daily_loss_pct", 2),    "u": "%"},
            {"lbl": "Weekly",    "cur": round(wl, 1),    "thr": th("max_weekly_loss_pct", 5),   "u": "%"},
            {"lbl": "CnsLoss",   "cur": consec,           "thr": th("max_consecutive_losses", 3),"u": ""},
            {"lbl": "TotalRisk", "cur": round(rp, 1),    "thr": th("max_total_risk_pct", 4),    "u": "%"},
            {"lbl": "VIX",       "cur": round(vix, 1),   "thr": th("vix_max_threshold", 35),    "u": ""},
            {"lbl": "Stage",     "cur": stage,            "thr": 4,                               "u": ""},
        ]
        for b in bs: b["fired"] = float(b["cur"]) >= float(b["thr"])
        return {"bs": bs, "any": any(b["fired"] for b in bs), "n": sum(1 for b in bs if b["fired"])}
    except Exception as e:
        return {"_error": str(e)}


# ── parallel loader ───────────────────────────────────────────────────────────

FETCHERS = {
    "run": fetch_run, "cfg": fetch_algo_config, "mkt": fetch_market,
    "port": fetch_portfolio, "perf": fetch_perf, "pos": fetch_positions,
    "trades": fetch_recent_trades, "sig": fetch_signals,
    "health": fetch_health, "cb": fetch_circuit,
    "srank": fetch_sector_ranking, "activity": fetch_activity,
}

def load_all():
    out = {}
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

def panel_orch(run, cfg):
    next_run  = next_run_str()
    mode      = cfg.get("mode", "?")
    mc2       = G if mode == "LIVE" else Y
    en        = "ENABLED" if cfg.get("enabled", True) else "DISABLED"
    ec        = G if cfg.get("enabled", True) else R
    max_n     = cfg.get("max_pos_n")
    min_score = cfg.get("min_score")
    score_s   = f"  score≥[white]{min_score}[/]" if min_score else ""
    slots_s   = f"  max [white]{max_n}[/] pos" if max_n else ""

    if not run or run.get("_error"):
        body = Text.from_markup(
            f"[dim]no run data[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]{score_s}{slots_s}\n"
            f"[dim]Next: {next_run}[/]\n[dim]—[/]"
        )
    else:
        age  = fmt_age(run.get("run_at"))
        sts  = ("[bold bright_green]✔ COMPLETED[/]" if run.get("success") and not run.get("halted")
                else ("[bold yellow]~ HALTED[/]" if run.get("halted")
                else "[bold bright_red]✗ ERROR[/]"))
        rid  = str(run.get("run_id") or "")[:22]
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
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]{score_s}{slots_s}\n"
            f"[dim]{rid}[/]\n"
            f"[dim]Next:[/] [white]{next_run}[/]  {phases_str}"
        )
    return Panel(body, title="[bold]ORCHESTRATOR[/]", border_style="blue", padding=(0, 1))


def panel_market(mkt):
    if not mkt or mkt.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]MARKET[/]", border_style="blue", padding=(0, 1))
    tier  = mkt.get("tier", "unknown")
    tc    = TIER_COLOR.get(tier, "dim")
    label = tier.replace("_", " ").upper()
    exp   = mkt.get("pct")
    exp_s = f"{float(exp):.0f}" if exp is not None else "--"
    bar   = exp_bar(exp or 0)
    vix   = f"{mkt['vix']:.1f}" if mkt.get("vix") is not None else "--"
    dist  = str(mkt.get("dist") or "--")
    stage = str(mkt.get("stage") or "--")
    halts = mkt.get("halts") or []
    halt_s = "  ".join(str(h) for h in halts) if halts else "none"
    hc    = Y if halts else DIM
    txt   = Text.from_markup(
        f"[{tc}][bold]{label}[/bold][/]\n"
        f"[{tc}]{exp_s}%  {bar}[/]\n"
        f"VIX:[bold white]{vix}[/]  Dist:[bold white]{dist}[/]  Stage:[bold white]{stage}[/]\n"
        f"[dim]Halts:[/]  [{hc}]{halt_s}[/]"
    )
    return Panel(txt, title="[bold]MARKET[/]", border_style="blue", padding=(0, 1))


def panel_circuit(cb):
    if not cb or cb.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]CIRCUIT BREAKERS[/]", border_style="blue", padding=(0, 1))
    n_f   = cb.get("n", 0)
    any_f = cb.get("any", False)
    hc    = R if any_f else G
    hs    = f"[!] {n_f} BREAKER{'S' if n_f != 1 else ''} FIRED" if any_f else "[+] ALL CLEAR"
    # Build 2-column grid for breakers to save vertical space
    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)
    bs = cb.get("bs", [])
    pairs = list(zip(bs[::2], bs[1::2] + [None]))
    for a, b in pairs:
        def fmt_b(br):
            if br is None: return ""
            fc  = R if br["fired"] else (Y if float(br["thr"]) > 0 and float(br["cur"]) / float(br["thr"]) >= 0.75 else G)
            ind = " [bold red]![/]" if br["fired"] else ""
            return f"[{fc}]{br['lbl']}: {br['cur']}{br['u']}/{br['thr']:.0f}{br['u']}[/] {hbar(br['cur'], br['thr'], w=5)}{ind}"
        tbl.add_row(Text.from_markup(fmt_b(a)), Text.from_markup(fmt_b(b)))
    content = Group(Text.from_markup(f"[{hc}][bold]{hs}[/bold][/]"), tbl)
    return Panel(content, title="[bold]CIRCUIT BREAKERS[/]", border_style="blue", padding=(0, 1))


def panel_portfolio(port, cfg):
    if not port or port.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]PORTFOLIO[/]", border_style="green", padding=(0, 1))
    pv   = float(port.get("total_portfolio_value") or 0)
    dr   = float(port.get("daily_return_pct") or 0)
    urp  = float(port.get("unrealized_pnl_pct") or 0)
    cash = float(port.get("total_cash") or 0)
    npos = int(port.get("position_count") or 0)
    max_n = int(cfg.get("max_pos_n") or 0) if cfg else 0
    pct   = float(cfg.get("max_pos_pct") or 0) if cfg else 0
    bp    = pv * pct / 100 if (pv and pct) else cash
    slots = max_n - npos if max_n else None
    slots_s = f"  Slots: [white]{slots}[/] open" if slots is not None else ""
    txt  = Text.from_markup(
        f"[bold white]{fmt_money(pv)}[/]\n"
        f"Cash: [white]{fmt_money(cash)}[/]  Positions: [white]{npos}[/]{slots_s}\n"
        f"Today:      [{G if dr  >= 0 else R}]{'+' if dr  >= 0 else ''}{dr:.2f}%[/]\n"
        f"Unrealized: [{G if urp >= 0 else R}]{'+' if urp >= 0 else ''}{urp:.2f}%[/]  "
        f"[dim]Buying power:[/] [white]{fmt_money(bp)}[/]"
    )
    return Panel(txt, title="[bold]PORTFOLIO[/]", border_style="green", padding=(0, 1))


def panel_performance(perf, rec):
    if not perf:
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
        f"Trades: [white]{perf.get('n', 0)}[/]  "
        f"([{G}]{perf.get('w', 0)}W[/] / [{R}]{perf.get('l', 0)}L[/])\n"
        f"Win Rate: [{G if (perf.get('wr') or 0) >= 50 else R}]{perf.get('wr', '--')}%[/]  "
        f"Streak: [{str_c}]{str_s}[/]\n"
        f"P&L: [{pnl_c}]{fmt_money(perf.get('pnl'))}[/]  "
        f"MaxDD: [white]{perf.get('maxdd', '--')}%[/]\n"
        f"PF: [{pf_c}]{pf_s}[/]  "
        f"Expect: [{exp_c}]{fmt_money(exp)}[/]  "
        f"Sharpe: [white]{perf.get('sharpe') or '--'}[/]\n"
        f"Avg R: [white]{avg_r_s}[/]  "
        f"Avg W: [{G}]{fmt_money(perf.get('avg_win'))}[/]  "
        f"Avg L: [{R}]{fmt_money(perf.get('avg_loss'))}[/]"
    )]
    closed = [t for t in rec if t.get("status") == "closed"][:3]
    if closed:
        rows.append(Text("Recent exits:", style="dim"))
        for t in closed:
            pnl = float(t.get("profit_loss_dollars") or 0)
            pct = float(t.get("profit_loss_pct") or 0)
            rv  = float(t.get("exit_r_multiple") or 0)
            c   = G if pnl >= 0 else R
            p   = "+" if pnl >= 0 else ""
            dt  = str(t.get("exit_date", "") or t.get("trade_date", ""))[:10]
            rows.append(Text.from_markup(
                f"  [{c}]{t.get('symbol')} {p}{pct:.1f}% / {p}{rv:.1f}R  {dt}[/]"
            ))
    return Panel(Group(*rows), title="[bold]PERFORMANCE[/]", border_style="green", padding=(0, 1))


def panel_positions(pos, compact=False):
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
        t.add_column("Sector", style="dim",     no_wrap=True, max_width=13)
    for p in pos:
        entry = float(p.get("avg_entry_price") or 0)
        price = float(p.get("current_price")   or 0)
        stop  = float(p.get("stop_loss_price") or 0) if p.get("stop_loss_price") else None
        t1    = float(p.get("target_1_price")  or 0) if p.get("target_1_price")  else None
        pnl   = float(p.get("unrealized_pnl_pct") or 0)
        days  = p.get("days_since_entry") or "--"
        stg   = p.get("weinstein_stage")
        sec   = (p.get("sector") or "--")[:13]
        rmul  = (price - entry) / (entry - stop)    if (stop and entry > stop)  else None
        dist  = (price - stop)  / price * 100         if (stop and price)         else None
        t1pct = (t1 - price)    / price * 100          if (t1 and price)          else None
        pc    = G if pnl >= 0  else R
        rc    = G if (rmul or 0) >= 0 else R
        dc    = R if (dist or 99) < 3 else (Y if (dist or 99) < 5 else "white")
        row = [
            p.get("symbol") or "--",
            f"${entry:.2f}",
            f"${price:.2f}",
            Text(f"{'+' if pnl >= 0 else ''}{pnl:.2f}%", style=pc),
            Text(f"{'+' if (rmul or 0) >= 0 else ''}{rmul:.2f}R" if rmul is not None else "--", style=rc),
            f"${stop:.2f}" if stop else "--",
            Text(f"{dist:.1f}%" if dist is not None else "--", style=dc),
        ]
        if not compact:
            row += [
                f"+{t1pct:.1f}%" if t1pct is not None else "--",
                str(days),
                f"S{stg}" if stg else "--",
                sec,
            ]
        t.add_row(*row)
    return Panel(t, title=f"[bold]POSITIONS ({len(pos)})[/]", border_style="cyan", padding=(0, 0))


def panel_signals(sig):
    if not sig or sig.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]SIGNALS & BREADTH[/]", border_style="magenta", padding=(0, 1))
    raw    = sig.get("n", 0)
    total  = sig.get("total", 0)
    passed = sig.get("pass", [])
    top    = sig.get("top", [])
    d      = sig.get("date")
    ds     = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    pct_s  = f"{raw / total * 100:.1f}%" if total > 0 else "--"
    g_data = sig.get("grades") or {}
    ga_n   = int(g_data.get("a") or 0)
    gb_n   = int(g_data.get("b") or 0)
    gc_n   = int(g_data.get("c") or 0)
    gd_n   = int(g_data.get("d") or 0)
    gt_n   = int(g_data.get("total") or 1)
    near   = sig.get("near") or []

    rows = [
        Text.from_markup(
            f"[dim]{ds}[/]  [white]{raw}[/][dim] BUY signals / {total} universe ({pct_s})[/]\n"
            f"[dim]Breadth:[/]  "
            f"[{G}]A:{ga_n}[/]  [{CY}]B:{gb_n}[/]  [yellow]C:{gc_n}[/]  [{R}]D:{gd_n}[/]  [dim]/{gt_n}[/]"
        ),
        Rule(style="dim"),
    ]

    # Top scorers in 2-column pairs
    rows.append(Text("[dim]Top scores:[/]"))
    pairs = list(zip(top[::2], top[1::2] + [None]))
    for a, b in pairs:
        sa   = float(a.get("score") or 0)
        ga   = grade(sa)
        ca   = G if sa >= 80 else CY
        left = f"[{ca}]{ga} {a['symbol']:<5} {sa:.0f}[/]"
        if b:
            sb    = float(b.get("score") or 0)
            gb    = grade(sb)
            cb2   = G if sb >= 80 else CY
            right = f"[{cb2}]{gb} {b['symbol']:<5} {sb:.0f}[/]"
            rows.append(Text.from_markup(f"  {left}   {right}"))
        else:
            rows.append(Text.from_markup(f"  {left}"))

    # Near-threshold watchlist
    if near:
        rows.append(Rule(style="dim"))
        rows.append(Text("[dim]Watchlist (near threshold):[/]"))
        npairs = list(zip(near[::2], near[1::2] + [None]))
        for a, b in npairs:
            sa   = float(a.get("score") or 0)
            left = f"[yellow]{a['symbol']:<5} {sa:.0f}[/]"
            if b:
                sb    = float(b.get("score") or 0)
                right = f"[yellow]{b['symbol']:<5} {sb:.0f}[/]"
                rows.append(Text.from_markup(f"  {left}   {right}"))
            else:
                rows.append(Text.from_markup(f"  {left}"))

    return Panel(Group(*rows), title="[bold]SIGNALS & BREADTH[/]", border_style="magenta", padding=(0, 1))


def panel_health(hlth):
    if not hlth:
        return Panel(Text("no data", style="dim"), title="[bold]DATA HEALTH[/]", border_style="yellow", padding=(0, 1))
    rows = []
    for r in hlth:
        ok   = r.get("st") == "ok"
        age  = r.get("age")
        c    = G if ok else R
        icon = "[+]" if ok else "[!]"
        nm   = (r.get("tbl") or "--")
        role = r.get("role", "")
        rc   = "dim" if role == "SUPP" else ("white" if role == "IMP" else "bold white")
        rows.append(Text.from_markup(
            f"[{c}]{icon}[/]  [{rc}]{nm:<18}[/]  [dim]{age}d old[/]"
        ))
    return Panel(Group(*rows), title="[bold]DATA HEALTH[/]", border_style="yellow", padding=(0, 1))


def panel_sector(pos, port):
    if not pos:
        return Panel(Text("no positions", style="dim"), title="[bold]SECTOR EXPOSURE[/]", border_style="bright_blue", padding=(0, 1))
    pv = float(port.get("total_portfolio_value") or 0)
    sd = {}
    for p in pos:
        sec = (p.get("sector") or "Unknown")
        val = float(p.get("position_value") or 0)
        pnl = float(p.get("unrealized_pnl_pct") or 0)
        if sec not in sd:
            sd[sec] = {"val": 0, "n": 0, "pnls": []}
        sd[sec]["val"] += val
        sd[sec]["n"] += 1
        sd[sec]["pnls"].append(pnl)
    rows = []
    for sec, d in sorted(sd.items(), key=lambda x: -x[1]["val"]):
        pct     = d["val"] / pv * 100 if pv else 0
        avg_pnl = sum(d["pnls"]) / len(d["pnls"]) if d["pnls"] else 0
        pc      = G if avg_pnl >= 0 else R
        bar_f   = int(min(pct, 30) / 30 * 8)
        bar     = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (8 - bar_f)}[/]"
        rows.append(Text.from_markup(
            f"[white]{sec[:14]:<14}[/]  {bar}  "
            f"[dim]{d['n']}p  {pct:.0f}%[/]  "
            f"[{pc}]{'+' if avg_pnl >= 0 else ''}{avg_pnl:.1f}%[/]"
        ))
    return Panel(Group(*rows), title="[bold]SECTOR EXPOSURE[/]", border_style="bright_blue", padding=(0, 1))


def panel_sector_ranking(srank):
    if not srank or (isinstance(srank, dict) and srank.get("_error")):
        return Panel(Text("no data", style="dim"), title="[bold]SECTOR RANKING[/]", border_style="cyan", padding=(0, 1))
    rows = []
    total = len(srank)
    mid   = total // 2
    # Top half = leaders, bottom = laggards
    leaders  = srank[:5]
    laggards = srank[-5:][::-1]
    def rank_delta(r):
        cur = r.get("current_rank")
        old = r.get("rank_1w_ago")
        if cur is None or old is None: return ""
        d = int(old) - int(cur)
        if d > 0:  return f"[{G}]▲{d}[/]"
        if d < 0:  return f"[{R}]▼{abs(d)}[/]"
        return "[dim]=[/]"
    rows.append(Text.from_markup(f"[{G}][bold]Leaders[/][/]  [dim]{total} sectors total[/]"))
    for r in leaders:
        sc  = r.get("current_rank")
        nm  = (r.get("sector_name") or "--")[:20]
        ms  = float(r.get("momentum_score") or 0)
        dlt = rank_delta(r)
        rows.append(Text.from_markup(
            f"  [{G}]#{sc:<2}[/]  [white]{nm:<20}[/]  [{CY}]{ms:.1f}[/]  {dlt}"
        ))
    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[{R}][bold]Laggards[/][/]"))
    for r in laggards:
        sc  = r.get("current_rank")
        nm  = (r.get("sector_name") or "--")[:20]
        ms  = float(r.get("momentum_score") or 0)
        dlt = rank_delta(r)
        rows.append(Text.from_markup(
            f"  [{R}]#{sc:<2}[/]  [dim]{nm:<20}[/]  [dim]{ms:.1f}[/]  {dlt}"
        ))
    return Panel(Group(*rows), title="[bold]SECTOR RANKING[/]", border_style="cyan", padding=(0, 1))


def panel_activity(act, run):
    """Show what happened in the last orchestrator run from audit log."""
    if not act or act.get("_error"):
        return Panel(Text("no data", style="dim"), title="[bold]ALGO ACTIVITY[/]", border_style="blue", padding=(0, 1))
    rid    = (act.get("run_id") or "")[:28]
    phases = act.get("phases") or []
    recent = act.get("recent_actions") or []
    rows   = []

    # Phase summary from last run
    if phases:
        rows.append(Text.from_markup(f"[dim]Run:[/] [white]{rid}[/]"))
        for p in phases:
            at  = p.get("action_type", "")
            if not at.startswith("phase_"): continue
            parts = at.split("_")
            num   = parts[1] if len(parts) > 1 else "?"
            name  = " ".join(parts[2:]).replace("_", " ") if len(parts) > 2 else at
            st    = p.get("status", "")
            sc    = G if st == "success" else (Y if st in ("halt", "warn", "halted") else R)
            si    = "+" if st == "success" else ("~" if st in ("halt", "warn", "halted") else "!")
            rows.append(Text.from_markup(
                f"  [{sc}]{si} P{num} {name[:28]}[/]"
            ))

    # Recent trade actions (entry/exit events)
    trade_actions = [a for a in recent if a.get("action_type") in
                     ("entry_executed", "exit_executed", "entry_rejected",
                      "position_exited", "order_placed", "order_rejected")]
    if trade_actions:
        rows.append(Rule(style="dim"))
        rows.append(Text("[dim]Recent actions:[/]"))
        for a in trade_actions[:6]:
            at = a.get("action_type", "")
            det = a.get("details") or {}
            if isinstance(det, str):
                try: det = json.loads(det)
                except: det = {}
            sym = det.get("symbol", "")
            ic  = G if "executed" in at or "placed" in at else R
            label = at.replace("_", " ").title()[:22]
            sym_s = f" {sym}" if sym else ""
            rows.append(Text.from_markup(f"  [{ic}]{label}{sym_s}[/]"))

    if not rows:
        rows.append(Text("no recent activity", style="dim"))
    return Panel(Group(*rows), title="[bold]ALGO ACTIVITY[/]", border_style="blue", padding=(0, 1))


def mascot_sidebar(data, frame, secs_to_refresh=None):
    """Fixed right-column mascot widget — goes in Layout sidebar."""
    fi   = mascot_pose(data, frame)
    mc   = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    cb   = data.get("cb") or {}
    mkt  = data.get("mkt") or {}
    tier = mkt.get("tier", "unknown")
    tier_lbl = tier.replace("_", " ").upper() if tier != "unknown" else ""
    tier_c   = TIER_COLOR.get(tier, "dim")

    lines = Text.from_markup(
        f"\n[bold {mc}]{pose[0]}[/]\n"
        f"[bold {mc}]{pose[1]}[/]\n"
        f"[bold {mc}]{pose[2]}[/]\n\n"
        f"[{tier_c}]{tier_lbl}[/]\n"
    )
    if secs_to_refresh is not None:
        lines = Text.from_markup(
            f"\n[bold {mc}]{pose[0]}[/]\n"
            f"[bold {mc}]{pose[1]}[/]\n"
            f"[bold {mc}]{pose[2]}[/]\n\n"
            f"[{tier_c}]{tier_lbl}[/]\n\n"
            f"[dim]refresh\n  in {secs_to_refresh}s[/]"
        )
    if cb.get("any"):
        fire_label = f"\n[bold bright_red]⚠ {cb.get('n', 0)} BREAKER[/]"
        lines = Text.from_markup(str(lines) + fire_label) if False else Text.from_markup(
            f"\n[bold {mc}]{pose[0]}[/]\n"
            f"[bold {mc}]{pose[1]}[/]\n"
            f"[bold {mc}]{pose[2]}[/]\n\n"
            f"[bold bright_red]⚠ CB FIRED[/]\n"
            + (f"[dim]refresh\n  in {secs_to_refresh}s[/]" if secs_to_refresh is not None else "")
        )
    return Panel(
        Align(lines, align="center"),
        title="[bold white]ALGO[/]",
        border_style=mc,
        padding=(0, 0),
    )


# ── loading screen (shown while queries run) ──────────────────────────────────

def loading_screen(frame):
    fi    = frame % len(MASCOT_FRAMES)
    mc    = MASCOT_COLORS[fi]
    pose  = MASCOT_FRAMES[fi]
    dots  = "." * (frame % 4)
    inner = Text.from_markup(
        f"\n[bold {mc}]{pose[0]}[/]\n"
        f"[bold {mc}]{pose[1]}[/]\n"
        f"[bold {mc}]{pose[2]}[/]\n\n"
        f"[dim]Loading{dots}[/]"
    )
    return Align(
        Panel(Align(inner, align="center"),
              title="[bold white]ALGO OPS DASHBOARD[/]",
              border_style="blue",
              width=40),
        align="center",
        vertical="middle",
    )


# ── full dashboard ────────────────────────────────────────────────────────────

def _main_content(data, compact, elapsed, frame):
    """Build the main content Group (all panels except sidebar mascot)."""
    run   = data.get("run")   or {}
    cfg   = data.get("cfg")   or {}
    mkt   = data.get("mkt")   or {}
    port  = data.get("port")  or {}
    perf  = data.get("perf")  or {}
    pos   = data.get("pos")   or []
    sig   = data.get("sig")   or {}
    hlth  = data.get("health") or []
    cb    = data.get("cb")    or {}
    rec   = data.get("trades") or []

    now_et = datetime.now(ET)
    mkt_s  = "[bold bright_green]MARKET OPEN[/]" if is_open() else "[dim]MARKET CLOSED[/]"
    ts     = now_et.strftime("%a %b %d  %I:%M %p ET")

    srank = data.get("srank") or []
    act   = data.get("activity") or {}

    return Group(
        Rule(
            f"[bold white]ALGO OPS DASHBOARD[/]  {mkt_s}  [dim]{ts}[/]  [dim]loaded {elapsed:.1f}s[/]",
            style="blue",
        ),
        # Row 1: system status
        Columns([panel_orch(run, cfg), panel_market(mkt), panel_circuit(cb)],
                equal=True, expand=True),
        # Row 2: portfolio metrics
        Columns([panel_portfolio(port, cfg), panel_performance(perf, rec), panel_sector(pos, port)],
                equal=True, expand=True),
        # Row 3: all open positions
        panel_positions(pos, compact),
        # Row 4: signals/breadth | sector ranking
        Columns([panel_signals(sig), panel_sector_ranking(srank)],
                equal=True, expand=True),
        # Row 5: activity log | data health
        Columns([panel_activity(act, run), panel_health(hlth)],
                equal=True, expand=True),
    )


def render_dashboard(data, compact=False, elapsed=0.0, frame=0,
                     watch_interval=None, last_load_time=None):
    """Return a Layout (watch mode) or Group (one-shot) renderable."""
    mkt = data.get("mkt") or {}
    cb  = data.get("cb")  or {}

    secs = None
    if watch_interval is not None and last_load_time is not None:
        secs = max(0, watch_interval - int(time.monotonic() - last_load_time))

    main    = _main_content(data, compact, elapsed, frame)
    sidebar = mascot_sidebar({"cb": cb, "mkt": mkt}, frame, secs_to_refresh=secs)

    layout = Layout()
    layout.split_row(
        Layout(name="main",    ratio=1),
        Layout(name="sidebar", size=16),
    )
    layout["main"].update(main)
    layout["sidebar"].update(sidebar)
    return layout


# ── run modes ─────────────────────────────────────────────────────────────────

def run_once(compact):
    """Load with animated mascot, then print static dashboard."""
    result  = [None]
    elapsed = [0.0]
    done    = threading.Event()

    def bg():
        t0 = time.monotonic()
        result[0] = load_all()
        elapsed[0] = time.monotonic() - t0
        done.set()

    t = threading.Thread(target=bg, daemon=True)
    t.start()

    frame = 0
    with Live(loading_screen(frame), console=CONSOLE, refresh_per_second=8,
              transient=True) as live:
        while not done.is_set():
            frame += 1
            live.update(loading_screen(frame))
            time.sleep(0.125)

    CONSOLE.clear()
    # One-shot: print main content without Layout (no full-screen takeover)
    data = result[0]
    mkt  = data.get("mkt") or {}
    cb   = data.get("cb")  or {}
    CONSOLE.print(_main_content(data, compact=compact, elapsed=elapsed[0], frame=frame))
    CONSOLE.print(Text.from_markup(f"  [dim]loaded in {elapsed[0]:.1f}s[/]"))


def run_watch(interval, compact):
    """Watch mode: anti-flicker Layout at 2fps, data reload every `interval` seconds."""
    result    = [None]
    elapsed   = [0.0]
    loading   = [True]
    last_load = [0.0]
    frame     = [0]

    def reload():
        loading[0] = True
        t0 = time.monotonic()
        result[0] = load_all()
        elapsed[0] = time.monotonic() - t0
        last_load[0] = time.monotonic()
        loading[0] = False

    # Initial load in background
    threading.Thread(target=reload, daemon=True).start()

    with Live(console=CONSOLE, refresh_per_second=2, screen=True) as live:
        try:
            while True:
                frame[0] += 1
                if loading[0] or result[0] is None:
                    live.update(loading_screen(frame[0]))
                else:
                    live.update(render_dashboard(
                        result[0],
                        compact=compact,
                        elapsed=elapsed[0],
                        frame=frame[0],
                        watch_interval=interval,
                        last_load_time=last_load[0],
                    ))
                    if not loading[0] and (time.monotonic() - last_load[0]) >= interval:
                        threading.Thread(target=reload, daemon=True).start()

                time.sleep(0.5)
        except KeyboardInterrupt:
            pass


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    pa = argparse.ArgumentParser(
        description="Algo ops terminal dashboard",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pa.add_argument("-w", "--watch",   nargs="?", const=30, type=int, metavar="SECS",
                    help="Watch mode, auto-refresh interval (default 30s)")
    pa.add_argument("--compact", "-c", action="store_true",
                    help="Omit T1 target and Sector columns from positions table")
    args = pa.parse_args()

    if args.watch is not None:
        run_watch(max(10, args.watch), args.compact)
    else:
        run_once(args.compact)


if __name__ == "__main__":
    main()
