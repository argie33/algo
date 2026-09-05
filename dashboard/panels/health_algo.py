"""Algo-run health panels (panel_algo_health, panel_algo_health_expanded) and their
general helpers.

Phase-execution status mapping/rendering (`_build_phase_execution_panel` and its
badge/metric helpers) lives in health_algo_phases.py - split out once this file grew
past the file-size ratchet's cap; panel_algo_health calls into it rather than doing
that work itself.
"""

import logging
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ..error_boundary import has_error
from ..formatters import fmt_age
from ..utilities import DIM, G, R, Y
from ._helpers import _best_halt_reason, _error_panel, _fmt_phases_halted
from .data_extractors import extract_health_items, safe_extract, safe_get_list
from .health_algo_phases import (
    _build_phase_badges_and_metrics,
    _build_phase_badges_from_audit,
    _build_phase_execution_panel,
)
from .health_freshness_sections import _calc_loader_queue_depth
from .health_orch import _extract_orch_risk_metrics_string
from .health_results import _build_past_runs_section
from .health_results_panel import _build_results_panel
from .health_shared import (
    ERROR_STATES,
    HALTED_STATES,
    NOTIF_SHORT_NAMES,
    PHASE_SUCCESS_STATES,
    SEV_COLORS,
    SKIPPED_STATES,
    _format_execution_stats,
    _format_phase_badge,
    _get_item_status,
    _get_status_safe,
)

logger = logging.getLogger(__name__)


def _calc_critical_tables_status(hlth_items: list[Any]) -> tuple[int, int]:
    """Calculate how many critical tables are ready vs stale.

    Returns: (ready_count, stale_count)
    """
    critical_items = [r for r in hlth_items if isinstance(r, dict) and r.get("role") == "CRIT"]
    ready = sum(1 for r in critical_items if _get_item_status(r) == "ok")
    stale = len(critical_items) - ready
    return ready, stale


def _format_algo_actions_and_activity(
    signals_gen: int, entries_exec: int, exits_exec: int, today_m: dict[str, Any], valid_metrics: list[Any]
) -> list[Text]:
    """Format 'what did the algo do' summary and 5-day activity strip."""
    rows: list[Text] = []

    # CRITICAL: Explicit check for unavailability marker instead of falsy fallback
    # Missing metrics data should not silently map to empty summary
    if today_m.get("_data_unavailable"):
        logger.warning(f"[METRICS_FORMAT] Metrics data unavailable: {today_m.get('reason', 'unknown')}")
        return rows

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

    # 5-day activity strip (GOVERNANCE: minimum 3/6 metrics, 50% completeness)
    if len(valid_metrics) >= 3:
        day_parts = []
        for m in valid_metrics[:5]:
            d = m.get("date")
            # CRITICAL: Explicit None check instead of OR fallback
            # Missing date should be handled explicitly, not default to empty string
            if d is None:
                d_s = ""
            elif hasattr(d, "strftime"):
                d_s = d.strftime("%d")
            else:
                d_s = str(d)[-2:]
            en = m.get("entries")
            ex = m.get("exits")
            # CRITICAL: Fail-fast on missing execution counts. Never silently fallback to 0.
            # Must distinguish between "0 entries executed" and "data unavailable".
            try:
                if en is None:
                    logger.warning("Execution metric 'entries' missing - data unavailable")
                    en_i = None
                else:
                    en_i = int(en)
                if ex is None:
                    logger.warning("Execution metric 'exits' missing - data unavailable")
                    ex_i = None
                else:
                    ex_i = int(ex)
            except (TypeError, ValueError) as e:
                logger.error(f"Execution metrics type conversion failed: {e}")
                en_i = None
                ex_i = None
            en_s = str(en_i) if en_i is not None else "--"
            ex_s = str(ex_i) if ex_i is not None else "--"
            e_c = G if (en_i is not None and en_i > 0) else DIM
            x_c = Y if (ex_i is not None and ex_i > 0) else DIM
            day_parts.append(f"[dim]{d_s}:[/][{e_c}]{en_s}↑[/][{x_c}]{ex_s}↓[/]")
        rows.append(Text.from_markup("[dim]5d activity:[/] " + "  ".join(day_parts)))

    return rows


