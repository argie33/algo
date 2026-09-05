"""panel_status: the focused algo-run STATUS panel. Split out of health_status.py to stay
under the file-size ratchet's cap - its formatter helpers live in health_status.py (which
kept the name) and are imported back here.
"""

import json
import logging
from typing import Any, cast

from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ..error_boundary import has_error
from ..formatters import fmt_age, next_run_str
from ..utilities import DIM, PHASE_NAMES, G, R, Y
from ._helpers import _best_halt_reason, _error_panel
from .data_extractors import extract_config_params, safe_get_dict, safe_get_list
from .health_shared import (
    NOTIF_SHORT_NAMES,
    PHASE_SUCCESS_STATES,
    SEV_COLORS,
    _format_phase_badge,
    _var_color,
)
from .health_status import (
    _format_comprehensive_table_loader_health,
    _format_exec_history_summary,
    _format_recent_trade_events,
    _pc,
)

logger = logging.getLogger(__name__)


def _format_notifications_summary(notifs: list[Any]) -> list[Text]:
    """Format notifications section."""
    rows: list[Text] = []
    valid_notifs_raw = safe_get_list(notifs)
    if not isinstance(valid_notifs_raw, list):
        valid_notifs_raw = []
    if not valid_notifs_raw:
        logger.debug(
            "[HEALTH_FORMAT] Notifications unavailable for display. "
            "No alerts to show - system is operating normally with no active notifications."
        )
        return rows

    for n in valid_notifs_raw[:4]:
        if not isinstance(n, dict):
            continue
        severity_val = n.get("severity")
        # CRITICAL: Explicit None check instead of implicit fallback
        # Missing severity indicates incomplete notification record
        if severity_val is None:
            logger.warning(f"[HEALTH] Notification missing 'severity'. Keys: {list(n.keys())}")
            severity_val = "info"
        sc = SEV_COLORS.get(severity_val, DIM)
        title_val = n.get("title")
        # CRITICAL: Explicit None check instead of implicit fallback
        if title_val is None:
            title_val = ""
        raw_t = title_val
        tl = raw_t.lower()
        # CRITICAL: Explicit fallback check instead of implicit slice
        # Missing or unmapped notification title should be logged
        title = next((v for k, v in NOTIF_SHORT_NAMES.items() if k in tl), None)
        if title is None:
            title = raw_t[:24]
            if raw_t:
                logger.debug(f"[HEALTH] Notification title not found in NOTIF_SHORT_NAMES: {raw_t[:40]}")
        age = fmt_age(n.get("created_at"))
        seen_val = n.get("seen")
        if seen_val is None:
            seen_val = True
        unread = "-" if not seen_val else " "
        rows.append(Text.from_markup(f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]"))

    return rows


def _format_daily_metrics_summary(algo_metrics: list[Any]) -> list[Text]:
    """Format daily trade activity summary."""
    rows: list[Text] = []
    valid_metrics_raw = safe_get_list(algo_metrics)
    if not isinstance(valid_metrics_raw, list):
        valid_metrics_raw = []
    if not valid_metrics_raw:
        logger.warning(
            "[METRICS_FORMAT] Daily algo metrics unavailable for display. "
            "No trade activity records found - metrics table may be empty or API returned null."
        )
        return rows

    valid_metrics: list[Any] = valid_metrics_raw
    rows.append(Text.from_markup("[dim]Daily trade activity:[/]"))
    for m in valid_metrics[:5]:
        if not isinstance(m, dict):
            continue
        d = m.get("date")
        # CRITICAL: Explicit None check instead of OR fallback
        # Missing date in metrics indicates incomplete data, should not default to "--"
        if d is None:
            d_s = "--"
        elif hasattr(d, "strftime"):
            d_s = d.strftime("%b %d")
        else:
            d_s = str(d)
        ta = m.get("total_actions")
        if ta is None:
            ta = 0
        else:
            try:
                ta = int(ta)
            except (TypeError, ValueError):
                ta = 0
        en = m.get("entries")
        if en is None:
            en = 0
        else:
            try:
                en = int(en)
            except (TypeError, ValueError):
                en = 0
        ex = m.get("exits")
        if ex is None:
            ex = 0
        else:
            try:
                ex = int(ex)
            except (TypeError, ValueError):
                ex = 0
        rows.append(
            Text.from_markup(
                f"  [dim]{d_s}:[/] [white]{ta}[/][dim] total actions,  [/][{G}]{en}[/][dim] entries  [/][{R}]{ex}[/][dim] exits[/]"
            )
        )

    return rows


def _format_audit_log_summary(audit: list[Any]) -> list[Text]:
    """Format audit log section (notable actions only)."""
    rows: list[Text] = []
    valid_audit_raw = safe_get_list(audit)
    if not isinstance(valid_audit_raw, list):
        valid_audit_raw = []
    if not valid_audit_raw:
        logger.debug(
            "[AUDIT_FORMAT] Audit log unavailable for display. "
            "No audit records found - API may have returned null or audit table is empty."
        )
        return rows

    valid_audit: list[Any] = valid_audit_raw
    notable = [
        a
        for a in valid_audit
        if isinstance(a, dict)
        and a.get("action_type")
        # CRITICAL: Explicit None check instead of OR fallback with str()
        # Missing action_type should trigger validation, not silent fallback
        and any(
            k in (str(a.get("action_type")) if a.get("action_type") is not None else "")
            for k in ("entry", "exit", "halt", "resume", "circuit")
        )
    ][:3]

    if not notable:
        return rows

    rows.append(Text.from_markup("[dim]Audit:[/]"))
    for a in notable:
        action_type_val = a.get("action_type")
        if action_type_val is None:
            logger.debug("[HEALTH] Audit entry missing action_type field - defaulting to empty string")
            action_type_val = ""
        at = (action_type_val if action_type_val else "").replace("_", " ")
        symbol_val = a.get("symbol")
        if symbol_val is None:
            logger.debug("[HEALTH] Audit entry missing symbol field - defaulting to empty string")
            symbol_val = ""
        sym = symbol_val if symbol_val else ""
        st_raw = a.get("status")
        if st_raw is None:
            st_raw = ""
        st = st_raw
        sc = G if st == "success" else (Y if st == "warn" else R)
        rows.append(Text.from_markup(f"  [{sc}]{at[:22]}[/]" + (f" [white]{sym}[/]" if sym else "")))

    return rows


# ── Helper functions for panel_algo_health() ──────────────────────────────────


def _format_risk_snapshot(risk_dict: dict[str, Any]) -> list[Text | Rule]:
    """Format risk metrics (VaR, CVaR, Beta, Concentration)."""
    from ..data_validation import safe_float

    rows: list[Text | Rule] = []
    var95_val = safe_float(risk_dict.get("var95"), default=None)
    # CRITICAL: Explicit None and value checks instead of OR fallback
    # Missing or zero VaR95 indicates incomplete risk data, should not silently return empty
    if var95_val is None or var95_val <= 0:
        logger.debug(
            "[RISK_FORMAT] Risk metrics unavailable for display. "
            "VaR 95% metric missing or zero - risk calculation may have failed or insufficient data."
        )
        return rows

    rows.append(Rule(style="dim"))
    beta_val = safe_float(risk_dict.get("beta"), default=None)
    conc5_val = safe_float(risk_dict.get("conc5"), default=None)
    cvar95_val = safe_float(risk_dict.get("cvar95"), default=None)
    svar_val = safe_float(risk_dict.get("svar"), default=None)

    beta_c = (
        R if (beta_val is not None and beta_val >= 1.2) else (Y if (beta_val is not None and beta_val >= 0.8) else G)
    )
    conc_c = (
        R
        if (conc5_val is not None and conc5_val >= 35)
        else (Y if (conc5_val is not None and conc5_val >= 25) else "white")
    )
    var_c = _var_color(var95_val)

    if var95_val is None or beta_val is None or cvar95_val is None or conc5_val is None:
        # CRITICAL: When beta = 0, show "--" instead of "0.00"
        beta_display_na = "-" if (beta_val is None or (beta_val is not None and beta_val <= 0)) else f"{beta_val:.2f}"
        rows.append(
            Text.from_markup(
                f"[dim]VaR 95%:[/][{var_c}]{'-' if var95_val is None else f'{var95_val:.2f}%'}[/]  "
                f"[dim]CVaR 95%:[/][{var_c}]{'-' if cvar95_val is None else f'{cvar95_val:.2f}%'}[/]  "
                f"[dim]Beta:[/][{beta_c}]{beta_display_na}[/]  "
                f"[dim]Top-5 Conc:[/][{conc_c}]{'-' if conc5_val is None else f'{conc5_val:.0f}%'}[/]"
            )
        )
    else:
        # At this point all values are guaranteed non-None
        # CRITICAL: When beta = 0, show "--" instead of "0.00"
        beta_display_else = "--" if beta_val <= 0 else f"{beta_val:.2f}"
        risk_parts = [
            f"[dim]VaR 95%:[/][{var_c}]{var95_val:.2f}%[/]",
            f"[dim]CVaR 95%:[/][{var_c}]{cvar95_val:.2f}%[/]",
            f"[dim]Beta:[/][{beta_c}]{beta_display_else}[/]",
            f"[dim]Top-5 Conc:[/][{conc_c}]{conc5_val:.0f}%[/]",
        ]
        if svar_val is not None and svar_val > 0:
            risk_parts.append(f"[dim]Stressed VaR:[/][{R}]{svar_val:.2f}%[/]")
        rows.append(Text.from_markup("  ".join(risk_parts)))

    return rows


def _format_notifications_section(valid_notifs: list[Any]) -> list[Text | Rule]:
    """Format notifications summary."""
    rows: list[Text | Rule] = []
    if not valid_notifs:
        logger.debug(
            "[NOTIF_FORMAT] Notifications section unavailable for display. "
            "No active alerts - system operating normally with no critical notifications."
        )
        return rows

    rows.append(Rule(style="dim"))
    notif_parts = []
    for n in valid_notifs[:5]:
        severity_val = n.get("severity")
        if severity_val is None:
            logger.debug("[HEALTH] Notification missing severity - defaulting to 'info' (DIM color)")
            severity_val = "info"
        sc = SEV_COLORS.get(severity_val, DIM)
        title_val = n.get("title")
        if title_val is None:
            logger.debug("[HEALTH] Notification missing title - defaulting to empty string")
            title_val = ""
        raw_t = title_val if title_val else ""
        title = next(
            (v for k, v in NOTIF_SHORT_NAMES.items() if k in raw_t.lower()),
            raw_t[:20],
        )
        age = fmt_age(n.get("created_at"))
        seen_val = n.get("seen")
        if seen_val is None:
            seen_val = True
        unread = "-" if not seen_val else "·"
        notif_parts.append(f"[{sc}]{unread}{title}[/][dim]{age}[/]")
    rows.append(Text.from_markup("[dim]Alerts:[/] " + "  ".join(notif_parts)))

    return rows


def panel_status(  # noqa: C901
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
    error_pnl = _error_panel("health", hlth, "STATUS")
    if error_pnl is not None:
        return error_pnl
    error_pnl = _error_panel("notifications", notifs, "STATUS")
    if error_pnl is not None:
        return error_pnl

    rows: list[Text | Rule] = []

    # Extract items from data dicts using safe helpers
    hlth_items_raw = safe_get_list(hlth)
    # Type guard: ensure hlth_items is a list
    hlth_items: list[Any] = hlth_items_raw if isinstance(hlth_items_raw, list) else []

    # ── Run status + schedule + mode + trading config ────────────────────────────
    run_valid = run and isinstance(run, dict) and not has_error(run)
    act_valid = act and isinstance(act, dict) and not has_error(act)
    run_id_top_raw = (
        cast(dict[str, Any], run).get("run_id")
        if run_valid
        else (cast(dict[str, Any], act).get("run_id") if act_valid else None)
    )
    run_id_top = run_id_top_raw if run_id_top_raw is not None else ""
    run_at_top = (
        cast(dict[str, Any], run).get("run_at")
        if run_valid
        else (cast(dict[str, Any], act).get("run_at") if act_valid else None)
    )
    if run_id_top or run_at_top:
        sts = (
            "[bold bright_green]✓ COMPLETED[/]"
            if (run_valid and isinstance(run, dict) and run.get("success") and not run.get("halted"))
            else (
                "[bold yellow]~ HALTED[/]"
                if (run_valid and isinstance(run, dict) and run.get("halted"))
                else (
                    "[bold bright_red]✗ ERROR[/]"
                    if (run_valid and isinstance(run, dict) and run.get("errored"))
                    else "[dim]RUN[/]"
                )
            )
        )
        age_s = f"  [dim]{fmt_age(run_at_top)}[/]" if run_at_top else ""
        rows.append(Text.from_markup(f"{sts}{age_s}"))

    # Config extraction - use helper to reduce .get() calls
    cfg_v = safe_get_dict(cfg)
    cfg_params = extract_config_params(cfg_v) if cfg_v else {}
    mode_raw = cfg_params.get("mode")
    mode = mode_raw if mode_raw is not None else ""
    if mode_raw is None:
        logger.debug("[HEALTH_STATUS] Config mode missing - display color defaulting to YELLOW (paper mode)")
    en_raw = cfg_params.get("enabled")
    en = en_raw if en_raw is not None else True
    if en_raw is None:
        logger.debug("[HEALTH_STATUS] Config enabled flag missing - defaulting to True")
    mc = G if "LIVE" in str(mode) else Y
    ec = G if en else R
    en_s = "ENABLED" if en else "DISABLED"
    next_r = next_run_str()
    rows.append(Text.from_markup(f"[{mc}]{mode or 'PAPER'}[/]  [{ec}]{en_s}[/]  [dim]Next run:[/] [white]{next_r}[/]"))

    # Trading config params - visible context for position sizing decisions
    cfg_parts = []
    max_pos_n = cfg_params.get("max_pos_n")
    max_sec_n = cfg_params.get("max_sec_n")
    base_risk = cfg_params.get("base_risk")
    t1_r = cfg_params.get("t1_r")
    # `is not None`, not truthiness - a real 0 (e.g. base_risk=0 during a halt, or
    # max_sec_n=0) is a meaningful configured value and must not disappear as if unset.
    if max_pos_n is not None:
        cfg_parts.append(f"[dim]slots:[/][white]{max_pos_n}[/]")
    if max_sec_n is not None:
        cfg_parts.append(f"[dim]sector≤4:[/][white]{max_sec_n}[/]")
    if base_risk is not None:
        cfg_parts.append(f"[dim]risk:[/][white]{base_risk}%[/]")
    if t1_r is not None:
        cfg_parts.append(f"[dim]T1:[/][white]{t1_r}R[/]")
    if cfg_parts:
        rows.append(Text.from_markup("  ".join(cfg_parts)))
    rows.append(Rule(style="dim"))

    # Execution history summary - last 7 runs
    hist_rows = _format_exec_history_summary(exec_hist)
    if hist_rows:
        rows.extend(hist_rows)
        rows.append(Rule(style="dim"))

    # Current run status - shown prominently even when history is empty
    run_id = run.get("run_id") if (run_valid and isinstance(run, dict)) else None
    run_at = run.get("run_at") if (isinstance(run, dict)) else None
    if not run_id and act_valid:
        act_run_id = act.get("run_id") if (isinstance(act, dict)) else None
        if act_run_id:
            run_id = act_run_id[:26]
        run_at = act.get("run_at") if (isinstance(act, dict)) else None
    if run_id:
        age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""
        r_stat = ""
        if run_valid and isinstance(run, dict):
            success = run.get("success")
            halted = run.get("halted")
            errored = run.get("errored")
            if success is None:
                logger.warning("[HEALTH] Run status 'success' field missing")
            if success:
                r_stat = f"  [{G}]OK COMPLETED[/]"
            elif halted:
                r_stat = f"  [{Y}]~ HALTED[/]"
            elif errored:
                r_stat = f"  [{R}]X ERROR[/]"
            elif success is not False and halted is not False and errored is not False:
                r_stat = ""
        rows.append(Text.from_markup(f"[dim]Run:[/] [white]{run_id[:30]}[/]{age_s}{r_stat}"))

        # Show phases_completed/halted/errored counts from the run object
        if run_valid and isinstance(run, dict):
            n_done = _pc(run.get("phases_completed"))
            n_hlt = _pc(run.get("phases_halted"))
            n_err = _pc(run.get("phases_errored"))
            if n_done + n_hlt + n_err > 0:
                done_s = f"[{G}]{n_done} phases OK[/]"
                hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
                err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
                rows.append(Text.from_markup(f"  {done_s}{hlt_s}{err_s}"))

    # Phase detail - named phases from exec_log with per-phase status and key data
    phase_badges = []
    run_source = (run.get("_source") if isinstance(run, dict) else None) if run_valid else None
    if run_valid and isinstance(run, dict) and run_source == "exec_log":
        halt_r = run.get("halt_reason")
        if halt_r is None:
            halt_r = ""
        summary = run.get("summary")
        if summary is None:
            summary = ""
        if run.get("halted") or halt_r:
            pr_val = run.get("phase_results") if isinstance(run, dict) else None
            if pr_val is None:
                pr_val = []
            for label, detail in _best_halt_reason(halt_r, pr_val):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"[{Y}]→ {prefix}{detail[:60]}[/]"))
        elif summary and isinstance(summary, str):
            rows.append(Text.from_markup(f"[dim]{summary[:65]}[/]"))

        if not isinstance(run, dict) or "phase_results" not in run:
            return Panel(
                Text.from_markup("[dim]⚠ phase_results data missing[/]"),
                title="[bold yellow]ALGO HEALTH[/]",
                border_style="yellow",
                padding=(0, 1),
            )
        phase_results = run["phase_results"]
        for p in phase_results:
            name_val = p.get("name")
            phase_val = p.get("phase")
            if phase_val is None:
                phase_val = ""
            raw = (name_val if name_val is not None else phase_val).lower()
            parts = raw.split("_")
            base = "_".join(parts[:2]) if len(parts) >= 2 else raw
            short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:9]
            ps_raw = p.get("status")
            if ps_raw is None:
                ps_raw = ""
            ps = ps_raw.lower()
            # Same benign-stub exemption as _build_phase_execution_panel/_build_results_panel
            # (see either for the full 2026-08-10 writeup): Phase 6's dry_run branch reports
            # status="degraded" unconditionally before any real exit logic runs, so this exact
            # literal "DRY-RUN" summary can never coexist with a genuine exit error. Without
            # this, this panel showed a yellow "~" (halted-looking) badge for Exit Execution on
            # every single local dry-run - the same false-halt confusion already fixed twice
            # elsewhere in this file but missed here (this panel is currently unreachable from
            # the live dashboard, but a real bug is still a real bug).
            is_dry_run_stub = ps == "degraded" and "DRY-RUN" in (p.get("summary") or "")
            sc = (
                G
                if ps in PHASE_SUCCESS_STATES
                else (DIM if is_dry_run_stub else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R))
            )
            si = (
                "✓"
                if ps in PHASE_SUCCESS_STATES
                else (
                    "⊘"
                    if is_dry_run_stub
                    else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
                )
            )
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")

            # Show error or key data for failed/halted phases
            error_val = p.get("error")
            if error_val is None:
                error_val = ""
            err = error_val if error_val else ""
            pdata = p.get("data")
            if isinstance(pdata, str):
                try:
                    pdata = json.loads(pdata)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse phase data JSON: {e}")
                    pdata = None
            elif not isinstance(pdata, dict) and pdata is not None:
                pdata = None
            if err and ps not in PHASE_SUCCESS_STATES:
                rows.append(Text.from_markup(f"  [{sc}]→ {err[:62]}[/]"))
            elif ps in ("halt", "halted") and pdata:
                halt_reason_val = pdata.get("halt_reason")
                if halt_reason_val is None:
                    halt_reason_val = ""
                reason_val = pdata.get("reason")
                if reason_val is None:
                    reason_val = ""
                reason = (halt_reason_val if halt_reason_val else (reason_val if reason_val else ""))[:55]
                if reason:
                    rows.append(Text.from_markup(f"  [{Y}]→ {reason}[/]"))
            elif ps in PHASE_SUCCESS_STATES and pdata:
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

        if run_valid and isinstance(run, dict):
            n_ok = _pc(run.get("phases_completed"))
            n_hlt = _pc(run.get("phases_halted"))
            n_err = _pc(run.get("phases_errored"))
        else:
            n_ok = n_hlt = n_err = 0
        if n_ok + n_hlt + n_err > 0:
            ok_s = f"[{G}]{n_ok} phases done[/]"
            hlt_s = f"  [{Y}]{n_hlt} halted[/]" if n_hlt else ""
            err_s = f"  [{R}]{n_err} errored[/]" if n_err else ""
            rows.append(Text.from_markup(f"  {ok_s}{hlt_s}{err_s}"))
    elif act_valid and isinstance(act, dict):
        phases_list = act.get("phases")
        if not phases_list:
            logger.error(
                f"[HEALTH] CRITICAL: Activity log missing 'phases' field. "
                f"Cannot display activity phase status. Available keys: {list(act.keys())}"
            )
            rows.append(
                Text.from_markup(
                    "[red bold]ERROR: Activity phase status unavailable[/] (orchestration activity log incomplete)"
                )
            )
            phases_list = []
        for p in phases_list:
            at_raw = p.get("action_type")
            if at_raw is None:
                at_raw = ""
            at = at_raw
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
            st_raw = p.get("status")
            if st_raw is None:
                st_raw = ""
            st = st_raw
            sc, si = _format_phase_badge(st)
            phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
        if phase_badges:
            rows.append(Text.from_markup("  ".join(phase_badges)))

    # Recent trade events (entry/exit/order) from audit_log
    trade_rows = _format_recent_trade_events(act)
    rows.extend(trade_rows)

    # Data & Loader Health (unified comprehensive view showing all tables with loader status)
    if hlth_items or loader:
        rows.append(Rule(style="dim"))
        table_loader_rows = _format_comprehensive_table_loader_health(hlth_items, loader)
        rows.extend(table_loader_rows)

    # Notifications (up to 4)
    valid_notifs_raw = safe_get_list(notifs)
    if isinstance(valid_notifs_raw, list) and valid_notifs_raw:
        valid_notifs_list: list[Any] = valid_notifs_raw
        rows.append(Rule(style="dim"))
        for n in valid_notifs_list[:4]:
            if not isinstance(n, dict):
                continue
            # CRITICAL: Explicit None check instead of OR fallback
            severity_val = n.get("severity")
            if severity_val is None:
                severity_val = "info"
            sc = SEV_COLORS.get(severity_val, DIM)
            # CRITICAL: Explicit None check instead of OR fallback
            title_val = n.get("title")
            if title_val is None:
                title_val = ""
            raw_t = title_val
            tl = raw_t.lower()
            title = next((v for k, v in NOTIF_SHORT_NAMES.items() if k in tl), raw_t[:24])
            age = fmt_age(n.get("created_at"))
            # CRITICAL: Explicit None check instead of complex nested ternary
            seen_val = n.get("seen")
            is_seen = seen_val if seen_val is not None else True
            unread = "-" if not is_seen else " "
            rows.append(Text.from_markup(f"[{sc}]{unread}[/] [{sc}]{title}[/] [dim]{age}[/]"))

    # Algo metrics daily (action counts)
    valid_metrics_raw = safe_get_list(algo_metrics)
    if isinstance(valid_metrics_raw, list) and valid_metrics_raw:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Daily trade activity:[/]"))
        for m in valid_metrics_raw[:5]:
            if not isinstance(m, dict):
                continue
            d = m.get("date")
            if d is None or not hasattr(d, "strftime"):
                logger.warning("[HEALTH] Daily metrics missing date field")
                d_s = "-"
            else:
                d_s = d.strftime("%b %d")

            # Explicit validation: all action counts must be present
            ta_raw = m.get("total_actions")
            en_raw = m.get("entries")
            ex_raw = m.get("exits")

            if ta_raw is None or en_raw is None or ex_raw is None:
                logger.error(
                    f"[AUDIT] CRITICAL: Daily metrics incomplete for {d_s}: "
                    f"total_actions={ta_raw}, entries={en_raw}, exits={ex_raw}. "
                    f"Cannot verify daily trading activity."
                )
                rows.append(
                    Text.from_markup(
                        f"  [dim]{d_s}:[/] [red bold]INCOMPLETE - audit data missing[/] "
                        "(check database for corrupted metrics records)"
                    )
                )
                continue

            try:
                ta = int(ta_raw)
                en = int(en_raw)
                ex = int(ex_raw)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse daily metrics for {d_s}: {e}")
                rows.append(Text.from_markup(f"  [dim]{d_s}:[/] [yellow]invalid data[/]"))
                continue

            rows.append(
                Text.from_markup(
                    f"  [dim]{d_s}:[/] [white]{ta}[/][dim] total actions,  [/][{G}]{en}[/][dim] entries  [/][{R}]{ex}[/][dim] exits[/]"
                )
            )

    # Audit log - most recent notable actions
    valid_audit_raw = safe_get_list(audit)
    if isinstance(valid_audit_raw, list) and valid_audit_raw:
        valid_audit_list: list[Any] = valid_audit_raw
        notable = [
            a
            for a in valid_audit_list
            if isinstance(a, dict)
            and a.get("action_type")
            # CRITICAL: Explicit None check instead of OR fallback with str()
            # Missing action_type should trigger validation, not silent fallback
            and any(
                k in (str(a.get("action_type")) if a.get("action_type") is not None else "")
                for k in ("entry", "exit", "halt", "resume", "circuit")
            )
        ][:3]
        if notable:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[dim]Audit:[/]"))
            for a in notable:
                action_type_val = a.get("action_type")
                # CRITICAL: Explicit None check instead of implicit fallback
                if action_type_val is None:
                    action_type_val = ""
                at = action_type_val.replace("_", " ")
                symbol_val = a.get("symbol")
                # CRITICAL: Explicit None check instead of nested ternary fallback
                if symbol_val is None:
                    symbol_val = ""
                sym = symbol_val
                st_raw = a.get("status")
                if st_raw is None:
                    st_raw = ""
                st = st_raw
                sc = G if st == "success" else (Y if st == "warn" else R)
                rows.append(Text.from_markup(f"  [{sc}]{at[:22]}[/]" + (f" [white]{sym}[/]" if sym else "")))

        if not rows:
            logger.warning(
                "[HEALTH_PANEL] Status panel has no activity to display. "
                "All data sources (run, activity, health, notifications) returned empty. "
                "Check orchestrator logs and data freshness."
            )
            rows.append(Text("⚠ No activity data available - check system logs", style="yellow"))
    return Panel(
        Group(*rows),
        title="[bold yellow]ALGO ACTIVITY & SYSTEM HEALTH[/]",
        border_style="yellow",
        padding=(0, 1),
    )


__all__ = [
    "_format_audit_log_summary",
    "_format_daily_metrics_summary",
    "_format_notifications_section",
    "_format_notifications_summary",
    "_format_risk_snapshot",
    "panel_status",
]
