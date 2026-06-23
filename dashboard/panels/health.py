"""Health and orchestration panel functions."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class HealthFormatter:
    """Centralized formatting logic for health dashboard panels."""

    @staticmethod
    def var_color(var95: float | None) -> str:
        """Choose color for VaR 95% value: red if ≥4%, yellow if ≥2%, white otherwise."""
        from ..utilities import R, Y

        if var95 is None:
            return "dim"
        if var95 >= 4:
            return R
        if var95 >= 2:
            return Y
        return "white"

    @staticmethod
    def format_phase_badge(phase_status: str) -> tuple[str, str]:
        """Format phase status to (color, icon) badge."""
        from ..utilities import G, R, Y

        ps_lower = phase_status.lower() if phase_status else ""
        success_states = ("success", "completed", "ok")
        halted_states = ("halt", "halted", "warn", "degraded", "skipped")
        if ps_lower in success_states:
            return G, "✓"
        elif ps_lower in halted_states:
            return Y, "~"
        else:
            return R, "✗"

    @staticmethod
    def fmt_age(r: dict[str, Any]) -> str:
        """Format age from health item dict."""
        from dashboard.data_validation import safe_float

        ah = r.get("age_hours")
        ad = r.get("age")
        if ah is not None:
            ah_f = safe_float(ah, default=0.0) or 0.0
            return f"{ah_f:.0f}h" if ah_f < 24 else f"{ah_f / 24:.1f}d"
        elif ad is not None:
            ad_f = safe_float(ad, default=0.0) or 0.0
            return f"{ad_f:.1f}d"
        return "?"

    @staticmethod
    def fmt_updated(r: dict[str, Any]) -> str:
        """Format last_updated/latest timestamp from health item dict."""
        lat = r.get("last_updated") or r.get("latest")
        if lat is not None and hasattr(lat, "strftime"):
            return str(lat.strftime("%m/%d"))
        if isinstance(lat, str) and len(lat) >= 10:
            return lat[5:10]
        return str(lat or "")[:5]

    @staticmethod
    def pc(v: list[Any] | int) -> int:
        """Count phases: convert list or int to count."""
        if isinstance(v, list):
            return len(v)
        if isinstance(v, int):
            return v
        return 0


try:
    from panel_registry import register_panel
except ImportError as e:
    logger.warning(f"Panel registry not available: {e} - panels will not auto-register")

    def register_panel(*args: Any, **kwargs: Any) -> Any:
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

from dashboard.data_validation import safe_float

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
    extract_health_items,
    extract_risk_metrics,
    safe_extract,
    safe_get_dict,
    safe_get_list,
)

# Status state constants
SUCCESS_STATES = ("success", "completed", "ok")
HALTED_STATES = ("halt", "halted", "warn", "degraded", "skipped")
ERROR_STATES = ("error", "failed")

# Role priority ordering for health items
ROLE_ORDER = {"CRIT": 0, "IMP": 1, "NORM": 2}

# Severity to color mapping
SEV_COLORS = {"critical": R, "warning": Y, "info": CY, "debug": DIM}

# Notification title short names
NOTIF_SHORT_NAMES = {
    "trading halted by circuit": "Halted: CB",
    "circuit breaker": "CB fired",
    "position entered": "Entered",
    "position exited": "Exited",
    "daily loss limit": "DailyLoss",
    "max drawdown": "MaxDD hit",
}

# Loader status indicators
LOADER_STATUS_ERROR = ("error", "failed", "stale")
LOADER_STATUS_LOADING = "loading"

# Key phase data fields (in priority order)
PHASE_DATA_KEYS = (
    "signals_generated",
    "entries_executed",
    "exits_executed",
    "positions_checked",
    "orders_placed",
    "symbols_checked",
    "trades_executed",
    "checks_passed",
    "score",
)


def _build_freshness_panel(hlth_items: list[Any], ready_to_trade: bool | None) -> Panel:
    """Build LEFT panel: data freshness table with status summary.

    Args:
        hlth_items: Validated list of health status items
        ready_to_trade: Boolean ready state (True/False/None)

    Returns:
        Rich Panel with freshness table
    """
    left_rows: list[Text] = []

    if not hlth_items:
        msg = "⚠ Data health unavailable — loaders may not have run yet.\n"
        msg += "Check Phase 1 orchestrator status or monitor logs."
        left_rows.append(Text(msg, style="dim"))
        return Panel(
            Group(*left_rows),
            title="[bold yellow]DATA FRESHNESS[/]  [dim][h] return[/]",
            border_style="yellow",
            padding=(0, 1),
        )

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
            Text(HealthFormatter.fmt_age(r), style=DIM if ok else Y),
            Text(HealthFormatter.fmt_updated(r), style="dim"),
            Text(rc_s, style="dim"),
            Text(st_label, style=G if ok else (Y if st == "empty" else R)),
        )

    left_rows.append(all_tbl)

    return Panel(
        Group(*left_rows),
        title="[bold yellow]DATA FRESHNESS[/]  [dim][h] return[/]",
        border_style="yellow",
        padding=(0, 1),
    )


def panel_orch(run: dict[str, Any] | None, cfg: dict[str, Any], risk: dict[str, Any] | None = None) -> Panel:
    error_pnl = _error_panel("config", cfg, "ORCHESTRATION")
    if error_pnl:
        return error_pnl

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

    min_score_f = safe_float(min_score, default=0.0)
    score_s = f"[dim]min score ≥[/][white]{min_score}[/]" if min_score and min_score_f > 0 else ""
    slots_s = f"[dim]max [/][white]{max_n}[/][dim] positions[/]" if max_n else ""
    sec_s = f"[dim]sector ≤[/][white]{max_sec_n}[/]" if max_sec_n else ""
    risk_s = f"[dim]base risk [/][white]{base_risk}%[/]" if base_risk else ""
    t1r_s = f"[dim]T1 target [/][white]{t1r}R[/]" if t1r else ""
    config_line = "  ".join(x for x in [score_s, slots_s, sec_s, risk_s, t1r_s] if x)

    # VaR line — only show if table is populated with real data
    var_line = ""
    risk_dict = safe_get_dict(risk) if risk and not has_error(risk) else {}
    var95_check = risk_dict.get("var95") if risk_dict else None
    var95_check_f = safe_float(var95_check, default=0.0)
    if risk_dict and var95_check is not None and var95_check_f > 0:
        risk_metrics = extract_risk_metrics(risk_dict)
        if risk_metrics:
            var95_val = risk_metrics["var95"]
            beta_val = risk_metrics["beta"]
            cvar95_val = risk_metrics["cvar95"]
            conc5_val = risk_metrics["conc5"]
            svar_val = risk_metrics["svar"]
            beta_c = R if beta_val >= 1.2 else (Y if beta_val >= 0.8 else G)
            var_c = HealthFormatter.var_color(var95_val)
            svar_f = safe_float(svar_val, default=0.0)
            svar_s = f"\n[dim]Stressed VaR:[/][{R}]{svar_f:.2f}%[/]" if svar_val is not None and svar_f > 0 else ""
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
        age = fmt_age(run.get("run_at"))
        sts = (
            "[bold bright_green]✓ COMPLETED[/]"
            if run.get("success") and not run.get("halted")
            else ("[bold yellow]~ HALTED[/]" if run.get("halted") else "[bold bright_red]✗ ERROR[/]")
        )

        pbadges = []
        # exec_log source: structured per-phase objects with names + statuses
        if run.get("_source") == "exec_log":
            phase_results = safe_get_list(run.get("phase_results"))
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
            phases_list = safe_get_list(run.get("phase_results") or run.get("phases"))
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


def _format_exec_history_summary(exec_hist: list[Any]) -> list[Text]:
    """Format last N runs summary (used in panel_status and panel_algo_health)."""
    rows: list[Text] = []
    valid_hist = safe_get_list(exec_hist)
    if not valid_hist:
        return rows

    n_ok = sum(1 for r in valid_hist if (r.get("overall_status", "") or "").lower() in ("success", "completed"))
    n_hlt = sum(1 for r in valid_hist if (r.get("overall_status", "") or "").lower() == "halted")
    n_err = sum(1 for r in valid_hist if (r.get("overall_status", "") or "").lower() in ("error", "failed"))
    total_h = len(valid_hist)
    wr_h = n_ok / total_h * 100 if total_h else 0
    wc_h = G if wr_h >= 80 else (Y if wr_h >= 50 else R)

    badges = []
    for r in valid_hist[:7]:
        s = (r.get("overall_status", "") or "").lower()
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
        (r for r in valid_hist if (r.get("overall_status", "") or "").lower() == "halted"),
        None,
    )
    if last_halt:
        lhr = last_halt.get("halt_reason", "")
        lph = _fmt_phases_halted(last_halt.get("phases_halted"))
        body = lhr or lph
        if body:
            ph_s = f"  [dim]({lph})[/]" if lph and lph not in lhr else ""
            rows.append(Text.from_markup(f"  [{Y}]a†³ {body[:55]}[/]{ph_s}"))

    return rows


def _format_recent_trade_events(act: dict[str, Any]) -> list[Text]:
    """Format recent trade events (entry/exit/order)."""
    rows: list[Text] = []
    act_valid = act and not has_error(act)
    if act_valid and "recent_actions" not in act:
        rows.append(Text.from_markup("[dim]⚠ recent_actions data missing[/]"))
        return rows
    recent = act.get("recent_actions", []) if act_valid else []

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
        det = a.get("details")
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse action details JSON: {e}")
                det = None
        elif not isinstance(det, dict) and det is not None:
            det = None
        sym = det.get("symbol", "") if det else ""
        ic = G if ("executed" in at or at == "position_exited") else (Y if "placed" in at else R)
        lbl = at.replace("_", " ").title()[:20]
        rows.append(Text.from_markup(f"  [{ic}]{lbl}{(' ' + sym) if sym else ''}[/]"))

    return rows


def _format_data_health_summary(hlth_items: list[Any]) -> list[Text]:
    """Format data health section (stale tables only)."""
    rows: list[Text] = []
    if not hlth_items:
        return rows

    stale = [r for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok"]
    if not stale:
        rows.append(Text.from_markup(f"[{G}]OK Data OK[/]  [dim]{len(hlth_items)} tables[/]"))
        crit = [r for r in hlth_items if isinstance(r, dict) and r.get("role") == "CRIT"]
        if crit:
            crit_parts = "  ".join(f"[{G}]OK[/][dim]{r.get('tbl', '')[:13]}[/]" for r in crit)
            rows.append(Text.from_markup(f"  {crit_parts}"))
    else:
        for r in stale[:4]:
            nm = str((r.get("tbl", "") or "--")[:13])
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
            if lat is not None:
                try:
                    lat_s = f" ({lat.strftime('%m/%d')})"
                except (AttributeError, TypeError):
                    if isinstance(lat, str) and len(lat) >= 10:
                        lat_s = f" ({lat[5:10]})"
                    else:
                        lat_s = f" ({str(lat)[:5]})"
            else:
                lat_s = ""
            rows.append(Text.from_markup(f"[{R}]X[/] [{cc}]{nm:<13}[/] [dim]{age_s} stale{lat_s}[/]"))

    return rows


def _format_loader_status(loader: list[Any]) -> list[Text]:
    """Format data loader status section."""
    rows: list[Text] = []
    valid_loader = safe_get_list(loader) or []
    problem_loader = [r for r in valid_loader if (r.get("status", "")) in LOADER_STATUS_ERROR]
    running_loader = [r for r in valid_loader if (r.get("status", "")) == LOADER_STATUS_LOADING]
    ok_count = len(valid_loader) - len(problem_loader) - len(running_loader)

    if problem_loader:
        ok_s = f"  [dim]{ok_count} ok[/]" if ok_count > 0 else ""
        rows.append(Text.from_markup(f"[{Y}]Loaders ({len(problem_loader)} issues){ok_s}:[/]"))
        for r in problem_loader[:3]:
            nm = str((r.get("table_name", "") or "--")[:14])
            st = r.get("status") or "?"
            age = r.get("age_days")
            age_s = str(f"{int(age)}d" if age is not None else "--")
            sc = R if st in ("error", "failed") else Y
            err = (r.get("error_message", "") or "")[:20]
            rows.append(Text.from_markup(f"  [{sc}]{nm:<14}[/] [dim]{age_s}[/]" + (f" [dim]{err}[/]" if err else "")))
    elif valid_loader:
        if running_loader:
            for r in running_loader[:3]:
                nm = (r.get("table_name", "") or "")[:12]
                pct = r.get("completion_pct")
                pct_s = f" {float(pct):.0f}%" if pct is not None else ""
                rows.append(Text.from_markup(f"[{CY}]Loading:[/][dim] {nm}{pct_s}[/]"))
        elif ok_count > 0:
            rows.append(Text.from_markup(f"[{G}]OK Loaders[/]  [dim]{ok_count} feeds healthy[/]"))

    return rows


def _format_notifications_summary(notifs: list[Any]) -> list[Text]:
    """Format notifications section."""
    rows: list[Text] = []
    valid_notifs = safe_get_list(notifs)
    if not valid_notifs:
        return rows

    for n in valid_notifs[:4]:
        sc = SEV_COLORS.get(n.get("severity", "info"), DIM)
        raw_t = n.get("title", "") or ""
        tl = raw_t.lower()
        title = next((v for k, v in NOTIF_SHORT_NAMES.items() if k in tl), raw_t[:24])
        age = fmt_age(n.get("created_at"))
        unread = "-" if not n.get("seen", True) else " "
        rows.append(Text.from_markup(f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]"))

    return rows


def _format_daily_metrics_summary(algo_metrics: list[Any]) -> list[Text]:
    """Format daily trade activity summary."""
    rows: list[Text] = []
    valid_metrics = safe_get_list(algo_metrics)
    if not valid_metrics:
        return rows

    rows.append(Text.from_markup("[dim]Daily trade activity:[/]"))
    for m in valid_metrics[:5]:
        d = m.get("date")
        d_s = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
        ta = int(m.get("total_actions", 0)) if "total_actions" in m else 0
        en = int(m.get("entries", 0)) if "entries" in m else 0
        ex = int(m.get("exits", 0)) if "exits" in m else 0
        rows.append(
            Text.from_markup(
                f"  [dim]{d_s}:[/] [white]{ta}[/][dim] total actions,  [/][{G}]{en}[/][dim] entries  [/][{R}]{ex}[/][dim] exits[/]"
            )
        )

    return rows


def _format_audit_log_summary(audit: list[Any]) -> list[Text]:
    """Format audit log section (notable actions only)."""
    rows: list[Text] = []
    valid_audit = safe_get_list(audit)
    if not valid_audit:
        return rows

    notable = [
        a
        for a in valid_audit
        if any(k in (a.get("action_type", "") or "") for k in ("entry", "exit", "halt", "resume", "circuit"))
    ][:3]

    if not notable:
        return rows

    rows.append(Text.from_markup("[dim]Audit:[/]"))
    for a in notable:
        at = (a.get("action_type", "") or "").replace("_", " ")
        sym = a.get("symbol", "") or ""
        st = a.get("status", "")
        sc = G if st == "success" else (Y if st == "warn" else R)
        rows.append(Text.from_markup(f"  [{sc}]{at[:22]}[/]" + (f" [white]{sym}[/]" if sym else "")))

    return rows


# ── Helper functions for panel_algo_health() ──────────────────────────────────


def _age_h(r: dict[str, Any]) -> float | None:
    """Extract age in hours from health item dict."""
    ah = r.get("age_hours")
    if ah is not None:
        return float(ah)
    ad = r.get("age")
    if ad is not None:
        return float(ad) * 24
    return None


def _age_fmt_c(r: dict[str, Any]) -> str:
    """Format age with hours/days suffix."""
    h = _age_h(r)
    if h is None:
        return "?"
    return f"{h:.0f}h" if h < 24 else f"{h / 24:.1f}d"


def _extract_phase_metrics_from_pdata(pdata: dict[str, Any] | None) -> tuple[int, int, int]:
    """Extract signals_generated, entries_executed, exits_executed from phase data.

    Returns:
        (signals_gen, entries_exec, exits_exec) - all ints >= 0
    """
    if not pdata:
        return 0, 0, 0

    sg = pdata.get("signals_generated") or 0
    ee = (pdata.get("entries_executed") or pdata.get("trades_executed")) or 0
    xe = pdata.get("exits_executed") or 0
    return int(sg) if sg else 0, int(ee) if ee else 0, int(xe) if xe else 0


def _parse_phase_data_json(pdata_raw: str | dict | None) -> dict[str, Any] | None:
    """Parse phase data field (may be string or dict)."""
    if isinstance(pdata_raw, str):
        try:
            return json.loads(pdata_raw)  # type: ignore
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse phase metrics data JSON: {e}")
            return None
    elif isinstance(pdata_raw, dict):
        return pdata_raw
    return None


def _format_health_data_stale_section(stale: list[Any], hlth_list: list[Any] | None) -> str:
    """Format data health when stale tables exist."""
    crit_stale = [r for r in stale if r.get("role") == "CRIT"]
    if crit_stale:
        rtt_pfx = f"[bold {R}]CRIT STALE[/]  "
    else:
        rtt_pfx = f"[{Y}]{len(stale)} stale[/]  "

    stale_parts = []
    ordered = crit_stale + [r for r in stale if r not in crit_stale]
    for r in ordered[:4]:
        nm = (r.get("tbl") or "--")[:16]
        cc = f"bold {R}" if r.get("role") == "CRIT" else R
        stale_parts.append(f"[{R}]✗[/][{cc}]{nm}[/] [dim]{_age_fmt_c(r)}[/]")
    return f"{rtt_pfx}" + "  ".join(stale_parts)


def _format_health_data_fresh_section(hlth_list: list[Any], crit: list[Any], ready_to_trade: bool | None, ages: list[float | None]) -> str:
    """Format data health when all tables are fresh."""
    if ready_to_trade is False:
        rtt_badge = f"[bold {R}]✗ NOT READY[/]"
    elif ready_to_trade is True:
        rtt_badge = f"[{G}]✓ READY TO TRADE[/]"
    else:
        rtt_badge = f"[{G}]✓ Data OK[/]"

    n_total = len(hlth_list)
    n_crit = len(crit)
    oldest_s = f"  [dim]oldest: {_age_fmt_c(max(hlth_list, key=lambda r: _age_h(r) or 0))}[/]" if ages else ""
    crit_s = f"  [dim]crit {n_crit}[/][{G}] ok[/]" if n_crit else ""
    return f"{rtt_badge}  [dim]{n_total} tables fresh[/]{crit_s}{oldest_s}"


def _build_phase_badges_and_metrics(run: dict[str, Any], phase_results: list[Any]) -> tuple[list[str], int, int, int]:
    """Build phase badges and extract aggregated metrics from phase results.

    Returns:
        (phase_badges_list, signals_gen, entries_exec, exits_exec)
    """
    phase_badges = []
    signals_gen = 0
    entries_exec = 0
    exits_exec = 0

    for p in phase_results:
        raw = (p.get("name") or p.get("phase", "")).lower()
        parts_p = raw.split("_")
        base = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
        short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
        ps = p.get("status", "")
        sc, si = HealthFormatter.format_phase_badge(ps)
        phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

        # Extract metrics from phase data
        pdata = p.get("data")
        pdata = _parse_phase_data_json(pdata)
        sg, ee, xe = _extract_phase_metrics_from_pdata(pdata)
        if sg:
            signals_gen = max(signals_gen, sg)
        if ee:
            entries_exec = max(entries_exec, ee)
        if xe:
            exits_exec = max(exits_exec, xe)

    return phase_badges, signals_gen, entries_exec, exits_exec


def _build_phase_badges_from_audit(phases_list: list[Any]) -> list[str]:
    """Build phase badges from audit log format."""
    phase_badges = []
    for p in phases_list:
        at = p.get("action_type", "")
        if not at.startswith("phase_"):
            continue
        parts_p = at.split("_")
        num = parts_p[1] if len(parts_p) > 1 else "?"
        if not num.isdigit():
            continue
        phase_key = f"phase_{num}"
        name_parts = parts_p[2:] if len(parts_p) > 2 else []
        default_short = "_".join(name_parts)[:7] if name_parts else f"P{num}"
        short = PHASE_NAMES.get(phase_key, default_short)[:8]
        st = p.get("status", "")
        sc, si = HealthFormatter.format_phase_badge(st)
        phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
    return phase_badges


def _format_algo_actions_and_activity(
    signals_gen: int, entries_exec: int, exits_exec: int, today_m: dict[str, Any], valid_metrics: list[Any]
) -> list[Text]:
    """Format 'what did the algo do' summary and 5-day activity strip."""
    rows: list[Text] = []

    # "What did the algo do today?" summary
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
            en = m.get("entries")
            ex = m.get("exits")
            en_s = str(int(en)) if en is not None else "--"
            ex_s = str(int(ex)) if ex is not None else "--"
            e_c = G if en is not None and en > 0 else DIM
            x_c = Y if ex is not None and ex > 0 else DIM
            day_parts.append(f"[dim]{d_s}:[/][{e_c}]{en_s}↑[/][{x_c}]{ex_s}↓[/]")
        rows.append(Text.from_markup("[dim]5d activity:[/] " + "  ".join(day_parts)))

    return rows


def _format_run_history_summary(valid_hist: list[Any] | None) -> list[Text]:
    """Format run history badges and summary stats."""
    rows: list[Text] = []
    if not valid_hist:
        return rows

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

    return rows


def _format_risk_snapshot(risk_dict: dict[str, Any]) -> list[Text | Rule]:
    """Format risk metrics (VaR, CVaR, Beta, Concentration)."""
    rows: list[Text | Rule] = []
    var95_val = risk_dict.get("var95")
    if not var95_val or float(var95_val) <= 0:
        return rows

    rows.append(Rule(style="dim"))
    beta_val = risk_dict.get("beta")
    conc5_val = risk_dict.get("conc5")
    cvar95_val = risk_dict.get("cvar95")
    svar_val = risk_dict.get("svar")

    beta_c = R if beta_val >= 1.2 else (Y if beta_val >= 0.8 else G)
    conc_c = R if conc5_val >= 35 else (Y if conc5_val >= 25 else "white")
    var_c = HealthFormatter.var_color(var95_val)

    risk_parts = [
        f"[dim]VaR 95%:[/][{var_c}]{var95_val:.2f}%[/]",
        f"[dim]CVaR 95%:[/][{var_c}]{cvar95_val:.2f}%[/]",
        f"[dim]Beta:[/][{beta_c}]{beta_val:.2f}[/]",
        f"[dim]Top-5 Conc:[/][{conc_c}]{conc5_val:.0f}%[/]",
    ]
    if svar_val and float(svar_val) > 0:
        risk_parts.append(f"[dim]Stressed VaR:[/][{R}]{float(svar_val):.2f}%[/]")
    rows.append(Text.from_markup("  ".join(risk_parts)))

    return rows


def _format_notifications_section(valid_notifs: list[Any]) -> list[Text | Rule]:
    """Format notifications summary."""
    rows: list[Text | Rule] = []
    if not valid_notifs:
        return rows

    rows.append(Rule(style="dim"))
    notif_parts = []
    for n in valid_notifs[:5]:
        sc = SEV_COLORS.get(n.get("severity", "info"), DIM)
        raw_t = n.get("title", "") or ""
        title = next(
            (v for k, v in NOTIF_SHORT_NAMES.items() if k in raw_t.lower()),
            raw_t[:20],
        )
        age = fmt_age(n.get("created_at"))
        unread = "-" if not n.get("seen", True) else "·"
        notif_parts.append(f"[{sc}]{unread}{title}[/][dim]{age}[/]")
    rows.append(Text.from_markup("[dim]Alerts:[/] " + "  ".join(notif_parts)))

    return rows


def panel_status(
    act: dict[str, Any] | None,
    hlth: dict[str, Any] | list[Any] | None,
    notifs: list[Any],
    algo_metrics: list[Any] | None = None,
    loader: list[Any] | None = None,
    audit: list[Any] | None = None,
    run: dict[str, Any] | None = None,
    exec_hist: list[Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> Panel:
    """Algo activity phases + data health + recent notifications + action counts + loader status."""
    if _error_panel("health", hlth, "STATUS"):
        return _error_panel("health", hlth, "STATUS")
    if _error_panel("notifications", notifs, "STATUS"):
        return _error_panel("notifications", notifs, "STATUS")

    rows: list[Text | Rule] = []

    # Extract items from data dicts using safe helpers
    hlth_items = safe_get_list(hlth)

    # ── Run status + schedule + mode + trading config ────────────────────────────
    run_valid = run and not has_error(run)
    act_valid = act and not has_error(act)
    run_id_top = run.get("run_id", "") if run_valid else (act.get("run_id", "") if act_valid else "")
    run_at_top = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    if run_id_top or run_at_top:
        sts = (
            "[bold bright_green]✓ COMPLETED[/]"
            if (run_valid and run.get("success") and not run.get("halted"))
            else (
                "[bold yellow]~ HALTED[/]"
                if (run_valid and run.get("halted"))
                else ("[bold bright_red]✗ ERROR[/]" if (run_valid and run.get("errored")) else "[dim]RUN[/]")
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
    hist_rows = _format_exec_history_summary(exec_hist)
    if hist_rows:
        rows.extend(hist_rows)
        rows.append(Rule(style="dim"))

    # Current run status — shown prominently even when history is empty
    run_id = run.get("run_id") if run_valid else None
    run_at = run.get("run_at") if run else None
    if not run_id and act_valid:
        act_run_id = act.get("run_id")
        if act_run_id:
            run_id = act_run_id[:26]
        run_at = act.get("run_at")
    if run_id:
        age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""
        r_stat = ""
        if run_valid:
            if run.get("success"):
                r_stat = f"  [{G}]OK COMPLETED[/]"
            elif run.get("halted"):
                r_stat = f"  [{Y}]~ HALTED[/]"
            elif run.get("errored"):
                r_stat = f"  [{R}]X ERROR[/]"
        rows.append(Text.from_markup(f"[dim]Run:[/] [white]{run_id[:30]}[/]{age_s}{r_stat}"))

        # Show phases_completed/halted/errored counts from the run object
        if run_valid:
            n_done = HealthFormatter.pc(run.get("phases_completed"))
            n_hlt = HealthFormatter.pc(run.get("phases_halted"))
            n_err = HealthFormatter.pc(run.get("phases_errored"))
            if n_done + n_hlt + n_err > 0:
                done_s = f"[{G}]{n_done} phases OK[/]"
                hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
                err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
                rows.append(Text.from_markup(f"  {done_s}{hlt_s}{err_s}"))

    # Phase detail — named phases from exec_log with per-phase status and key data
    phase_badges = []
    run_source = run.get("_source") if run_valid else None
    if run_valid and run_source == "exec_log":
        halt_r = run.get("halt_reason", "")
        summary = run.get("summary", "")
        if run.get("halted") or halt_r:
            for label, detail in _best_halt_reason(halt_r, run.get("phase_results")):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"[{Y}]a†³ {prefix}{detail[:60]}[/]"))
        elif summary and isinstance(summary, str):
            rows.append(Text.from_markup(f"[dim]{summary[:65]}[/]"))

        if "phase_results" not in run:
            rows.append(Text.from_markup("[dim]⚠ phase_results data missing[/]"))
            return rows
        phase_results = run["phase_results"]
        for p in phase_results:
            raw = (p.get("name") or p.get("phase", "")).lower()
            parts = raw.split("_")
            base = "_".join(parts[:2]) if len(parts) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
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

            # Show error or key data for failed/halted phases
            err = p.get("error", "") or ""
            pdata = p.get("data")
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
                reason = (pdata.get("halt_reason", "") or pdata.get("reason", "") or "")[:55]
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
                        rows.append(Text.from_markup(f"  [dim]{short}:[/] [white]{key.replace('_', ' ')}={val}[/]"))
                        break

        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

        n_ok = HealthFormatter.pc(run.get("phases_completed"))
        n_hlt = HealthFormatter.pc(run.get("phases_halted"))
        n_err = HealthFormatter.pc(run.get("phases_errored"))
        if n_ok + n_hlt + n_err > 0:
            ok_s = f"[{G}]{n_ok} phases done[/]"
            hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
            err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
            rows.append(Text.from_markup(f"  {ok_s}{hlt_s}{err_s}"))
    elif act_valid:
        phases_list = act.get("phases")
        if not phases_list:
            logger.warning(
                f"[HEALTH] Activity log missing 'phases' field. Available keys: {list(act.keys())}. "
                "Activity phase status will not be displayed."
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
            st = p.get("status", "")
            sc, si = HealthFormatter.format_phase_badge(st)
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

    # Recent trade events (entry/exit/order) from audit_log
    trade_rows = _format_recent_trade_events(act)
    rows.extend(trade_rows)

    # Data health (stale tables only)
    if hlth_items:
        rows.append(Rule(style="dim"))
        health_rows = _format_data_health_summary(hlth_items)
        rows.extend(health_rows)

    # Notifications (up to 4)
    valid_notifs = safe_get_list(notifs)
    if valid_notifs:
        rows.append(Rule(style="dim"))
        for n in valid_notifs[:4]:
            sc = SEV_COLORS.get(n.get("severity", "info"), DIM)
            raw_t = n.get("title", "") or ""
            tl = raw_t.lower()
            title = next((v for k, v in NOTIF_SHORT_NAMES.items() if k in tl), raw_t[:24])
            age = fmt_age(n.get("created_at"))
            unread = "-" if not n.get("seen", True) else " "
            rows.append(Text.from_markup(f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]"))

    # Algo metrics daily (action counts)
    valid_metrics = safe_get_list(algo_metrics)
    if valid_metrics:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Daily trade activity:[/]"))
        for m in valid_metrics[:5]:
            d = m.get("date")
            d_s = d.strftime("%b %d") if hasattr(d, "strftime") else str(d or "--")
            ta = int(m.get("total_actions", 0)) if "total_actions" in m else 0
            en = int(m.get("entries", 0)) if "entries" in m else 0
            ex = int(m.get("exits", 0)) if "exits" in m else 0
            rows.append(
                Text.from_markup(
                    f"  [dim]{d_s}:[/] [white]{ta}[/][dim] total actions,  [/][{G}]{en}[/][dim] entries  [/][{R}]{ex}[/][dim] exits[/]"
                )
            )

    # Data loader status (errors/stale from data_loader_status table)
    valid_loader = safe_get_list(loader) or []
    problem_loader = [r for r in valid_loader if (r.get("status", "")) in ("error", "failed", "stale")]
    running_loader = [r for r in valid_loader if (r.get("status", "")) == "loading"]
    ok_count = len(valid_loader) - len(problem_loader) - len(running_loader)
    if problem_loader:
        rows.append(Rule(style="dim"))
        ok_s = f"  [dim]{ok_count} ok[/]" if ok_count > 0 else ""
        rows.append(Text.from_markup(f"[{Y}]Loaders ({len(problem_loader)} issues){ok_s}:[/]"))
        for r in problem_loader[:3]:
            nm = str((r.get("table_name", "") or "--")[:14])
            st = r.get("status") or "?"
            age = r.get("age_days")
            age_s = str(f"{int(age)}d" if age is not None else "--")
            sc = R if st in ("error", "failed") else Y
            err = (r.get("error_message", "") or "")[:20]
            rows.append(Text.from_markup(f"  [{sc}]{nm:<14}[/] [dim]{age_s}[/]" + (f" [dim]{err}[/]" if err else "")))
    elif valid_loader:
        if running_loader:
            rows.append(Rule(style="dim"))
            for r in running_loader[:3]:
                nm = (r.get("table_name", "") or "")[:12]
                pct = r.get("completion_pct")
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
            if any(k in (a.get("action_type", "") or "") for k in ("entry", "exit", "halt", "resume", "circuit"))
        ][:3]
        if notable:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[dim]Audit:[/]"))
            for a in notable:
                at = (a.get("action_type", "") or "").replace("_", " ")
                sym = a.get("symbol", "") or ""
                st = a.get("status", "")
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
    run: dict[str, Any] | None,
    act: dict[str, Any] | None,
    hlth: dict[str, Any] | list[Any] | None,
    notifs: list[Any],
    algo_metrics: list[Any] | None = None,
    audit: list[Any] | None = None,
    exec_hist: list[Any] | None = None,
    risk: dict[str, Any] | None = None,
) -> Panel:
    """Focused 'did the algo work?' panel: run outcome → what it did → system health."""
    if _error_panel("health", hlth, "HEALTH"):
        return _error_panel("health", hlth, "HEALTH")
    if _error_panel("notifications", notifs, "HEALTH"):
        return _error_panel("notifications", notifs, "HEALTH")

    rows: list[Text | Rule] = []

    # ── A: Run outcome ────────────────────────────────────────────────────────
    run_valid = run and not has_error(run)
    act_valid = act and not has_error(act)
    run_at = run.get("run_at") if run_valid else (act.get("run_at") if act_valid else None)
    age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid:
        # Validate critical fields exist upfront (fail-fast pattern)
        try:
            run_fields = safe_extract(
                run,
                "success",
                "halted",
                "errored",
                "run_id",
                "halt_reason",
                "summary",
                "phase_results",
            )
            success = run_fields["success"]
            halted = run_fields["halted"]
            errored = run_fields["errored"]
        except KeyError as e:
            logger.warning(f"Run data missing critical field: {e}")
            return _error_panel("run", {"_error": f"Run data incomplete: {e}"}, "HEALTH")

        if success and not halted:
            sts = f"[bold {G}]OK COMPLETED[/]"
        elif halted:
            sts = f"[bold {Y}]~ HALTED[/]"
        elif errored:
            sts = f"[bold {R}]X ERROR[/]"
        else:
            sts = "[dim]UNKNOWN[/]"
        rid = (run_fields["run_id"] or "")[:28]
        rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r = run_fields["halt_reason"] or ""
        summary = run_fields["summary"] or ""
        phase_results = run_fields["phase_results"]
        if halted or halt_r:
            for label, detail in _best_halt_reason(halt_r, phase_results):
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

    if run_valid and run.get("_source") == "exec_log":
        if "phase_results" not in run:
            return 0
        phase_results = run["phase_results"]
        phase_badges, signals_gen, entries_exec, exits_exec = _build_phase_badges_and_metrics(run, phase_results)
    elif run_valid or act_valid:
        src = run if run_valid else act
        phases_list = src.get("phase_results") or src.get("phases")
        if not phases_list:
            logger.warning(
                f"[HEALTH] Data source missing both 'phase_results' and 'phases'. Available keys: {list(src.keys())}. "
                "Phase status will not be displayed."
            )
            phases_list = []
        phase_badges = _build_phase_badges_from_audit(phases_list)

    if phase_badges:
        rows.append(Text.from_markup("  ".join(phase_badges)))

    # Fallback: use algo_metrics for today's entry/exit counts
    valid_metrics = safe_get_list(algo_metrics) or []
    today_m = valid_metrics[0] if valid_metrics else {}
    if not entries_exec:
        en = today_m.get("entries")
        if en is not None:
            entries_exec = int(en)
    if not exits_exec:
        ex = today_m.get("exits")
        if ex is not None:
            exits_exec = int(ex)

    # "What did the algo do today?" summary and 5-day activity
    action_activity_rows = _format_algo_actions_and_activity(
        signals_gen, entries_exec, exits_exec, today_m, valid_metrics
    )
    rows.extend(action_activity_rows)

    rows.append(Rule(style="dim"))

    # ── C: Run history (last 7 runs as badges) ───────────────────────────────
    valid_hist = safe_get_list(exec_hist)
    history_rows = _format_run_history_summary(valid_hist)
    rows.extend(history_rows)

    rows.append(Rule(style="dim"))

    # ── D: Data health (compact) ──────────────────────────────────────────────
    if hlth:
        hlth_list = safe_get_list(hlth)
        ready_to_trade = hlth.get("ready_to_trade") if isinstance(hlth, dict) else None
        stale = [r for r in hlth_list if isinstance(r, dict) and r.get("st") != "ok"] if hlth_list else []

        if not stale and hlth_list:
            crit = [r for r in hlth_list if r.get("role") == "CRIT"]
            ages = [_age_h(r) for r in hlth_list if _age_h(r) is not None]
            health_text = _format_health_data_fresh_section(hlth_list, crit, ready_to_trade, ages)
            rows.append(Text.from_markup(health_text))
        else:
            health_text = _format_health_data_stale_section(stale, hlth_list)
            rows.append(Text.from_markup(health_text))

    # ── E: Risk snapshot (VaR / CVaR / Beta / Concentration) ────────────────────
    risk_dict = safe_get_dict(risk) if not has_error(risk) else {}
    if risk_dict:
        var95_val = risk_dict.get("var95")
        if var95_val and float(var95_val) > 0:
            rows.append(Rule(style="dim"))
            beta_val = risk_dict.get("beta")
            conc5_val = risk_dict.get("conc5")
            cvar95_val = risk_dict.get("cvar95")
            svar_val = risk_dict.get("svar")
            beta_c = R if beta_val >= 1.2 else (Y if beta_val >= 0.8 else G)
            conc_c = R if conc5_val >= 35 else (Y if conc5_val >= 25 else "white")
            var_c = HealthFormatter.var_color(var95_val)
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
    valid_notifs = safe_get_list(notifs)
    if valid_notifs:
        rows.append(Rule(style="dim"))
        notif_parts = []
        for n in valid_notifs[:5]:
            sc = SEV_COLORS.get(n.get("severity", "info"), DIM)
            raw_t = n.get("title", "") or ""
            title = next(
                (v for k, v in NOTIF_SHORT_NAMES.items() if k in raw_t.lower()),
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


def _build_results_panel(run: dict[str, Any] | None, act: dict[str, Any] | None, algo_metrics: list[Any], exec_hist: list[Any], risk: dict[str, Any] | None, notifs: list[Any], audit: list[Any]) -> Panel:
    """Build RIGHT panel: run results, history, risk, notifications, audit.

    Args:
        run: Run data (validated for errors)
        act: Activity data (fallback if run missing)
        algo_metrics: Today's metrics + 5d history
        exec_hist: Full run execution history
        risk: Risk metrics (VaR, beta, concentration)
        notifs: Notification items
        audit: Audit log entries

    Returns:
        Rich Panel with run results and history
    """
    right_rows: list[Text | Rule] = [
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
        if "phase_results" in run:
            for p in safe_get_list(run["phase_results"]) or []:
                raw = (p.get("name") or p.get("phase", "")).lower()
                parts_p = raw.split("_")
                base = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
                short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
                ps = p.get("status", "")
                sc, si = HealthFormatter.format_phase_badge(ps)
            phase_badges_e.append(f"[{sc}]{si}[dim]{short}[/][/]")
    if phase_badges_e:
        right_rows.append(Text.from_markup("  ".join(phase_badges_e)))

    signals_gen = entries_exec = exits_exec = 0
    if run_valid and run.get("_source") == "exec_log":
        if "phase_results" in run:
            for p in safe_get_list(run["phase_results"]) or []:
                pdata = p.get("data")
                if isinstance(pdata, str):
                    try:
                        pdata = json.loads(pdata)
                    except (json.JSONDecodeError, ValueError):
                        pdata = None
                elif not isinstance(pdata, dict):
                    pdata = None
                if pdata:
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

    valid_hist_e = exec_hist if (exec_hist and not (isinstance(exec_hist, dict) and has_error(exec_hist))) else []
    if valid_hist_e:
        n_ok = sum(1 for r in valid_hist_e if (r.get("overall_status", "") or "").lower() in ("success", "completed"))
        wc = G if n_ok == len(valid_hist_e) else (Y if n_ok > 0 else R)
        right_rows.append(
            Text.from_markup(f"[dim]Run history ({len(valid_hist_e)}):[/]  [{wc}]{n_ok}/{len(valid_hist_e)} success[/]")
        )
        for r in valid_hist_e:
            s = (r.get("overall_status", "") or "").lower()
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

    risk_dict_b = safe_get_dict(risk) if not has_error(risk) else {}
    var95_b = risk_dict_b.get("var95") if risk_dict_b else None
    if risk_dict_b and var95_b is not None and float(var95_b) > 0:
        right_rows.append(Rule(style="dim"))
        var95_val_e = var95_b
        beta_val_e = risk_dict_b.get("beta")
        conc5_val_e = risk_dict_b.get("conc5")
        cvar95_val_e = risk_dict_b.get("cvar95")
        svar_val_e = risk_dict_b.get("svar")
        beta_c = (
            R
            if beta_val_e is not None and beta_val_e >= 1.2
            else (Y if beta_val_e is not None and beta_val_e >= 0.8 else G)
        )
        conc_c = (
            R
            if conc5_val_e is not None and conc5_val_e >= 35
            else (Y if conc5_val_e is not None and conc5_val_e >= 25 else "white")
        )
        var_c = R if var95_val_e >= 4 else (Y if var95_val_e >= 2 else "white")
        risk_parts_e = [
            f"[dim]VaR95:[/][{var_c}]{var95_val_e:.2f}%[/]",
        ]
        if cvar95_val_e is not None:
            risk_parts_e.append(f"[dim]CVaR:[/][{var_c}]{cvar95_val_e:.2f}%[/]")
        if beta_val_e is not None:
            risk_parts_e.append(f"[dim]Beta:[/][{beta_c}]{beta_val_e:.2f}[/]")
        if conc5_val_e is not None:
            risk_parts_e.append(f"[dim]Top5:[/][{conc_c}]{conc5_val_e:.0f}%[/]")
        if svar_val_e and float(svar_val_e) > 0:
            risk_parts_e.append(f"[dim]StressVaR:[/][{R}]{float(svar_val_e):.2f}%[/]")
        right_rows.append(Text.from_markup("  ".join(risk_parts_e)))

    valid_notifs = safe_get_list(notifs)
    if valid_notifs:
        right_rows.append(Rule(style="dim"))
        right_rows.append(Text.from_markup("[dim]Notifications:[/]"))
        for n in valid_notifs:
            sc = SEV_COLORS.get(n.get("severity", "info"), DIM)
            title = n.get("title", "") or ""
            age = fmt_age(n.get("created_at"))
            unread = "-" if not n.get("seen", True) else "."
            right_rows.append(Text.from_markup(f"  [{sc}]{unread} {title}[/] [dim]{age}[/]"))

    valid_audit_exp = safe_get_list(audit)
    if valid_audit_exp:
        right_rows.append(Rule(style="dim"))
        right_rows.append(Text.from_markup("[dim]Audit log:[/]"))
        for a in valid_audit_exp[:20]:
            at = (a.get("action_type", "") or "").replace("_", " ")
            sym = a.get("symbol", "") or ""
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

    return Panel(
        Group(*right_rows),
        title="[bold yellow]RUN RESULTS & HISTORY[/]  [dim][h] return[/]",
        border_style="yellow",
        padding=(0, 1),
    )


def panel_algo_health_expanded(
    run: dict[str, Any] | None,
    act: dict[str, Any] | None,
    hlth: dict[str, Any] | list[Any] | None,
    notifs: list[Any],
    algo_metrics: list[Any] | None = None,
    audit: list[Any] | None = None,
    exec_hist: list[Any] | None = None,
    risk: dict[str, Any] | None = None,
) -> Layout:
    """Full-screen algo health — dual column: data freshness (left) | run results (right)."""
    if _error_panel("health", hlth, "HEALTH EXPANDED"):
        return _error_panel("health", hlth, "HEALTH EXPANDED")
    if _error_panel("notifications", notifs, "HEALTH EXPANDED"):
        return _error_panel("notifications", notifs, "HEALTH EXPANDED")

    hlth_items, ready_to_trade = extract_health_items(hlth)
    left_panel = _build_freshness_panel(hlth_items, ready_to_trade)
    right_panel = _build_results_panel(run, act, algo_metrics, exec_hist, risk, notifs, audit)

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