def _format_run_history_summary(valid_hist: list[Any] | None) -> list[Text]:
    """Format run history badges and summary stats."""
    rows: list[Text] = []
    if not valid_hist:
        logger.debug(
            "[HISTORY_FORMAT] Run history unavailable for summary display. "
            "Execution history list is empty or null. Cannot show success rate or past run outcomes."
        )
        return rows

    # Type guard: valid_hist is guaranteed non-empty and not None after the check above
    hist_items: list[Any] = valid_hist
    n_ok = sum(1 for r in hist_items if _get_status_safe(r) in PHASE_SUCCESS_STATES)
    # See _format_run_history_summary above - "degraded"/"blocked"/"skipped" run-level
    # statuses must use the same HALTED_STATES/SKIPPED_STATES buckets as _format_phase_badge(),
    # not fall through to a red error badge just because they aren't the literal "halted".
    n_hlt = sum(1 for r in hist_items if _get_status_safe(r) in HALTED_STATES)
    n_skip = sum(1 for r in hist_items if _get_status_safe(r) in SKIPPED_STATES)
    n_err = sum(1 for r in hist_items if _get_status_safe(r) in ERROR_STATES)
    total_h = len(hist_items)

    badges = []
    for r in hist_items[:7]:
        s = _get_status_safe(r)
        color, icon = _format_phase_badge(s)
        badges.append(f"[{color}]{icon}[/]")

    wc = G if n_ok == total_h else (Y if n_ok > 0 else R)
    rows.append(
        Text.from_markup(
            f"[dim]Last {total_h} runs:[/] {''.join(badges)}"
            f"  [{wc}]{n_ok}/{total_h} success[/]"
            + (f"  [{Y}]{n_hlt} halted[/]" if n_hlt else "")
            + (f"  [{DIM}]{n_skip} skipped[/]" if n_skip else "")
            + (f"  [{R}]{n_err} error[/]" if n_err else "")
        )
    )

    last_halt = next(
        (r for r in valid_hist if _get_status_safe(r) == "halted"),
        None,
    )
    if last_halt:
        lhr = last_halt.get("halt_reason")
        # CRITICAL: Explicit None check instead of implicit fallback
        if lhr is None:
            lhr = ""
        lph = _fmt_phases_halted(last_halt.get("phases_halted"))
        # CRITICAL: Explicit conditional instead of OR fallback
        # Missing halt reason must be distinguished from empty phases
        if lhr:
            body = lhr
        elif lph:
            body = lph
        else:
            body = None
        if body:
            # HIGH-002 FIX: Explicit None check instead of OR fallback
            # If lhr is None (no halt reason), treat it as missing data, not empty string
            if lph and lhr is not None and lph not in lhr:
                ph_s = f"  [dim]({lph})[/]"
            else:
                ph_s = ""
            rows.append(Text.from_markup(f"  [{Y}]→ {body[:68]}[/]{ph_s}"))

    return rows


