#!/usr/bin/env python3
"""
Algo Ops Terminal Dashboard  --  single-pane morning brief.

Usage:
  python scripts/algo_dashboard.py            # one-shot
  python scripts/algo_dashboard.py -w         # auto-refresh every 30s
  python scripts/algo_dashboard.py -w 60      # auto-refresh every 60s
  python scripts/algo_dashboard.py --compact  # skip T1/Sector columns
"""

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

# Windows: switch console to UTF-8 so rich can render box/check chars
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
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("pip install rich")

# ── globals ──────────────────────────────────────────────────────
ET = ZoneInfo("America/New_York")
CONSOLE = Console(force_terminal=True, legacy_windows=False, highlight=False)

G  = "bright_green";  R = "bright_red";  Y = "yellow"
CY = "cyan";  DIM = "dim";  W = "bold white"

TIER_COLOR = {
    "confirmed_uptrend": "bright_green",
    "healthy_uptrend":   "green",
    "pressure":          "yellow",
    "caution":           "orange1",
    "correction":        "bright_red",
}

# Breakdancing mascot — cycles through poses in watch mode
MASCOT_FRAMES = [
    r" \o/" + "\n  | " + "\n / \\",   # standing groove
    r"  o/" + "\n /| " + "\n  |\\",   # side lean right
    r" /o\\" + "\n  | " + "\n \\/",   # windmill
    r" \\o_" + "\n /| " + "\n  |\\",  # freeze
    r" / \\" + "\n  | " + "\n \\o/",  # headstand
    r"  o\\" + "\n  |\\" + "\n /  ",  # lean left
]
MASCOT_COLORS = ["bright_cyan","bright_green","bright_yellow","bright_magenta","bright_cyan","green"]

# ── DB ───────────────────────────────────────────────────────────

