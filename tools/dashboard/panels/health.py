"""Health and orchestration panel functions."""

import json
import logging

logger = logging.getLogger(__name__)

try:
    from panel_registry import register_panel
except ImportError as e:
    logger.warning(f"Panel registry not available: {e} - panels will not auto-register")
    def register_panel(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from data_validation import safe_float

from utilities import (
    MASCOT_W,
    MASCOT_FRAMES,
    MASCOT_COLORS,
    LOAD_SEQ,
    PHASE_NAMES,
    TIER_COLOR,
    TIER_SHORT,
    G,
    R,
    Y,
    CY,
    DIM,
)
from formatters import (
    fmt_age,
    fmt_money,
    fmt_money_short,
    tier_from_pct,
    hbar,
    exp_bar,
    mini_bar,
    sign,
    sparkline,
    next_run_str,
)

from ._helpers import (
    _error_panel,
    _score_cell,
    _build_buy_sig_map,
    _swing_cell,
    _composite_score_color,
    _best_halt_reason,
    _fmt_phases_halted,
)


def panel_orch(run, cfg, risk=None):
    next_run = next_run_str()
    mode = cfg.get("mode", "?")
    mc2 = G if "LIVE" in mode else Y
    en = "ENABLED" if cfg.get("enabled", True) else "DISABLED"
    ec = G if cfg.get("enabled", True) else R
    max_n = cfg.get("max_pos_n")
    max_sec_n = cfg.get("max_sec_n")
    min_score = cfg.get("min_score")
    base_risk = cfg.get("base_risk")
    t1r = cfg.get("t1_r")

    score_s = (
        f"[dim]min score ≥[/][white]{min_score}[/]"
        if min_score and float(min_score) > 0
        else ""
    )
    slots_s = f"[dim]max [/][white]{max_n}[/][dim] positions[/]" if max_n else ""
    sec_s = f"[dim]sector ≤[/][white]{max_sec_n}[/]" if max_sec_n else ""
    risk_s = f"[dim]base risk [/][white]{base_risk}%[/]" if base_risk else ""
    t1r_s = f"[dim]T1 target [/][white]{t1r}R[/]" if t1r else ""
    config_line = "  ".join(x for x in [score_s, slots_s, sec_s, risk_s, t1r_s] if x)

    # VaR line — only show if table is populated with real data
    var_line = ""
    if (
        risk
        and not risk.get("_error")
        and risk.get("var95")
        and float(risk.get("var95") or 0) > 0
    ):
        beta_c = (
            R
            if (risk.get("beta") or 0) >= 1.2
            else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        )
        var_c = R if (risk.get("var95") or 0) >= 4 else (Y if (risk.get("var95") or 0) >= 2 else "white")
        svar_s = (
            f"\n[dim]Stressed VaR:[/][{R}]{(risk.get('svar') or 0):.2f}%[/]"
            if risk.get("svar") and float(risk.get("svar") or 0) > 0
            else ""
        )
        var_line = (
            f"\n[dim]VaR 95%:[/][{var_c}]{(risk.get('var95') or 0):.2f}%[/]"
            f"  [dim]CVaR 95%:[/][{var_c}]{(risk.get('cvar95') or 0):.2f}%[/]"
            f"  [dim]Portfolio Beta:[/][{beta_c}]{(risk.get('beta') or 0):.2f}[/]"
            f"  [dim]Top-5 Conc:[/][white]{(risk.get('conc5') or 0):.0f}%[/]" + svar_s
        )

    if not run or run.get("_error"):
        error_msg = (
            f"[{R}]run fetch failed[/]: {run.get('_error')}"
            if isinstance(run, dict) and run.get("_error")
            else "[dim]run: no data[/]"
        )
        body = Text.from_markup(
            f"{error_msg}\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next run:[/] [white]{next_run}[/]" + var_line
        )
    else:
        age = fmt_age(run.get("run_at"))
        sts = (
            "[bold bright_green]✓ COMPLETED[/]"
            if run.get("success") and not run.get("halted")
            else (
                "[bold yellow]~ HALTED[/]"
                if run.get("halted")
                else "[bold bright_red]✗ ERROR[/]"
            )
        )

        pbadges = []
        # exec_log source: structured per-phase objects with names + statuses
        if run.get("_source") == "exec_log":
            for p in run.get("phase_results") or []:
                raw = (p.get("name") or p.get("phase", "")).lower()
                parts = raw.split("_")
                base = "_".join(parts[:2]) if len(parts) >= 2 else raw
                short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
                ps = (p.get("status") or "").lower()
                pc = (
                    G
                    if ps in ("success", "completed")
                    else (Y if ps in ("halt", "halted", "warn") else R)
                )
                pi = (
                    "✓"
                    if ps in ("success", "completed")
                    else ("~" if ps in ("halt", "halted", "warn") else "✗")
                )
                pbadges.append(f"[{pc}]{pi}{short}[/]")
            # Show halt reason if halted
            halt_r = run.get("halt_reason") or ""
            summary = run.get("summary") or ""
            if halt_r or run.get("halted"):
                _details = _best_halt_reason(halt_r, run.get("phase_results"))
                _lines = [f"{lb+': ' if lb else ''}{dt[:60]}" for lb, dt in _details]
                extra = (
                    ("\n" + "\n".join(f"[{Y}]{ln}[/]" for ln in _lines))
                    if _lines
                    else ""
                )
            else:
                extra = f"\n[dim]{summary[:50]}[/]" if summary else ""
        else:
            # audit_log fallback: phase_N or phase_N_name format
            for p in (run.get("phase_results") or run.get("phases") or []):
                at = p.get("action_type", "")
                if not at.startswith("phase_"):
                    continue
                parts = at.split("_")
                num = parts[1] if len(parts) > 1 else "?"
                if not num.isdigit():
                    continue
                phase_key = f"phase_{num}"
                name_parts = parts[2:] if len(parts) > 2 else []
                default_short = "_".join(name_parts)[:7] if name_parts else f"P{num}"
                short = PHASE_NAMES.get(phase_key, default_short)[:9]
                ps = p.get("status", "")
                pc = G if ps == "success" else (Y if ps in ("halt", "warn") else R)
                pi = (
                    "✓" if ps == "success" else ("~" if ps in ("halt", "warn") else "✗")
                )
                pbadges.append(f"[{pc}]{pi}{short}[/]")
            extra = ""

        phases_str = "  ".join(pbadges) if pbadges else "[dim]──[/]"
        body = Text.from_markup(
            f"{sts}  [dim]{age}[/]\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next run:[/] [white]{next_run}[/]\n"
            f"{phases_str}" + extra + var_line
        )
    return Panel(
        body, title="[bold cyan]ORCHESTRATOR[/]", border_style="cyan", padding=(0, 1)
    )




def panel_status(
    act,
    hlth,
    notifs,
    algo_metrics=None,
    loader=None,
    audit=None,
    run=None,
    exec_hist=None,
    cfg=None,
):
    """Algo activity phases + data health + recent notifications + action counts + loader status."""
    rows: list = []

    # Extract items from data dicts
    hlth_items = (
        hlth.get("items", [])
        if isinstance(hlth, dict) and "items" in hlth
        else (hlth if isinstance(hlth, list) else [])
    )

    # ── Run status + schedule + mode + trading config ────────────────────────────
    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_id_top = (
        (run.get("run_id") or "")
        if run_valid
        else ((act.get("run_id") or "") if act_valid else "")
    )
    run_at_top = (
        run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    )
    if run_id_top or run_at_top:
        sts = (
            "[bold bright_green]✓ COMPLETED[/]"
            if (run_valid and run.get("success") and not run.get("halted"))
            else (
                "[bold yellow]~ HALTED[/]"
                if (run_valid and run.get("halted"))
                else (
                    "[bold bright_red]✗ ERROR[/]"
                    if (run_valid and run.get("errored"))
                    else "[dim]RUN[/]"
                )
            )
        )
        age_s = f"  [dim]{fmt_age(run_at_top)}[/]" if run_at_top else ""
        rows.append(Text.from_markup(f"{sts}{age_s}"))
    cfg_v = cfg or {}
    mode = cfg_v.get("mode", "")
    en = cfg_v.get("enabled", True)
    mc = G if "LIVE" in str(mode) else Y
    ec = G if en else R
    en_s = "ENABLED" if en else "DISABLED"
    next_r = next_run_str()
    rows.append(
        Text.from_markup(
            f"[{mc}]{mode or 'PAPER'}[/]  [{ec}]{en_s}[/]  [dim]Next run:[/] [white]{next_r}[/]"
        )
    )
    # Trading config params — visible context for position sizing decisions
    cfg_parts = []
    if cfg_v.get("max_pos_n"):
        cfg_parts.append(f"[dim]slots:[/][white]{cfg_v['max_pos_n']}[/]")
    if cfg_v.get("max_sec_n"):
        cfg_parts.append(f"[dim]sector≤4:[/][white]{cfg_v['max_sec_n']}[/]")
    if cfg_v.get("base_risk"):
        cfg_parts.append(f"[dim]risk:[/][white]{cfg_v['base_risk']}%[/]")
    if cfg_v.get("t1_r"):
        cfg_parts.append(f"[dim]T1:[/][white]{cfg_v['t1_r']}R[/]")
    if cfg_parts:
        rows.append(Text.from_markup("  ".join(cfg_parts)))
    rows.append(Rule(style="dim"))

    def _pc(v):
        if isinstance(v, list):
            return len(v)
        if isinstance(v, int):
            return v
        return 0

    # Execution history summary — last 7 runs
    valid_hist = (
        exec_hist
        if (exec_hist and not (isinstance(exec_hist, dict) and exec_hist.get("_error")))
        else []
    )
    if valid_hist:
        n_ok = sum(
            1
            for r in valid_hist
            if (r.get("overall_status") or "").lower() in ("success", "completed")
        )
        n_hlt = sum(
            1 for r in valid_hist if (r.get("overall_status") or "").lower() == "halted"
        )
        n_err = sum(
            1
            for r in valid_hist
            if (r.get("overall_status") or "").lower() in ("error", "failed")
        )
        total_h = len(valid_hist)
        wr_h = n_ok / total_h * 100 if total_h else 0
        wc_h = G if wr_h >= 80 else (Y if wr_h >= 50 else R)
        badges = []
        for r in valid_hist[:7]:
            s = (r.get("overall_status") or "").lower()
            if s in ("success", "completed"):
                badges.append(f"[{G}]OK[/]")
            elif s == "halted":
                badges.append(f"[{Y}]~[/]")
            else:
                badges.append(f"[{R}]X[/]")
        rows.append(
            Text.from_markup(
                f"[dim]Last {total_h} runs:[/] {''.join(badges)}"
                f"  [{wc_h}]{n_ok}/{total_h} success[/]"
                + (f"  [{Y}]{n_hlt} halted[/]" if n_hlt else "")
                + (f"  [{R}]{n_err} error[/]" if n_err else "")
            )
        )
        last_halt = next(
            (
                r
                for r in valid_hist
                if (r.get("overall_status") or "").lower() == "halted"
            ),
            None,
        )
        if last_halt:
            lhr = last_halt.get("halt_reason") or ""
            lph = _fmt_phases_halted(last_halt.get("phases_halted"))
            body = lhr or lph
            if body:
                ph_s = f"  [dim]({lph})[/]" if lph and lph not in lhr else ""
                rows.append(Text.from_markup(f"  [{Y}]a†³ {body[:55]}[/]{ph_s}"))
        rows.append(Rule(style="dim"))

    # Current run status — shown prominently even when history is empty
    run_id = (run.get("run_id") or "") if run and not run.get("_error") else ""
    run_at = run.get("run_at") if run else None
    if not run_id and act and not act.get("_error"):
        run_id = (act.get("run_id") or "")[:26]
        run_at = act.get("run_at")
    if run_id:
        age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""
        r_stat = ""
        if run and not run.get("_error"):
            if run.get("success"):
                r_stat = f"  [{G}]OK COMPLETED[/]"
            elif run.get("halted"):
                r_stat = f"  [{Y}]~ HALTED[/]"
            elif run.get("errored"):
                r_stat = f"  [{R}]X ERROR[/]"
        rows.append(
            Text.from_markup(f"[dim]Run:[/] [white]{run_id[:30]}[/]{age_s}{r_stat}")
        )

        # Show phases_completed/halted/errored counts from the run object
        if run and not run.get("_error"):
            n_done = _pc(run.get("phases_completed"))
            n_hlt = _pc(run.get("phases_halted"))
            n_err = _pc(run.get("phases_errored"))
            if n_done + n_hlt + n_err > 0:
                done_s = f"[{G}]{n_done} phases OK[/]"
                hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
                err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
                rows.append(Text.from_markup(f"  {done_s}{hlt_s}{err_s}"))

    # Phase detail — named phases from exec_log with per-phase status and key data
    phase_badges = []
    if run and not run.get("_error") and run.get("_source") == "exec_log":
        halt_r = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"[{Y}]a†³ {prefix}{detail[:60]}[/]"))
        elif summary and isinstance(summary, str):
            rows.append(Text.from_markup(f"[dim]{summary[:65]}[/]"))

        phase_results = run.get("phase_results") or []
        for p in phase_results:
            raw = (p.get("name") or p.get("phase", "")).lower()
            parts = raw.split("_")
            base = "_".join(parts[:2]) if len(parts) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
            ps = (p.get("status") or "").lower()
            sc = (
                G
                if ps in ("success", "completed", "ok")
                else (
                    Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R
                )
            )
            si = (
                "✓"
                if ps in ("success", "completed", "ok")
                else (
                    "~"
                    if ps in ("halt", "halted", "warn", "degraded", "skipped")
                    else "✗"
                )
            )
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

            # Show error or key data for failed/halted phases
            err = p.get("error") or ""
            pdata = p.get("data") or {}
            if isinstance(pdata, str):
                try:
                    pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase data JSON: {e}")
                    pdata = {}
            if err and ps not in ("success", "completed", "ok"):
                rows.append(Text.from_markup(f"  [{sc}]a†³ {err[:62]}[/]"))
            elif ps in ("halt", "halted") and pdata:
                reason = (pdata.get("halt_reason") or pdata.get("reason") or "")[:55]
                if reason:
                    rows.append(Text.from_markup(f"  [{Y}]a†³ {reason}[/]"))
            elif ps in ("success", "completed", "ok") and pdata:
                # Surface a key metric per phase if available
                for key in (
                    "signals_generated",
                    "entries_executed",
                    "exits_executed",
                    "positions_checked",
                    "orders_placed",
                    "symbols_checked",
                    "trades_executed",
                    "checks_passed",
                    "score",
                ):
                    val = pdata.get(key)
                    if val is not None:
                        rows.append(
                            Text.from_markup(
                                f"  [dim]{short}:[/] [white]{key.replace('_', ' ')}={val}[/]"
                            )
                        )
                        break

        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

        n_ok = _pc(run.get("phases_completed"))
        n_hlt = _pc(run.get("phases_halted"))
        n_err = _pc(run.get("phases_errored"))
        if n_ok + n_hlt + n_err > 0:
            ok_s = f"[{G}]{n_ok} phases done[/]"
            hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
            err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
            rows.append(Text.from_markup(f"  {ok_s}{hlt_s}{err_s}"))
    elif act and not act.get("_error"):
        for p in act.get("phases") or []:
            at = p.get("action_type", "")
            if not at.startswith("phase_"):
                continue
            parts = at.split("_")
            num = parts[1] if len(parts) > 1 else "?"
            if not num.isdigit():
                continue
            phase_key = f"phase_{num}"
            name_parts = parts[2:] if len(parts) > 2 else []
            default_short = "_".join(name_parts)[:7] if name_parts else f"P{num}"
            short = PHASE_NAMES.get(phase_key, default_short)[:9]
            st = p.get("status", "")
            sc = (
                G if st == "success" else (Y if st in ("halt", "warn", "halted") else R)
            )
            si = (
                "✓"
                if st == "success"
                else ("~" if st in ("halt", "warn", "halted") else "✗")
            )
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

    # Recent trade events (entry/exit/order) from audit_log
    recent = (
        (act.get("recent_actions") or []) if (act and not act.get("_error")) else []
    )
    trade_evts = [
        a
        for a in recent
        if a.get("action_type")
        in (
            "entry_executed",
            "exit_executed",
            "entry_rejected",
            "position_exited",
            "order_placed",
            "order_rejected",
        )
    ]
    for a in trade_evts[:4]:
        at = a.get("action_type", "")
        det = a.get("details") or {}
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse action details JSON: {e}")
                det = {}
        sym = det.get("symbol", "")
        ic = (
            G
            if ("executed" in at or at == "position_exited")
            else (Y if "placed" in at else R)
        )
        lbl = at.replace("_", " ").title()[:20]
        rows.append(Text.from_markup(f"  [{ic}]{lbl}{(' ' + sym) if sym else ''}[/]"))

    # Data health (stale tables only)
    if hlth_items:
        rows.append(Rule(style="dim"))
        stale = [r for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok"]
        if not stale:
            rows.append(
                Text.from_markup(
                    f"[{G}]OK Data OK[/]  [dim]{len(hlth_items)} tables[/]"
                )
            )
            crit = [
                r for r in hlth_items if isinstance(r, dict) and r.get("role") == "CRIT"
            ]
            if crit:
                crit_parts = "  ".join(
                    f"[{G}]OK[/][dim]{r.get('tbl','')[:13]}[/]" for r in crit
                )
                rows.append(Text.from_markup(f"  {crit_parts}"))
        else:
            for r in stale[:4]:
                nm = str((r.get("tbl") or "--")[:13])
                age_hours = r.get("age_hours")
                age_days = r.get("age")
                if age_hours is not None:
                    age_s = f"{age_hours:.0f}h" if age_hours < 24 else f"{age_hours / 24:.1f}d"
                elif age_days is not None:
                    age_s = f"{float(age_days):.1f}d"
                else:
                    age_s = "?"
                rc = r.get("role", "")
                cc = "bold white" if rc == "CRIT" else "white"
                lat = r.get("last_updated") or r.get("latest")
                if hasattr(lat, "strftime"):
                    lat_s = f" ({lat.strftime('%m/%d')})"
                elif isinstance(lat, str) and len(lat) >= 10:
                    lat_s = f" ({lat[5:10]})"
                else:
                    lat_s = f" ({str(lat)[:5]})" if lat else ""
                rows.append(
                    Text.from_markup(
                        f"[{R}]X[/] [{cc}]{nm:<13}[/] [dim]{age_s} stale{lat_s}[/]"
                    )
                )

    # Notifications (up to 4)
    valid_notifs = (
        notifs
        if (notifs and not (isinstance(notifs, dict) and notifs.get("_error")))
        else []
    )
    if valid_notifs:
        rows.append(Rule(style="dim"))
        SEV_C = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        _SHORT = {
            "trading halted by circuit": "Halted: CB",
            "circuit breaker": "CB fired",
            "position entered": "Entered",
            "position exited": "Exited",
            "daily loss limit": "DailyLoss",
            "max drawdown": "MaxDD hit",
        }
        for n in valid_notifs[:4]:
            sc = SEV_C.get(n.get("severity", "info"), DIM)
            raw_t = n.get("title") or ""
            tl = raw_t.lower()
            title = next((v for k, v in _SHORT.items() if k in tl), raw_t[:24])
            age = fmt_age(n.get("created_at"))
            unread = "-" if not n.get("seen", True) else " "
            rows.append(
                Text.from_markup(f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]")
            )

    # Algo metrics daily (action counts)
    valid_metrics = (
        algo_metrics
        if (
            algo_metrics
            and not (isinstance(algo_metrics, dict) and algo_metrics.get("_error"))
        )
        else []
    )
    if valid_metrics:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Daily trade activity:[/]"))
        for m in valid_metrics[:5]:
            d = m.get("date")
            d_s = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
            ta = int(m.get("total_actions") or 0)
            en = int(m.get("entries") or 0)
            ex = int(m.get("exits") or 0)
            rows.append(
                Text.from_markup(
                    f"  [dim]{d_s}:[/] [white]{ta}[/][dim] total actions,  [/][{G}]{en}[/][dim] entries  [/][{R}]{ex}[/][dim] exits[/]"
                )
            )

    # Data loader status (errors/stale from data_loader_status table)
    valid_loader = (
        loader
        if (loader and not (isinstance(loader, dict) and loader.get("_error")))
        else []
    )
    problem_loader = [
        r
        for r in valid_loader
        if (r.get("status") or "") in ("error", "failed", "stale")
    ]
    running_loader = [r for r in valid_loader if (r.get("status") or "") == "loading"]
    ok_count = len(valid_loader) - len(problem_loader) - len(running_loader)
    if problem_loader:
        rows.append(Rule(style="dim"))
        ok_s = f"  [dim]{ok_count} ok[/]" if ok_count > 0 else ""
        rows.append(
            Text.from_markup(f"[{Y}]Loaders ({len(problem_loader)} issues){ok_s}:[/]")
        )
        for r in problem_loader[:3]:
            nm = str((r.get("table_name") or "--")[:14])
            st = r.get("status") or "?"
            age = r.get("age_days")
            age_s = str(f"{int(age)}d" if age is not None else "--")
            sc = R if st in ("error", "failed") else Y
            err = (r.get("error_message") or "")[:20]
            rows.append(
                Text.from_markup(
                    f"  [{sc}]{nm:<14}[/] [dim]{age_s}[/]"
                    + (f" [dim]{err}[/]" if err else "")
                )
            )
    elif valid_loader:
        if running_loader:
            rows.append(Rule(style="dim"))
            for r in running_loader[:3]:
                nm = (r.get("table_name") or "")[:12]
                pct = r.get("completion_pct")
                pct_s = f" {float(pct):.0f}%" if pct is not None else ""
                rows.append(Text.from_markup(f"[{CY}]Loading:[/][dim] {nm}{pct_s}[/]"))
        elif ok_count > 0:
            rows.append(Rule(style="dim"))
            rows.append(
                Text.from_markup(
                    f"[{G}]OK Loaders[/]  [dim]{ok_count} feeds healthy[/]"
                )
            )

    # Audit log — most recent notable actions
    valid_audit = (
        audit
        if (audit and not (isinstance(audit, dict) and audit.get("_error")))
        else []
    )
    if valid_audit:
        notable = [
            a
            for a in valid_audit
            if any(
                k in (a.get("action_type") or "")
                for k in ("entry", "exit", "halt", "resume", "circuit")
            )
        ][:3]
        if notable:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[dim]Audit:[/]"))
            for a in notable:
                at = (a.get("action_type") or "").replace("_", " ")
                sym = a.get("symbol") or ""
                st = a.get("status") or ""
                sc = G if st == "success" else (Y if st == "warn" else R)
                rows.append(
                    Text.from_markup(
                        f"  [{sc}]{at[:22]}[/]" + (f" [white]{sym}[/]" if sym else "")
                    )
                )

    if not rows:
        rows.append(Text("no activity", style="dim"))
    return Panel(
        Group(*rows),
        title="[bold yellow]ALGO ACTIVITY & SYSTEM HEALTH[/]",
        border_style="yellow",
        padding=(0, 1),
    )


def panel_algo_health(
    run,
    act,
    hlth,
    notifs,
    algo_metrics=None,
    audit=None,
    exec_hist=None,
    risk=None,
):
    """Focused 'did the algo work?' panel: run outcome → what it did → system health."""
    rows: list = []

    # ── A: Run outcome ────────────────────────────────────────────────────────
    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_at = (
        run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    )
    age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

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
        halt_r = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"  [{Y}]→ {prefix}{detail[:80]}[/]"))
        elif summary:
            rows.append(Text.from_markup(f"  [dim]{summary[:72]}[/]"))
    elif act_valid:
        rows.append(
            Text.from_markup(f"[dim]Last run (audit):[/]  [dim]{fmt_age(run_at)}[/]")
        )
    else:
        rows.append(Text.from_markup("[dim]No run data - algo has not run yet[/]"))

    # ── B: Phase badges + aggregated "what did it do?" metrics ───────────────
    signals_gen = 0
    entries_exec = 0
    exits_exec = 0
    phase_badges: list = []

    def _pc(v):
        if isinstance(v, list):
            return len(v)
        if isinstance(v, int):
            return v
        return 0

    if run_valid and run.get("_source") == "exec_log":
        for p in run.get("phase_results") or []:
            raw = (p.get("name") or p.get("phase", "")).lower()
            parts_p = raw.split("_")
            base = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
            ps = (p.get("status") or "").lower()
            sc = (
                G
                if ps in ("success", "completed", "ok")
                else (
                    Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R
                )
            )
            si = (
                "✓"
                if ps in ("success", "completed", "ok")
                else (
                    "~"
                    if ps in ("halt", "halted", "warn", "degraded", "skipped")
                    else "✗"
                )
            )
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
            pdata = p.get("data") or {}
            if isinstance(pdata, str):
                try:
                    pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase metrics data JSON: {e}")
                    pdata = {}
            sg = pdata.get("signals_generated")
            ee = pdata.get("entries_executed") or pdata.get("trades_executed")
            xe = pdata.get("exits_executed")
            if sg:
                signals_gen = max(signals_gen, int(sg))
            if ee:
                entries_exec = max(entries_exec, int(ee))
            if xe:
                exits_exec = max(exits_exec, int(xe))
    elif run_valid or act_valid:
        src = run if run_valid else act
        for p in (src.get("phase_results") or src.get("phases") or []):
            at = p.get("action_type", "")
            if not at.startswith("phase_"):
                continue
            parts_p = at.split("_")
            num = parts_p[1] if len(parts_p) > 1 else "?"
            if not num.isdigit():
                continue
            # "phase_1_data_freshness" → base "phase_1", name from remaining parts
            phase_key = f"phase_{num}"
            name_parts = parts_p[2:] if len(parts_p) > 2 else []
            default_short = ("_".join(name_parts)[:7] if name_parts else f"P{num}")
            short = PHASE_NAMES.get(phase_key, default_short)[:8]
            st = p.get("status", "")
            sc = (
                G if st == "success" else (Y if st in ("halt", "warn", "halted") else R)
            )
            si = (
                "✓"
                if st == "success"
                else ("~" if st in ("halt", "warn", "halted") else "✗")
            )
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

    if phase_badges:
        rows.append(Text.from_markup("  ".join(phase_badges)))

    # Fallback: use algo_metrics for today's entry/exit counts
    valid_metrics = (
        algo_metrics
        if (
            algo_metrics
            and not (isinstance(algo_metrics, dict) and algo_metrics.get("_error"))
        )
        else []
    )
    today_m = valid_metrics[0] if valid_metrics else {}
    if not entries_exec:
        entries_exec = int(today_m.get("entries") or 0)
    if not exits_exec:
        exits_exec = int(today_m.get("exits") or 0)

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
    avg_sig_score = today_m.get("avg_signal_score")
    if avg_sig_score is not None:
        avg_sig_v = float(avg_sig_score)
        if avg_sig_v > 0:
            sc_c = G if avg_sig_v >= 80 else (Y if avg_sig_v >= 65 else "white")
            action_parts.append(f"[dim]Avg score:[/][{sc_c}]{avg_sig_v:.0f}[/]")
    if action_parts:
        rows.append(Text.from_markup("  ".join(action_parts)))

    # 5-day activity strip
    if len(valid_metrics) >= 2:
        day_parts = []
        for m in valid_metrics[:5]:
            d = m.get("date")
            d_s = d.strftime("%d") if hasattr(d, "strftime") else str(d or "")[-2:]
            en = int(m.get("entries") or 0)
            ex = int(m.get("exits") or 0)
            e_c = G if en > 0 else DIM
            x_c = Y if ex > 0 else DIM
            day_parts.append(f"[dim]{d_s}:[/][{e_c}]{en}↑[/][{x_c}]{ex}↓[/]")
        rows.append(Text.from_markup("[dim]5d activity:[/] " + "  ".join(day_parts)))

    rows.append(Rule(style="dim"))

    # ── C: Run history (last 7 runs as badges) ───────────────────────────────
    valid_hist = (
        exec_hist
        if (exec_hist and not (isinstance(exec_hist, dict) and exec_hist.get("_error")))
        else []
    )
    if valid_hist:
        n_ok = sum(
            1
            for r in valid_hist
            if (r.get("overall_status") or "").lower() in ("success", "completed")
        )
        n_hlt = sum(
            1 for r in valid_hist if (r.get("overall_status") or "").lower() == "halted"
        )
        n_err = sum(
            1
            for r in valid_hist
            if (r.get("overall_status") or "").lower() in ("error", "failed")
        )
        total_h = len(valid_hist)
        badges = []
        for r in valid_hist[:7]:
            s = (r.get("overall_status") or "").lower()
            badges.append(
                f"[{G}]OK[/]"
                if s in ("success", "completed")
                else (f"[{Y}]~[/]" if s == "halted" else f"[{R}]X[/]")
            )
        wc = G if n_ok == total_h else (Y if n_ok > 0 else R)
        rows.append(
            Text.from_markup(
                f"[dim]Last {total_h} runs:[/] {''.join(badges)}"
                f"  [{wc}]{n_ok}/{total_h} success[/]"
                + (f"  [{Y}]{n_hlt} halted[/]" if n_hlt else "")
                + (f"  [{R}]{n_err} error[/]" if n_err else "")
            )
        )
        last_halt = next(
            (
                r
                for r in valid_hist
                if (r.get("overall_status") or "").lower() == "halted"
            ),
            None,
        )
        if last_halt:
            lhr = last_halt.get("halt_reason") or ""
            lph = _fmt_phases_halted(last_halt.get("phases_halted"))
            body = lhr or lph
            if body:
                ph_s = f"  [dim]({lph})[/]" if lph and lph not in lhr else ""
                rows.append(Text.from_markup(f"  [{Y}]→ {body[:68]}[/]{ph_s}"))

    rows.append(Rule(style="dim"))

    # ── D: Data health (compact) ──────────────────────────────────────────────
    if hlth:
        hlth_list = (
            hlth.get("items", [])
            if isinstance(hlth, dict) and "items" in hlth
            else (hlth if isinstance(hlth, list) else [])
        )
        ready_to_trade = hlth.get("ready_to_trade") if isinstance(hlth, dict) else None
        stale = [r for r in hlth_list if isinstance(r, dict) and r.get("st") != "ok"]

        def _age_h(r):
            ah = r.get("age_hours")
            if ah is not None:
                return float(ah)
            ad = r.get("age")
            if ad is not None:
                return float(ad) * 24
            return None

        def _age_fmt_c(r):
            h = _age_h(r)
            if h is None:
                return "?"
            return f"{h:.0f}h" if h < 24 else f"{h / 24:.1f}d"

        if not stale:
            crit = [r for r in hlth_list if r.get("role") == "CRIT"]
            if ready_to_trade is False:
                rtt_badge = f"[bold {R}]✗ NOT READY[/]"
            elif ready_to_trade is True:
                rtt_badge = f"[{G}]✓ READY TO TRADE[/]"
            else:
                rtt_badge = f"[{G}]✓ Data OK[/]"
            n_total = len(hlth_list)
            n_crit = len(crit)
            ages = [_age_h(r) for r in hlth_list if _age_h(r) is not None]
            oldest_s = f"  [dim]oldest: {_age_fmt_c(max(hlth_list, key=lambda r: _age_h(r) or 0))}[/]" if ages else ""
            crit_s = f"  [dim]crit {n_crit}[/][{G}] ok[/]" if n_crit else ""
            rows.append(Text.from_markup(
                f"{rtt_badge}  [dim]{n_total} tables fresh[/]{crit_s}{oldest_s}"
            ))
        else:
            crit_stale = [r for r in stale if r.get("role") == "CRIT"]
            if ready_to_trade is False:
                rtt_pfx = f"[bold {R}]✗ NOT READY[/]  "
            elif crit_stale:
                rtt_pfx = f"[bold {R}]CRIT STALE[/]  "
            else:
                rtt_pfx = f"[{Y}]{len(stale)} stale[/]  "
            stale_parts = []
            ordered = crit_stale + [r for r in stale if r not in crit_stale]
            for r in ordered[:4]:
                nm = (r.get("tbl") or "--")[:16]
                cc = f"bold {R}" if r.get("role") == "CRIT" else R
                stale_parts.append(f"[{R}]✗[/][{cc}]{nm}[/] [dim]{_age_fmt_c(r)}[/]")
            rows.append(Text.from_markup(f"{rtt_pfx}" + "  ".join(stale_parts)))

    # ── E: Risk snapshot (VaR / CVaR / Beta / Concentration) ────────────────────
    if (
        risk
        and not risk.get("_error")
        and risk.get("var95")
        and float(risk.get("var95") or 0) > 0
    ):
        rows.append(Rule(style="dim"))
        beta_c = (
            R
            if (risk.get("beta") or 0) >= 1.2
            else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        )
        conc_c = (
            R
            if (risk.get("conc5") or 0) >= 35
            else (Y if (risk.get("conc5") or 0) >= 25 else "white")
        )
        var_c = R if (risk.get("var95") or 0) >= 4 else (Y if (risk.get("var95") or 0) >= 2 else "white")
        risk_parts = [
            f"[dim]VaR 95%:[/][{var_c}]{(risk.get('var95') or 0):.2f}%[/]",
            f"[dim]CVaR 95%:[/][{var_c}]{(risk.get('cvar95') or 0):.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{(risk.get('beta') or 0):.2f}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{(risk.get('conc5') or 0):.0f}%[/]",
        ]
        if risk.get("svar") and float(risk.get("svar") or 0) > 0:
            risk_parts.append(
                f"[dim]Stressed VaR:[/][{R}]{(risk.get('svar') or 0):.2f}%[/]"
            )
        rows.append(Text.from_markup("  ".join(risk_parts)))

    # ── F: Notifications (compact) ────────────────────────────────────────────
    notifs_items = (
        notifs.get("items", [])
        if isinstance(notifs, dict) and "items" in notifs
        else (notifs if isinstance(notifs, list) else [])
    )
    notifs_error = notifs.get("_error") if isinstance(notifs, dict) else None
    valid_notifs = notifs_items if notifs_items and not notifs_error else []
    if valid_notifs:
        rows.append(Rule(style="dim"))
        SEV_C = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        _SHORT = {
            "trading halted by circuit": "Halted:CB",
            "circuit breaker": "CB fired",
            "position entered": "Entered",
            "position exited": "Exited",
            "daily loss limit": "DailyLoss",
            "max drawdown": "MaxDD",
        }
        notif_parts = []
        for n in valid_notifs[:5]:
            sc = SEV_C.get(n.get("severity", "info"), DIM)
            raw_t = n.get("title") or ""
            title = next(
                (v for k, v in _SHORT.items() if k in raw_t.lower()), raw_t[:20]
            )
            age = fmt_age(n.get("created_at"))
            unread = "-" if not n.get("seen", True) else "·"
            notif_parts.append(f"[{sc}]{unread}{title}[/][dim]{age}[/]")
        rows.append(Text.from_markup("[dim]Alerts:[/] " + "  ".join(notif_parts)))

    if not rows:
        rows.append(Text("no activity", style="dim"))
    return Panel(
        Group(*rows),
        title="[bold yellow]ALGO HEALTH[/]  [dim][h] expand[/]",
        border_style="yellow",
        padding=(0, 1),
    )


