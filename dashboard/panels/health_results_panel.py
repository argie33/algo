"""_build_results_panel: the ALGO HEALTH EXPANDED full-screen panel, wired to
panel_algo_health_expanded. Split out of health_results.py (which keeps this panel's
smaller section-builder helpers and re-exports them for it to call into) once that
file grew past the file-size ratchet's cap.
"""

import logging
from typing import Any

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from algo.config.orchestrator_config import OrchestratorConfig
from dashboard.data_validation import safe_int

from ..error_boundary import has_error
from ..formatters import fmt_age
from ..utilities import DIM, G, R, Y
from .data_extractors import safe_get_list
from .health_results import (
    _build_halt_reason_pattern_section,
    _build_past_runs_section,
    _build_phase_health_section,
    _build_phase_reliability_section,
    _build_run_history_section,
)

logger = logging.getLogger(__name__)


def _build_results_panel(  # noqa: C901
    run: dict[str, Any] | None,
    act: dict[str, Any] | None,
    algo_metrics: list[Any],
    exec_hist: list[Any],
    risk: dict[str, Any] | None,
    notifs: list[Any],
    hlth: dict[str, Any] | list[Any] | None = None,
    exec_patterns: dict[str, Any] | None = None,
    orch_extended: dict[str, Any] | None = None,
) -> Panel:
    """Build ALGO HEALTH EXPANDED panel: PHASE EXECUTION DETAIL, run history, and
    cross-run phase reliability trend.

    Dedicated fullscreen view focused on phase execution with maximum detail:
    - Shows all 9 phases with comprehensive metrics for the latest run, in a single
      narrowed left column - freeing the right column for the algo health trend
      (run history / phase health / failure patterns, from orch_extended - see below).
      Per-table loader-operational detail (errors, repeated failures, never-started
      loaders) lives on the DATA FRESHNESS panel instead - that's loader health, not
      algo health, and this panel's fixed-height column previously showing it pushed
      the algo health trend below the Live(screen=True) viewport, making it invisible.
    - Every available detail for each phase displayed
    - Phase Reliability: 30-day cross-run trend of which phases halt/error most, and why
      (is this phase failing all the time, or was this a one-off?)
    - Past runs: per-run phase completion breakdown, not just overall run status
    - Run History / Phase Health / Failure Patterns: longer-window orchestrator health,
      from orch_extended - moved here from the data-freshness [l] panel, now rendered in
      the third column so it's always visible instead of appended after the fold

    Args:
        run: Run data (for phase status mapping)
        hlth: Health data containing execution_health with all phase details
        exec_patterns: 30-day per-phase halt/error counts + example reasons (from
            /api/algo/execution/patterns) - the cross-run trend view
        orch_extended: Extended orchestrator data (run_history, phase_health,
            failure_patterns) from /api/algo/freshness/extended

    Returns:
        Rich Panel focused entirely on phase execution detail
    """

    # Header with run status summary
    header_rows: list[Text] = []
    phase_summary_map: dict[int, dict[str, Any]] = {}  # For looking up phase results

    if run and isinstance(run, dict) and not has_error(run):
        # Build phase results map for diagnostics
        phase_results_raw = run.get("phase_results")
        if phase_results_raw:
            phase_results_list = safe_get_list(phase_results_raw)
            if isinstance(phase_results_list, list):
                for p in phase_results_list:
                    if isinstance(p, dict):
                        phase_val = p.get("phase")
                        if phase_val is not None:
                            try:
                                phase_num = int(str(phase_val).replace("phase_", ""))
                                phase_summary_map[phase_num] = {
                                    "status": p.get("status", "").lower(),
                                    "summary": p.get("summary", ""),
                                    "error": p.get("error", ""),
                                    "name": p.get("name", ""),
                                }
                            except (ValueError, TypeError):
                                pass

        sts = (
            f"[bold {G}]OK COMPLETED[/]"
            if run.get("success") and not run.get("halted")
            else (f"[bold {Y}]~ HALTED[/]" if run.get("halted") else f"[bold {R}]ERROR[/]")
        )
        age = fmt_age(run.get("run_at"))
        rid = run.get("run_id", "")
        header_rows.append(Text.from_markup(f"{sts}  [dim]{age} | {rid}[/]"))

    # Add risk metrics summary if available, or error marker if missing
    if risk and isinstance(risk, dict):
        risk_parts = []
        var95 = risk.get("var95")
        if var95 is not None and isinstance(var95, (int, float)):
            risk_parts.append(f"VaR 95%: {var95:.2f}%")
        cvar95 = risk.get("cvar95")
        if cvar95 is not None and isinstance(cvar95, (int, float)):
            risk_parts.append(f"CVaR 95%: {cvar95:.2f}%")
        beta = risk.get("beta")
        if beta is not None and isinstance(beta, (int, float)):
            risk_parts.append(f"Portfolio Beta: {beta:.2f}")
        conc5 = risk.get("conc5")
        if conc5 is not None and isinstance(conc5, (int, float)):
            risk_parts.append(f"Top 5%: {conc5:.1f}%")

        if risk_parts:
            header_rows.append(Text.from_markup(f"[dim]{' | '.join(risk_parts)}[/]"))
    elif risk is None:
        # Explicit error marker when risk data is missing - fail-fast visibility
        header_rows.append(Text.from_markup(f"[{R}]⚠ Risk data unavailable[/]"))

    # Build phase details - split across two tight columns (phases 1-5 / 6-9, same
    # split used before the panel was ever narrowed to one column) so all 9 phases
    # fit within the fixed expanded-view height. A third, narrower column squeezes
    # in the algo health trend (run history / phase health / failure patterns).
    left_phase_rows: list[Text | Rule] = []
    right_phase_rows: list[Text | Rule] = []

    if hlth and isinstance(hlth, dict):
        execution_health = hlth.get("execution_health")
        if execution_health and isinstance(execution_health, dict):
            # Build phase status map
            phase_status_map: dict[int, dict[str, Any]] = {}
            if run and isinstance(run, dict):
                phase_results_raw = run.get("phase_results")
                if phase_results_raw:
                    phase_results_list = safe_get_list(phase_results_raw)
                    if isinstance(phase_results_list, list):
                        for p in phase_results_list:
                            if isinstance(p, dict):
                                phase_val = p.get("phase")
                                status_val = p.get("status")
                                if phase_val is not None and status_val is not None:
                                    try:
                                        phase_num = int(str(phase_val).replace("phase_", ""))
                                        phase_status_map[phase_num] = {
                                            "status": str(status_val).lower(),
                                            "summary": p.get("summary") or "",
                                        }
                                    except (ValueError, TypeError):
                                        pass

            # Define all 9 phases
            phases_def = [
                (1, "PHASE 1: Data Freshness Check", execution_health.get("phase_1_data_check")),
                (2, "PHASE 2: Circuit Breakers", execution_health.get("phase_2_circuit_breakers")),
                (3, "PHASE 3: Position Monitor", execution_health.get("phase_3_position_monitor")),
                (4, "PHASE 4: Broker Reconciliation", execution_health.get("phase_4_broker_reconciliation")),
                (5, "PHASE 5: Exposure Policy", execution_health.get("phase_5_exposure_policy")),
                (6, "PHASE 6: Exit Execution", execution_health.get("phase_6_exit_execution")),
                (7, "PHASE 7: Signal Generation", execution_health.get("phase_7_signal_generation")),
                (8, "PHASE 8: Entry Execution", execution_health.get("phase_8_entry_execution")),
                (9, "PHASE 9: Portfolio Snapshot", execution_health.get("phase_9_portfolio_snapshot")),
            ]

            # Build phase details
            for phase_num, phase_name, phase_data in phases_def:
                phase_status = phase_status_map.get(phase_num, {})
                status_str = phase_status.get("status", "not_run")
                phase_summary = phase_summary_map.get(phase_num, {})
                phase_error = phase_summary.get("error", "")
                phase_summary_text = phase_summary.get("summary", "")

                # Determine status icon and color based on orchestrator result
                if status_str in ("success", "completed", "ok"):
                    status_icon = "[bold green]✓[/]"
                    status_label = "OK"
                    color = G
                elif status_str in ("halt", "halted"):
                    status_icon = "[bold yellow]~[/]"
                    status_label = "HALTED"
                    color = Y
                elif status_str == "degraded" and "DRY-RUN" in phase_status.get("summary", ""):
                    # Same benign-stub exemption as orchestrator.py's _final_report() (2026-07-27
                    # fix) and the compact algo-health panel above: Phase 6's dry_run branch
                    # unconditionally reports status="degraded" before any real per-item exit
                    # logic runs, so this exact literal can never coexist with a genuine exit
                    # error. Without this, this panel showed "⚠ WARNING" for Exit Execution on
                    # every single local dry-run - a run that Run History (reading the same
                    # run's overall_status, which already carries this exemption) correctly
                    # shows as "✓ OK" - making the two panels contradict each other for the
                    # exact same run.
                    status_icon = "[dim]⊘[/]"
                    status_label = "SKIPPED (dry-run)"
                    color = DIM
                elif status_str in ("warn", "degraded", "completed_degraded"):
                    status_icon = "[bold yellow]⚠[/]"
                    status_label = "WARNING"
                    color = Y
                elif status_str == "skipped":
                    status_icon = "[dim]⊘[/]"
                    status_label = "SKIPPED"
                    color = DIM
                elif status_str in ("error", "failed"):
                    status_icon = "[bold red]✗[/]"
                    status_label = "ERROR"
                    color = R
                else:
                    status_icon = "[dim]-[/]"
                    status_label = "NOT RUN"
                    color = DIM

                # Phase header with status
                phase_header = Text.from_markup(
                    f"{status_icon} [bold {color}]{phase_name}[/] [{color}]{status_label}[/]"
                )

                target_rows = left_phase_rows if phase_num <= 5 else right_phase_rows

                target_rows.append(phase_header)

                # Add phase summary if available
                if phase_summary_text and status_str != "success":
                    target_rows.append(Text.from_markup(f"  [dim]{phase_summary_text[:80]}[/]"))

                # Add error message if phase failed
                if phase_error and status_str in ("error", "failed"):
                    target_rows.append(Text.from_markup(f"  [{R}]ERROR: {phase_error[:70]}[/]"))

                # Phase details based on data available
                if phase_data is None:
                    target_rows.append(Text.from_markup("  [dim]No data available[/]"))
                elif phase_num == 1:  # Data Freshness
                    if phase_data.get("tables_validated") is not None:
                        target_rows.append(
                            Text.from_markup(f"  Tables: {phase_data.get('tables_validated')} validated")
                        )
                    if phase_data.get("tables_fresh") is not None:
                        fresh_color = G if phase_data.get("tables_fresh") == phase_data.get("tables_validated") else Y
                        target_rows.append(
                            Text.from_markup(f"  [{fresh_color}]Fresh: {phase_data.get('tables_fresh')}[/]")
                        )
                    if phase_data.get("tables_stale") is not None:
                        stale_color = R if (safe_int(phase_data.get("tables_stale"), default=0) or 0) > 0 else G
                        target_rows.append(
                            Text.from_markup(f"  [{stale_color}]Stale: {phase_data.get('tables_stale')}[/]")
                        )
                    if phase_data.get("stale_tables") and isinstance(phase_data.get("stale_tables"), list):
                        for tbl in phase_data.get("stale_tables", [])[:3]:
                            if isinstance(tbl, dict):
                                tbl_name = tbl.get("table_name", "?")
                                age = tbl.get("age", "?")
                                target_rows.append(Text.from_markup(f"    • {tbl_name}: [{Y}]{age}[/]"))

                elif phase_num == 2:  # Circuit Breakers
                    if "any_triggered" not in phase_data:
                        target_rows.append(Text.from_markup(f"  [{R}]ERROR: Missing circuit breaker status[/]"))
                    else:
                        triggered = phase_data["any_triggered"]
                        triggered_color = R if triggered else G
                        triggered_text = "TRIGGERED" if triggered else "OK"
                        target_rows.append(Text.from_markup(f"  Status: [{triggered_color}]{triggered_text}[/]"))
                    if "drawdown_pct" in phase_data and phase_data["drawdown_pct"] is not None:
                        dd = phase_data["drawdown_pct"]
                        dd_color = (
                            R
                            if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_HALT_PCT
                            else Y
                            if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_CAUTION_PCT
                            else G
                        )
                        dd_status = (
                            "TRIGGERED"
                            if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_HALT_PCT
                            else "CAUTION"
                            if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_CAUTION_PCT
                            else "OK"
                        )
                        target_rows.append(Text.from_markup(f"  Drawdown: [{dd_color}]{dd:.1f}% ({dd_status})[/]"))
                    if "daily_loss_pct" in phase_data and phase_data["daily_loss_pct"] is not None:
                        dl = phase_data["daily_loss_pct"]
                        dl_color = (
                            R
                            if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_HALT_PCT
                            else Y
                            if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_CAUTION_PCT
                            else G
                        )
                        dl_status = (
                            "TRIGGERED"
                            if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_HALT_PCT
                            else "CAUTION"
                            if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_CAUTION_PCT
                            else "OK"
                        )
                        target_rows.append(Text.from_markup(f"  Daily Loss: [{dl_color}]{dl:.1f}% ({dl_status})[/]"))
                    if "vix_level" in phase_data and phase_data["vix_level"] is not None:
                        vix = phase_data["vix_level"]
                        vix_color = (
                            R
                            if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_EXTREME
                            else Y
                            if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_HIGH
                            else G
                        )
                        vix_status = (
                            "EXTREME"
                            if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_EXTREME
                            else "HIGH"
                            if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_HIGH
                            else "NORMAL"
                        )
                        target_rows.append(Text.from_markup(f"  VIX: [{vix_color}]{vix:.1f} ({vix_status})[/]"))
                    var = phase_data.get("var95")
                    if var is not None:
                        var_color = R if var >= 4 else Y if var >= 2 else G
                        target_rows.append(Text.from_markup(f"  VaR 95%: [{var_color}]{var:.2f}%[/]"))

                elif phase_num == 3:  # Position Monitor
                    open_pos = phase_data.get("open_positions")
                    if open_pos is not None:
                        pos_color = G if open_pos == 0 else Y if open_pos <= 5 else R
                        target_rows.append(Text.from_markup(f"  Open Positions: [{pos_color}]{open_pos}[/]"))
                    oldest_days = phase_data.get("oldest_days")
                    if oldest_days is not None:
                        target_rows.append(Text.from_markup(f"  Oldest: {oldest_days}d"))
                    max_loss = phase_data.get("max_loss_pct")
                    if max_loss is not None:
                        loss_color = R if max_loss <= -5 else Y if max_loss <= -2 else G
                        target_rows.append(Text.from_markup(f"  Max Loss: [{loss_color}]{max_loss:.1f}%[/]"))
                    total_pnl = phase_data.get("total_unrealized_pnl")
                    if total_pnl is not None:
                        # MISLABELED 2026-08-23 (goal session): same field/bug as the other
                        # phase_num==3 branch above - total_unrealized_pnl is open-position-
                        # only, not a real total including closed/realized trades.
                        pnl_color = G if total_pnl >= 0 else R
                        target_rows.append(Text.from_markup(f"  Unrealized P&L: [{pnl_color}]${total_pnl:,.0f}[/]"))

                elif phase_num == 4:  # Broker Reconciliation
                    sync_count = phase_data.get("sync_count")
                    if sync_count is not None:
                        target_rows.append(Text.from_markup(f"  Syncs: {sync_count}"))
                    match_pct = phase_data.get("avg_match_pct")
                    if match_pct is not None:
                        match_color = G if match_pct >= 95 else Y if match_pct >= 80 else R
                        target_rows.append(Text.from_markup(f"  Match Rate: [{match_color}]{match_pct:.0f}%[/]"))
                    errors = phase_data.get("errors_found")
                    if errors is not None and errors > 0:
                        target_rows.append(Text.from_markup(f"  [{R}]Errors: {errors}[/]"))

                elif phase_num == 5:  # Exposure Policy
                    regime = phase_data.get("market_regime")
                    if regime:
                        target_rows.append(Text.from_markup(f"  Regime: {regime}"))
                    entry_allowed = phase_data.get("entry_allowed")
                    if entry_allowed is not None:
                        entry_color = G if entry_allowed else R
                        entry_text = "ALLOWED" if entry_allowed else "BLOCKED"
                        target_rows.append(Text.from_markup(f"  Entries: [{entry_color}]{entry_text}[/]"))
                    max_entries = phase_data.get("max_new_entries")
                    if max_entries is not None:
                        target_rows.append(Text.from_markup(f"  Max Slots: {max_entries}"))
                    halt_active = phase_data.get("halt_active")
                    if halt_active:
                        target_rows.append(Text.from_markup(f"  [{R}]HALT ACTIVE[/]"))
                        halt_reason = phase_data.get("halt_reason")
                        if halt_reason:
                            target_rows.append(Text.from_markup(f"    Reason: {halt_reason[:60]}"))

                elif phase_num == 6:  # Exit Execution
                    exits = phase_data.get("exits_executed")
                    if exits is not None:
                        exit_color = G if exits > 0 else Y
                        target_rows.append(Text.from_markup(f"  [{exit_color}]Exits: {exits}[/]"))
                    sr = phase_data.get("success_rate")
                    exits_count = phase_data.get("exits_executed")
                    if sr is not None and exits_count is not None and exits_count > 0:
                        sr_color = G if sr >= 80 else Y if sr >= 50 else R
                        fail_text = f" ({int(100 - sr)}% failed)" if sr < 100 else ""
                        target_rows.append(Text.from_markup(f"  Success: [{sr_color}]{sr:.0f}%{fail_text}[/]"))
                    profit = phase_data.get("avg_profit")
                    if profit is not None:
                        profit_color = G if profit > 0 else R if profit < 0 else Y
                        profit_text = "LOSS" if profit < 0 else "PROFIT"
                        target_rows.append(
                            Text.from_markup(f"  Avg Profit: [{profit_color}]${profit:,.0f} ({profit_text})[/]")
                        )
                    syms = phase_data.get("symbols_exited")
                    if syms:
                        if isinstance(syms, list):
                            target_rows.append(Text.from_markup(f"  Symbols: {', '.join(syms[:5])}"))
                        elif isinstance(syms, str):
                            target_rows.append(Text.from_markup(f"  Symbols: {syms[:50]}"))

                elif phase_num == 7:  # Signal Generation
                    signals_gen = phase_data.get("signals_generated")
                    if signals_gen is not None:
                        target_rows.append(Text.from_markup(f"  [{G}]Signals: {signals_gen}[/]"))
                    bs = phase_data.get("buy_signals")
                    ss = phase_data.get("sell_signals")
                    if bs is not None or ss is not None:
                        bs_display = bs if bs is not None else 0
                        ss_display = ss if ss is not None else 0
                        target_rows.append(Text.from_markup(f"  Buy: [{G}]{bs_display}[/]  Sell: [{Y}]{ss_display}[/]"))
                    strength = phase_data.get("avg_strength")
                    if strength is not None:
                        strength_color = G if strength >= 70 else Y if strength >= 50 else R
                        target_rows.append(Text.from_markup(f"  Avg Strength: [{strength_color}]{strength:.1f}[/]"))
                    syms = phase_data.get("symbols_with_signals")
                    if syms:
                        if isinstance(syms, list):
                            target_rows.append(Text.from_markup(f"  Symbols: {', '.join(syms[:5])}"))
                        elif isinstance(syms, str):
                            target_rows.append(Text.from_markup(f"  Symbols: {syms[:50]}"))

                elif phase_num == 8:  # Entry Execution
                    entries = phase_data.get("entries_executed")
                    if entries is not None:
                        entry_color = G if entries > 0 else Y
                        target_rows.append(Text.from_markup(f"  [{entry_color}]Entries: {entries}[/]"))
                    sr = phase_data.get("success_rate")
                    entries_count = phase_data.get("entries_executed")
                    if sr is not None and entries_count is not None and entries_count > 0:
                        sr_color = G if sr >= 80 else Y if sr >= 50 else R
                        fail_text = f" ({int(100 - sr)}% failed)" if sr < 100 else ""
                        target_rows.append(Text.from_markup(f"  Success: [{sr_color}]{sr:.0f}%{fail_text}[/]"))
                    avg_price = phase_data.get("avg_entry_price")
                    if avg_price is not None:
                        target_rows.append(Text.from_markup(f"  Avg Entry Price: ${avg_price:,.2f}"))
                    syms = phase_data.get("symbols_entered")
                    if syms:
                        if isinstance(syms, list):
                            target_rows.append(Text.from_markup(f"  Symbols: {', '.join(syms[:5])}"))
                        elif isinstance(syms, str):
                            target_rows.append(Text.from_markup(f"  Symbols: {syms[:50]}"))

                elif phase_num == 9:  # Portfolio Snapshot
                    portfolio = phase_data.get("portfolio_value")
                    if portfolio is not None:
                        target_rows.append(Text.from_markup(f"  Portfolio: ${portfolio:,.0f}"))
                    cash = phase_data.get("cash_available")
                    if cash is not None:
                        cash_color = G if cash > 0 else R
                        target_rows.append(Text.from_markup(f"  Cash: [{cash_color}]${cash:,.0f}[/]"))
                    ret_pct = phase_data.get("total_return_pct")
                    if ret_pct is not None:
                        ret_color = G if ret_pct > 0 else R
                        target_rows.append(Text.from_markup(f"  Return: [{ret_color}]{ret_pct:.2f}%[/]"))
                    if phase_data.get("latest_snapshot"):
                        target_rows.append(Text.from_markup(f"  Snapshot: {phase_data.get('latest_snapshot')[:19]}"))

                target_rows.append(Text(""))  # Spacing between phases

    # Long-window orchestrator/phase health (moved here from the data-freshness [l] panel -
    # this is run/phase health information, not per-table data freshness, so it belongs on
    # this panel instead; see panel_data_freshness_expanded for the table-freshness detail
    # that panel kept). Built BEFORE the phase layout below so it can fill the third column
    # directly - it previously was appended at the very end of content_rows, after the
    # fixed-size phase layout, reliability trend and past-runs history, which pushed it
    # past the Live(screen=True) alternate-screen viewport on any normal terminal height
    # (Rich Layout regions crop rather than scroll), making it effectively invisible even
    # though the code building it was correct. Per-table loader errors/repeated-failures/
    # never-started detail that used to occupy this column moved back to the DATA FRESHNESS
    # panel (_build_freshness_panel) - it's genuine loader/table health, not algo health,
    # and this panel's fixed real estate is better spent on content that's actually about
    # the algo (run history, phase reliability, halt-reason patterns).
    run_history_rows = _build_run_history_section(orch_extended.get("run_history") if orch_extended else None)
    phase_health_rows = _build_phase_health_section(orch_extended.get("phase_health") if orch_extended else None)
    failure_pattern_rows = _build_halt_reason_pattern_section(
        orch_extended.get("failure_patterns") if orch_extended else None
    )
    algo_trend_rows: list[Text | Rule] = []
    algo_trend_rows.extend(run_history_rows)
    algo_trend_rows.extend(phase_health_rows)
    algo_trend_rows.extend(failure_pattern_rows)
    # Each _build_*_section helper leads with its own dim Rule as a between-sections
    # divider - drop a leading one here since the trend_panel border/title below
    # already separates this column, and a Rule directly under the title looks redundant.
    if algo_trend_rows and isinstance(algo_trend_rows[0], Rule):
        algo_trend_rows.pop(0)

    # Phases 1-5 / 6-9 in their own tight columns (keeps the panel's total height in
    # check - all 9 phases stacked in one column ran past the fixed expanded-view
    # height and got clipped), algo health trend squeezed into a third, narrower
    # column alongside them so it's always visible instead of clipped off the bottom.
    # The trend column gets its own bordered Panel (title doubling as its heading)
    # instead of a bare Group, so there's a visible vertical rule marking where the
    # two phase columns end and the algo-health trend begins - Layout.split_row alone
    # has no divider between regions.
    layout: Layout | Group
    if algo_trend_rows:
        trend_panel = Panel(
            Group(*algo_trend_rows),
            title="[bold cyan]Algo Health Trends[/]",
            title_align="left",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        layout = Layout()
        layout.split_row(
            Layout(Group(*left_phase_rows), ratio=3, name="left_phases"),
            Layout(Group(*right_phase_rows), ratio=3, name="right_phases"),
            # minimum_size guards against ratio-based shrinking folding long halt-reason
            # identifiers (e.g. "phase_6_exit_execution halted: ...") into unreadable
            # single-word-per-line wrapping at the default 80-col console width used by
            # both the plain terminal renderer and tests/test_helpers/assertions.py's
            # render_panel_to_text - see test_data_freshness_expanded_orch_extended.py,
            # which caught the exact wrap-mangled text as a regression.
            Layout(trend_panel, ratio=2, minimum_size=44, name="algo_trend"),
        )
    else:
        layout = Layout()
        layout.split_row(
            Layout(Group(*left_phase_rows), ratio=1, name="left_phases"),
            Layout(Group(*right_phase_rows), ratio=1, name="right_phases"),
        )

    # Cross-run trend (30d) - is this phase failing all the time, or was this a one-off?
    reliability_rows = _build_phase_reliability_section(exec_patterns)

    # Per-run detail (last 8 runs) - how far each specific run got, and which phase stopped it
    past_runs_rows = _build_past_runs_section(exec_hist)

    # Add header at top if we have it, then phase detail, then trend, then per-run history
    content_rows: list[Any] = []
    if header_rows:
        content_rows.extend(header_rows)
        content_rows.append(Rule(style="dim"))
    content_rows.append(layout)
    if reliability_rows:
        content_rows.extend(reliability_rows)
    if past_runs_rows:
        content_rows.extend(past_runs_rows)

    all_content = Group(*content_rows) if content_rows else layout

    return Panel(
        all_content,
        title=r"[bold yellow]PHASE EXECUTION DETAILS[/]  [dim]\[h] return[/]",
        border_style="yellow",
        padding=(0, 1),
    )


__all__ = ["_build_results_panel"]
