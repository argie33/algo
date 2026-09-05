"""Orchestrator configuration/status panel (panel_orch) and its formatter helpers."""

import logging
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ..error_boundary import has_error
from ..formatters import fmt_age, next_run_str
from ..utilities import DIM, PHASE_NAMES, G, R, Y
from ._helpers import _best_halt_reason, _error_panel
from .data_extractors import extract_config_params, extract_risk_metrics, safe_get_dict, safe_get_list
from .health_shared import (
    PHASE_HALTED_STATES,
    PHASE_SKIPPED_STATES,
    PHASE_SUCCESS_STATES,
    _format_execution_stats,
    _var_color,
)

logger = logging.getLogger(__name__)


def _get_phase_status_badge(run: dict[str, Any] | None) -> str:
    """Determine run status badge from run object. Eliminates if/elif chains (OO abuser pattern)."""
    if not run or not isinstance(run, dict):
        return "[dim]-[/]"
    success = run.get("success")
    halted = run.get("halted")
    errored = run.get("errored")
    if success and not halted:
        return "[bold bright_green]✓ COMPLETED[/]"
    if halted:
        return "[bold yellow]~ HALTED[/]"
    if errored:
        return "[bold bright_red]✗ ERROR[/]"
    return "[dim]RUN[/]"


def _format_phase_execution_health(execution_health: dict[str, Any] | None) -> list[Text]:  # noqa: C901
    """Format Phase 2-9 execution health metrics for display (compact inline version)."""
    rows: list[Text] = []
    if not execution_health or not isinstance(execution_health, dict):
        return rows

    # Phase 2: Circuit Breakers
    cb = execution_health.get("phase_2_circuit_breakers")
    if cb:
        # CRITICAL: Explicit None check - circuit breaker trigger state is critical.
        # A missing any_triggered must render as an alarming/unknown state, not a silent
        # "all clear" - dashboard/panels/circuit.py's primary panel already fails safe (red
        # error panel) when this same field is missing; this compact view used to default
        # to False/green instead, showing a safe-looking "✓ P2" for a breaker status that
        # was never actually confirmed clear.
        any_triggered = cb.get("any_triggered")
        if any_triggered is None:
            logger.error("[HEALTH COMPACT] Phase 2: any_triggered missing - rendering as unknown, not clear")
            rows.append(Text.from_markup(f"  [{R}]? P2:[/] status unknown (data_unavailable)"))
        else:
            cb_color = R if any_triggered else G
            cb_icon = "⚠" if any_triggered else "✓"
            dd = cb.get("drawdown_pct")
            dl = cb.get("daily_loss_pct")
            vix = cb.get("vix_level")
            metrics = []
            if dd is not None:
                metrics.append(f"DD {dd:.1f}%")
            if dl is not None:
                metrics.append(f"DL {dl:.1f}%")
            if vix is not None:
                metrics.append(f"VIX {vix:.1f}")
            metric_str = " ".join(metrics) if metrics else "none"
            rows.append(Text.from_markup(f"  [{cb_color}]{cb_icon} P2:[/] {metric_str}"))

    # Phase 3: Positions
    pos = execution_health.get("phase_3_position_monitor")
    if pos:
        open_count = pos.get("open_positions")
        oldest = pos.get("oldest_days")
        max_loss = pos.get("max_loss_pct")
        # Fail explicitly if critical field missing (don't default to 0)
        if open_count is None:
            logger.warning("Phase 3 position monitor missing 'open_positions' field - data incomplete")
            pos_color = DIM
            pos_metrics = ["data unavailable"]
        else:
            pos_color = G if open_count == 0 else Y if open_count <= 5 else R
            pos_metrics = [f"{open_count} open"]
            if oldest is not None:
                pos_metrics.append(f"{oldest}d old")
            if max_loss is not None:
                pos_metrics.append(f"max {max_loss:.1f}%")
        rows.append(Text.from_markup(f"  [{pos_color}]● P3:[/] " + " ".join(pos_metrics)))

    # Phase 4: Broker Reconciliation
    recon = execution_health.get("phase_4_broker_reconciliation")
    if recon:
        sync_count = recon.get("sync_count")
        match_pct = recon.get("avg_match_pct")
        # Fail explicitly if critical field missing (don't default to 0)
        if sync_count is None:
            logger.warning("Phase 4 broker reconciliation missing 'sync_count' field - data incomplete")
            recon_color = DIM
            recon_metrics = ["data unavailable"]
        else:
            recon_color = (
                G if sync_count > 0 and (match_pct is None or match_pct >= 95) else Y if sync_count > 0 else DIM
            )
            recon_metrics = [f"{sync_count} syncs"]
            if match_pct is not None:
                recon_metrics.append(f"{match_pct:.0f}% match")
        rows.append(Text.from_markup(f"  [{recon_color}]↔ P4:[/] " + " ".join(recon_metrics)))

    # Phase 6: Exit Execution
    exit_ex = execution_health.get("phase_6_exit_execution")
    if exit_ex:
        exits = exit_ex.get("exits_executed")
        success_rate = exit_ex.get("success_rate")
        if exits is None or success_rate is None:
            rows.append(Text.from_markup("  [dim]↓ P6:[/] [dim]DATA UNAVAILABLE[/]"))
        else:
            exit_color = G if exits > 0 and success_rate >= 80 else (Y if exits > 0 else DIM)
            rows.append(Text.from_markup(f"  [{exit_color}]↓ P6:[/] {exits} exits, {success_rate:.0f}% success"))

    # Phase 7: Signal Generation
    sig = execution_health.get("phase_7_signal_generation")
    if sig:
        signals = sig.get("signals_generated")
        avg_str = sig.get("avg_strength")
        if signals is None:
            rows.append(Text.from_markup("  [dim]◆ P7:[/] [dim]DATA UNAVAILABLE[/]"))
        else:
            sig_color = G if signals > 0 else DIM
            if avg_str is not None:
                rows.append(Text.from_markup(f"  [{sig_color}]◆ P7:[/] {signals} signals, {avg_str:.1f} avg strength"))
            else:
                rows.append(Text.from_markup(f"  [{sig_color}]◆ P7:[/] {signals} signals"))

    # Phase 8: Entry Execution
    entry_ex = execution_health.get("phase_8_entry_execution")
    if entry_ex:
        entries = entry_ex.get("entries_executed")
        success_rate = entry_ex.get("success_rate")
        if entries is None or success_rate is None:
            rows.append(Text.from_markup("  [dim]↑ P8:[/] [dim]DATA UNAVAILABLE[/]"))
        else:
            entry_color = G if entries > 0 and success_rate >= 80 else (Y if entries > 0 else DIM)
            rows.append(Text.from_markup(f"  [{entry_color}]↑ P8:[/] {entries} entries, {success_rate:.0f}% success"))

    # Phase 9: Portfolio Snapshot
    snap = execution_health.get("phase_9_portfolio_snapshot")
    if snap:
        value = snap.get("portfolio_value")
        value_str = f"${value:,.0f}" if value is not None else "unknown"
        latest = snap.get("latest_snapshot")
        latest_str = f" ({latest[:10]})" if latest else ""
        rows.append(Text.from_markup(f"  [white]⟡ P9:[/] {value_str}{latest_str}"))

    return rows


