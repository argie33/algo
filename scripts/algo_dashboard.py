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
        return {"n": len(trades), "w": len(wins), "l": len(losses),
                "wr": round(wr, 1), "pnl": round(pnl, 2), "streak": streak,
                "sharpe": sharpe, "maxdd": round(maxdd, 1)}
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
        top = q(c, """
            SELECT s.symbol, s.score, cp.sector
            FROM swing_trader_scores s
            LEFT JOIN company_profile cp ON cp.ticker = s.symbol
            WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
            ORDER BY s.score DESC LIMIT 12""")
        return {"n": int(sig["n"] or 0) if sig else 0,
                "date": sig["d"] if sig else None,
                "top": top,
                "pass": [s for s in top if float(s.get("score") or 0) >= 60]}
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

def panel_orch(run, cfg, data_for_mascot, frame):
    g = Table.grid(padding=(0, 1))
    g.add_column("content", ratio=1)
    g.add_column("mascot", no_wrap=True, justify="right", min_width=7)

    next_run  = next_run_str()
    mode      = cfg.get("mode", "?")
    mc2       = G if mode == "LIVE" else Y
    en        = "ENABLED" if cfg.get("enabled", True) else "DISABLED"
    ec        = G if cfg.get("enabled", True) else R
    max_n     = cfg.get("max_pos_n")
    min_score = cfg.get("min_score")

    if not run or run.get("_error"):
        body = Text.from_markup(
            f"[dim]no run data[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]Next: {next_run}[/]\n"
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
        score_s = f"  min score:[white]{min_score}[/]" if min_score else ""
        slots_s = f"  max pos:[white]{max_n}[/]" if max_n else ""
        body = Text.from_markup(
            f"{sts}  [dim]{age}[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]{score_s}{slots_s}\n"
            f"[dim]{rid}[/]\n"
            f"[dim]Next:[/] [white]{next_run}[/]  {phases_str}"
        )

    fi   = mascot_pose(data_for_mascot, frame)
    mc   = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    mascot_txt = Text.from_markup(
        f"[bold {mc}]{pose[0]}[/]\n[bold {mc}]{pose[1]}[/]\n[bold {mc}]{pose[2]}[/]"
    )
    g.add_row(body, mascot_txt)
    return Panel(g, title="[bold]ORCHESTRATOR[/]", border_style="blue", padding=(0, 1))


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
    rows = [Text.from_markup(
        f"Trades: [white]{perf.get('n', 0)}[/]  ([{G}]{perf.get('w', 0)}W[/] / [{R}]{perf.get('l', 0)}L[/])\n"
        f"Win Rate: [{G if (perf.get('wr') or 0) >= 50 else R}]{perf.get('wr', '--')}%[/]\n"
        f"P&L: [{pnl_c}]{fmt_money(perf.get('pnl'))}[/]  "
        f"MaxDD: [white]{perf.get('maxdd', '--')}%[/]\n"
        f"Sharpe: [white]{perf.get('sharpe') or '--'}[/]  "
        f"Streak: [{str_c}]{str_s}[/]"
    )]
    # Recent trades
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
        return Panel(Text("no data", style="dim"), title="[bold]TOP SIGNALS[/]", border_style="magenta", padding=(0, 1))
    raw    = sig.get("n", 0)
    passed = sig.get("pass", [])
    d      = sig.get("date")
    ds     = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    pct_s  = f"{len(passed) / raw * 100:.1f}%" if raw > 0 else "--"
    rows   = [Text.from_markup(
        f"[dim]{ds}[/]  [white]{raw}[/] [dim]BUY candidates[/]  "
        f"[{G}]{len(passed)}[/] [dim]passed ({pct_s})[/]"
    )]
    pairs = list(zip(passed[::2], passed[1::2] + [None]))
    for a, b in pairs:
        sa   = float(a.get("score") or 0)
        ga   = grade(sa)
        ca   = G if sa >= 80 else CY
        left = f"[{ca}]{ga} {a['symbol']} {sa:.0f}[/]"
        if b:
            sb   = float(b.get("score") or 0)
            gb   = grade(sb)
            cb2  = G if sb >= 80 else CY
            right = f"[{cb2}]{gb} {b['symbol']} {sb:.0f}[/]"
            rows.append(Text.from_markup(f"  {left}   {right}"))
        else:
            rows.append(Text.from_markup(f"  {left}"))
    return Panel(Group(*rows), title="[bold]TOP SIGNALS[/]", border_style="magenta", padding=(0, 1))


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

def render_dashboard(data, compact=False, elapsed=0.0, frame=0):
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

    # Derive mascot pose from actual market/system state
    fi   = mascot_pose({"cb": cb, "mkt": mkt}, frame)
    mc   = MASCOT_COLORS[fi]

    elements = []

    # ── header ──────────────────────────────────────────────────────────
    elements.append(Rule(
        f"[bold white]ALGO OPS DASHBOARD[/]  {mkt_s}  [dim]{ts}[/]  [dim]loaded {elapsed:.1f}s[/]",
        style="blue"
    ))

    # ── row 1: orchestrator | market | circuit breakers ──────────────────
    elements.append(Columns([
        panel_orch(run, cfg, data, frame),
        panel_market(mkt),
        panel_circuit(cb),
    ], equal=True, expand=True))

    # ── row 2: portfolio | performance ───────────────────────────────────
    elements.append(Columns([
        panel_portfolio(port, cfg),
        panel_performance(perf, rec),
    ], equal=True, expand=True))

    # ── row 3: positions (full width) ────────────────────────────────────
    elements.append(panel_positions(pos, compact))

    # ── row 4: signals | data health ─────────────────────────────────────
    elements.append(Columns([
        panel_signals(sig),
        panel_health(hlth),
    ], equal=True, expand=True))

    return Group(*elements)


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
    CONSOLE.print(render_dashboard(result[0], compact=compact, elapsed=elapsed[0], frame=frame))


def run_watch(interval, compact):
    """Continuously animate mascot at 8fps, reload data every `interval` seconds."""
    result  = [None]
    elapsed = [0.0]
    loading = [True]
    last_load = [0.0]
    frame   = [0]

    def reload():
        loading[0] = True
        t0 = time.monotonic()
        result[0] = load_all()
        elapsed[0] = time.monotonic() - t0
        last_load[0] = time.monotonic()
        loading[0] = False

    # Initial load
    t = threading.Thread(target=reload, daemon=True)
    t.start()

    with Live(console=CONSOLE, refresh_per_second=8, screen=False) as live:
        try:
            while True:
                frame[0] += 1
                if loading[0] or result[0] is None:
                    live.update(loading_screen(frame[0]))
                else:
                    now = time.monotonic()
                    secs_left = max(0, interval - int(now - last_load[0]))
                    dash = render_dashboard(result[0], compact=compact,
                                            elapsed=elapsed[0], frame=frame[0])
                    # Append refresh countdown
                    footer = Text.from_markup(
                        f"  [dim]Watch mode  —  next refresh in {secs_left}s  —  Ctrl+C to exit[/]"
                    )
                    live.update(Group(dash, footer))

                    # Trigger background reload when due
                    if not loading[0] and (now - last_load[0]) >= interval:
                        t = threading.Thread(target=reload, daemon=True)
                        t.start()

                time.sleep(0.125)
        except KeyboardInterrupt:
            pass
    CONSOLE.print("\n[dim]stopped[/]")


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
