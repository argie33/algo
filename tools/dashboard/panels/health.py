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

from ..error_boundary import has_error
from ..formatters import (
    fmt_age,
    next_run_str,
)
from ..utilities import (
    CY,
    DIM,
    PHASE_NAMES,
    G,
    R,
    Y,
)
from ._helpers import (
    _best_halt_reason,
    _error_panel,
    _fmt_phases_halted,
)
from .data_extractors import (
    extract_config_params,
    extract_risk_metrics,
    safe_get_dict,
    safe_get_field,
    safe_get_list,
)


def _var_color(var95: float | None) -> str:
    """Choose color for VaR 95% value: red if ≥4%, yellow if ≥2%, white otherwise."""
    if var95 is None:
        return "dim"
    if var95 >= 4:
        return R
    if var95 >= 2:
        return Y
    return "white"


def panel_orch(run, cfg, risk=None):
    if _error_panel("config", cfg, "ORCHESTRATION"):
        return _error_panel("config", cfg, "ORCHESTRATION")

    next_run = next_run_str()
    cfg_params = extract_config_params(cfg)
    mode = cfg_params["mode"]
    mc2 = G if "LIVE" in mode else Y
    en = "ENABLED" if cfg_params["enabled"] else "DISABLED"
    ec = G if cfg_params["enabled"] else R
    max_n = cfg_params["max_pos_n"]
    max_sec_n = cfg_params["max_sec_n"]
    min_score = cfg_params["min_score"]
    base_risk = cfg_params["base_risk"]
    t1r = cfg_params["t1_r"]

    score_s = f"[dim]min score ≥[/][white]{min_score}[/]" if min_score and float(min_score) > 0 else ""
    slots_s = f"[dim]max [/][white]{max_n}[/][dim] positions[/]" if max_n else ""
    sec_s = f"[dim]sector ≤[/][white]{max_sec_n}[/]" if max_sec_n else ""
    risk_s = f"[dim]base risk [/][white]{base_risk}%[/]" if base_risk else ""
    t1r_s = f"[dim]T1 target [/][white]{t1r}R[/]" if t1r else ""
    config_line = "  ".join(x for x in [score_s, slots_s, sec_s, risk_s, t1r_s] if x)

    # VaR line — only show if table is populated with real data
    var_line = ""
    if risk and not has_error(risk) and risk.get("var95") and float(risk["var95"]) > 0:
        risk_metrics = extract_risk_metrics(risk)
        if risk_metrics:
            var95_val = risk_metrics["var95"]
            beta_val = risk_metrics["beta"]
            cvar95_val = risk_metrics["cvar95"]
            conc5_val = risk_metrics["conc5"]
            svar_val = risk_metrics["svar"]
            beta_c = R if beta_val >= 1.2 else (Y if beta_val >= 0.8 else G)
            var_c = _var_color(var95_val)
            svar_s = (
                f"\n[dim]Stressed VaR:[/][{R}]{float(svar_val):.2f}%[/]"
                if svar_val and float(svar_val) > 0
                else ""
            )
            var_line = (
                f"\n[dim]VaR 95%:[/][{var_c}]{var95_val:.2f}%[/]"
                f"  [dim]CVaR 95%:[/][{var_c}]{cvar95_val:.2f}%[/]"
                f"  [dim]Portfolio Beta:[/][{beta_c}]{beta_val:.2f}[/]"
                f"  [dim]Top-5 Conc:[/][white]{conc5_val:.0f}%[/]" + svar_s
            )

    if not run or has_error(run):
        error_msg = (
            f"[{R}]run fetch failed[/]: {run.get('_error')}"
            if isinstance(run, dict) and has_error(run)
            else "[dim]run: no data[/]"
        )
        body = Text.from_markup(
            f"{error_msg}\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next run:[/] [white]{next_run}[/]" + var_line
        )
    else:
        age = fmt_age(run["run_at"])
        sts = (
            "[bold bright_green]✓ COMPLETED[/]"
            if run["success"] and not run.get("halted")
            else ("[bold yellow]~ HALTED[/]" if run.get("halted") else "[bold bright_red]✗ ERROR[/]")
        )

        pbadges = []
        # exec_log source: structured per-phase objects with names + statuses
        if run.get("_source") == "exec_log":
            phase_results = run.get("phase_results")
            if not phase_results:
                logger.warning(
                    f"[HEALTH] exec_log source missing 'phase_results'. Available keys: {list(run.keys())}. "
                    "Phase status will not be displayed."
                )
                phase_results = []
            for p in phase_results:
                raw = (p.get("name") or p.get("phase", "")).lower()
                parts = raw.split("_")
                base = "_".join(parts[:2]) if len(parts) >= 2 else raw
                short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
                ps = (p.get("status", "")).lower()
                pc = G if ps in ("success", "completed") else (Y if ps in ("halt", "halted", "warn") else R)
                pi = "✓" if ps in ("success", "completed") else ("~" if ps in ("halt", "halted", "warn") else "✗")
                pbadges.append(f"[{pc}]{pi}{short}[/]")
            # Show halt reason if halted
            halt_r = run.get("halt_reason", "")
            summary = run.get("summary", "")
            if halt_r or run.get("halted"):
                _details = _best_halt_reason(halt_r, run.get("phase_results"))
                _lines = [f"{lb + ': ' if lb else ''}{dt[:60]}" for lb, dt in _details]
                extra = ("\n" + "\n".join(f"[{Y}]{ln}[/]" for ln in _lines)) if _lines else ""
            else:
                extra = f"\n[dim]{summary[:50]}[/]" if summary else ""
        else:
            # audit_log fallback: phase_N or phase_N_name format
            phases_list = run.get("phase_results") or run.get("phases")
            if not phases_list:
                logger.warning(
                    f"[HEALTH] audit_log missing both 'phase_results' and 'phases'. Available keys: {list(run.keys())}. "
                    "Phase status will not be displayed."
                )
                phases_list = []
            for p in phases_list:
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
                pi = "✓" if ps == "success" else ("~" if ps in ("halt", "warn") else "✗")
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
    return Panel(body, title="[bold cyan]ORCHESTRATOR[/]", border_style="cyan", padding=(0, 1))


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
    if _error_panel("health", hlth, "STATUS"):
        return _error_panel("health", hlth, "STATUS")
    if _error_panel("notifications", notifs, "STATUS"):
        return _error_panel("notifications", notifs, "STATUS")

    rows: list = []

    # Extract items from data dicts using safe helpers
    hlth_items = safe_get_list(hlth)

    # Helper to count phase list items
    def _pc(v):
        if isinstance(v, list):
            return len(v)
        if isinstance(v, int):
            return v
        return 0

    # ── Run status + schedule + mode + trading config ────────────────────────────
    run_valid = run and not has_error(run)
    act_valid = act and not has_error(act)
    run_id_top = safe_get_field(run, "run_id", "") if run_valid else (safe_get_field(act, "run_id", "") if act_valid else "")
    run_at_top = safe_get_field(run, "run_at") if run_valid else (safe_get_field(act, "run_at") if act_valid else None)
    if run_id_top or run_at_top:
        sts = (
            "[bold bright_green]✓ COMPLETED[/]"
            if (run_valid and safe_get_field(run, "success") and not safe_get_field(run, "halted"))
            else (
                "[bold yellow]~ HALTED[/]"
                if (run_valid and safe_get_field(run, "halted"))
                else ("[bold bright_red]✗ ERROR[/]" if (run_valid and safe_get_field(run, "errored")) else "[dim]RUN[/]")
            )
        )
        age_s = f"  [dim]{fmt_age(run_at_top)}[/]" if run_at_top else ""
        rows.append(Text.from_markup(f"{sts}{age_s}"))

    # Config extraction — use helper to reduce .get() calls
    cfg_v = safe_get_dict(cfg)
    cfg_params = extract_config_params(cfg_v) if cfg_v else {}
    mode = cfg_params.get("mode", "")
    en = cfg_params.get("enabled", True)
    mc = G if "LIVE" in str(mode) else Y
    ec = G if en else R
    en_s = "ENABLED" if en else "DISABLED"
    next_r = next_run_str()
    rows.append(Text.from_markup(f"[{mc}]{mode or 'PAPER'}[/]  [{ec}]{en_s}[/]  [dim]Next run:[/] [white]{next_r}[/]"))

    # Trading config params — visible context for position sizing decisions
    cfg_parts = []
    max_pos_n = cfg_params.get("max_pos_n")
    max_sec_n = cfg_params.get("max_sec_n")
    base_risk = cfg_params.get("base_risk")
    t1_r = cfg_params.get("t1_r")
    if max_pos_n:
        cfg_parts.append(f"[dim]slots:[/][white]{max_pos_n}[/]")
    if max_sec_n:
        cfg_parts.append(f"[dim]sector≤4:[/][white]{max_sec_n}[/]")
    if base_risk:
        cfg_parts.append(f"[dim]risk:[/][white]{base_risk}%[/]")
    if t1_r:
        cfg_parts.append(f"[dim]T1:[/][white]{t1_r}R[/]")
    if cfg_parts:
        rows.append(Text.from_markup("  ".join(cfg_parts)))
    rows.append(Rule(style="dim"))

    # Execution history summary — last 7 runs
    valid_hist = safe_get_list(exec_hist)
    if valid_hist:
        n_ok = sum(1 for r in valid_hist if (safe_get_field(r, "overall_status", "") or "").lower() in ("success", "completed"))
        n_hlt = sum(1 for r in valid_hist if (safe_get_field(r, "overall_status", "") or "").lower() == "halted")
        n_err = sum(1 for r in valid_hist if (safe_get_field(r, "overall_status", "") or "").lower() in ("error", "failed"))
        total_h = len(valid_hist)
        wr_h = n_ok / total_h * 100 if total_h else 0
        wc_h = G if wr_h >= 80 else (Y if wr_h >= 50 else R)
        badges = []
        for r in valid_hist[:7]:
            s = (safe_get_field(r, "overall_status", "") or "").lower()
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
            (r for r in valid_hist if (safe_get_field(r, "overall_status", "") or "").lower() == "halted"),
            None,
        )
        if last_halt:
            lhr = safe_get_field(last_halt, "halt_reason", "")
            lph = _fmt_phases_halted(safe_get_field(last_halt, "phases_halted"))
            body = lhr or lph
            if body:
                ph_s = f"  [dim]({lph})[/]" if lph and lph not in lhr else ""
                rows.append(Text.from_markup(f"  [{Y}]a†³ {body[:55]}[/]{ph_s}"))
        rows.append(Rule(style="dim"))

    # Current run status — shown prominently even when history is empty
    run_id = safe_get_field(run, "run_id") if run_valid else None
    run_at = safe_get_field(run, "run_at") if run else None
    if not run_id and act_valid:
        act_run_id = safe_get_field(act, "run_id")
        if act_run_id:
            run_id = act_run_id[:26]
        run_at = safe_get_field(act, "run_at")
    if run_id:
        age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""
        r_stat = ""
        if run_valid:
            if safe_get_field(run, "success"):
                r_stat = f"  [{G}]OK COMPLETED[/]"
            elif safe_get_field(run, "halted"):
                r_stat = f"  [{Y}]~ HALTED[/]"
            elif safe_get_field(run, "errored"):
                r_stat = f"  [{R}]X ERROR[/]"
        rows.append(Text.from_markup(f"[dim]Run:[/] [white]{run_id[:30]}[/]{age_s}{r_stat}"))

        # Show phases_completed/halted/errored counts from the run object
        if run_valid:
            n_done = _pc(safe_get_field(run, "phases_completed"))
            n_hlt = _pc(safe_get_field(run, "phases_halted"))
            n_err = _pc(safe_get_field(run, "phases_errored"))
            if n_done + n_hlt + n_err > 0:
                done_s = f"[{G}]{n_done} phases OK[/]"
                hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
                err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
                rows.append(Text.from_markup(f"  {done_s}{hlt_s}{err_s}"))

    # Phase detail — named phases from exec_log with per-phase status and key data
    phase_badges = []
    run_source = safe_get_field(run, "_source") if run_valid else None
    if run_valid and run_source == "exec_log":
        halt_r = safe_get_field(run, "halt_reason", "")
        summary = safe_get_field(run, "summary", "")
        if safe_get_field(run, "halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, safe_get_field(run, "phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"[{Y}]a†³ {prefix}{detail[:60]}[/]"))
        elif summary and isinstance(summary, str):
            rows.append(Text.from_markup(f"[dim]{summary[:65]}[/]"))

        phase_results = safe_get_field(run, "phase_results", [])
        for p in phase_results:
            raw = (safe_get_field(p, "name") or safe_get_field(p, "phase", "")).lower()
            parts = raw.split("_")
            base = "_".join(parts[:2]) if len(parts) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
            ps = (safe_get_field(p, "status", "")).lower()
            sc = (
                G
                if ps in ("success", "completed", "ok")
                else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            )
            si = (
                "✓"
                if ps in ("success", "completed", "ok")
                else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
            )
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

            # Show error or key data for failed/halted phases
            err = safe_get_field(p, "error", "") or ""
            pdata = safe_get_field(p, "data")
            if isinstance(pdata, str):
                try:
                    pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase data JSON: {e}")
                    pdata = None
            elif not isinstance(pdata, dict) and pdata is not None:
                pdata = None
            if err and ps not in ("success", "completed", "ok"):
                rows.append(Text.from_markup(f"  [{sc}]a†³ {err[:62]}[/]"))
            elif ps in ("halt", "halted") and pdata:
                reason = (safe_get_field(pdata, "halt_reason", "") or safe_get_field(pdata, "reason", "") or "")[:55]
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
                    val = safe_get_field(pdata, key)
                    if val is not None:
                        rows.append(Text.from_markup(f"  [dim]{short}:[/] [white]{key.replace('_', ' ')}={val}[/]"))
                        break

        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

        n_ok = _pc(safe_get_field(run, "phases_completed"))
        n_hlt = _pc(safe_get_field(run, "phases_halted"))
        n_err = _pc(safe_get_field(run, "phases_errored"))
        if n_ok + n_hlt + n_err > 0:
            ok_s = f"[{G}]{n_ok} phases done[/]"
            hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
            err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
            rows.append(Text.from_markup(f"  {ok_s}{hlt_s}{err_s}"))
    elif act_valid:
        phases_list = safe_get_field(act, "phases")
        if not phases_list:
            logger.warning(
                f"[HEALTH] Activity log missing 'phases' field. Available keys: {list(act.keys())}. "
                "Activity phase status will not be displayed."
            )
            phases_list = []
        for p in phases_list:
            at = safe_get_field(p, "action_type", "")
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
            st = safe_get_field(p, "status", "")
            sc = G if st == "success" else (Y if st in ("halt", "warn", "halted") else R)
            si = "✓" if st == "success" else ("~" if st in ("halt", "warn", "halted") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

    # Recent trade events (entry/exit/order) from audit_log
    recent = safe_get_field(act, "recent_actions", []) if act_valid else []
    trade_evts = [
        a
        for a in recent
        if safe_get_field(a, "action_type")
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
        at = safe_get_field(a, "action_type", "")
        det = safe_get_field(a, "details")
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse action details JSON: {e}")
                det = None
        elif not isinstance(det, dict) and det is not None:
            det = None
        sym = safe_get_field(det, "symbol", "") if det else ""
        ic = G if ("executed" in at or at == "position_exited") else (Y if "placed" in at else R)
        lbl = at.replace("_", " ").title()[:20]
        rows.append(Text.from_markup(f"  [{ic}]{lbl}{(' ' + sym) if sym else ''}[/]"))

    # Data health (stale tables only)
    if hlth_items:
        rows.append(Rule(style="dim"))
        stale = [r for r in hlth_items if isinstance(r, dict) and safe_get_field(r, "st") != "ok"]
        if not stale:
            rows.append(Text.from_markup(f"[{G}]OK Data OK[/]  [dim]{len(hlth_items)} tables[/]"))
            crit = [r for r in hlth_items if isinstance(r, dict) and safe_get_field(r, "role") == "CRIT"]
            if crit:
                crit_parts = "  ".join(f"[{G}]OK[/][dim]{safe_get_field(r, 'tbl', '')[:13]}[/]" for r in crit)
                rows.append(Text.from_markup(f"  {crit_parts}"))
        else:
            for r in stale[:4]:
                nm = str((safe_get_field(r, "tbl", "") or "--")[:13])
                age_hours = safe_get_field(r, "age_hours")
                age_days = safe_get_field(r, "age")
                if age_hours is not None:
                    age_s = f"{age_hours:.0f}h" if age_hours < 24 else f"{age_hours / 24:.1f}d"
                elif age_days is not None:
                    age_s = f"{float(age_days):.1f}d"
                else:
                    age_s = "?"
                rc = safe_get_field(r, "role", "")
                cc = "bold white" if rc == "CRIT" else "white"
                lat = safe_get_field(r, "last_updated") or safe_get_field(r, "latest")
                if hasattr(lat, "strftime"):
                    lat_s = f" ({lat.strftime('%m/%d')})"
                elif isinstance(lat, str) and len(lat) >= 10:
                    lat_s = f" ({lat[5:10]})"
                else:
                    lat_s = f" ({str(lat)[:5]})" if lat else ""
                rows.append(Text.from_markup(f"[{R}]X[/] [{cc}]{nm:<13}[/] [dim]{age_s} stale{lat_s}[/]"))

    # Notifications (up to 4)
    valid_notifs = safe_get_list(notifs)
    if valid_notifs:
        rows.append(Rule(style="dim"))
        sev_colors = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        short_names = {
            "trading halted by circuit": "Halted: CB",
            "circuit breaker": "CB fired",
            "position entered": "Entered",
            "position exited": "Exited",
            "daily loss limit": "DailyLoss",
            "max drawdown": "MaxDD hit",
        }
        for n in valid_notifs[:4]:
            sc = sev_colors.get(safe_get_field(n, "severity", "info"), DIM)
            raw_t = safe_get_field(n, "title", "") or ""
            tl = raw_t.lower()
            title = next((v for k, v in short_names.items() if k in tl), raw_t[:24])
            age = fmt_age(safe_get_field(n, "created_at"))
            unread = "-" if not safe_get_field(n, "seen", True) else " "
            rows.append(Text.from_markup(f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]"))

    # Algo metrics daily (action counts)
    valid_metrics = safe_get_list(algo_metrics)
    if valid_metrics:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Daily trade activity:[/]"))
        for m in valid_metrics[:5]:
            d = safe_get_field(m, "date")
            d_s = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
            ta = int(safe_get_field(m, "total_actions", 0)) if "total_actions" in m else 0
            en = int(safe_get_field(m, "entries", 0)) if "entries" in m else 0
            ex = int(safe_get_field(m, "exits", 0)) if "exits" in m else 0
            rows.append(
                Text.from_markup(
                    f"  [dim]{d_s}:[/] [white]{ta}[/][dim] total actions,  [/][{G}]{en}[/][dim] entries  [/][{R}]{ex}[/][dim] exits[/]"
                )
            )

    # Data loader status (errors/stale from data_loader_status table)
    valid_loader = safe_get_list(loader)
    problem_loader = [r for r in valid_loader if (safe_get_field(r, "status", "")) in ("error", "failed", "stale")]
    running_loader = [r for r in valid_loader if (safe_get_field(r, "status", "")) == "loading"]
    ok_count = len(valid_loader) - len(problem_loader) - len(running_loader)
    if problem_loader:
        rows.append(Rule(style="dim"))
        ok_s = f"  [dim]{ok_count} ok[/]" if ok_count > 0 else ""
        rows.append(Text.from_markup(f"[{Y}]Loaders ({len(problem_loader)} issues){ok_s}:[/]"))
        for r in problem_loader[:3]:
            nm = str((safe_get_field(r, "table_name", "") or "--")[:14])
            st = safe_get_field(r, "status") or "?"
            age = safe_get_field(r, "age_days")
            age_s = str(f"{int(age)}d" if age is not None else "--")
            sc = R if st in ("error", "failed") else Y
            err = (safe_get_field(r, "error_message", "") or "")[:20]
            rows.append(Text.from_markup(f"  [{sc}]{nm:<14}[/] [dim]{age_s}[/]" + (f" [dim]{err}[/]" if err else "")))
    elif valid_loader:
        if running_loader:
            rows.append(Rule(style="dim"))
            for r in running_loader[:3]:
                nm = (safe_get_field(r, "table_name", "") or "")[:12]
                pct = safe_get_field(r, "completion_pct")
                pct_s = f" {float(pct):.0f}%" if pct is not None else ""
                rows.append(Text.from_markup(f"[{CY}]Loading:[/][dim] {nm}{pct_s}[/]"))
        elif ok_count > 0:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup(f"[{G}]OK Loaders[/]  [dim]{ok_count} feeds healthy[/]"))

    # Audit log — most recent notable actions
    valid_audit = safe_get_list(audit)
    if valid_audit:
        notable = [
            a
            for a in valid_audit
            if any(k in (safe_get_field(a, "action_type", "") or "") for k in ("entry", "exit", "halt", "resume", "circuit"))
        ][:3]
        if notable:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[dim]Audit:[/]"))
            for a in notable:
                at = (safe_get_field(a, "action_type", "") or "").replace("_", " ")
                sym = safe_get_field(a, "symbol", "") or ""
                st = safe_get_field(a, "status", "")
                sc = G if st == "success" else (Y if st == "warn" else R)
                rows.append(Text.from_markup(f"  [{sc}]{at[:22]}[/]" + (f" [white]{sym}[/]" if sym else "")))

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
    if _error_panel("health", hlth, "HEALTH"):
        return _error_panel("health", hlth, "HEALTH")
    if _error_panel("notifications", notifs, "HEALTH"):
        return _error_panel("notifications", notifs, "HEALTH")

    rows: list = []

    # ── A: Run outcome ────────────────────────────────────────────────────────
    run_valid = run and not has_error(run)
    act_valid = act and not has_error(act)
    run_at = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
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
        rid = (run.get("run_id", ""))[:28]
        rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r = run.get("halt_reason", "")
        summary = run.get("summary", "")
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"  [{Y}]→ {prefix}{detail[:80]}[/]"))
        elif summary:
            rows.append(Text.from_markup(f"  [dim]{summary[:72]}[/]"))
    elif act_valid:
        rows.append(Text.from_markup(f"[dim]Last run (audit):[/]  [dim]{fmt_age(run_at)}[/]"))
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
        for p in run.get("phase_results", []):
            raw = (p.get("name") or p.get("phase", "")).lower()
            parts_p = raw.split("_")
            base = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
            ps = (p.get("status", "")).lower()
            sc = (
                G
                if ps in ("success", "completed", "ok")
                else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            )
            si = (
                "✓"
                if ps in ("success", "completed", "ok")
                else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
            )
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
            pdata = p.get("data")
            if isinstance(pdata, str):
                try:
                    pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase metrics data JSON: {e}")
                    pdata = None
            elif not isinstance(pdata, dict) and pdata is not None:
                pdata = None
            sg = pdata.get("signals_generated") if pdata else None
            ee = (pdata.get("entries_executed") or pdata.get("trades_executed")) if pdata else None
            xe = pdata.get("exits_executed") if pdata else None
            if sg:
                signals_gen = max(signals_gen, int(sg))
            if ee:
                entries_exec = max(entries_exec, int(ee))
            if xe:
                exits_exec = max(exits_exec, int(xe))
    elif run_valid or act_valid:
        src = run if run_valid else act
        phases_list = src.get("phase_results") or src.get("phases")
        if not phases_list:
            logger.warning(
                f"[HEALTH] Data source missing both 'phase_results' and 'phases'. Available keys: {list(src.keys())}. "
                "Phase status will not be displayed."
            )
            phases_list = []
        for p in phases_list:
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
            default_short = "_".join(name_parts)[:7] if name_parts else f"P{num}"
            short = PHASE_NAMES.get(phase_key, default_short)[:8]
            st = p.get("status", "")
            sc = G if st == "success" else (Y if st in ("halt", "warn", "halted") else R)
            si = "✓" if st == "success" else ("~" if st in ("halt", "warn", "halted") else "✗")
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

    if phase_badges:
        rows.append(Text.from_markup("  ".join(phase_badges)))

    # Fallback: use algo_metrics for today's entry/exit counts
    valid_metrics = (
        algo_metrics if (algo_metrics and not (isinstance(algo_metrics, dict) and has_error(algo_metrics))) else []
    )
    today_m = valid_metrics[0] if valid_metrics else {}
    if not entries_exec and "entries" in today_m:
        entries_exec = int(today_m["entries"])
    if not exits_exec and "exits" in today_m:
        exits_exec = int(today_m["exits"])

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

    # 5-day activity strip (last 5 days)
    if len(valid_metrics) >= 2:
        day_parts = []
        for m in valid_metrics[:5]:
            d = m.get("date")
            d_s = d.strftime("%d") if hasattr(d, "strftime") else str(d or "")[-2:]
            en = m.get("entries")
            ex = m.get("exits")
            # Show "--" if counts are missing, not 0 (which would hide incomplete data)
            en_s = str(int(en)) if en is not None else "--"
            ex_s = str(int(ex)) if ex is not None else "--"
            e_c = G if en is not None and en > 0 else DIM
            x_c = Y if ex is not None and ex > 0 else DIM
            day_parts.append(f"[dim]{d_s}:[/][{e_c}]{en_s}↑[/][{x_c}]{ex_s}↓[/]")
        rows.append(Text.from_markup("[dim]5d activity:[/] " + "  ".join(day_parts)))

    rows.append(Rule(style="dim"))

    # ── C: Run history (last 7 runs as badges) ───────────────────────────────
    valid_hist = exec_hist if (exec_hist and not (isinstance(exec_hist, dict) and has_error(exec_hist))) else []
    if valid_hist:
        n_ok = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() in ("success", "completed"))
        n_hlt = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() == "halted")
        n_err = sum(1 for r in valid_hist if (r.get("overall_status") or "").lower() in ("error", "failed"))
        total_h = len(valid_hist)
        badges = []
        for r in valid_hist[:7]:
            s = (r.get("overall_status") or "").lower()
            badges.append(
                f"[{G}]OK[/]" if s in ("success", "completed") else (f"[{Y}]~[/]" if s == "halted" else f"[{R}]X[/]")
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
            (r for r in valid_hist if (r.get("overall_status") or "").lower() == "halted"),
            None,
        )
        if last_halt:
            lhr = last_halt.get("halt_reason", "")
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
            rows.append(Text.from_markup(f"{rtt_badge}  [dim]{n_total} tables fresh[/]{crit_s}{oldest_s}"))
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
    if risk and not has_error(risk) and risk["var95"] and float(risk["var95"]) > 0:
        rows.append(Rule(style="dim"))
        var95_val = risk["var95"]
        beta_val = risk["beta"]
        conc5_val = risk["conc5"]
        cvar95_val = risk["cvar95"]
        svar_val = risk.get("svar")
        beta_c = R if beta_val >= 1.2 else (Y if beta_val >= 0.8 else G)
        conc_c = R if conc5_val >= 35 else (Y if conc5_val >= 25 else "white")
        var_c = _var_color(var95_val)
        risk_parts = [
            f"[dim]VaR 95%:[/][{var_c}]{var95_val:.2f}%[/]",
            f"[dim]CVaR 95%:[/][{var_c}]{cvar95_val:.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{beta_val:.2f}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{conc5_val:.0f}%[/]",
        ]
        if svar_val and float(svar_val) > 0:
            risk_parts.append(f"[dim]Stressed VaR:[/][{R}]{float(svar_val):.2f}%[/]")
        rows.append(Text.from_markup("  ".join(risk_parts)))

    # ── F: Notifications (compact) ────────────────────────────────────────────
    notifs_items = (
        notifs.get("items", [])
        if isinstance(notifs, dict) and "items" in notifs
        else (notifs if isinstance(notifs, list) else [])
    )
    notifs_error = has_error(notifs) if isinstance(notifs, dict) else None
    valid_notifs = notifs_items if notifs_items and not notifs_error else []
    if valid_notifs:
        rows.append(Rule(style="dim"))
        sev_colors = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        short_names = {
            "trading halted by circuit": "Halted:CB",
            "circuit breaker": "CB fired",
            "position entered": "Entered",
            "position exited": "Exited",
            "daily loss limit": "DailyLoss",
            "max drawdown": "MaxDD",
        }
        notif_parts = []
        for n in valid_notifs[:5]:
            sc = sev_colors.get(safe_get_field(n, "severity", "info"), DIM)
            raw_t = safe_get_field(n, "title", "") or ""
            title = next(
                (v for k, v in short_names.items() if k in raw_t.lower()),
                raw_t[:20],
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
    if _error_panel("health", hlth, "HEALTH EXPANDED"):
        return _error_panel("health", hlth, "HEALTH EXPANDED")
    if _error_panel("notifications", notifs, "HEALTH EXPANDED"):
        return _error_panel("notifications", notifs, "HEALTH EXPANDED")

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
        crit_stale = [r for r in hlth_items if isinstance(r, dict) and r.get("role") == "CRIT" and r.get("st") != "ok"]
        if crit_stale:
            crit_names = "  ".join(f"[bold white]{r.get('tbl', '')[:18]}[/]" for r in crit_stale)
            left_rows.append(Text.from_markup(f"[bold {R}]⚠ CRIT STALE:[/]  {crit_names}"))
        rtt_part = ""
        if ready_to_trade is True:
            rtt_part = f"  [bold {G}]✓ READY TO TRADE[/]"
        elif ready_to_trade is False:
            rtt_part = f"  [bold {R}]✗ NOT READY[/]"
        status_c = G if stale_count == 0 else (Y if stale_count <= 2 else R)
        left_rows.append(
            Text.from_markup(
                f"[dim]Freshness:[/] [{status_c}]{len(hlth_items) - stale_count}/{len(hlth_items)} fresh[/]"
                + (f"  [{R}]{stale_count} stale[/]" if stale_count else "")
                + rtt_part
            )
        )

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
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="dim",
            padding=(0, 1),
            expand=True,
            row_styles=["", "dim"],
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
            ii = "✓" if ok else ("-" if st == "empty" else "✗")
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
        msg = "⚠ Data health unavailable — loaders may not have run yet.\n"
        msg += "Check Phase 1 orchestrator status or monitor logs."
        left_rows.append(Text(msg, style="dim"))

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

    run_valid = run and not has_error(run)
    act_valid = act and not has_error(act)
    run_at = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid:
        sts = (
            f"[bold {G}]OK COMPLETED[/]"
            if run.get("success") and not run.get("halted")
            else (f"[bold {Y}]~ HALTED[/]" if run.get("halted") else f"[bold {R}]X ERROR[/]")
        )
        rid = run.get("run_id", "")
        rid = run.get("run_id", "")
        right_rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r = run.get("halt_reason", "")
        summary = run.get("summary", "")
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                right_rows.append(Text.from_markup(f"  [{Y}]-> {prefix}{detail}[/]"))
        elif summary:
            right_rows.append(Text.from_markup(f"  [dim]{summary}[/]"))

    phase_badges_e: list = []
    if run_valid and run.get("_source") == "exec_log":
        for p in run.get("phase_results", []):
            raw = (p.get("name") or p.get("phase", "")).lower()
            parts_p = raw.split("_")
            base = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
            ps = (p.get("status", "")).lower()
            sc = (
                G
                if ps in ("success", "completed", "ok")
                else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            )
            si = (
                "v"
                if ps in ("success", "completed", "ok")
                else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "x")
            )
            phase_badges_e.append(f"[{sc}]{si}[dim]{short}[/][/]")
    if phase_badges_e:
        right_rows.append(Text.from_markup("  ".join(phase_badges_e)))

    # entries/exits today
    signals_gen = 0
    entries_exec = 0
    exits_exec = 0
    if run_valid and run.get("_source") == "exec_log":
        for p in run.get("phase_results", []):
            pdata = p.get("data")
            if isinstance(pdata, str):
                try:
                    import json as _json

                    pdata = _json.loads(pdata)
                except Exception:
                    pdata = None
            elif not isinstance(pdata, dict) and pdata is not None:
                pdata = None
            sg = pdata.get("signals_generated") if pdata else None
            ee = (pdata.get("entries_executed") or pdata.get("trades_executed")) if pdata else None
            xe = pdata.get("exits_executed")
            if sg:
                signals_gen = max(signals_gen, int(sg))
            if ee:
                entries_exec = max(entries_exec, int(ee))
            if xe:
                exits_exec = max(exits_exec, int(xe))

    valid_metrics_e = (
        algo_metrics if (algo_metrics and not (isinstance(algo_metrics, dict) and has_error(algo_metrics))) else []
    )
    today_m_e = valid_metrics_e[0] if valid_metrics_e else {}
    if not entries_exec:
        en = today_m_e.get("entries")
        entries_exec = int(en) if en is not None else 0
    if not exits_exec:
        ex = today_m_e.get("exits")
        exits_exec = int(ex) if ex is not None else 0

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
            en = m.get("entries")
            ex = m.get("exits")
            en_s = str(int(en)) if en is not None else "--"
            ex_s = str(int(ex)) if ex is not None else "--"
            e_c = G if en is not None and en > 0 else DIM
            x_c = Y if ex is not None and ex > 0 else DIM
            day_parts_e.append(f"[dim]{d_s}:[/][{e_c}]{en_s}up[/][{x_c}]{ex_s}dn[/]")
        right_rows.append(Text.from_markup("[dim]5d:[/] " + "  ".join(day_parts_e)))

    right_rows.append(Rule(style="dim"))

    # Full run history
    valid_hist_e = exec_hist if (exec_hist and not (isinstance(exec_hist, dict) and has_error(exec_hist))) else []
    if valid_hist_e:
        n_ok = sum(1 for r in valid_hist_e if (r.get("overall_status") or "").lower() in ("success", "completed"))
        wc = G if n_ok == len(valid_hist_e) else (Y if n_ok > 0 else R)
        right_rows.append(
            Text.from_markup(f"[dim]Run history ({len(valid_hist_e)}):[/]  [{wc}]{n_ok}/{len(valid_hist_e)} success[/]")
        )
        for r in valid_hist_e:
            s = (r.get("overall_status") or "").lower()
            dt = r.get("started_at")
            dt_s = dt.strftime("%b %d  %I:%M %p") if hasattr(dt, "strftime") else str(dt or "")[:16]
            ic = G if s in ("success", "completed") else (Y if s == "halted" else R)
            ii = "v" if s in ("success", "completed") else ("~" if s == "halted" else "x")
            hr = r.get("halt_reason", "")
            lph = _fmt_phases_halted(r.get("phases_halted"))
            body = hr or lph
            ph_s = f"  [dim]({lph})[/]" if lph and lph not in (hr or "") else ""
            hr_s = f"  [{Y}]-> {body}[/]{ph_s}" if body else ""
            right_rows.append(Text.from_markup(f"  [{ic}]{ii}[/] [dim]{dt_s}[/]  [{ic}]{s}[/]{hr_s}"))

    # Risk snapshot
    if risk and not has_error(risk) and risk.get("var95") is not None and float(risk.get("var95")) > 0:
        right_rows.append(Rule(style="dim"))
        var95_val_e = risk.get("var95")
        beta_val_e = risk.get("beta")
        conc5_val_e = risk.get("conc5")
        cvar95_val_e = risk.get("cvar95")
        svar_val_e = risk.get("svar")
        beta_c = R if beta_val_e >= 1.2 else (Y if beta_val_e >= 0.8 else G)
        conc_c = R if conc5_val_e >= 35 else (Y if conc5_val_e >= 25 else "white")
        var_c = R if var95_val_e >= 4 else (Y if var95_val_e >= 2 else "white")
        risk_parts_e = [
            f"[dim]VaR95:[/][{var_c}]{var95_val_e:.2f}%[/]",
            f"[dim]CVaR:[/][{var_c}]{cvar95_val_e:.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{beta_val_e:.2f}[/]",
            f"[dim]Top5:[/][{conc_c}]{conc5_val_e:.0f}%[/]",
        ]
        if svar_val_e and float(svar_val_e) > 0:
            risk_parts_e.append(f"[dim]StressVaR:[/][{R}]{float(svar_val_e):.2f}%[/]")
        right_rows.append(Text.from_markup("  ".join(risk_parts_e)))

    # Notifications
    notifs_items_exp = (
        notifs.get("items", [])
        if isinstance(notifs, dict) and "items" in notifs
        else (notifs if isinstance(notifs, list) else [])
    )
    notifs_error_exp = has_error(notifs) if isinstance(notifs, dict) else None
    valid_notifs = notifs_items_exp if notifs_items_exp and not notifs_error_exp else []
    if valid_notifs:
        right_rows.append(Rule(style="dim"))
        right_rows.append(Text.from_markup("[dim]Notifications:[/]"))
        sev_colors = {"critical": R, "warning": Y, "info": CY, "debug": DIM}
        for n in valid_notifs:
            if not isinstance(n, dict):
                continue
            sc = sev_colors.get(n.get("severity", "info"), DIM)
            title = n.get("title") or ""
            age = fmt_age(safe_get_field(n, "created_at"))
            unread = "-" if not safe_get_field(n, "seen", True) else "."
            right_rows.append(Text.from_markup(f"  [{sc}]{unread} {title}[/] [dim]{age}[/]"))

    # Audit log
    valid_audit_exp = audit if (audit and not (isinstance(audit, dict) and has_error(audit))) else []
    if valid_audit_exp:
        right_rows.append(Rule(style="dim"))
        right_rows.append(Text.from_markup("[dim]Audit log:[/]"))
        for a in valid_audit_exp[:20]:
            if not isinstance(a, dict):
                continue
            at = (a.get("action_type") or "").replace("_", " ")
            sym = a.get("symbol") or ""
            st_a = a.get("status", "")
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
    "panel_algo_health",
    "panel_algo_health_expanded",
    "panel_orch",
    "panel_status",
]