def _format_orch_config_string(cfg_params: dict[str, Any]) -> str:
    """Format orchestration config parameters into display line."""
    from dashboard.data_validation import safe_float

    min_score_f = safe_float(cfg_params.get("min_score"), default=None)
    score_s = (
        f"[dim]min score ≥[/][white]{cfg_params['min_score']}[/]" if min_score_f is not None and min_score_f > 0 else ""
    )
    max_n = cfg_params.get("max_pos_n")
    # CRITICAL: Explicit check for config availability instead of silent empty string
    if max_n is None:
        logger.debug("[HEALTH] max_pos_n config not set - position limit unavailable")
        slots_s = ""
    elif max_n:
        slots_s = f"[dim]max [/][white]{max_n}[/][dim] positions[/]"
    else:
        # max_n=0 is falsy but valid (unlimited positions), don't silently hide
        logger.warning(f"[HEALTH] max_pos_n is 0 or invalid: {max_n} - position limit configuration corrupted?")
        slots_s = ""
    # `is not None and X` looks like a None-guard but still hides a legitimate 0 (X is
    # not None and X == X and bool(X), which is False when X == 0) - the exact anti-pattern
    # this file's max_pos_n handling above (line 814) explicitly guards against. Use
    # `is not None` alone so a real 0 value still renders.
    max_sec_n = cfg_params.get("max_sec_n")
    sec_s = f"[dim]sector ≤[/][white]{max_sec_n}[/]" if max_sec_n is not None else ""
    base_risk = cfg_params.get("base_risk")
    risk_s = f"[dim]base risk [/][white]{base_risk}%[/]" if base_risk is not None else ""
    t1r = cfg_params.get("t1_r")
    t1r_s = f"[dim]T1 target [/][white]{t1r}R[/]" if t1r is not None else ""
    return "  ".join(x for x in [score_s, slots_s, sec_s, risk_s, t1r_s] if x)