def get_conn():
    miss = [k for k in ("DB_HOST","DB_USER","DB_PASSWORD","DB_NAME") if not os.environ.get(k)]
    if miss:
        sys.exit(f"Missing env vars: {', '.join(miss)}")
    return psycopg2.connect(
        host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT",5432)),
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
    rows = q(c, sql, p); return rows[0] if rows else None

# ── formatters ───────────────────────────────────────────────────

def fmt_age(ts):
    if ts is None: return "--"
    if isinstance(ts, str): ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:   ts = ts.replace(tzinfo=timezone.utc)
    m = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
    if m < 60:   return f"{m}m ago"
    if m < 1440: return f"{m//60}h{m%60:02d}m ago"
    return f"{m//1440}d ago"

def fmt_money(v):
    if v is None: return "--"
    v = float(v)
    if abs(v)>=1e6: return f"${v/1e6:.2f}M"
    if abs(v)>=1e3: return f"${v:,.0f}"
    return f"${v:.2f}"

def grade(s):
    s = float(s)
    if s>=90: return "A+"
    if s>=80: return "A "
    if s>=70: return "B "
    if s>=60: return "C "
    return "D "

def tier_from_pct(p):
    if p is None: return "unknown"
    p = float(p)
    if p>=80: return "confirmed_uptrend"
    if p>=60: return "healthy_uptrend"
    if p>=40: return "pressure"
    if p>=20: return "caution"
    return "correction"

def is_open():
    n = datetime.now(ET)
    if n.weekday()>=5: return False
    t = n.hour*60+n.minute
    return 570 <= t <= 960

def hbar(cur, thr, w=6):
    r = min(float(cur)/float(thr), 1.0) if thr and float(thr)>0 else 0
    f = int(r*w)
    c = R if r>=1 else (Y if r>=0.75 else G)
    return f"[{c}]{'#'*f}[/][dim]{'.'*(w-f)}[/]"

def exp_bar(pct, w=8):
    f = int(min(float(pct or 0),100)/100*w)
    return "#"*f + "."*(w-f)

# ── fetchers (each returns {} / [] on error) ─────────────────────

def fetch_run(c):
    try:
        latest = q1(c,"""
            SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
            FROM algo_audit_log WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id' ORDER BY MAX(created_at) DESC LIMIT 1""")
        if not latest or not latest.get("run_id"): return {}
        rid = latest["run_id"]
        phases = q(c,"""SELECT action_type,status FROM algo_audit_log
                        WHERE details->>'run_id'=%s ORDER BY created_at ASC""",(rid,))
        halted  = any(p["status"]=="halt"  for p in phases)
        errored = any(p["status"]=="error" for p in phases)
        return {"run_id":rid,"run_at":latest["run_at"],
                "success":bool(phases) and not errored,"halted":halted,"phases":phases}
    except Exception as e: return {"_error":str(e)}

def fetch_algo_config(c):
    try:
        rows = q(c,"SELECT key,value FROM algo_config WHERE key=ANY(%s)",
                 (['enable_algo','execution_mode'],))
        d = {r["key"]:r["value"] for r in rows}
        return {"enabled": d.get("enable_algo","true").lower()=="true",
                "mode":    d.get("execution_mode","unknown").upper()}
    except Exception as e: return {"_error":str(e)}

def fetch_market(c):
    try:
        exp = q1(c,"SELECT exposure_pct,halt_reasons FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
        h   = q1(c,"SELECT market_stage,vix_level,distribution_days_4w FROM market_health_daily ORDER BY date DESC LIMIT 1")
        pct = float(exp["exposure_pct"] or 0) if exp else None
        halts = exp.get("halt_reasons") or [] if exp else []
        if isinstance(halts,str):
            try: halts=json.loads(halts)
            except: halts=[halts] if halts else []
        vix_v = h.get("vix_level") if h else None
        return {"pct":pct,"tier":tier_from_pct(pct),"halts":halts,
                "vix":  float(vix_v) if (vix_v is not None and float(vix_v)>0) else None,
                "dist": h.get("distribution_days_4w") if h else None,
                "stage":h.get("market_stage") if h else None}
    except Exception as e: return {"_error":str(e)}

def fetch_portfolio(c):
    try:
        return dict(q1(c,"""SELECT snapshot_date,total_portfolio_value,daily_return_pct,
                               unrealized_pnl_pct,position_count,total_cash
                           FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1""") or {})
    except Exception as e: return {"_error":str(e)}

def fetch_perf(c):
    try:
        trades = q(c,"""SELECT profit_loss_dollars,exit_r_multiple,profit_loss_pct
                        FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL
                        ORDER BY exit_date ASC""")
        if not trades: return {}
        wins   = [t for t in trades if float(t.get("profit_loss_dollars") or 0)>0]
        losses = [t for t in trades if float(t.get("profit_loss_dollars") or 0)<=0]
        pnl    = sum(float(t.get("profit_loss_dollars") or 0) for t in trades)
        wr     = len(wins)/len(trades)*100 if trades else 0
        streak = 0
        for t in reversed(trades):
            w = float(t.get("profit_loss_dollars") or 0)>0
            if streak>=0 and w:      streak+=1
            elif streak<=0 and not w: streak-=1
            else: break
        snaps = q(c,"""SELECT daily_return_pct,total_portfolio_value
                       FROM algo_portfolio_snapshots ORDER BY snapshot_date ASC""")
        sharpe=None; maxdd=0.0
        if len(snaps)>=10:
            rets=[float(s.get("daily_return_pct") or 0)/100 for s in snaps if s.get("daily_return_pct") is not None]
            if len(rets)>1:
                mn=statistics.mean(rets); sd=statistics.stdev(rets)
                if sd>0: sharpe=round(mn/sd*(252**.5),2)
            pk=0.0
            for s in snaps:
                v=float(s.get("total_portfolio_value") or 0)
                if v>pk: pk=v
                if pk>0: maxdd=max(maxdd,(pk-v)/pk*100)
        return {"n":len(trades),"w":len(wins),"l":len(losses),"wr":round(wr,1),
                "pnl":round(pnl,2),"streak":streak,"sharpe":sharpe,"maxdd":round(maxdd,1)}
    except Exception as e: return {"_error":str(e)}

def fetch_positions(c):
    try:
        return q(c,"""
            WITH lt AS (SELECT DISTINCT ON(symbol) symbol,stop_loss_price,target_1_price
                        FROM algo_trades WHERE status='open' ORDER BY symbol,trade_date DESC),
                 ltt AS (SELECT DISTINCT ON(symbol) symbol,weinstein_stage
                         FROM trend_template_data ORDER BY symbol,date DESC)
            SELECT p.symbol,p.avg_entry_price,p.current_price,
                   p.unrealized_pnl_pct,p.position_value,p.days_since_entry,
                   lt.stop_loss_price,lt.target_1_price,
                   ltt.weinstein_stage,cp.sector
            FROM algo_positions p
            LEFT JOIN lt  ON lt.symbol=p.symbol
            LEFT JOIN ltt ON ltt.symbol=p.symbol
            LEFT JOIN company_profile cp ON cp.ticker=p.symbol
            WHERE p.status='open' ORDER BY p.position_value DESC""")
    except: return []

def fetch_recent_trades(c):
    try:
        return q(c,"""SELECT symbol,trade_date,exit_date,status,
                             profit_loss_dollars,profit_loss_pct,exit_r_multiple
                      FROM algo_trades ORDER BY COALESCE(exit_date,trade_date) DESC LIMIT 5""")
    except: return []

def fetch_signals(c):
    try:
        sig = q1(c,"""SELECT COUNT(*) AS n,MAX(date) AS d FROM buy_sell_daily
                      WHERE signal='BUY' AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY')""")
        top = q(c,"""SELECT s.symbol,s.score,cp.sector FROM swing_trader_scores s
                     LEFT JOIN company_profile cp ON cp.ticker=s.symbol
                     WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
                     ORDER BY s.score DESC LIMIT 12""")
        return {"n":int(sig["n"] or 0) if sig else 0,
                "date":sig["d"] if sig else None,
                "top":top,
                "pass":[s for s in top if float(s.get("score") or 0)>=60]}
    except Exception as e: return {"_error":str(e)}

def fetch_health(c):
    try:
        return q(c,"""
            SELECT tbl,role,latest,age,CASE WHEN age IS NULL OR age>stale THEN 'stale' ELSE 'ok' END AS st
            FROM (
              SELECT 'price_daily'     tbl,'CRIT' role,MAX(date)::date latest,(CURRENT_DATE-MAX(date)::date) age,3 stale FROM price_daily UNION ALL
              SELECT 'buy_sell_daily', 'CRIT', MAX(date)::date,(CURRENT_DATE-MAX(date)::date),3 FROM buy_sell_daily UNION ALL
              SELECT 'swing_scores',   'CRIT', MAX(date)::date,(CURRENT_DATE-MAX(date)::date),3 FROM swing_trader_scores UNION ALL
              SELECT 'technicals',     'IMP',  MAX(date)::date,(CURRENT_DATE-MAX(date)::date),3 FROM technical_data_daily UNION ALL
              SELECT 'market_health',  'IMP',  MAX(date)::date,(CURRENT_DATE-MAX(date)::date),7 FROM market_health_daily UNION ALL
              SELECT 'trend_template', 'IMP',  MAX(date)::date,(CURRENT_DATE-MAX(date)::date),7 FROM trend_template_data UNION ALL
              SELECT 'sector_ranking', 'SUPP', MAX(date)::date,(CURRENT_DATE-MAX(date)::date),14 FROM sector_ranking UNION ALL
              SELECT 'economic_data',  'SUPP', MAX(date)::date,(CURRENT_DATE-MAX(date)::date),14 FROM economic_data
            ) s ORDER BY CASE role WHEN 'CRIT' THEN 1 WHEN 'IMP' THEN 2 ELSE 3 END,tbl""")
    except: return []

def fetch_circuit(c):
    try:
        cfg = {r["key"]:float(r["value"]) for r in q(c,
            "SELECT key,value FROM algo_config WHERE key=ANY(%s)",
            (['halt_drawdown_pct','max_daily_loss_pct','max_consecutive_losses',
              'max_total_risk_pct','vix_max_threshold','max_weekly_loss_pct'],))}
        snaps = q(c,"SELECT total_portfolio_value,daily_return_pct FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 30")
        lat   = snaps[0] if snaps else {}
        pk    = max((float(s.get("total_portfolio_value") or 0) for s in snaps), default=0)
        cur   = float(lat.get("total_portfolio_value") or 0)
        dd    = (pk-cur)/pk*100 if pk>0 else 0
        dl    = -min(0.0, float(lat.get("daily_return_pct") or 0))
        wl    = -min(0.0, sum(float(s.get("daily_return_pct") or 0) for s in snaps[:5]))
        trades= q(c,"SELECT profit_loss_dollars FROM algo_trades WHERE status='closed' AND exit_date IS NOT NULL ORDER BY exit_date DESC LIMIT 20")
        consec=0
        for t in trades:
            if float(t.get("profit_loss_dollars") or 0)<0: consec+=1
            else: break
        h = q1(c,"SELECT vix_level,market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1")
        vix  = float(h.get("vix_level") or 0) if h else 0.0
        stage= int(h.get("market_stage") or 1) if h else 1
        rr   = q1(c,"""WITH lt AS(SELECT DISTINCT ON(symbol) symbol,stop_loss_price FROM algo_trades WHERE status='open' ORDER BY symbol,trade_date DESC)
                        SELECT SUM(GREATEST(p.current_price-lt.stop_loss_price,0)*p.quantity) AS risk,
                               (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1) AS pv
                        FROM algo_positions p LEFT JOIN lt ON lt.symbol=p.symbol WHERE p.status='open'""")
        rp = float(rr["risk"] or 0)/float(rr["pv"] or 1)*100 if rr and rr.get("risk") and rr.get("pv") else 0
        def th(k,d): return cfg.get(k,d)
        bs=[
            {"lbl":"DD",    "cur":round(dd,1),  "thr":th("halt_drawdown_pct",20),      "u":"%"},
            {"lbl":"Daily", "cur":round(dl,1),   "thr":th("max_daily_loss_pct",2),      "u":"%"},
            {"lbl":"Weekly","cur":round(wl,1),   "thr":th("max_weekly_loss_pct",5),     "u":"%"},
            {"lbl":"CnsLoss","cur":consec,        "thr":th("max_consecutive_losses",3),  "u":""},
            {"lbl":"Risk",  "cur":round(rp,1),   "thr":th("max_total_risk_pct",4),      "u":"%"},
            {"lbl":"VIX",   "cur":round(vix,1),  "thr":th("vix_max_threshold",35),      "u":""},
            {"lbl":"Stage", "cur":stage,          "thr":4,                               "u":""},
        ]
        for b in bs: b["fired"] = float(b["cur"])>=float(b["thr"])
        return {"bs":bs,"any":any(b["fired"] for b in bs),"n":sum(1 for b in bs if b["fired"])}
    except Exception as e: return {"_error":str(e)}

# ── parallel load ─────────────────────────────────────────────────

FETCHERS = {"run":fetch_run,"cfg":fetch_algo_config,"mkt":fetch_market,
            "port":fetch_portfolio,"perf":fetch_perf,"pos":fetch_positions,
            "trades":fetch_recent_trades,"sig":fetch_signals,
            "health":fetch_health,"cb":fetch_circuit}

def load_all():
    out={}
    def one(name,fn):
        conn=None
        try:
            conn=get_conn(); conn.autocommit=True
            return name,fn(conn)
        except Exception as e: return name,{"_error":str(e)}
        finally:
            if conn:
                try: conn.close()
                except: pass
    with ThreadPoolExecutor(max_workers=len(FETCHERS)) as pool:
        for f in as_completed({pool.submit(one,k,v):k for k,v in FETCHERS.items()}):
            n,d=f.result(); out[n]=d
    return out

# ── render ────────────────────────────────────────────────────────

def render(data, compact=False, elapsed=0.0, frame=0):
    run   = data.get("run") or {}
    cfg   = data.get("cfg") or {}
    mkt   = data.get("mkt") or {}
    port  = data.get("port") or {}
    perf  = data.get("perf") or {}
    pos   = data.get("pos") or []
    sig   = data.get("sig") or {}
    hlth  = data.get("health") or []
    cb    = data.get("cb") or {}
    rec   = data.get("trades") or []

    now_et = datetime.now(ET)
    mkt_s  = "[bold bright_green]MARKET OPEN[/]" if is_open() else "[dim]MARKET CLOSED[/]"
    ts     = now_et.strftime("%a %b %d  %I:%M %p ET")

    lines = []  # list of rich Text/str to print in order

    # ── HEADER with breakdancing mascot ─────────────────────────
    fi   = frame % len(MASCOT_FRAMES)
    mc   = MASCOT_COLORS[fi]
    mpose= MASCOT_FRAMES[fi]
    hdr_grid = Table.grid(expand=True)
    hdr_grid.add_column("rule", ratio=1)
    hdr_grid.add_column("guy", no_wrap=True, justify="right", min_width=12)
    hdr_grid.add_row(
        Rule(f"[bold white]ALGO OPS[/]  {mkt_s}  [dim]{ts}[/]", style="blue"),
        Panel(Text(mpose, style=f"bold {mc}"), border_style=mc, padding=(0,1), expand=False),
    )
    lines.append(hdr_grid)

    # ── STATUS BLOCK (one panel, 4 dense rows) ──────────────────
    grid = Table.grid(padding=(0,1))
    grid.add_column("lbl", style="dim bold", no_wrap=True, min_width=5)
    grid.add_column("val", no_wrap=False)

    # -- ORCH row
    if run.get("_error") or not run:
        orch_text = Text(f"no data: {run.get('_error','')}", style="dim")
    else:
        age  = fmt_age(run.get("run_at"))
        sts  = ("[bold bright_green][+] COMPLETED[/]" if run.get("success") and not run.get("halted")
                else ("[bold yellow][~] HALTED[/]"    if run.get("halted")
                else "[bold bright_red][!] ERROR[/]"))
        mode_s  = cfg.get("mode","?")
        mode_c  = G if mode_s=="LIVE" else Y
        enbl_s  = "ENABLED" if cfg.get("enabled",True) else "DISABLED"
        enbl_c  = G if cfg.get("enabled",True) else R
        rid     = str(run.get("run_id") or "")[:20]
        phases  = run.get("phases",[])
        pbadges = []
        for p in phases:
            at = p.get("action_type","")
            if not at.startswith("phase_"): continue
            num = at.split("_")[1] if len(at.split("_"))>1 else "?"
            ps  = p.get("status","")
            pc  = G if ps=="success" else (Y if ps in ("halt","warn") else R)
            pi  = "+" if ps=="success" else ("!" if ps in ("halt","warn") else "x")
            pbadges.append(f"[{pc}]P{num}{pi}[/]")
        phase_str = " ".join(pbadges) if pbadges else "[dim]--[/]"
        orch_text = Text.from_markup(
            f"{sts}  [dim]{age}[/]  [{mode_c}][{mode_s}][/]  [{enbl_c}]{enbl_s}[/]  "
            f"[dim]run:[/][dim]{rid}[/]  {phase_str}"
        )
    grid.add_row("ORCH", orch_text)

    # -- MKT row
    if mkt.get("_error") or not mkt:
        mkt_text = Text(f"no data", style="dim")
    else:
        tier   = mkt.get("tier","unknown")
        tc     = TIER_COLOR.get(tier,"dim")
        label  = tier.replace("_"," ").upper()
        exp    = mkt.get("pct")
        bar    = exp_bar(exp or 0)
        vix    = f"{mkt['vix']:.1f}" if mkt.get("vix") is not None else "--"
        dist   = str(mkt.get("dist") or "--")
        stage  = str(mkt.get("stage") or "--")
        halts  = mkt.get("halts") or []
        halt_s = ("  ".join(str(h) for h in halts)) if halts else "none"
        hc     = Y if halts else DIM
        mkt_text = Text.from_markup(
            f"[{tc}][bold]{label}[/bold][/]  [{tc}]{exp or '--':.0f}% [{bar}][/]  "
            f"VIX:[bold]{vix}[/]  Dist:[bold]{dist}[/]  Stage:[bold]{stage}[/]  "
            f"[dim]Halts:[/]  [{hc}]{halt_s}[/]"
        )
    grid.add_row("MKT", mkt_text)

    # -- CB row
    if cb.get("_error") or not cb:
        cb_text = Text("no data", style="dim")
    else:
        n_fired = cb.get("n",0)
        any_f   = cb.get("any",False)
        hdr_c   = R if any_f else G
        hdr_s   = f"[!] {n_fired} FIRED" if any_f else "[+] ALL CLEAR"
        cb_parts = [f"[{hdr_c}]{hdr_s} ({n_fired}/7)[/]"]
        for b in cb.get("bs",[]):
            fc = R if b["fired"] else (Y if (float(b["thr"])>0 and float(b["cur"])/float(b["thr"])>=0.75) else G)
            cb_parts.append(f"  [{fc}]{b['lbl']}:{b['cur']}{b['u']}/{b['thr']:.0f}{b['u']}[/] {hbar(b['cur'],b['thr'])}")
        cb_text = Text.from_markup("".join(cb_parts))
    grid.add_row("CB", cb_text)

    # -- PORT row
    pv   = float(port.get("total_portfolio_value") or 0)
    dr   = float(port.get("daily_return_pct") or 0)
    urp  = float(port.get("unrealized_pnl_pct") or 0)
    cash = float(port.get("total_cash") or 0)
    npos = int(port.get("position_count") or 0)
    streak = perf.get("streak") or 0
    str_s  = f"+{streak}W" if streak>=0 else f"{abs(streak)}L"
    str_c  = G if streak>=0 else R
    pnl_c  = G if (perf.get("pnl") or 0)>=0 else R
    port_text = Text.from_markup(
        f"[bold white]{fmt_money(pv)}[/]  "
        f"Today:[{G if dr>=0 else R}]{'+' if dr>=0 else ''}{dr:.2f}%[/]  "
        f"Unrealized:[{G if urp>=0 else R}]{'+' if urp>=0 else ''}{urp:.2f}%[/]  "
        f"Cash:[white]{fmt_money(cash)}[/]  Positions:[white]{npos}[/]  [dim]|[/]  "
        f"Trades:[white]{perf.get('n',0)}[/]([{G}]{perf.get('w',0)}W[/]/[{R}]{perf.get('l',0)}L[/])  "
        f"Win:[{G if (perf.get('wr') or 0)>=50 else R}]{perf.get('wr','--')}%[/]  "
        f"P&L:[{pnl_c}]{fmt_money(perf.get('pnl'))}[/]  "
        f"Sharpe:[white]{perf.get('sharpe') or '--'}[/]  "
        f"MaxDD:[white]{perf.get('maxdd','--')}%[/]  "
        f"Streak:[{str_c}]{str_s}[/]"
    ) if port else Text("no portfolio data", style="dim")
    grid.add_row("PORT", port_text)

    # -- RECENT TRADES row (last 3 closed + open)
    open_trades  = [t for t in rec if t.get("status")=="open"]
    closed_trades= [t for t in rec if t.get("status")=="closed"][:3]
    if closed_trades or open_trades:
        parts=[]
        for t in closed_trades:
            sym  = t.get("symbol","?")
            pnl  = float(t.get("profit_loss_dollars") or 0)
            pct  = float(t.get("profit_loss_pct") or 0)
            r    = float(t.get("exit_r_multiple") or 0)
            c    = G if pnl>=0 else R
            pref = "+" if pnl>=0 else ""
            dt   = str(t.get("exit_date",""))[:10] if t.get("exit_date") else str(t.get("trade_date",""))[:10]
            parts.append(f"[{c}]{sym} {pref}{pct:.1f}%/{pref}{r:.1f}R ({dt})[/]")
        for t in open_trades:
            sym = t.get("symbol","?")
            dt  = str(t.get("trade_date",""))[:10]
            parts.append(f"[dim]{sym} OPEN ({dt})[/]")
        grid.add_row("TRADES", Text.from_markup("  ".join(parts)))

    lines.append(Panel(grid, border_style="blue", padding=(0,1)))

    # ── POSITIONS TABLE ──────────────────────────────────────────
    if not pos:
        lines.append(Text("  No open positions -- algo is flat", style="dim"))
    else:
        t = Table(box=box.SIMPLE_HEAD, show_header=True,
                  header_style="dim", padding=(0,1), row_styles=["","dim"])
        t.add_column(f"Symbol ({len(pos)})", style="bold white", no_wrap=True, min_width=6)
        t.add_column("Entry",   justify="right", no_wrap=True)
        t.add_column("Price",   justify="right", no_wrap=True)
        t.add_column("P&L%",    justify="right", no_wrap=True)
        t.add_column("R-Mult",  justify="right", no_wrap=True)
        t.add_column("Stop",    justify="right", no_wrap=True)
        t.add_column("Dist%",   justify="right", no_wrap=True)
        if not compact:
            t.add_column("T1->",  justify="right", no_wrap=True)
            t.add_column("Days",  justify="right", no_wrap=True)
            t.add_column("Stg",   justify="center", no_wrap=True, min_width=3)
            t.add_column("Sector",style="dim", no_wrap=True, max_width=12)

        for p in pos:
            entry = float(p.get("avg_entry_price") or 0)
            price = float(p.get("current_price")   or 0)
            stop  = float(p.get("stop_loss_price") or 0) if p.get("stop_loss_price") else None
            t1    = float(p.get("target_1_price")  or 0) if p.get("target_1_price")  else None
            pnl   = float(p.get("unrealized_pnl_pct") or 0)
            days  = p.get("days_since_entry") or "--"
            stg   = p.get("weinstein_stage")
            sec   = (p.get("sector") or "--")[:12]

            rmul  = ((price-entry)/(entry-stop)) if (stop and entry>stop) else None
            dist  = ((price-stop)/price*100)      if (stop and price)     else None
            t1pct = ((t1-price)/price*100)         if (t1 and price)      else None

            pc = G if pnl>=0 else R
            rc = G if (rmul or 0)>=0 else R
            dc = R if (dist or 99)<3 else (Y if (dist or 99)<5 else "white")

            row=[
                p.get("symbol") or "--",
                f"${entry:.2f}",
                f"${price:.2f}",
                Text(f"{'+' if pnl>=0 else ''}{pnl:.2f}%", style=pc),
                Text(f"{'+' if (rmul or 0)>=0 else ''}{rmul:.2f}R" if rmul is not None else "--", style=rc),
                f"${stop:.2f}" if stop else "--",
                Text(f"{dist:.1f}%" if dist is not None else "--", style=dc),
            ]
            if not compact:
                row+=[
                    f"+{t1pct:.1f}%" if t1pct is not None else "--",
                    str(days),
                    f"S{stg}" if stg else "--",
                    sec,
                ]
            t.add_row(*row)
        lines.append(t)

    # ── SIGNALS (single line) ────────────────────────────────────
    if sig and not sig.get("_error"):
        raw    = sig.get("n",0)
        passed = sig.get("pass",[])
        d      = sig.get("date")
        ds     = d.strftime("%b %d") if hasattr(d,"strftime") else str(d or "--")
        pct_s  = f"{len(passed)/raw*100:.1f}%" if raw>0 else "--"
        top_s  = "  ".join(
            f"[{G if float(s.get('score') or 0)>=80 else CY}]{grade(s.get('score') or 0).strip()} {s['symbol']} {float(s.get('score') or 0):.0f}[/]"
            for s in passed[:8]
        )
        lines.append(Text.from_markup(
            f"  [dim bold]SIGNALS[/]  [dim]{ds}[/]  "
            f"[white]{raw}[/] [dim]BUY[/]  "
            f"[{G}]{len(passed)}[/] [dim]passed ({pct_s})[/]  "
            f"[dim]|[/]  {top_s}"
        ))
    else:
        lines.append(Text("  SIGNALS  no data", style="dim"))

    # ── DATA HEALTH (single line) ────────────────────────────────
    if hlth:
        parts=[]
        for r in hlth:
            ok  = r.get("st")=="ok"
            age = r.get("age")
            c   = G if ok else R
            ic  = "[+]" if ok else "[!]"
            nm  = (r.get("tbl") or "--")
            parts.append(f"[{c}]{ic}[white]{nm}[/][dim]({age}d)[/][/]")
        lines.append(Text.from_markup(f"  [dim bold]DATA[/]   " + "  ".join(parts)))
    else:
        lines.append(Text("  DATA   no data", style="dim"))

    # ── FOOTER ───────────────────────────────────────────────────
    lines.append(Text(f"  [dim]loaded {elapsed:.1f}s[/]"))

    return Group(*lines)


# ── main ──────────────────────────────────────────────────────────

def main():
    pa = argparse.ArgumentParser(description="Algo ops terminal dashboard", epilog=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("-w","--watch", nargs="?", const=30, type=int, metavar="SECS")
    pa.add_argument("--compact","-c", action="store_true")
    args = pa.parse_args()

    frame = [0]

    def once():
        CONSOLE.print("[dim]Loading...[/]", end="\r")
        t0 = time.monotonic()
        data = load_all()
        el = time.monotonic()-t0
        CONSOLE.clear()
        CONSOLE.print(render(data, compact=args.compact, elapsed=el, frame=frame[0]))
        frame[0] += 1

    if args.watch is not None:
        iv = max(10, args.watch)
        CONSOLE.print(f"[dim]Auto-refresh {iv}s  Ctrl+C to exit[/]")
        try:
            while True:
                once()
                time.sleep(iv)
        except KeyboardInterrupt:
            CONSOLE.print("\n[dim]stopped[/]")
    else:
        once()

if __name__=="__main__":
    main()