def panel_algo_health(  # noqa: C901
    run: dict[str, Any] | None,
    act: dict[str, Any] | None,
    hlth: dict[str, Any] | list[Any] | None,
    notifs: list[Any],
    algo_metrics: list[Any] | None = None,
    audit: list[Any] | None = None,
    exec_hist: list[Any] | None = None,
    risk: dict[str, Any] | None = None,
    exec_stats: dict[str, Any] | None = None,
) -> Panel:
    """Focused 'did the algo work?' panel: run outcome → what it did → system health.

    Now includes recent execution statistics (last 24h failures) to make hidden
    failure rates visible instead of only showing the latest run.
    """
    hlth_err = _error_panel("health", hlth, "HEALTH")
    if hlth_err is not None:
        return hlth_err
    notif_err = _error_panel("notifications", notifs, "HEALTH")
    if notif_err is not None:
        return notif_err

    rows: list[Text | Rule | Panel] = []

    # ── A: Run outcome ────────────────────────────────────────────────────────
    run_valid = run and isinstance(run, dict) and not has_error(run)
    act_valid = act and isinstance(act, dict) and not has_error(act)
    run_at = (
        (run.get("run_at") if isinstance(run, dict) else None)
        if run_valid
        else (act.get("run_at") if isinstance(act, dict) and act_valid else None)
    )
    age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid and isinstance(run, dict):
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
            error_pnl = _error_panel("run", {"_error": f"Run data incomplete: {e}"}, "HEALTH")
            if error_pnl is not None:
                return error_pnl
            return Panel(Text("Run data incomplete"), border_style="red")

        if success and not halted:
            sts = f"[bold {G}]OK COMPLETED[/]"
        elif halted:
            sts = f"[bold {Y}]~ HALTED[/]"
        elif errored:
            sts = f"[bold {R}]X ERROR[/]"
        else:
            sts = "[dim]UNKNOWN[/]"
        # MEDIUM FIX: Explicit None check instead of or operator for run_id display
        run_id_val = run_fields["run_id"]
        rid = run_id_val[:28] if run_id_val is not None else ""
        rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r = run_fields["halt_reason"]
        if halt_r is None:
            halt_r = ""
        summary = run_fields["summary"]
        if summary is None:
            summary = ""
        phase_results = run_fields["phase_results"]
        if halted or halt_r:
            # MEDIUM FIX: Explicit None check instead of silent empty list default
            phase_results_guard = phase_results if phase_results is not None else []
            if phase_results is None:
                logger.warning("Phase results unavailable for halt reason display")
            for label, detail in _best_halt_reason(halt_r, phase_results_guard):
                prefix = f"{label}: " if label else ""
                rows.append(Text.from_markup(f"  [{Y}]→ {prefix}{detail[:80]}[/]"))
        elif summary:
            rows.append(Text.from_markup(f"  [dim]{summary[:72]}[/]"))
    elif act_valid:
        rows.append(Text.from_markup(f"[dim]Last run (audit):[/]  [dim]{fmt_age(run_at)}[/]"))
    else:
        rows.append(Text.from_markup("[dim]No run data - algo has not run yet[/]"))

    # ── A.2: Data readiness summary (NEW) ─────────────────────────────────────
    hlth_items_raw, _ = extract_health_items(hlth if hlth is not None else {})
    hlth_items = hlth_items_raw if isinstance(hlth_items_raw, list) else []

    if hlth_items:
        crit_ready, crit_stale = _calc_critical_tables_status(hlth_items)
        crit_total = crit_ready + crit_stale
        if crit_total > 0:
            crit_color = G if crit_stale == 0 else Y if crit_stale == 1 else R
            rows.append(Text.from_markup(f"  [dim]Critical data:[/] [{crit_color}]{crit_ready}/{crit_total} ready[/]"))

    # A.3 "Degraded mode alert" (hlth_dict.get("degraded_mode_active")) removed 2026-08-03 -
    # see _build_system_status_section's comment: the underlying 0.5x position-size feature
    # was deleted from the codebase in 2026-06, and its DynamoDB remnant is unreachable on
    # both the write and read side. Not a dashboard wiring gap - nothing to wire it to.

    # ── A.4: Loader health summary (NEW) ──────────────────────────────────────
    if hlth_items:
        loading_count, _ = _calc_loader_queue_depth(hlth_items)
        total_loaders = len(hlth_items)
        failed_loaders = sum(1 for r in hlth_items if isinstance(r, dict) and _get_item_status(r) in ("error", "stale"))
        succeeded_loaders = total_loaders - failed_loaders
        if loading_count > 0:
            rows.append(
                Text.from_markup(f"  [dim]Loaders:[/] [{G}]{succeeded_loaders} ok[/] [{Y}]{loading_count} loading[/]")
            )
        elif failed_loaders > 0:
            rows.append(
                Text.from_markup(f"  [dim]Loaders:[/] [{G}]{succeeded_loaders} ok[/] [{R}]{failed_loaders} failed[/]")
            )

    # ── A.5: Execution stats (last 24h failures) ──────────────────────────────
    stats_line = _format_execution_stats(exec_stats)
    if stats_line:
        rows.append(stats_line)
        rows.append(Rule(style="dim"))

    # ── B: Phase badges + aggregated "what did it do?" metrics ───────────────
    signals_gen = 0
    entries_exec = 0
    exits_exec = 0
    phase_badges: list[str] = []

    if run_valid and isinstance(run, dict) and run.get("_source") == "exec_log":
        if isinstance(run, dict) and "phase_results" not in run:
            return Panel(
                Text.from_markup("[dim]Phase results missing from run data[/]"),
                title="[bold yellow]ALGO HEALTH[/]",
                border_style="yellow",
                padding=(0, 1),
            )
        phase_results = run["phase_results"]
        phase_badges, signals_gen, entries_exec, exits_exec = _build_phase_badges_and_metrics(run, phase_results)
    elif (run_valid and isinstance(run, dict)) or (act_valid and isinstance(act, dict)):
        src = run if (run_valid and isinstance(run, dict)) else (act if (act_valid and isinstance(act, dict)) else {})
        phase_results_val = src.get("phase_results")
        if phase_results_val is None:
            phase_results_val = src.get("phases")
        phases_list = phase_results_val
        if not phases_list:
            logger.warning(
                f"[HEALTH] Data source missing both 'phase_results' and 'phases'. Available keys: {list(src.keys())}. "
                "Phase status will not be displayed."
            )
            phases_list = []
        phase_badges = _build_phase_badges_from_audit(phases_list)

    if phase_badges:
        rows.append(Text.from_markup("  ".join(phase_badges)))

    # Algo metrics for today's entry/exit counts. FAIL-FAST: must not be None.
    valid_metrics: list[Any] | None = None
    if algo_metrics is None:
        logger.warning("[ALGO_METRICS] Metrics data is None")
    else:
        try:
            valid_metrics_raw = safe_get_list(algo_metrics)
            # Type guard: convert dict (error marker) to None for consistency
            if isinstance(valid_metrics_raw, dict):
                valid_metrics = None
            else:
                valid_metrics = valid_metrics_raw
        except (ValueError, TypeError) as e:
            logger.warning(f"Algo metrics data error: {e}")
        if valid_metrics is None:
            logger.warning("[ALGO_METRICS] Metrics data is None after validation")

    today_m: dict[str, Any] | None = None
    if valid_metrics:
        today_m = valid_metrics[0]
        if not entries_exec:
            en = today_m.get("entries")
            if en is not None:
                entries_exec = int(en)
        if not exits_exec:
            ex = today_m.get("exits")
            if ex is not None:
                exits_exec = int(ex)
    else:
        # CRITICAL: Explicit unavailability marker, not empty dict
        # Missing metrics data must be visible to downstream code
        today_m = {"_data_unavailable": True, "reason": "no_metrics_data"}

    # "What did the algo do today?" summary and 5-day activity
    action_activity_rows = _format_algo_actions_and_activity(
        signals_gen, entries_exec, exits_exec, today_m, valid_metrics if valid_metrics else []
    )
    rows.extend(action_activity_rows)

    rows.append(Rule(style="dim"))

    # ── C: Run history (last 7 runs as badges) ───────────────────────────────
    valid_hist_raw = safe_get_list(exec_hist)
    valid_hist_list: list[Any] | None = None
    if isinstance(valid_hist_raw, list):
        valid_hist_list = valid_hist_raw
    if valid_hist_list is None:
        logger.debug("[EXEC_HIST] Execution history is None (expected in local dev if orchestrator hasn't run yet)")
        history_rows = []
    else:
        history_rows = _format_run_history_summary(valid_hist_list)
    rows.extend(history_rows)

    rows.append(Rule(style="dim"))

    # ── D: Phase 1-9 Execution Health (Prominent Panel) ────────────────────────────────────
    # Table-by-table data freshness (what used to render here) now lives in its own
    # dedicated DATA FRESHNESS panel (panel_data_freshness) - see dashboard row 1, which
    # frees this panel to focus on "what did the algo actually do" rather than competing
    # for space with per-table staleness detail.
    if hlth and isinstance(hlth, dict):
        execution_health = hlth.get("execution_health")
        if execution_health is not None:
            phase_panel = _build_phase_execution_panel(execution_health, run, hlth_items)
            if phase_panel:
                rows.append(phase_panel)

    # ── D2: Portfolio risk snapshot ───────────────────────────────────────────
    # `risk` was already fetched and passed into this panel but never read - the
    # compact ALGO HEALTH view showed no VaR/CVaR/beta/concentration info even
    # though it's computed and only surfaced in the expanded view. Reuse the same
    # formatter so both views stay consistent.
    risk_line = _extract_orch_risk_metrics_string(risk).strip()
    if risk_line:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(risk_line))

    # ── E: Notifications (compact) ────────────────────────────────────────────
    valid_notifs_raw = safe_get_list(notifs)
    if isinstance(valid_notifs_raw, list) and valid_notifs_raw:
        rows.append(Rule(style="dim"))
        notif_parts = []
        for n in valid_notifs_raw[:5]:
            if not isinstance(n, dict):
                continue
            severity = n.get("severity")
            if severity is None:
                logger.warning("[HEALTH] Notification missing severity field")
                severity = "info"
            sc = SEV_COLORS.get(severity, DIM)
            title_val = n.get("title")
            if title_val is None:
                logger.warning("[HEALTH] Notification missing title field")
                title_val = ""
            raw_t = title_val if title_val else ""
            title = next(
                (v for k, v in NOTIF_SHORT_NAMES.items() if k in raw_t.lower()),
                raw_t[:20],
            )
            age = fmt_age(n.get("created_at"))
            # CRITICAL: Explicit None check instead of complex nested ternary
            seen_val = n.get("seen")
            is_seen = seen_val if seen_val is not None else True
            unread = "-" if not is_seen else " "
            notif_parts.append(f"[{sc}]{unread}{title}[/][dim]{age}[/]")
        rows.append(Text.from_markup("[dim]Alerts:[/] " + "  ".join(notif_parts)))

    # ── F: Past runs section (bottom) ───────────────────────────────────────────
    if valid_hist_list is not None and valid_hist_list:
        past_runs_rows = _build_past_runs_section(valid_hist_list)
        if past_runs_rows:
            rows.extend(past_runs_rows)

    if not rows:
        logger.warning(
            "[HEALTH_PANEL] Algo health panel has no data to display. "
            "All data sources (run, activity, health, notifications) returned empty. "
            "Check orchestrator status and data loader health."
        )
        rows.append(Text("⚠ No health data available - check logs for errors", style="yellow"))
    return Panel(
        Group(*rows),
        title=r"[bold yellow]ALGO HEALTH[/]  [dim]\[h] expand[/]",
        border_style="yellow",
        padding=(0, 1),
    )