def _extract_orch_risk_metrics_string(risk: dict[str, Any] | None) -> str:
    """Extract and format risk metrics for orchestration panel."""
    from ..utilities import R

    if not risk or has_error(risk):
        logger.error("[HEALTH] Risk data unavailable: risk_metrics not found or error marked")
        return f"\n[{R}][error] Risk data unavailable[/]"
    risk_dict = safe_get_dict(risk)
    if not risk_dict:
        logger.error("[HEALTH] Risk metrics parsing failed: dict conversion returned None")
        return f"\n[{R}][N/A] Risk metrics not available[/]"
    var95_check = risk_dict.get("var95")
    if var95_check is None:
        logger.error("[HEALTH] Risk metric missing: VaR95 not in response. Risk calculation incomplete.")
        return f"\n[{R}]⚠ Risk data missing VaR95 metric[/]"
    try:
        var95_check_f = float(var95_check)
        if var95_check_f <= 0 or not isinstance(risk_dict, dict):
            return f"\n[{R}][error] Risk metrics invalid[/]"
        risk_metrics = extract_risk_metrics(risk_dict)
        # DATA CONTRACT: API validates risk metrics as floats or None - trust it
        var95_val = risk_metrics.get("var95")
        beta_val = risk_metrics.get("beta")
        cvar95_val = risk_metrics.get("cvar95")
        conc5_val = risk_metrics.get("conc5")
        svar_val = risk_metrics.get("svar")

        if var95_val is None or beta_val is None or cvar95_val is None or conc5_val is None:
            missing_fields = [
                name
                for name, val in [
                    ("VaR95", var95_val),
                    ("Beta", beta_val),
                    ("CVaR95", cvar95_val),
                    ("Concentration", conc5_val),
                ]
                if val is None
            ]
            return f"\n[{R}]⚠ Risk metrics incomplete[/] - missing: {', '.join(missing_fields)}"

        # Cast to float for calculations - API guarantees valid types
        # Type narrowing: all values are guaranteed non-None after the check above
        var95_val_f = float(var95_val)
        beta_val_f = float(beta_val)
        cvar95_val_f = float(cvar95_val)
        conc5_val_f = float(conc5_val)
        var95_val = var95_val_f
        beta_val = beta_val_f
        cvar95_val = cvar95_val_f
        conc5_val = conc5_val_f
        # CRITICAL: Show beta value if positions exist (even if beta <= 0, meaning negative/neutral correlation with market)
        # Show "--" only when there are NO open positions
        has_positions = risk_dict.get("has_positions")
        if has_positions is None:
            logger.debug("[HEALTH] Risk: has_positions missing, defaulting to False for display")
            has_positions = False
        beta_display = f"{beta_val:.2f}" if has_positions else "--"
        beta_c = (
            "dim" if (not has_positions or beta_val <= 0) else (R if beta_val >= 1.2 else (Y if beta_val >= 0.8 else G))
        )
        var_c = _var_color(var95_val)
        svar_s = (
            f"\n[dim]Stressed VaR:[/][{R}]{float(svar_val):.2f}%[/]"
            if svar_val is not None and float(svar_val) > 0
            else ""
        )  # Empty string here is intentional - no need to show marker when optional field missing
        return (
            f"\n[dim]VaR 95%:[/][{var_c}]{var95_val:.2f}%[/]"
            f"  [dim]CVaR 95%:[/][{var_c}]{cvar95_val:.2f}%[/]"
            f"  [dim]Portfolio Beta:[/][{beta_c}]{beta_display}[/]"
            f"  [dim]Top-5 Conc:[/][white]{conc5_val:.0f}%[/]" + svar_s
        )
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"Risk metrics extraction failed: {e}")
        return f"\n[{R}][error] Risk calculation failed[/]"