def panel_algo_health_expanded(
    run,
    act,
    hlth,
    notifs,
    algo_metrics=None,
    audit=None,
    exec_hist=None,
    risk=None,
):
    """Full-screen algo health — dual column: data freshness (left) | run results (right)."""
    hlth_items = (
        hlth.get("items", [])
        if isinstance(hlth, dict) and "items" in hlth
        else (hlth if isinstance(hlth, list) else [])
    )
    ready_to_trade = hlth.get("ready_to_trade") if isinstance(hlth, dict) else None

    # ── LEFT: full data-freshness table ────────────────────────────────────────
    left_rows: list = []

    if hlth_items:
        stale_count = sum(1 for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok")
        crit_stale = [
            r for r in hlth_items
            if isinstance(r, dict) and r.get("role") == "CRIT" and r.get("st") != "ok"
        ]
        if crit_stale:
            crit_names = "  ".join(f"[bold white]{r.get('tbl', '')[:18]}[/]" for r in crit_stale)
            left_rows.append(Text.from_markup(f"[bold {R}]⚠ CRIT STALE:[/]  {crit_names}"))
        rtt_part = ""
        if ready_to_trade is True:
            rtt_part = f"  [bold {G}]✓ READY TO TRADE[/]"
        elif ready_to_trade is False:
            rtt_part = f"  [bold {R}]✗ NOT READY[/]"
        status_c = G if stale_count == 0 else (Y if stale_count <= 2 else R)
        left_rows.append(Text.from_markup(
            f"[dim]Freshness:[/] [{status_c}]{len(hlth_items) - stale_count}/{len(hlth_items)} fresh[/]"
            + (f"  [{R}]{stale_count} stale[/]" if stale_count else "")
            + rtt_part
        ))

        def _fmt_age_e(r):
            ah = r.get("age_hours")
            ad = r.get("age")
            if ah is not None:
                return f"{ah:.0f}h" if float(ah) < 24 else f"{float(ah) / 24:.1f}d"
            elif ad is not None:
                return f"{float(ad):.1f}d"
            return "?"

        def _fmt_lat_e(r):
            lat = r.get("last_updated") or r.get("latest")
            if hasattr(lat, "strftime"):
                return lat.strftime("%m/%d")
            if isinstance(lat, str) and len(lat) >= 10:
                return lat[5:10]
            return str(lat or "")[:5]

        _role_order = {"CRIT": 0, "IMP": 1, "NORM": 2}
        sorted_items = sorted(
            [r for r in hlth_items if isinstance(r, dict)],
            key=lambda r: (_role_order.get(r.get("role") or "NORM", 2), r.get("tbl") or ""),
        )
        all_tbl = Table(
            box=box.SIMPLE_HEAD, show_header=True, header_style="dim",
            padding=(0, 1), expand=True, row_styles=["", "dim"],
        )
        all_tbl.add_column("Role", no_wrap=True, min_width=4)
        all_tbl.add_column("Table", no_wrap=True, min_width=26)
        all_tbl.add_column("Age", no_wrap=True, min_width=5, justify="right")
        all_tbl.add_column("Updated", no_wrap=True, min_width=5)
        all_tbl.add_column("Rows", no_wrap=True, min_width=8, justify="right")
        all_tbl.add_column("Status", no_wrap=True, min_width=6)
        for r in sorted_items:
            nm = str(r.get("tbl") or "--")
            role = str(r.get("role") or "NORM")
            st = r.get("st", "ok")
            ok = st == "ok"
            ic = G if ok else (Y if st == "empty" else R)
            ii = "✓" if ok else ("−" if st == "empty" else "✗")
            rc = "bold white" if role == "CRIT" else (Y if role == "IMP" else DIM)
            row_count = r.get("row_count")
            rc_s = f"{row_count:,}" if row_count is not None else "--"
            st_label = "ok" if ok else st.upper()
            all_tbl.add_row(
                Text(role, style=rc),
                Text.from_markup(f"[{ic}]{ii}[/] [{rc}]{nm}[/]"),
                Text(_fmt_age_e(r), style=DIM if ok else Y),
                Text(_fmt_lat_e(r), style="dim"),
                Text(rc_s, style="dim"),
                Text(st_label, style=G if ok else (Y if st == "empty" else R)),
            )
        left_rows.append(all_tbl)
    else:
        left_rows.append(Text("no data health info", style="dim"))

    left_panel = Panel(
        Group(*left_rows),
        title="[bold yellow]DATA FRESHNESS[/]  [dim][h] return[/]",
        border_style="yellow",
        padding=(0, 1),
    )

    # ── RIGHT: run results, history, risk, notifications, audit ─────────────────
    right_rows: list = [
        Text.from_markup("[dim]press [/][bold yellow]h[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    run_valid = run and not run.get("_error")
    act_valid = act and not act.get("_error")
    run_at = (
        run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    )
    age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid:
        sts = (
            f"[bold {G}]OK COMPLETED[/]"
            if run.get("success") and not run.get("halted")
            else (
                f"[bold {Y}]~ HALTED[/]"
                if run.get("halted")
                else f"[bold {R}]X ERROR[/]"
            )
        )
        rid = run.get("run_id") or ""
        rid = run.get("run_id") or ""
        right_rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r = run.get("halt_reason") or ""
        summary = run.get("summary") or ""
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                right_rows.append(Text.from_markup(f"  [{Y}]-> {prefix}{detail}[/]"))
        elif summary:
            right_rows.append(Text.from_markup(f"  [dim]{summary}[/]"))

    phase_badges_e: list = []
    if run_valid and run.get("_source") == "exec_log":
        for p in run.get("phase_results") or []:
            raw = (p.get("name") or p.get("phase", "")).lower()
            parts_p = raw.split("_")
            base = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
            ps = (p.get("status") or "").lower()
            sc = (
                G
                if ps in ("success", "completed", "ok")
                else (
                    Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R
                )
            )
            si = (
                "v"
                if ps in ("success", "completed", "ok")
                else (
                    "~"
                    if ps in ("halt", "halted", "warn", "degraded", "skipped")
                    else "x"
                )
            )
            phase_badges_e.append(f"[{sc}]{si}[dim]{short}[/][/]")
    if phase_badges_e:
        right_rows.append(Text.from_markup("  ".join(phase_badges_e)))

    # entries/exits today
    signals_gen = 0
    entries_exec = 0
    exits_exec = 0
    if run_valid and run.get("_source") == "exec_log":
        for p in run.get("phase_results") or []:
            pdata = p.get("data") or {}
            if isinstance(pdata, str):
                try:
                    import json as _json
                    pdata = _json.loads(pdata)
                except Exception:
                    pdata = {}
            sg = pdata.get("signals_generated")
            ee = pdata.get("entries_executed") or pdata.get("trades_executed")
            xe = pdata.get("exits_executed")
            if sg:
                signals_gen = max(signals_gen, int(sg))
            if ee:
                entries_exec = max(entries_exec, int(ee))
            if xe:
                exits_exec = max(exits_exec, int(xe))

    valid_metrics_e = (
        algo_metrics
        if (algo_metrics and not (isinstance(algo_metrics, dict) and algo_metrics.get("_error")))
        else []
    )
    today_m_e = valid_metrics_e[0] if valid_metrics_e else {}
    if not entries_exec:
        entries_exec = int(today_m_e.get("entries") or 0)
    if not exits_exec:
        exits_exec = int(today_m_e.get("exits") or 0)

    action_parts_e = []
    if signals_gen > 0:
        action_parts_e.append(f"[dim]Signals:[/][white]{signals_gen}[/]")
    action_parts_e.append(f"[dim]Entries:[/][{G if entries_exec > 0 else DIM}]{entries_exec}[/]")
    action_parts_e.append(f"[dim]Exits:[/][{Y if exits_exec > 0 else DIM}]{exits_exec}[/]")
    avg_sig_score_e = today_m_e.get("avg_signal_score")
    if avg_sig_score_e is not None:
        avg_sig_v = float(avg_sig_score_e)
        if avg_sig_v > 0:
            sc_c = G if avg_sig_v >= 80 else (Y if avg_sig_v >= 65 else "white")
            action_parts_e.append(f"[dim]Avg score:[/][{sc_c}]{avg_sig_v:.0f}[/]")
    if action_parts_e:
        right_rows.append(Text.from_markup("  ".join(action_parts_e)))

    if len(valid_metrics_e) >= 2:
        day_parts_e = []
        for m in valid_metrics_e[:5]:
            d = m.get("date")
            d_s = d.strftime("%d") if hasattr(d, "strftime") else str(d or "")[-2:]
            en = int(m.get("entries") or 0)
            ex = int(m.get("exits") or 0)
            e_c = G if en > 0 else DIM
            x_c = Y if ex > 0 else DIM
            day_parts_e.append(f"[dim]{d_s}:[/][{e_c}]{en}up[/][{x_c}]{ex}dn[/]")
        right_rows.append(Text.from_markup("[dim]5d:[/] " + "  ".join(day_parts_e)))

    right_rows.append(Rule(style="dim"))

    # Full run history
    valid_hist_e = (
        exec_hist
        if (exec_hist and not (isinstance(exec_hist, dict) and exec_hist.get("_error")))
        else []
    )
    if valid_hist_e:
        n_ok = sum(
            1
            for r in valid_hist_e
            if (r.get("overall_status") or "").lower() in ("success", "completed")
        )
        wc = G if n_ok == len(valid_hist_e) else (Y if n_ok > 0 else R)
        right_rows.append(
            Text.from_markup(
                f"[dim]Run history ({len(valid_hist_e)}):[/]  [{wc}]{n_ok}/{len(valid_hist_e)} success[/]"
            )
        )
        for r in valid_hist_e:
            s = (r.get("overall_status") or "").lower()
            dt = r.get("started_at")
            dt_s = (
                dt.strftime("%b %d  %I:%M %p")
                if hasattr(dt, "strftime")
                else str(dt or "")[:16]
            )
            ic = G if s in ("success", "completed") else (Y if s == "halted" else R)
            ii = (
                "v"
                if s in ("success", "completed")
                else ("~" if s == "halted" else "x")
            )
            hr = r.get("halt_reason") or ""
            lph = _fmt_phases_halted(r.get("phases_halted"))
            body = hr or lph
            ph_s = f"  [dim]({lph})[/]" if lph and lph not in (hr or "") else ""
            hr_s = f"  [{Y}]-> {body}[/]{ph_s}" if body else ""
            right_rows.append(
                Text.from_markup(f"  [{ic}]{ii}[/] [dim]{dt_s}[/]  [{ic}]{s}[/]{hr_s}")
            )

    # Risk snapshot
    if (
        risk
        and not risk.get("_error")
        and risk.get("var95")
        and float(risk.get("var95") or 0) > 0
    ):
        right_rows.append(Rule(style="dim"))
        beta_c = (
            R
            if (risk.get("beta") or 0) >= 1.2
            else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        )
        conc_c = (
            R
            if (risk.get("conc5") or 0) >= 35
            else (Y if (risk.get("conc5") or 0) >= 25 else "white")
        )
        var_c = (
            R if (risk.get("var95") or 0) >= 4
            else (Y if (risk.get("var95") or 0) >= 2 else "white")
        )
        risk_parts_e = [
            f"[dim]VaR95:[/][{var_c}]{(risk.get('var95') or 0):.2f}%[/]",
            f"[dim]CVaR:[/][{var_c}]{(risk.get('cvar95') or 0):.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{(risk.get('beta') or 0):.2f}[/]",
            f"[dim]Top5:[/][{conc_c}]{(risk.get('conc5') or 0):.0f}%[/]",
        ]
        if risk.get("svar") and float(risk.get("svar") or 0) > 0:
            risk_parts_e.append(
                f"[dim]StressVaR:[/][{R}]{(risk.get('svar') or 0):.2f}%[/]"
            )
        right_rows.append(Text.from_markup("  ".join(risk_parts_e)))

    # Notifications
    notifs_items_exp = (
        notifs.get("items", [])
        if isinstance(notifs, dict) and "items" in notifs
        else (notifs if isinstance(notifs, list) else [])
    )
    notifs_error_exp = notifs.get("_error") if isinstance(notifs, dict) else None
    valid_notifs = notifs_items_exp if notifs_items_exp and not notifs_error_exp else []
    if valid_notifs:
        right_rows.append(Rule(style="dim"))
        right_rows.append(Text.from_markup("[dim]Notifications:[/]"))
        SEV_C = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        for n in valid_notifs:
            if not isinstance(n, dict):
                continue
            sc = SEV_C.get(n.get("severity", "info"), DIM)
            title = n.get("title") or ""
            age = fmt_age(n.get("created_at"))
            unread = "-" if not n.get("seen", True) else "."
            right_rows.append(Text.from_markup(f"  [{sc}]{unread} {title}[/] [dim]{age}[/]"))

    # Audit log
    valid_audit_exp = (
        audit
        if (audit and not (isinstance(audit, dict) and audit.get("_error")))
        else []
    )
    if valid_audit_exp:
        right_rows.append(Rule(style="dim"))
        right_rows.append(Text.from_markup("[dim]Audit log:[/]"))
        for a in valid_audit_exp[:20]:
            if not isinstance(a, dict):
                continue
            at = (a.get("action_type") or "").replace("_", " ")
            sym = a.get("symbol") or ""
            st_a = a.get("status") or ""
            sc = G if st_a in ("success", "ok") else (Y if st_a in ("warn", "warning") else R)
            ts_s = fmt_age(a.get("created_at") or a.get("timestamp"))
            right_rows.append(
                Text.from_markup(
                    f"  [{sc}]{at[:32]}[/]"
                    + (f" [white]{sym}[/]" if sym else "")
                    + (f"  [dim]{ts_s}[/]" if ts_s else "")
                )
            )

    right_panel = Panel(
        Group(*right_rows),
        title="[bold yellow]RUN RESULTS & HISTORY[/]  [dim][h] return[/]",
        border_style="yellow",
        padding=(0, 1),
    )

    dual = Layout()
    dual.split_row(
        Layout(left_panel, ratio=2, name="freshness"),
        Layout(right_panel, ratio=3, name="runs"),
    )
    return dual



__all__ = [
    "panel_orch",
    "panel_status",
    "panel_algo_health",
    "panel_algo_health_expanded",
]