def panel_algo_health_expanded(
    run: dict[str, Any] | None,
    act: dict[str, Any] | None,
    hlth: dict[str, Any] | list[Any] | None,
    notifs: list[Any],
    algo_metrics: list[Any] | None = None,
    exec_hist: list[Any] | None = None,
    risk: dict[str, Any] | None = None,
    exec_patterns: dict[str, Any] | None = None,
    orch_extended: dict[str, Any] | None = None,
) -> Panel:
    """Full-screen algo health: run outcome, phase execution detail, run history,
    30-day phase reliability trend, alerts.

    Data freshness detail lives in its own panel_data_freshness_expanded now - see that
    function for the per-table breakdown this used to show side-by-side with.
    """
    hlth_err_exp = _error_panel("health", hlth, "ALGO HEALTH EXPANDED")
    if hlth_err_exp is not None:
        return hlth_err_exp
    notif_err_exp = _error_panel("notifications", notifs, "ALGO HEALTH EXPANDED")
    if notif_err_exp is not None:
        return notif_err_exp

    # GOVERNANCE: Log when optional data sources are missing (fail-fast visibility).
    # These fallbacks to empty lists are intentional for UI graceful degradation.
    if algo_metrics is None:
        logger.warning("Health panel: algo_metrics is None, using empty list for display")
        algo_metrics_display = []
    else:
        algo_metrics_display = algo_metrics
    if exec_hist is None:
        logger.warning("Health panel: exec_hist is None, using empty list for display")
        exec_hist_display = []
    else:
        exec_hist_display = exec_hist
    if exec_patterns is None:
        logger.debug("Health panel: exec_patterns unavailable - phase reliability trend will be omitted")
    return _build_results_panel(
        run,
        act,
        algo_metrics_display,
        exec_hist_display,
        risk,
        notifs,
        hlth,
        exec_patterns=exec_patterns,
        orch_extended=orch_extended,
    )


__all__ = [
    "_calc_critical_tables_status",
    "_format_algo_actions_and_activity",
    "_format_run_history_summary",
    "panel_algo_health",
    "panel_algo_health_expanded",
]