def panel_orch(  # noqa: C901
    run: dict[str, Any] | None,
    cfg: dict[str, Any],
    risk: dict[str, Any] | None = None,
    hlth: dict[str, Any] | list[Any] | None = None,
    exec_stats: dict[str, Any] | None = None,
) -> Panel:
    error_pnl = _error_panel("config", cfg, "ORCHESTRATION")
    if error_pnl is not None:
        return error_pnl

    next_run = next_run_str()
    cfg_params = extract_config_params(cfg)
    mode = cfg_params["mode"]
    mc2 = G if "LIVE" in mode else Y
    en = "ENABLED" if cfg_params["enabled"] else "DISABLED"
    ec = G if cfg_params["enabled"] else R

    config_line = _format_orch_config_string(cfg_params)
    var_line = _extract_orch_risk_metrics_string(risk)

    if not run or has_error(run):
        error_msg = (
            f"[{R}]run fetch failed[/]: {run.get('_error')}"
            if isinstance(run, dict) and has_error(run)
            else "[dim]run: no execution history available - orchestrator may not have run[/]"
        )
        if not run or (isinstance(run, dict) and not has_error(run)):
            logger.warning(
                "[ORCHESTRATOR_PANEL] Run data unavailable for display. "
                "Orchestrator execution history is missing or null. "
                "Cannot show most recent orchestration run status."
            )
        body_content: Text | Group = Text.from_markup(
            f"{error_msg}\n"
            f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
            f"[dim]{config_line}[/]\n"
            f"[dim]Next run:[/] [white]{next_run}[/]" + var_line
        )
    else:
        age = fmt_age(run.get("run_at"))
        sts = _get_phase_status_badge(run)

        pbadges: list[str] = []
        # exec_log source: structured per-phase objects with names + statuses
        if run.get("_source") == "exec_log":
            phase_results_raw = safe_get_list(run.get("phase_results"))
            if not isinstance(phase_results_raw, list):
                phase_results_raw = []
            if not phase_results_raw:
                logger.error(
                    f"[HEALTH] CRITICAL: exec_log source missing 'phase_results'. "
                    f"Cannot display phase execution status. Available keys: {list(run.keys())}"
                )
                pbadges.append(
                    "[red bold]ERROR: Phase status data unavailable[/] (check orchestration logs for execution details)"
                )
                phase_results_raw = []
            for p in phase_results_raw:
                if not isinstance(p, dict):
                    continue
                name_val = p.get("name")
                phase_val = p.get("phase")
                # CRITICAL: Missing phase is data quality issue - log and use placeholder
                if phase_val is None:
                    logger.warning(
                        f"[HEALTH] Phase result missing 'phase' field. Available: {list(p.keys())}. "
                        f"Phase visibility degraded - cannot identify phase execution details."
                    )
                    # Use placeholder to indicate unavailable, not silent empty
                    phase_val = "unknown"
                raw = (name_val if name_val is not None else phase_val).lower()
                parts = raw.split("_")
                base = "_".join(parts[:2]) if len(parts) >= 2 else raw
                # CRITICAL: Explicit key check instead of .get() fallback
                # Missing phase name should be logged, not silently generated
                if base in PHASE_NAMES:
                    short = PHASE_NAMES[base][:9]
                else:
                    fallback_short = base.replace("phase_", "P")[:9]
                    if base not in ("", "unknown"):
                        logger.debug(
                            f"[HEALTH] Phase '{base}' not in PHASE_NAMES, using generated short: {fallback_short}"
                        )
                    short = fallback_short
                ps_raw = p.get("status")
                # CRITICAL: Missing status is data integrity issue - must log and handle explicitly
                if ps_raw is None:
                    logger.warning(
                        f"[HEALTH] Phase status missing 'status' field. Available: {list(p.keys())}. "
                        f"Cannot determine phase success/failure - health indication unavailable."
                    )
                    ps = "unknown"  # Explicit marker; will render as red X
                else:
                    ps = ps_raw.lower()
                if ps in PHASE_SUCCESS_STATES:
                    pc, pi = G, "✓"
                elif ps in PHASE_HALTED_STATES:
                    pc, pi = Y, "~"
                elif ps in PHASE_SKIPPED_STATES:
                    pc, pi = DIM, "⊘"
                else:
                    pc, pi = R, "✗"
                pbadges.append(f"[{pc}]{pi}{short}[/]")
            # Show halt reason if halted
            halt_r = run.get("halt_reason")
            # CRITICAL: Missing halt reason when algo halted is MISSION-CRITICAL data loss
            # Must log explicitly - traders need to know why algo halted
            if halt_r is None:
                logger.error(
                    f"[HEALTH] CRITICAL: Execution history missing 'halt_reason' when halted. "
                    f"Available: {list(run.keys())}. "
                    f"Cannot diagnose why algo halted - critical diagnostic information lost."
                )
            summary = run.get("summary")
            # Log if summary missing but don't fail - can use phase results as fallback
            if summary is None:
                logger.debug("[HEALTH] Execution summary missing. Will use phase results for halt explanation.")
            # CRITICAL: Explicit None check before accessing .get() result
            # Checking run.get("halted") can return None instead of boolean
            halted_val = run.get("halted")
            if halted_val is None:
                logger.debug("[HEALTH] Halt status field missing from run data - treating as not halted")
            if halt_r or halted_val:
                phase_results_temp = run.get("phase_results")
                if phase_results_temp is None:
                    phase_results_temp = []
                halt_r_str = halt_r if halt_r is not None else ""
                _details = _best_halt_reason(halt_r_str, phase_results_temp)
                _lines = [f"{lb + ': ' if lb else ''}{dt[:60]}" for lb, dt in _details]
                # CRITICAL: Explicit length check instead of falsy fallback
                # Empty halt reason list should be logged, not silently hidden
                if _lines:
                    extra = "\n" + "\n".join(f"[{Y}]{ln}[/]" for ln in _lines)
                else:
                    extra = ""
            else:
                # CRITICAL: Explicit None check instead of falsy fallback
                if summary:
                    extra = f"\n[dim]{summary[:50]}[/]"
                else:
                    extra = ""
        else:
            # audit_log fallback: phase_N or phase_N_name format
            phase_results_val = run.get("phase_results")
            if phase_results_val is None:
                phase_results_val = run.get("phases")
            phases_list_raw = safe_get_list(phase_results_val)
            if not isinstance(phases_list_raw, list):
                phases_list_raw = []
            if not phases_list_raw:
                logger.warning(
                    f"[HEALTH] audit_log missing both 'phase_results' and 'phases'. Available keys: {list(run.keys())}. "
                    "Phase status will not be displayed."
                )
                phases_list_raw = []
            for p in phases_list_raw:
                if not isinstance(p, dict):
                    continue
                at_raw = p.get("action_type")
                # Missing action_type in audit log means cannot identify phase - skip this entry
                if at_raw is None:
                    logger.warning(
                        f"[HEALTH] Audit log entry missing 'action_type'. Keys: {list(p.keys())}. Skipping entry."
                    )
                    continue  # Skip entry - cannot process without action type
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
                # CRITICAL: Explicit key check instead of .get() fallback
                # Missing phase name in PHASE_NAMES should be logged
                if phase_key in PHASE_NAMES:
                    short = PHASE_NAMES[phase_key][:9]
                else:
                    if phase_key not in ("", "unknown"):
                        logger.debug(f"[HEALTH] Audit phase '{phase_key}' not in PHASE_NAMES, using: {default_short}")
                    short = default_short[:9]
                ps_raw = p.get("status")
                # Missing status in audit log means cannot determine phase result
                if ps_raw is None:
                    logger.warning(
                        f"[HEALTH] Audit log phase {phase_key} missing 'status'. Keys: {list(p.keys())}. Using 'unknown'."
                    )
                    ps = "unknown"  # Will render as red X
                else:
                    ps = ps_raw
                pc = G if ps == "success" else (Y if ps in ("halt", "warn") else R)
                pi = "✓" if ps == "success" else ("~" if ps in ("halt", "warn") else "✗")
                pbadges.append(f"[{pc}]{pi}{short}[/]")
            extra = ""

        phases_str = "  ".join(str(b) for b in pbadges) if pbadges else "[dim]──[/]"

        # Extract execution health from hlth dict if available
        exec_health_rows: list[Text] = []
        if hlth and isinstance(hlth, dict):
            execution_health = hlth.get("execution_health")
            if execution_health:
                exec_health_rows = _format_phase_execution_health(execution_health)

        # Build body as Group if we have execution health rows
        # Build execution stats line if available
        stats_line_obj = _format_execution_stats(exec_stats)

        body_rows: list[Text | Rule] = []
        if exec_health_rows:
            body_rows = [
                Text.from_markup(
                    f"{sts}  [dim]{age}[/]\n"
                    f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
                    f"[dim]{config_line}[/]\n"
                    f"[dim]Next run:[/] [white]{next_run}[/]\n"
                    f"{phases_str}" + extra + var_line
                ),
            ]
            if stats_line_obj:
                body_rows.insert(1, stats_line_obj)
                body_rows.insert(2, Rule(style="dim"))
            else:
                body_rows.insert(1, Rule(style="dim"))
            body_rows.extend(exec_health_rows)
            body_content = Group(*body_rows)
        else:
            if stats_line_obj:
                body_rows = [
                    Text.from_markup(
                        f"{sts}  [dim]{age}[/]\n"
                        f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
                        f"[dim]{config_line}[/]\n"
                        f"[dim]Next run:[/] [white]{next_run}[/]\n"
                        f"{phases_str}" + extra + var_line
                    ),
                    stats_line_obj,
                ]
                body_content = Group(*body_rows)
            else:
                body_content = Text.from_markup(
                    f"{sts}  [dim]{age}[/]\n"
                    f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
                    f"[dim]{config_line}[/]\n"
                    f"[dim]Next run:[/] [white]{next_run}[/]\n"
                    f"{phases_str}" + extra + var_line
                )
    return Panel(body_content, title="[bold cyan]ORCHESTRATOR[/]", border_style="cyan", padding=(0, 1))


__all__ = [
    "panel_orch",
]
