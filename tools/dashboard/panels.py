"""Panel rendering functions for the dashboard display.

Panels self-register with the panel registry via @register_panel decorator
to enable dynamic discovery and extensibility.
"""

import json
import logging
import statistics
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Import panel registry for self-registration
try:
    from panel_registry import register_panel
except ImportError as e:
    logger.warning(f"Panel registry not available: {e} - panels will not auto-register")
    # Fallback: create no-op decorator
    def register_panel(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from data_validation import safe_int, safe_float

from utilities import (
    CONSOLE, ET, MASCOT_W, MASCOT_FRAMES, MASCOT_COLORS, LOAD_SEQ,
    PHASE_NAMES, TIER_COLOR, TIER_SHORT,
    compute_sector_agg, normalize_positions_data,
    G, R, Y, CY, DIM, MG, WH,
)
from formatters import (
    fmt_age, fmt_money, fmt_money_short, grade, tier_from_pct,
    hbar, exp_bar, mini_bar, sign, sparkline, mkt_hours_str, next_run_str, is_open
)


def mascot_pose(data: dict, frame: int) -> int:
    if (data.get("cb") or {}).get("any"):
        seq = [4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 7]
        return seq[(frame // 2) % len(seq)]
    return LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]


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
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse phases_halted JSON: {e}")
            phases_halted = [phases_halted]
    if not isinstance(phases_halted, (list, tuple)):
        return ""
    names = []
    for p in phases_halted:
        raw   = str(p).lower()
        parts = raw.split("_")
        base  = "_".join(parts[:2]) if len(parts) >= 2 else raw
        names.append(PHASE_NAMES.get(base, raw.replace("phase_", "P")))
    return ", ".join(names[:3])


def _error_panel(data_name: str, data, title: str, border="magenta"):
    """Create a panel showing granular error info for failed data sources."""
    if not data:
        return Panel(
            Text(f"{data_name}: no data", style="dim"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1)
        )

    if isinstance(data, dict) and data.get("_error"):
        error_msg = data.get("_error", "Unknown error")
        return Panel(
            Text.from_markup(f"[{R}]{data_name}[/] fetch failed:\n[dim]{error_msg}[/]"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1)
        )

    return None


def _extract_items(data: any) -> list:
    """Safely extract items list from data structure, propagating errors."""
    if isinstance(data, dict):
        if data.get("_error"):
            return data
        if "items" in data:
            return data.get("items", [])
    elif isinstance(data, list):
        return data
    return []


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

    score_s   = f"[dim]min score â‰¥[/][white]{min_score}[/]" if min_score and float(min_score) > 0 else ""
    slots_s   = f"[dim]max [/][white]{max_n}[/][dim] positions[/]" if max_n else ""
    sec_s     = f"[dim]sector â‰¤[/][white]{max_sec_n}[/]" if max_sec_n else ""
    risk_s    = f"[dim]base risk [/][white]{base_risk}%[/]" if base_risk else ""
    t1r_s     = f"[dim]T1 target [/][white]{t1r}R[/]" if t1r else ""
    pyr_s     = f"[{G}]pyramid on[/]" if pyr else ""
    config_line = "  ".join(x for x in [score_s, slots_s, sec_s, risk_s, t1r_s, pyr_s] if x)

    # VaR line âE" only show if table is populated with real data
    var_line = ""
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        beta_c = R if (risk.get("beta") or 0) >= 1.2 else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        svar_s = f"\n[dim]Stressed VaR:[/][{R}]{risk.get('svar', 0):.2f}%[/]" if risk.get("svar") and float(risk.get("svar") or 0) > 0 else ""
        var_line = (f"\n[dim]VaR 95%:[/][white]{risk.get('var95', 0):.2f}%[/]"
                    f"  [dim]CVaR 95%:[/][white]{risk.get('cvar95', 0):.2f}%[/]"
                    f"  [dim]Portfolio Beta:[/][{beta_c}]{risk.get('beta', 0):.2f}[/]"
                    f"  [dim]Top-5 Conc:[/][white]{risk.get('conc5', 0):.0f}%[/]"
                    + svar_s)

    if not run or run.get("_error"):
        error_msg = (f"[{R}]run fetch failed[/]: {run.get('_error')}"
                     if isinstance(run, dict) and run.get("_error")
                     else "[dim]run: no data[/]")
        body = Text.from_markup(
            f"{error_msg}\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next run:[/] [white]{next_run}[/]"
            + var_line
        )
    else:
        age  = fmt_age(run.get("run_at"))
        sts  = ("[bold bright_green]✓ COMPLETED[/]" if run.get("success") and not run.get("halted")
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

        phases_str = "  ".join(pbadges) if pbadges else "[dim]──[/]"
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
    err_panel = _error_panel("market", mkt, "MARKET", border="blue")
    if err_panel:
        return err_panel
    tier  = mkt.get("tier", "unknown")
    tc    = TIER_COLOR.get(tier, "dim")
    lbl   = TIER_SHORT.get(tier, "LOADING")
    exp   = mkt.get("pct")
    exp_s = f"{float(exp):.0f}%" if exp is not None else "--"
    bar   = exp_bar(exp or 0, w=10)
    vix   = f"{mkt['vix']:.1f}" if mkt.get("vix") is not None else "--"
    vc    = DIM if mkt.get("vix") is None else (R if mkt.get("vix") >= 30 else (Y if mkt.get("vix") >= 20 else G))
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
    nhnl  = (nh - nl) if (nh is not None and nl is not None) else None
    nhnl_c = G if nhnl >= 50 else (Y if nhnl >= 0 else R) if nhnl is not None else DIM

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
        nhnl_s = f"  [dim]NH-NL:[/][{nhnl_c}]{sign(nhnl)}{nhnl}[/]" if nhnl is not None else ""
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
        fg_bar_s = f"[{fg_c}]{'#' * fg_bar}[/][dim]{'#' * (8 - fg_bar)}[/]"
        lines.append(f"[dim]Fear & Greed:[/][{fg_c}]{fg_v:.0f} % {fg_lbl}[/] {fg_bar_s}")

    txt = Text.from_markup("\n".join(lines))
    return Panel(txt, title="[bold blue]MARKET[/]", border_style="blue", padding=(0, 1))


@register_panel("circuit", endpoint_deps=["cb"], optional=False, description="Circuit breaker status")
def panel_circuit(cb, risk=None):
    err_panel = _error_panel("circuit breakers", cb, "CIRCUIT BREAKERS", border="blue")
    if err_panel:
        return err_panel
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
            fired = br.get("fired", False)
            thr = br.get("thr", 0)
            cur = br.get("cur", 0)
            fc  = R if fired else (Y if float(thr) > 0 and float(cur) / float(thr) >= 0.75 else G)
            ind = "[bold red] ![/]" if fired else ""
            return f"[{fc}]{br.get('lbl', 'N/A')}:[/]{cur}{br.get('u', '')}[dim]/{thr:.0f}{br.get('u', '')}[/]{hbar(cur, thr, w=4)}{ind}"
        tbl.add_row(Text.from_markup(fmt_b(a)), Text.from_markup(fmt_b(b)))
    parts = [Text.from_markup(f"[{hc}][bold]{hs}[/bold][/]"), tbl]
    return Panel(Group(*parts), title="[bold blue]CIRCUIT BREAKERS[/]", border_style="blue", padding=(0, 1))


@register_panel("header", endpoint_deps=["mkt", "sentiment"], optional=False, description="Header")
def panel_header_market(mkt, sentiment, ts, mkt_s, elapsed, refresh_s="", cfg=None, data_source="AWS"):
    """Compact market header - fits alongside exposure factors + monkey in the top row."""
    source_color = "cyan" if data_source == "LOCAL" else "dim"
    rows = [Text.from_markup(f"{mkt_s}  [dim]{ts}[/]  [dim]{elapsed:.1f}s[/]{refresh_s}  [{source_color}]{data_source}[/]")]
    if mkt and not mkt.get("_error"):
        tier    = mkt.get("tier", "unknown")
        tc      = TIER_COLOR.get(tier, "dim")
        lbl     = TIER_SHORT.get(tier, "LOADING")
        exp     = mkt.get("pct")
        exp_s   = f"{float(exp):.0f}%" if exp is not None else "--"
        bar     = exp_bar(exp or 0, w=8)
        vix     = f"{mkt['vix']:.1f}" if mkt.get("vix") is not None else "--"
        vc      = DIM if mkt.get("vix") is None else (R if mkt.get("vix") >= 30 else (Y if mkt.get("vix") >= 20 else G))
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
            nhnl   = (nh - nl) if (nh is not None and nl is not None) else None
            nhnl_c = G if nhnl >= 50 else (Y if nhnl >= 0 else R) if nhnl is not None else DIM
            adr_s  = f"  [dim]A/D:[/][white]{adr:.1f}[/]" if adr is not None else ""
            nhnl_s = f"[dim]NH-NL:[/][{nhnl_c}]{sign(nhnl)}{nhnl}[/]" if nhnl is not None else "[dim]NH-NL: --[/]"
            rows.append(Text.from_markup(
                f"[dim]UpVol:[/][{uvc}]{upvol:.0f}%[/]{adr_s}  "
                f"[dim]NH:[/][{G}]{nh or '--'}[/] [dim]NL:[/][{R}]{nl or '--'}[/]  "
                f"{nhnl_s}"
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
            fg_bar_s = f"[{fg_c}]{'#' * fg_bar}[/][dim]{'#' * (6 - fg_bar)}[/]"
            line5 += f"  [dim]F&G:[/][{fg_c}]{fg_v:.0f} % {fg_lbl}[/] {fg_bar_s}"
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
            if pyr:       parts6.append(f"[{G}]pyrOK[/]")
            if min_score: parts6.append(f"[dim]scoreâ‰¥[/][white]{min_score}[/]")
            if max_n:     parts6.append(f"[dim]slots:[/][white]{max_n}[/]")
            if base_risk: parts6.append(f"[dim]risk:[/][white]{base_risk}%[/]")
            if t1r:       parts6.append(f"[dim]T1:[/][white]{t1r}R[/]")
            parts6.append(f"[dim]next:[/][white]{next_run_str()}[/]")
            rows.append(Text.from_markup("  ".join(parts6)))
    else:
        rows.append(Text("no market data", style="dim"))
    return Panel(Group(*rows), title="[bold blue]MARKET[/]", border_style="blue", padding=(0, 1))


@register_panel("portfolio", endpoint_deps=["port", "cfg", "risk", "perf"], optional=False, description="Portfolio")
def panel_portfolio(port, cfg, risk=None, perf=None):
    err_panel = _error_panel("portfolio", port, "PORTFOLIO", border="green")
    if err_panel:
        return err_panel

    pv    = safe_float(port.get("total_portfolio_value"), default=None)
    dr    = safe_float(port.get("daily_return_pct"), default=None)
    urp   = safe_float(port.get("unrealized_pnl_pct"), default=None)
    cash  = safe_float(port.get("total_cash"), default=None)
    npos  = int(port.get("position_count") or 0)
    cum   = port.get("cumulative_return_pct")
    mxdd  = port.get("max_drawdown_pct")
    lgpos = port.get("largest_position_pct")
    snap  = port.get("snapshot_date")
    bp    = safe_float(port.get("total_buying_power"), default=None)
    max_n = int(cfg.get("max_pos_n") or 0) if cfg else 0
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
    dr_s  = f"[{G if dr >= 0 else R}]{sign(dr)}{dr:.2f}%[/]" if dr is not None else "[dim]--[/]"
    urp_s = f"[{G if urp >= 0 else R}]{sign(urp)}{urp:.2f}%[/]" if urp is not None else "[dim]--[/]"
    rows.append(Text.from_markup(
        f"[dim]Day:[/] {dr_s}  "
        f"[dim]Unrlzd:[/] {urp_s}"
    ))

    # Line 4: cumulative return + max drawdown (always show, "--" when missing)
    cum_v  = float(cum) if cum is not None else None
    mxdd_v = float(mxdd) if mxdd is not None else None
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
        rows.append(Text.from_markup(
            f"[dim]VaR:[/][white]{risk.get('var95', 0):.2f}%[/]  "
            f"[dim]CVaR:[/][white]{risk.get('cvar95', 0):.2f}%[/]  "
            f"[dim]Î²:[/][{beta_c}]{risk.get('beta', 0):.2f}[/]  "
            f"[dim]Conc5:[/][white]{risk.get('conc5', 0):.0f}%[/]"
        ))

    return Panel(Group(*rows), title="[bold green]PORTFOLIO[/]", border_style="green", padding=(0, 1))


def _calculate_adjusted_win_rate(perf, pos):
    """E10 Fix: Include losing open positions in win rate calculation.

    Win rate should reflect all active positions (closed + open losses), not just closed trades.
    Counts open positions with unrealized_pnl_pct < 0 as losses.
    """
    if not perf or perf.get("_error"):
        return perf.get("wr"), perf.get("w"), perf.get("l")

    closed_wins = perf.get("w") or 0
    closed_losses = perf.get("l") or 0
    losing_open = 0

    if pos and not pos.get("_error"):
        pos_items, _, _ = normalize_positions_data(pos)
        for p in pos_items:
            if isinstance(p, dict):
                pnl = safe_float(p.get("unrealized_pnl_pct"), default=None)
                if pnl is not None and pnl < 0:
                    losing_open += 1

    total_trades = closed_wins + closed_losses + losing_open
    if total_trades == 0:
        return 0, closed_wins, closed_losses + losing_open

    adjusted_wr = (closed_wins / total_trades) * 100
    return adjusted_wr, closed_wins, closed_losses + losing_open


@register_panel("performance", endpoint_deps=["perf", "trades", "perf_anl"], optional=True, description="Performance")
def panel_performance_spark(perf, rec, perf_anl=None, pos=None):
    """Performance metrics + equity sparkline + rolling analytics."""
    err_panel = _error_panel("performance", perf, "PERFORMANCE", border="green")
    if err_panel:
        return err_panel

    streak  = perf.get("streak") if perf.get("streak") is not None else 0
    str_s   = f"+{streak}W" if streak >= 0 else f"{abs(streak)}L"
    str_c   = G if streak >= 0 else R
    pnl_val = perf.get("pnl")
    pnl_c   = G if pnl_val is not None and pnl_val >= 0 else R
    pf      = perf.get("profit_factor")
    pf_s    = f"{pf:.2f}" if pf is not None else "--"
    pf_c    = G if pf is not None and pf >= 1.5 else (Y if pf is not None and pf >= 1.0 else R)
    exp     = perf.get("expectancy") if perf.get("expectancy") is not None else 0
    exp_c   = G if exp >= 0 else R
    avg_r   = perf.get("avg_r")
    avg_r_s = f"{avg_r:.2f}R" if avg_r is not None else "--"

    wr_v, adj_w, adj_l = _calculate_adjusted_win_rate(perf, pos)
    dd_v = perf.get('maxdd') if perf.get('maxdd') is not None else 0
    dd_c = R if dd_v >= 10 else (Y if dd_v >= 5 else G)
    closed_wins = perf.get('w', 0)
    closed_losses = perf.get('l', 0)
    losing_open = adj_l - closed_losses
    rows = [
        Text.from_markup(
            f"[bold white]{closed_wins + closed_losses + losing_open} Trades[/]  "
            f"[{G}]{closed_wins}W[/][dim]/[/][{R}]{adj_l}L[/]  "
            f"[dim]WR:[/][{G if wr_v >= 50 else R}]{wr_v:.1f}%{f' (+{losing_open} open L)' if losing_open > 0 else ''}[/]  "
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
        for item in recent_rets[-5:]:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                dt, ret = item[0], item[1]
            else:
                continue
            rc = G if (ret or 0) >= 0 else R
            if hasattr(dt, "strftime"):
                d_s = dt.strftime("%a")
            elif isinstance(dt, str):
                try:
                    from datetime import datetime
                    dt_obj = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                    d_s = dt_obj.strftime("%a")
                except (ValueError, AttributeError, TypeError) as e:
                    logger.debug(f"Failed to parse datetime {dt}: {e}")
                    d_s = str(dt)[:3]
            else:
                d_s = str(dt)[:3]
            parts.append(f"[dim]{d_s}[/][{rc}]{sign(ret)}{ret:.1f}%[/]")
        if parts:
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

    # Recent closed trades âE" last 3 exits with result
    rec_items = rec.get("items", []) if isinstance(rec, dict) else rec if isinstance(rec, list) else []
    recent = [t for t in rec_items if isinstance(t, dict) and t.get("status") == "closed" and t.get("exit_date")][:3]
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


@register_panel("positions", endpoint_deps=["pos", "trades"], optional=True, description="Positions")
def panel_positions(pos, compact=False, trades=None):
    """Display open positions table. Normalizes input from {"items": [...]} format."""
    # Check if placeholder/fallback data is being displayed
    is_placeholder = False
    if isinstance(pos, dict):
        is_placeholder = pos.get("_is_placeholder") or pos.get("_is_fallback_data")

    # Issue 3.1 FIX: Use unified normalization function
    pos_items, pos_timestamp, has_error = normalize_positions_data(pos)
    if has_error:
        err_msg = pos.get("_error") if isinstance(pos, dict) else "Unknown error"
        return Panel(Text(f"  Error: {err_msg}", style="red"), title="[bold red]POSITIONS[/]", border_style="red", padding=(0, 1))

    if not pos_items:
        return Panel(Text("  No open positions - algo is flat", style="dim"),
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
    invalid_count = 0
    for p in pos_items:
        if not isinstance(p, dict):
            invalid_count += 1
            logger.error(f"panel_positions: invalid position (not a dict): {type(p).__name__}")
            continue
        entry = safe_float(p.get("avg_entry_price"), default=None)
        price = safe_float(p.get("current_price"), default=None)
        pval  = safe_float(p.get("position_value"), default=None)
        stop  = safe_float(p.get("stop_loss_price"), default=None)
        t1    = safe_float(p.get("target_1_price"), default=None)
        pnl   = safe_float(p.get("unrealized_pnl_pct"), default=None)
        days  = p.get("days_since_entry") or "--"
        stg   = p.get("weinstein_stage")
        swg   = p.get("swing_score")
        sec   = (p.get("sector") or "--")[:12]
        rmul  = float(p.get("r_multiple")) if p.get("r_multiple") is not None else None
        dist  = float(p.get("distance_to_stop_pct")) if p.get("distance_to_stop_pct") is not None else None
        t1pct = float(p.get("distance_to_t1_pct")) if p.get("distance_to_t1_pct") is not None else None
        pc    = G if (pnl is not None and pnl >= 0) else R
        rc    = G if (rmul is not None and rmul >= 0) else R
        dc    = R if (dist is not None and dist < 3) else (Y if (dist is not None and dist < 5) else "white")
        row = [
            p.get("symbol") or "--",
            fmt_money_short(pval) if pval is not None else "--",
            f"${entry:.2f}" if entry is not None else "--",
            f"${price:.2f}" if price is not None else "--",
            Text(f"{sign(pnl)}{pnl:.2f}%" if pnl is not None else "--", style=pc),
            Text(f"{sign(rmul)}{rmul:.2f}R" if rmul is not None else "--", style=rc),
            f"${stop:.2f}" if stop is not None else "--",
            Text(f"{dist:.1f}%" if dist is not None else "--", style=dc),
        ]
        if not compact:
            swg_s = float(swg) if swg is not None else None
            swg_c = G if (swg_s is not None and swg_s >= 80) else (Y if (swg_s is not None and swg_s >= 60) else "white")
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
               if isinstance(tr, dict) and tr.get("status") in ("pending", "pending_new", "rejected")] if trades else []

    # Build content with optional placeholder warning and pending trades
    content_items = []
    if is_placeholder:
        content_items.append(Text.from_markup("[bold red]📊 PLACEHOLDER DATA - Positions may not be accurate[/]"))
    content_items.append(t)
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
                pend_rows.append(Text.from_markup(f"  [{Y}]◌ {sym}[/] [dim]{age_s} {st}[/]"))
        content_items.extend(pend_rows)

    content = Group(*content_items) if len(content_items) > 1 else (content_items[0] if content_items else t)

    border = "red" if is_placeholder else "cyan"
    age_s = f"  [dim]{fmt_age(pos_timestamp)}[/]" if pos_timestamp is not None else ""
    if invalid_count > 0:
        logger.error(f"panel_positions: encountered {invalid_count} invalid position(s); display may be incomplete")
        border = "red"
        title_str = f"[bold red]POSITIONS ⚠ DATA ERROR ({invalid_count} invalid)[/]"
    elif is_placeholder:
        title_str = "[bold red]POSITIONS ⚠ PLACEHOLDER DATA[/]"
    else:
        title_str = f"[bold cyan]POSITIONS ({len(pos_items)})[/]"
    return Panel(content, title=f"{title_str}{age_s}  [dim][p] expand[/]", border_style=border, padding=(0, 0))


@register_panel("signals", endpoint_deps=["sig", "sig_eval"], optional=True, description="Signals")
def panel_signals_compact(sig, sig_eval=None):
    """Signals & screening - actual BUY signals from buy_sell_daily with setup detail."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel

    # Check if placeholder/fallback data is being displayed
    is_placeholder = sig.get("_is_placeholder") or sig.get("_is_fallback_data")

    raw   = sig.get("n", 0)
    total = sig.get("total", 0)
    d     = sig.get("date")
    ds    = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    g     = sig.get("grades") or {}
    ga, gb, gc, gd = (int(g.get(k)) if g.get(k) is not None else None for k in ("a", "b", "c", "d"))
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

    # ── Row 1: count  Â·  7-day sparkline  Â·  grade pool  Â·  date ─────────────
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))
    trend = sig.get("trend") or []
    spark_s = ""
    if len(trend) >= 2:
        counts  = [int(t.get("buy_n") or 0) for t in reversed(trend)]
        max_b   = max(counts) if counts else 1
        spark   = "".join("â-â-‚â-ƒâ-„â-...â-†â-‡â-ˆ"[min(7, int(v / max(max_b, 1) * 7.9))] for v in counts)
        spark_s = f"  [{CY}]{spark}[/]"
    n_near = len(near)
    near_hint = f"  [{CY}]{n_near} near[/]" if n_near else ""
    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"
    rows = [Text.from_markup(
        f"[{buy_c}][bold]{raw} BUY[/][/]{spark_s}  [dim]from {total} screened  {ds}[/]"
        f"  [{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]{near_hint}"
    )]

    # ── Row 2: A-grade radar (always; near-misses only when nothing better) ──
    if top_a:
        parts = []
        for s in top_a[:8]:
            sc   = float(s.get("score")) if s.get("score") is not None else None
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{s.get('symbol','')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{s.get('symbol','')}[/][dim]--[/]")
        extra = f"  [dim]+{ga - min(ga, 8)} more[/]" if ga is not None and ga > 8 else ""
        rows.append(Text.from_markup("[dim]A radar:[/]  " + "  ".join(parts) + extra))
    elif near:
        parts = []
        for a in near[:8]:
            sc = float(a.get('score')) if a.get('score') is not None else None
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            parts.append(f"[{CY}]{a['symbol']}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near threshold:[/]  " + "  ".join(parts)))

    # ── Row 3: Funnel arrow chain  Â·  avg score  Â·  top blockers ─────────────
    if sig_eval and not sig_eval.get("_error"):
        ev_tot = sig_eval.get("total", 0)
        ev_t1  = sig_eval.get("t1", 0)
        ev_t5  = sig_eval.get("t5", 0)
        ev_avg = sig_eval.get("avg_score", 0)
        ev_c   = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
        rejected   = sig_eval.get("rejected") or []
        if rejected:
            block_parts = []
            for rj in rejected[:3]:
                reason_abbr = _shorten_reason(rj['evaluation_reason'])
                description = rj.get('description', '')
                if description:
                    block_parts.append(f"[dim]{reason_abbr}:{rj['n']}[/] [bright_black]({description})[/]")
                else:
                    block_parts.append(f"[dim]{reason_abbr}:{rj['n']}[/]")
            blocks_s = "  [dim]blocked:[/]  " + "  ".join(block_parts)
        else:
            blocks_s = ""
        rows.append(Text.from_markup(
            f"[dim]{ev_tot} â†'[/] [{ev_c}]{ev_t5} qualified[/]"
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
                Text(f"S{stg}" if stg else "──", style=stg_c),
                Text(sig_t, style="dim"),
                Text(f"{sq:.0f}"       if sq     is not None else "──", style=sq_c),
                Text(f"{swg:.0f}"      if swg    is not None else "──", style=swg_c),
                Text(f"{rr:.1f}"       if rr     is not None else "──", style=rr_c),
                Text(f"${float(entry):.2f}" if entry is not None else "──", style="dim"),
                Text(f"${float(stop):.2f}"  if stop  is not None else "──", style="dim"),
                Text(f"{vsurge:+.0f}%" if vsurge is not None else "──", style=vs_c),
            )
        rows.append(t)
    else:
        if total == 0:
            rows.append(Text.from_markup(f"[{Y}]No signals -- buy_sell_daily may be stale (check Data Health)[/]"))
        else:
            rows.append(Text.from_markup(f"[dim]0 BUY signals from {total} screened[/]"))

    # ── Near-miss strip (only when A-grade stocks exist above; otherwise shown on row 2) ──
    if near and top_a:
        rows.append(Rule(style="dim"))
        parts = []
        for a in near[:8]:
            sc = float(a.get('score')) if a.get('score') is not None else None
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            parts.append(f"[{CY}]{a['symbol']}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near BUY (55-69):[/]  " + "  ".join(parts)))

    # Add placeholder warning if needed
    if is_placeholder:
        rows.insert(0, Text.from_markup("[bold red]📊 PLACEHOLDER DATA - Signals may not be accurate[/]"))

    age_s = f"  [dim]{fmt_age(sig.get('timestamp'))}[/]" if sig.get('timestamp') is not None else ""
    border = "red" if is_placeholder else "magenta"
    title = "[bold red]BUY SIGNALS ⚠ PLACEHOLDER DATA[/]" if is_placeholder else "[bold magenta]BUY SIGNALS & SCREENING[/]"
    return Panel(Group(*rows), title=f"{title}{age_s}  [dim][s] expand[/]", border_style=border, padding=(0, 1))


@register_panel("trades", endpoint_deps=["trades"], optional=True, description="Trades")
def panel_recent_trades(trades):
    # Closed/recent trade history - sits alongside positions panel
    trades_timestamp = None
    if isinstance(trades, dict):
        trades_timestamp = trades.get("timestamp")
        trades_list = trades.get("items", [])
    else:
        trades_list = trades if isinstance(trades, list) else []

    if not trades_list:
        age_s = f"  [dim]{fmt_age(trades_timestamp)}[/]" if trades_timestamp is not None else ""
        return Panel(Text('no recent trades', style='dim'),
                     title=f'[bold cyan]RECENT TRADES[/]{age_s}', border_style='cyan', padding=(0, 1))

    # Check if placeholder/fallback data is being displayed
    is_placeholder = any(t.get("_is_placeholder") or t.get("_is_fallback_data") for t in trades_list if isinstance(t, dict))

    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="dim bold",
              padding=(0, 1), row_styles=["", "dim"], expand=True)
    t.add_column("Sym",  style="bold white", no_wrap=True, min_width=4)
    t.add_column("Date", style="dim",        no_wrap=True, min_width=5)
    t.add_column("P&L$", justify="right",    no_wrap=True, min_width=6)
    t.add_column("P&L%", justify="right",    no_wrap=True, min_width=5)
    t.add_column("R",    justify="right",    no_wrap=True, min_width=4)
    t.add_column("St",   style="dim",        no_wrap=True, min_width=4)
    for tr in trades_list[:10]:
        sym    = tr.get("symbol") or "--"
        date   = tr.get("exit_date") or tr.get("trade_date")
        date_s = date.strftime("%b%d") if hasattr(date, "strftime") else str(date or "--")[:5]
        pnl_d  = float(tr.get("profit_loss_dollars") or 0)
        pnl_p  = float(tr.get("profit_loss_pct") or 0)
        rmul   = tr.get("exit_r_multiple")
        status = (tr.get("status") or "")
        is_closed = status == "closed"
        pc  = G if pnl_d > 0 else (R if is_closed else Y)
        si  = f"[{G}]OK[/]" if pnl_d > 0 else (f"[{R}]X[/]" if is_closed else f"[{Y}]◌[/]")
        t.add_row(
            Text.from_markup(f"{si} {sym}"),
            date_s,
            Text(f"{sign(pnl_d)}${abs(pnl_d):.0f}" if is_closed else "--", style=pc),
            Text(f"{sign(pnl_p)}{pnl_p:.1f}%" if is_closed else "--",      style=pc),
            Text(f"{float(rmul):.2f}R" if rmul is not None else "--",       style=pc),
            status[:4],
        )

    # Build content with optional placeholder warning
    content_items = []
    if is_placeholder:
        content_items.append(Text.from_markup("[bold red]📊 PLACEHOLDER DATA - Trades may not be accurate[/]"))
    content_items.append(t)

    content = Group(*content_items) if len(content_items) > 1 else t

    age_s = f"  [dim]{fmt_age(trades_timestamp)}[/]" if trades_timestamp is not None else ""
    border = "red" if is_placeholder else "cyan"
    title = "[bold red]RECENT TRADES ⚠ PLACEHOLDER DATA[/]" if is_placeholder else "[bold cyan]RECENT TRADES[/]"
    return Panel(content, title=f"{title}{age_s}", border_style=border, padding=(0, 0))


def _rdelta(r, wk="rank_1w_ago", wk4=None):
    """Rank delta formatter: shows rank change with ↑/↓ symbols and color coding."""
    cur, old = r.get("current_rank", 0), r.get(wk)
    if old is None: return ""
    d = int(old) - int(cur)
    s1 = (f"[{G}]↑{d}[/]" if d > 0 else (f"[{R}]↓{abs(d)}[/]" if d < 0 else "[dim]=[/]"))
    if wk4:
        old4 = r.get(wk4)
        if old4 is not None:
            d4 = int(old4) - int(cur)
            s4 = (f"[{G}]↑{d4}[/]" if d4 > 0 else (f"[{R}]↓{abs(d4)}[/]" if d4 < 0 else "[dim]=[/]"))
            return f"{s1}[dim]/[/]{s4}"
    return s1


@register_panel("sectors", endpoint_deps=["srank", "pos", "port", "sec_rot", "irank"], optional=True, description="Sectors")
def panel_sector_compact(srank, pos, port, sec_rot=None, irank=None):
    """Rotation + holdings (max 2) + sector leaders (1 pair) + industries (2 pairs) = 8 lines."""
    rows = []

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
    sorted_secs, total_secs, pv = compute_sector_agg(pos, port)
    if sorted_secs:
        show_secs   = sorted_secs[:6]
        hdr_more    = f" [dim](top 6 of {total_secs})[/]" if total_secs > 6 else ""
        rows.append(Text.from_markup(f"[dim]Holdings by sector:{hdr_more}[/]"))

        def fmt_sec_item(sec, dv):
            pct     = dv["val"] / pv * 100 if pv else 0
            avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
            pc      = G if avg_pnl >= 0 else R
            bar_f   = int(min(pct, 30) / 30 * 3)
            bar_s   = f"[{pc}]{'#' * bar_f}[/][dim]{'-' * (3 - bar_f)}[/]"
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
        rows.append(Text.from_markup("[dim]Top sectors by rank (momentum score, â-²â-¼= rank change vs 1wk/4wk):[/]"))
        for a, b in zip(valid_srank[::2], valid_srank[1::2] + [None]):
            na  = (a.get("sector_name") or "")[:10]
            mma = a.get("momentum_score")
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            la  = f"[{G}]#{a['current_rank']}[/] [dim]{na}[/]{ms_a}{_rdelta(a, wk4='rank_4w_ago')}"
            if b:
                nb  = (b.get("sector_name") or "")[:10]
                mmb = b.get("momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                rows.append(Text.from_markup(f" {la}    [{G}]#{b['current_rank']}[/] [dim]{nb}[/]{ms_b}{_rdelta(b, wk4='rank_4w_ago')}"))
            else:
                rows.append(Text.from_markup(f" {la}"))

    # Top industries (sub-sector groups)
    valid_irank = irank if (irank and not (isinstance(irank, dict) and irank.get("_error"))) else []
    if valid_irank:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Top industries (sub-sector groups, â-²â-¼= vs 1wk):[/]"))
        for a, b in zip(valid_irank[:4][::2], valid_irank[:4][1::2] + [None]):
            na  = (a.get("industry") or "")[:12]
            mma = a.get("momentum_score")
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            la  = f"[{CY}]#{a['current_rank']}[/] [white]{na}[/]{ms_a}{_rdelta(a)}"
            if b:
                nb  = (b.get("industry") or "")[:12]
                mmb = b.get("momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                rows.append(Text.from_markup(f" {la}    [{CY}]#{b['current_rank']}[/] [white]{nb}[/]{ms_b}{_rdelta(b)}"))
            else:
                rows.append(Text.from_markup(f" {la}"))

    if not rows:
        return Panel(Text("no data", style="dim"), title="[bold]SECTORS & INDUSTRIES[/]", border_style="cyan", padding=(0, 1))
    return Panel(Group(*rows), title="[bold cyan]SECTORS & INDUSTRIES[/]  [dim][r] expand[/]", border_style="cyan", padding=(0, 1))


@register_panel("economic", endpoint_deps=["eco", "econ_cal"], optional=True, description="Economic")
def panel_economic_pulse(eco, econ_cal=None):
    """Economic factors the algo uses to calculate market exposure score."""
    err_panel = _error_panel("economic pulse", eco, "ECONOMIC INPUTS", border="bright_magenta")
    if err_panel:
        return err_panel
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
    if oil  is not None: other.append(f"[dim]WTI Crude Oil:[/][white]${oil:.2f}[/]")
    if nfci is not None:
        nc  = G if nfci <= -0.3 else (Y if nfci <= 0.3 else R)
        lbl = "accommodative" if nfci < 0 else ("tight" if nfci > 0.3 else "neutral")
        other.append(f"[dim]Chicago Fed (NFCI):[/][{nc}]{nfci:+.3f}[/][dim] {lbl}[/]")
    if dxy is not None:
        dxy_c = R if dxy >= 110 else (Y if dxy >= 100 else G)
        other.append(f"[dim]USD Index (DXY):[/][{dxy_c}]{dxy:.1f}[/]")
    if other: rows.append(Text.from_markup("  ".join(other)))

    # Inflation breakevens + consumer sentiment + mortgage rates
    extra = []
    if be10 is not None:
        be_c = R if be10 >= 3.0 else (Y if be10 >= 2.5 else G)
        extra.append(f"[dim]10Y Inflation Breakeven:[/][{be_c}]{be10:.2f}%[/]")
    if be5 is not None:
        be5_c = R if be5 >= 3.0 else (Y if be5 >= 2.5 else G)
        extra.append(f"[dim]5Y Breakeven:[/][{be5_c}]{be5:.2f}%[/]")
    if mortgage is not None:
        mg_c = R if mortgage >= 7.0 else (Y if mortgage >= 6.0 else G)
        extra.append(f"[dim]30Y Mortgage:[/][{mg_c}]{mortgage:.2f}%[/]")
    if umcsent is not None:
        uc = G if umcsent >= 80 else (Y if umcsent >= 60 else R)
        extra.append(f"[dim]UMich Consumer Sentiment:[/][{uc}]{umcsent:.0f}[/]")
    if extra: rows.append(Text.from_markup("  ".join(extra)))

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
            key     = (str(ed) + full_nm[:24]).lower()
            if key in seen_keys: continue
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
    return Panel(Group(*rows), title="[bold bright_magenta]ECONOMIC INPUTS â†' Exposure Score[/]",
                 border_style="bright_magenta", padding=(0, 1))


@register_panel("exposure", endpoint_deps=["exp_factors"], optional=True, description="Exposure")
def panel_exposure_compact(exp_f):
    """12-factor exposure score - compact 2-col layout."""
    err_panel = _error_panel("exposure factors", exp_f, "EXPOSURE FACTORS", border="blue")
    if err_panel:
        return err_panel
    raw     = safe_float(exp_f.get("raw_score"), default=None)
    epct    = safe_float(exp_f.get("exposure_pct"), default=None)
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
            st = (f.get("state") or "").replace("_under_pressure", "→").replace("_", " ")[:9]
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
        f"[dim]Score:[/][white]{raw:.0f}[/][dim]/100[/] {raw_bar} [dim]â†' allocation[/] [{tc}][bold]{epct:.0f}%[/][/]  [dim]{regime[:24]}[/]"
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
            f"[bold bright_green]OK COMPLETED[/]" if (run_valid and run.get("success") and not run.get("halted"))
            else (f"[bold yellow]~ HALTED[/]" if (run_valid and run.get("halted"))
            else (f"[bold bright_red]âœ˜ ERROR[/]" if (run_valid and run.get("errored"))
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
    # Trading config params âE" visible context for position sizing decisions
    cfg_parts = []
    if cfg_v.get("max_pos_n"):    cfg_parts.append(f"[dim]slots:[/][white]{cfg_v['max_pos_n']}[/]")
    if cfg_v.get("max_sec_n"):   cfg_parts.append(f"[dim]sectorâ‰¤4:[/][white]{cfg_v['max_sec_n']}[/]")
    if cfg_v.get("base_risk"):   cfg_parts.append(f"[dim]risk:[/][white]{cfg_v['base_risk']}%[/]")
    if cfg_v.get("t1_r"):        cfg_parts.append(f"[dim]T1:[/][white]{cfg_v['t1_r']}R[/]")
    if cfg_v.get("pyramid"):     cfg_parts.append(f"[{G}]pyrOK[/]")
    if cfg_parts:
        rows.append(Text.from_markup("  ".join(cfg_parts)))
    rows.append(Rule(style="dim"))

    def _pc(v):
        if isinstance(v, list): return len(v)
        if isinstance(v, int):  return v
        return 0

    # Execution history summary âE" last 7 runs
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
            if s in ("success", "completed"): badges.append(f"[{G}]OK[/]")
            elif s == "halted":               badges.append(f"[{Y}]~[/]")
            else:                             badges.append(f"[{R}]X[/]")
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
                rows.append(Text.from_markup(f"  [{Y}]â†³ {body[:55]}[/]{ph_s}"))
        rows.append(Rule(style="dim"))

    # Current run status âE" shown prominently even when history is empty
    run_id = (run.get("run_id") or "") if run and not run.get("_error") else ""
    run_at = run.get("run_at") if run else None
    if not run_id and act and not act.get("_error"):
        run_id = (act.get("run_id") or "")[:26]
        run_at = act.get("run_at")
    if run_id:
        age_s  = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""
        r_stat = ""
        if run and not run.get("_error"):
            if run.get("success"):   r_stat = f"  [{G}]OK COMPLETED[/]"
            elif run.get("halted"):  r_stat = f"  [{Y}]~ HALTED[/]"
            elif run.get("errored"): r_stat = f"  [{R}]X ERROR[/]"
        rows.append(Text.from_markup(f"[dim]Run:[/] [white]{run_id[:30]}[/]{age_s}{r_stat}"))

        # Show phases_completed/halted/errored counts from the run object
        if run and not run.get("_error"):
            n_done = _pc(run.get("phases_completed"))
            n_hlt  = _pc(run.get("phases_halted"))
            n_err  = _pc(run.get("phases_errored"))
            if n_done + n_hlt + n_err > 0:
                done_s = f"[{G}]{n_done} phases OK[/]"
                hlt_s  = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
                err_s  = f"  [{R}]{n_err} errored[/]" if n_err else ""
                rows.append(Text.from_markup(f"  {done_s}{hlt_s}{err_s}"))

    # Phase detail âE" named phases from exec_log with per-phase status and key data
    phase_badges = []
    if run and not run.get("_error") and run.get("_source") == "exec_log":
        halt_r  = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"[{Y}]â†³ {prefix}{detail[:60]}[/]"))
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
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase data JSON: {e}")
                    pdata = {}
            if err and ps not in ("success", "completed", "ok"):
                rows.append(Text.from_markup(f"  [{sc}]â†³ {err[:62]}[/]"))
            elif ps in ("halt", "halted") and pdata:
                reason = (pdata.get("halt_reason") or pdata.get("reason") or "")[:55]
                if reason:
                    rows.append(Text.from_markup(f"  [{Y}]â†³ {reason}[/]"))
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
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse action details JSON: {e}")
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
            rows.append(Text.from_markup(f"[{G}]OK Data OK[/]  [dim]{len(hlth)} tables[/]"))
            crit = [r for r in hlth if r.get("role") == "CRIT"]
            if crit:
                crit_parts = "  ".join(f"[{G}]OK[/][dim]{r.get('tbl','')[:13]}[/]" for r in crit)
                rows.append(Text.from_markup(f"  {crit_parts}"))
        else:
            for r in stale[:4]:
                nm  = (r.get("tbl") or "--")[:10]
                age = r.get("age") or "?"
                rc  = r.get("role", "")
                cc  = "bold white" if rc == "CRIT" else "white"
                lat = r.get("latest")
                lat_s = f" ({lat.strftime('%m/%d') if hasattr(lat, 'strftime') else str(lat)[:5]})" if lat else ""
                rows.append(Text.from_markup(f"[{R}]X[/] [{cc}]{nm:<10}[/] [dim]{age}d stale{lat_s}[/]"))

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
            unread = "-" if not n.get("seen", True) else " "
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
            rows.append(Text.from_markup(f"[{G}]OK Loaders[/]  [dim]{ok_count} feeds healthy[/]"))

    # Audit log âE" most recent notable actions
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


@register_panel("health", endpoint_deps=["run", "activity", "health", "notifs", "algo_metrics", "audit", "exec_hist", "risk"], optional=True, description="Health")
def panel_algo_health(run, act, hlth, notifs, algo_metrics=None, loader=None, audit=None, exec_hist=None, risk=None):
    """Focused 'did the algo work?' panel: run outcome â†' what it did â†' system health."""
    rows: list = []

    # Extract items from data dicts and check for errors
    hlth_items = hlth.get("items", []) if isinstance(hlth, dict) and "items" in hlth else (hlth if isinstance(hlth, list) else [])
    hlth_error = hlth.get("_error") if isinstance(hlth, dict) else None
    algo_metrics_items = algo_metrics.get("items", []) if isinstance(algo_metrics, dict) and "items" in algo_metrics else (algo_metrics if isinstance(algo_metrics, list) else [])
    algo_metrics_error = algo_metrics.get("_error") if isinstance(algo_metrics, dict) else None
    loader_items = loader.get("items", []) if isinstance(loader, dict) and "items" in loader else (loader if isinstance(loader, list) else [])
    loader_error = loader.get("_error") if isinstance(loader, dict) else None
    audit_items = audit.get("items", []) if isinstance(audit, dict) and "items" in audit else (audit if isinstance(audit, list) else [])
    audit_error = audit.get("_error") if isinstance(audit, dict) else None
    exec_hist_items = exec_hist.get("items", []) if isinstance(exec_hist, dict) and "items" in exec_hist else (exec_hist if isinstance(exec_hist, list) else [])
    exec_hist_error = exec_hist.get("_error") if isinstance(exec_hist, dict) else None

    # ── A: Run outcome ────────────────────────────────────────────────────────
    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_at    = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    age_s     = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid:
        if run.get("success") and not run.get("halted"):
            sts = f"[bold {G}]OK COMPLETED[/]"
        elif run.get("halted"):
            sts = f"[bold {Y}]~ HALTED[/]"
        elif run.get("errored"):
            sts = f"[bold {R}]X ERROR[/]"
        else:
            sts = "[dim]UNKNOWN[/]"
        rid = (run.get("run_id") or "")[:28]
        rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r  = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"  [{Y}]â†³ {prefix}{detail[:80]}[/]"))
        elif summary:
            rows.append(Text.from_markup(f"  [dim]{summary[:72]}[/]"))
    elif act_valid:
        rows.append(Text.from_markup(f"[dim]Last run (audit):[/]  [dim]{fmt_age(run_at)}[/]"))
    else:
        rows.append(Text.from_markup("[dim]No run data - algo has not run yet[/]"))

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
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase metrics data JSON: {e}")
                    pdata = {}
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

    # "What did the algo do today?" summary âE" the core insight
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
            d_s = d.strftime("%d") if hasattr(d, "strftime") else str(d or "")[-2:]
            en  = int(m.get("entries") or 0)
            ex  = int(m.get("exits")   or 0)
            e_c = G if en > 0 else DIM
            x_c = Y if ex > 0 else DIM
            day_parts.append(f"[dim]{d_s}:[/][{e_c}]{en}â-²[/][{x_c}]{ex}â-¼[/]")
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
            badges.append(f"[{G}]OK[/]" if s in ("success", "completed") else (f"[{Y}]~[/]" if s == "halted" else f"[{R}]X[/]"))
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
                rows.append(Text.from_markup(f"  [{Y}]â†³ {body[:68]}[/]{ph_s}"))

    rows.append(Rule(style="dim"))

    # ── D: Data health (compact) ──────────────────────────────────────────────
    if hlth:
        hlth_list = [r for r in hlth if isinstance(r, dict)]
        stale = [r for r in hlth_list if r.get("st") != "ok"]
        if not stale:
            crit  = [r for r in hlth_list if r.get("role") == "CRIT"]
            ok_s  = "  ".join(f"[{G}]OK[/][dim]{r.get('tbl','')[:10]}[/]" for r in crit[:5])
            rows.append(Text.from_markup(f"[{G}]OK Data OK[/]  [dim]{len(hlth_list)} tables[/]  {ok_s}"))
        else:
            stale_parts = []
            for r in stale[:5]:
                nm  = (r.get("tbl") or "--")[:9]
                age = r.get("age") or "?"
                cc  = "bold white" if r.get("role") == "CRIT" else "white"
                stale_parts.append(f"[{R}]X[/][{cc}]{nm}[/][dim]{age}d[/]")
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
        rows.append(Text.from_markup(f"[dim]Loaders:[/] [{G}]OK {ok_count} healthy[/]"))

    # ── E: Risk snapshot (VaR / CVaR / Beta / Concentration) ────────────────────
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        rows.append(Rule(style="dim"))
        beta_c = R if (risk.get("beta") or 0) >= 1.2 else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        conc_c = R if (risk.get("conc5") or 0) >= 35 else (Y if (risk.get("conc5") or 0) >= 25 else "white")
        risk_parts = [
            f"[dim]VaR 95%:[/][white]{risk.get('var95', 0):.2f}%[/]",
            f"[dim]CVaR 95%:[/][white]{risk.get('cvar95', 0):.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{risk.get('beta', 0):.2f}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{risk.get('conc5', 0):.0f}%[/]",
        ]
        if risk.get("svar") and float(risk.get("svar") or 0) > 0:
            risk_parts.append(f"[dim]Stressed VaR:[/][{R}]{risk.get('svar', 0):.2f}%[/]")
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
            unread = "-" if not n.get("seen", True) else "Â·"
            notif_parts.append(f"[{sc}]{unread}{title}[/][dim]{age}[/]")
        rows.append(Text.from_markup("[dim]Alerts:[/] " + "  ".join(notif_parts)))

    if not rows:
        rows.append(Text("no activity", style="dim"))
    return Panel(Group(*rows), title="[bold yellow]ALGO HEALTH[/]  [dim][h] expand[/]", border_style="yellow", padding=(0, 1))


# ── mascot panel (compact âE" dancing man only) ────────────────────────────────
# MASCOT_W defined above in the mascot section.
# MASCOT_H = 1 top border + 1 blank + 4 pose lines + 1 blank + 1 bottom border = 8

MASCOT_H = 8


def mascot_compact(data: dict, frame: int) -> Panel:
    fi   = mascot_pose(data, frame)
    mc   = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    # No justify= âE" strings are pre-padded to exactly 11 chars (panel content width).
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


# ── loading layout âE" mascot compact in top-right ──────────────────────────────

def loading_layout(frame: int, data_source: str = "AWS") -> Layout:
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

    source_color = "cyan" if data_source == "LOCAL" else "dim"
    hdr_text = Text.from_markup(
        f"[bold white]ALGO OPS DASHBOARD[/]  [dim]{dots}[/]  [{source_color}]{data_source}[/]"
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


@register_panel("signals_expanded", endpoint_deps=["sig", "sig_eval"], optional=True, description="Signals Expanded")
def panel_signals_expanded(sig, sig_eval=None):
    """Full-screen buy signals - all signals, full text, breakout quality, base type."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel

    # Check if placeholder/fallback data is being displayed
    is_placeholder = sig.get("_is_placeholder") or sig.get("_is_fallback_data")

    raw   = sig.get("n", 0)
    total = sig.get("total", 0)
    d     = sig.get("date")
    ds    = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
    g     = sig.get("grades") or {}
    ga, gb, gc, gd = (int(g.get(k)) if g.get(k) is not None else None for k in ("a", "b", "c", "d"))
    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))
    rows = [Text.from_markup(
        f"[{buy_c}][bold]{raw} BUY SIGNALS[/][/]  [dim]from {total} screened  {ds}[/]  "
        f"[{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]  "
        f"[dim]press [/][bold magenta]s[/][dim] to return[/]"
    )]

    top_a = sig.get("top_a") or []
    if top_a:
        parts = []
        for s in top_a:
            sc = float(s.get("score")) if s.get("score") is not None else None
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{s.get('symbol','')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{s.get('symbol','')}[/][dim]--[/]")
        rows.append(Text.from_markup("[dim]A-grade radar:[/] " + "  ".join(parts)))

    if sig_eval and not sig_eval.get("_error"):
        ev_tot = sig_eval.get("total", 0); ev_t5 = sig_eval.get("t5", 0); ev_avg = sig_eval.get("avg_score", 0)
        ev_c = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
        funnel = (f"[dim]Funnel  T1:[/]{sig_eval.get('t1',0)} [dim]T2:[/]{sig_eval.get('t2',0)} "
                  f"[dim]T3:[/]{sig_eval.get('t3',0)} [dim]T4:[/]{sig_eval.get('t4',0)} "
                  f"[dim]T5:[/][{ev_c}]{ev_t5}[/][dim]/{ev_tot}  avg score:[/]{ev_avg:.0f}")
        rejected = sig_eval.get("rejected") or []
        if rejected:
            block_items = []
            for rj in rejected:
                reason_full = rj['evaluation_reason'][:32]
                description = rj.get('description', '')
                if description:
                    block_items.append(f"[dim]{reason_full}:{rj['n']}[/] [bright_black]({description[:40]})[/]")
                else:
                    block_items.append(f"[dim]{reason_full}:{rj['n']}[/]")
            blocks = "  ".join(block_items)
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
        rows.append(Text.from_markup("[dim]Near BUY threshold (swing score 55-69):[/]"))
        parts = []
        for a in near:
            sc = float(a.get('score')) if a.get('score') is not None else None
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            parts.append(f"[{CY}]{a['symbol']}[/][dim] {sc_s}[/]")
        for i in range(0, len(parts), 4):
            rows.append(Text.from_markup("  " + "    ".join(parts[i:i+4])))

    # Add placeholder warning if needed
    if is_placeholder:
        rows.insert(0, Text.from_markup("[bold red]📊 PLACEHOLDER DATA - Signals may not be accurate[/]"))

    border = "red" if is_placeholder else "magenta"
    title = "[bold red]BUY SIGNALS ⚠ PLACEHOLDER DATA[/]" if is_placeholder else "[bold magenta]BUY SIGNALS - EXPANDED[/]"
    return Panel(Group(*rows), title=f"{title}  [dim][s] return[/]", border_style=border, padding=(0, 1))


@register_panel("health_expanded", endpoint_deps=["run", "activity", "health", "notifs", "algo_metrics", "audit", "exec_hist", "risk"], optional=True, description="Health Expanded")
def panel_algo_health_expanded(run, act, hlth, notifs, algo_metrics=None, loader=None, audit=None, exec_hist=None, risk=None):
    """Full-screen algo health - complete run history, all data tables, all notifications."""
    rows: list = [Text.from_markup("[dim]press [/][bold yellow]h[/][dim] to return to dashboard[/]"), Rule(style="dim")]

    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_at    = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    age_s     = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid:
        sts = (f"[bold {G}]OK COMPLETED[/]" if run.get("success") and not run.get("halted")
               else (f"[bold {Y}]~ HALTED[/]" if run.get("halted")
               else f"[bold {R}]X ERROR[/]"))
        rid = (run.get("run_id") or "")
        rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r  = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"  [{Y}]â†³ {prefix}{detail}[/]"))
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

    # Full run history âE" all runs, untruncated halt reasons, with timestamps
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
            hr_s = f"  [{Y}]â†³ {body}[/]{ph_s}" if body else ""
            rows.append(Text.from_markup(f"  [{ic}]{ii}[/] [dim]{dt_s}[/]  [{ic}]{s}[/]{hr_s}"))

    rows.append(Rule(style="dim"))

    # All data tables âE" ok and stale, with role and date
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
        beta_c = R if (risk.get("beta") or 0) >= 1.2 else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        conc_c = R if (risk.get("conc5") or 0) >= 35 else (Y if (risk.get("conc5") or 0) >= 25 else "white")
        risk_parts = [
            f"[dim]VaR 95%:[/][white]{risk.get('var95', 0):.2f}%[/]",
            f"[dim]CVaR 95%:[/][white]{risk.get('cvar95', 0):.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{risk.get('beta', 0):.2f}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{risk.get('conc5', 0):.0f}%[/]",
        ]
        if risk.get("svar") and float(risk.get("svar") or 0) > 0:
            risk_parts.append(f"[dim]Stressed VaR:[/][{R}]{risk.get('svar', 0):.2f}%[/]")
        rows.append(Text.from_markup("  ".join(risk_parts)))

    # All notifications âE" untruncated titles
    valid_notifs = notifs if (notifs and not (isinstance(notifs, dict) and notifs.get("_error"))) else []
    if valid_notifs:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Notifications:[/]"))
        SEV_C = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        for n in valid_notifs:
            sc     = SEV_C.get(n.get("severity", "info"), DIM)
            title  = n.get("title") or ""
            age    = fmt_age(n.get("created_at"))
            unread = "-" if not n.get("seen", True) else "Â·"
            rows.append(Text.from_markup(f"  [{sc}]{unread} {title}[/] [dim]{age}[/]"))

    return Panel(Group(*rows), title="[bold yellow]ALGO HEALTH - EXPANDED[/]  [dim][h] return[/]", border_style="yellow", padding=(0, 1))


@register_panel("sectors_expanded", endpoint_deps=["srank", "pos", "port", "sec_rot", "irank"], optional=True, description="Sectors Expanded")
def panel_sectors_expanded(srank, pos, port, sec_rot=None, irank=None):
    """Full-screen sectors - all sector and industry rankings, full portfolio breakdown."""
    rows: list = [Text.from_markup("[dim]press [/][bold cyan]r[/][dim] to return to dashboard[/]"), Rule(style="dim")]

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
    # Issue 3.1 FIX: Use unified normalization function
    pos_list, _, _ = normalize_positions_data(pos)
    if pos_list:
        pv = float(port.get("total_portfolio_value") or 0)
        sd: dict = {}
        invalid_count = 0
        for p in pos_list:
            if not isinstance(p, dict):
                invalid_count += 1
                logger.error(f"panel_sectors_expanded: invalid position (not a dict): {type(p).__name__}")
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
            logger.error(f"panel_sectors_expanded: encountered {invalid_count} invalid position(s); sector totals may be incomplete")
        sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])
        rows.append(Text.from_markup("[dim]Portfolio by sector:[/]"))
        for sec, dv in sorted_secs:
            pct     = dv["val"] / pv * 100 if pv else 0
            avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
            pc      = G if avg_pnl >= 0 else R
            bar_f   = int(min(pct, 25) / 25 * 8)
            bar_s   = f"[{pc}]{'#' * bar_f}[/][dim]{'-' * (8 - bar_f)}[/]"
            rows.append(Text.from_markup(
                f"  [white]{sec:<24}[/]{bar_s} [dim]{pct:.1f}%  {dv['n']} pos[/]  [{pc}]{sign(avg_pnl)}{avg_pnl:.1f}% avg P&L[/]"
            ))
        rows.append(Rule(style="dim"))

    # All sector rankings âE" one per row, full names, 1wk and 4wk changes
    valid_srank = [r for r in (srank or []) if not (isinstance(srank, dict) and srank.get("_error"))]
    if valid_srank:
        rows.append(Text.from_markup("[dim]All sectors  (rank  momentum  â-²â-¼1wk/4wk):[/]"))
        for r in valid_srank:
            nm  = r.get("sector_name") or ""
            mm  = r.get("momentum_score")
            ms  = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rows.append(Text.from_markup(
                f"  [{G}]#{r['current_rank']:<2}[/]  [white]{nm:<28}[/]{ms}  {_rdelta(r, wk4='rank_4w_ago')}"
            ))
        rows.append(Rule(style="dim"))

    # All industries âE" full names, 1wk change
    valid_irank = irank if (irank and not (isinstance(irank, dict) and irank.get("_error"))) else []
    if valid_irank:
        rows.append(Text.from_markup("[dim]All industries  (rank  momentum  â-²â-¼1wk):[/]"))
        for r in valid_irank:
            nm  = r.get("industry") or ""
            mm  = r.get("momentum_score")
            ms  = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rows.append(Text.from_markup(
                f"  [{CY}]#{r['current_rank']:<2}[/]  [white]{nm:<32}[/]{ms}  {_rdelta(r)}"
            ))

    if not rows:
        return Panel(Text("no data", style="dim"), title="[bold]SECTORS[/]", border_style="cyan", padding=(0, 1))
    return Panel(Group(*rows), title="[bold cyan]SECTORS & INDUSTRIES - EXPANDED[/]  [dim][r] return[/]", border_style="cyan", padding=(0, 1))


def _extract_items(data: Any) -> list:
    """Normalize data structure by extracting items list, propagating errors.

    Handles both formats:
    - {"_error": "..."} → {"_error": "..."} (propagate error)
    - {"items": [...]} → [...]
    - [...] → [...]
    - {} or None → []
    """
    if isinstance(data, dict):
        if data.get("_error"):
            return data
        return data.get("items", []) if "items" in data else []
    if isinstance(data, list):
        return data
    return []


# ── dashboard layout ──────────────────────────────────────────────────────────

