"""Phase-execution detail for the ALGO HEALTH panel: the per-phase-badge status
formatters (`_build_phase_badges_and_metrics` / `_build_phase_badges_from_audit`) and
the full PHASE EXECUTION DETAILS sub-panel (`_build_phase_execution_panel`) that
panel_algo_health renders inline, plus the small helpers those two use.

Split out of health_algo.py (which re-exports these via dashboard.panels.health) once
it grew past the file-size ratchet's cap - this is a cohesive concern (phase status
mapping and rendering) that panel_algo_health calls into rather than something it does
itself.
"""

import json
import logging
from typing import Any, cast

from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from algo.config.orchestrator_config import OrchestratorConfig
from dashboard.data_validation import safe_float, safe_int

from ..formatters import fmt_age
from ..utilities import CY, DIM, PHASE_NAMES, G, R, Y
from .data_extractors import safe_get_list
from .health_shared import HALTED_STATES, _format_phase_badge, _get_item_status

logger = logging.getLogger(__name__)


def _build_loader_operational_detail_rows(hlth_items: list[Any] | None) -> list[Text | Rule]:
    """Loader errors, repeated failures, pending loaders, and stuck runners.

    FIX 2026-08-12: Now includes PENDING loaders (waiting to run) and RUNNING loaders
    (stuck >30min). These are distinct from data staleness - they are operational issues
    with the loader pipeline itself, not just aged data.
    """
    rows: list[Text | Rule] = []
    if not hlth_items:
        return rows

    # Collect loader state issues (distinct from error_message which is last error)
    loader_state_issues = [
        (r.get("tbl") or r.get("name") or "unknown", issue)
        for r in hlth_items
        if isinstance(r, dict) and (issue := r.get("loader_state_issue"))
    ]

    loader_errors = [
        (r.get("tbl") or r.get("name") or "unknown", r.get("loader_error"), r.get("loader_run_status"))
        for r in hlth_items
        if isinstance(r, dict) and r.get("loader_error")
    ]
    repeated_failures: list[tuple[str, int, Any]] = []
    for r in hlth_items:
        if isinstance(r, dict):
            n_fail_raw = r.get("consecutive_failures")
            if isinstance(n_fail_raw, (int, float)) and n_fail_raw >= 2:
                repeated_failures.append(
                    (r.get("tbl") or r.get("name") or "unknown", int(n_fail_raw), r.get("last_success_at"))
                )
    never_started = [
        r.get("tbl") or r.get("name") or "unknown"
        for r in hlth_items
        if isinstance(r, dict) and _get_item_status(r) != "ok" and r.get("loader_run_status") == "NOT_STARTED"
    ]

    if not (loader_state_issues or loader_errors or repeated_failures or never_started):
        return rows

    rows.append(Text.from_markup("[bold cyan]Loader Operational Health[/]"))

    # FIX 2026-08-12: Show loader state issues (PENDING, RUNNING/stuck, repeated failures)
    # These are distinct from fetch errors - they indicate pipeline flow problems
    if loader_state_issues:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[bold {R}]Loader Pipeline Issues:[/]"))
        for tbl_name, issue in loader_state_issues[:8]:
            icon = "⏳" if "PENDING" in issue else "⏱️ " if "TIMEOUT" in issue else "⚠️"
            rows.append(Text.from_markup(f"  {icon} [{R}]{tbl_name}:[/] [dim]{issue}[/]"))
        if len(loader_state_issues) > 8:
            rows.append(Text.from_markup(f"  [dim]...and {len(loader_state_issues) - 8} more[/]"))

    if loader_errors:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[bold {R}]Loader Fetch Errors:[/]"))
        for tbl_name, err, lrs in loader_errors[:5]:
            tag = f"[{lrs}] " if lrs in ("TIMEOUT", "FAILED") else ""
            rows.append(Text.from_markup(f"  [{R}]{tbl_name}:[/] [dim]{tag}{str(err)[:50]}[/]"))
        if len(loader_errors) > 5:
            rows.append(Text.from_markup(f"  [dim]...and {len(loader_errors) - 5} more[/]"))

    if repeated_failures:
        repeated_failures.sort(key=lambda t: t[1], reverse=True)
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[bold {R}]Repeated failures:[/]"))
        for tbl_name, n_fail, last_ok in repeated_failures[:5]:
            last_ok_s = f"last ok {fmt_age(last_ok)}" if last_ok else "never succeeded"
            rows.append(Text.from_markup(f"  [{R}]{tbl_name}:[/] [dim]{n_fail}x, {last_ok_s}[/]"))
        if len(repeated_failures) > 5:
            rows.append(Text.from_markup(f"  [dim]...and {len(repeated_failures) - 5} more[/]"))

    if never_started:
        rows.append(Rule(style="dim"))
        rows.append(
            Text.from_markup(f"[bold {R}]Never run:[/]  " + "  ".join(f"[white]{n}[/]" for n in never_started[:6]))
        )
        if len(never_started) > 6:
            rows.append(Text.from_markup(f"  [dim]...and {len(never_started) - 6} more[/]"))

    return rows


def _build_phase_execution_panel(  # noqa: C901
    execution_health: dict[str, Any] | None,
    run: dict[str, Any] | None = None,
    hlth_items: list[Any] | None = None,
) -> Panel | None:
    """Build PHASE EXECUTION HEALTH panel showing ALL 9 phases with expanded details.

    Each phase shows:
    - ✓ COMPLETED: phase executed successfully with full metrics
    - ~ HALTED/SKIPPED: phase halted or skipped with reason
    - ✗ ERROR: phase failed with error details
    - ⊘ NOT RUN: phase hasn't executed yet

    Returns a Rich Panel with all phases, or None if no data available.
    """
    if not execution_health:
        return None

    # Build phase status map from run data
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
                                    "name": p.get("name", ""),
                                    "summary": p.get("summary", ""),
                                }
                            except (ValueError, TypeError):
                                pass

    # Define all 9 phases with metadata
    phases_def = [
        (1, "Data Freshness Check", "data_check", execution_health.get("phase_1_data_check")),
        (2, "Circuit Breakers", "circuit_breakers", execution_health.get("phase_2_circuit_breakers")),
        (3, "Position Monitor", "position_monitor", execution_health.get("phase_3_position_monitor")),
        (4, "Broker Reconciliation", "reconciliation", execution_health.get("phase_4_broker_reconciliation")),
        (5, "Exposure Policy", "exposure_policy", execution_health.get("phase_5_exposure_policy")),
        (6, "Exit Execution", "exit_execution", execution_health.get("phase_6_exit_execution")),
        (7, "Signal Generation", "signal_generation", execution_health.get("phase_7_signal_generation")),
        (8, "Entry Execution", "entry_execution", execution_health.get("phase_8_entry_execution")),
        (9, "Portfolio Snapshot", "portfolio_snapshot", execution_health.get("phase_9_portfolio_snapshot")),
    ]

    # Track phase statistics
    executed = sum(1 for p in phase_status_map.values() if p["status"] in ("success", "completed", "ok"))
    halted = sum(1 for p in phase_status_map.values() if p["status"] in HALTED_STATES)
    skipped = sum(1 for p in phase_status_map.values() if p["status"] == "skipped")
    errored = sum(1 for p in phase_status_map.values() if p["status"] in ("error", "failed"))
    not_run = 9 - len(phase_status_map)

    # Build phase rows showing ALL 9 phases with expanded details, split across two
    # tight columns (1-5 / 6-9) so the panel's total height stays in check.
    left_phase_rows: list[Text | Rule] = []
    right_phase_rows: list[Text | Rule] = []

    for phase_num, phase_name, _phase_key, phase_data in phases_def:
        target_rows = left_phase_rows if phase_num <= 5 else right_phase_rows
        phase_status = phase_status_map.get(phase_num, {})
        status_str = phase_status.get("status", "not_run")

        # Determine status icon and color
        if status_str in ("success", "completed", "ok"):
            status_icon = "[bold green]✓[/]"
            status_text = "COMPLETED"
            base_color = G
        elif status_str == "blocked":
            # Distinct from HALTED: a safety guard (e.g. Phase 8's market-hours/stale-signal/
            # pending-order guards) correctly prevented execution - PhaseResult.ok treats this
            # as a successful outcome, not a failure. Labeling it "HALTED" would read as an
            # incident every time the guard does its job correctly (which, for Phase 8 outside
            # market hours, is every run).
            status_icon = "[bold yellow]■[/]"
            status_text = "BLOCKED (guard)"
            base_color = Y
        elif status_str == "degraded" and "DRY-RUN" in (phase_status.get("summary") or ""):
            # Same benign-stub exemption already applied to orchestrator.py's _final_report()
            # console log and overall-success calc (see that file's 2026-07-27 fix): Phase 6's
            # dry_run branch reports status="degraded" unconditionally, before any real
            # per-item exit-execution logic runs, so this literal "DRY-RUN" summary can never
            # coexist with a genuine exit error. Left unexempted here, this panel - the primary
            # way this system is actually observed via `python -m dashboard --local` - showed "~
            # HALTED" for Exit Execution on every single local dry-run, indistinguishable from
            # a real halt.
            status_icon = "[dim]⊘[/]"
            status_text = "SKIPPED (dry-run)"
            base_color = DIM
        elif status_str in ("halt", "halted", "warn", "degraded"):
            status_icon = "[bold yellow]~[/]"
            status_text = "HALTED"
            base_color = Y
        elif status_str == "skipped":
            # Distinct from HALTED: this phase never ran because an earlier phase
            # halted (skip_if_halted=YES per GOVERNANCE.md), not because it failed
            # itself. Conflating the two here previously made every downstream phase
            # look like it independently halted.
            status_icon = "[dim]⊘[/]"
            status_text = "SKIPPED (halt upstream)"
            base_color = DIM
        elif status_str in ("error", "failed"):
            status_icon = "[bold red]✗[/]"
            status_text = "ERROR"
            base_color = R
        else:  # not_run or no data
            status_icon = "[dim]⊘[/]"
            status_text = "NOT RUN"
            base_color = DIM

        # Phase header
        phase_header = f"  {status_icon} [bold]{phase_name}[/] [{base_color}]{status_text}[/]"
        target_rows.append(Text.from_markup(phase_header))

        # NOT RUN means this specific orchestrator run's phase_results has no entry for this
        # phase (e.g. an earlier phase halted before it started). The detail rows below,
        # though, come from execution_health - a live, independent query of each phase's
        # underlying table (e.g. circuit_breaker_status) - not from this run. Without this
        # note, "Circuit Breakers NOT RUN" next to a detail line reading "Status: TRIGGERED"
        # reads as self-contradictory instead of "didn't run this time, but here's the
        # latest live reading regardless."
        if status_str == "not_run" and phase_data is not None:
            target_rows.append(Text.from_markup("      [dim](live check, not from this run)[/]"))

        # Phase details - expand each phase with all relevant info
        if phase_data is None:
            target_rows.append(Text.from_markup("      [dim]─ no data available[/]"))
        elif phase_num == 1:  # Data Freshness Check
            tables_validated = phase_data.get("tables_validated")
            tables_fresh = phase_data.get("tables_fresh")
            tables_stale = phase_data.get("tables_stale")
            validation_status = phase_data.get("validation_status")
            stale_tables = phase_data.get("stale_tables")

            if tables_validated is not None:
                target_rows.append(Text.from_markup(f"      [dim]Tables validated:[/] {tables_validated}"))
            if tables_fresh is not None:
                target_rows.append(Text.from_markup(f"      [dim]Tables fresh:[/] [{G}]{tables_fresh}[/]"))
            if tables_stale is not None:
                stale_color = R if tables_stale >= 3 else Y if tables_stale > 0 else G
                target_rows.append(Text.from_markup(f"      [dim]Tables stale:[/] [{stale_color}]{tables_stale}[/]"))
            if stale_tables and isinstance(stale_tables, (list, dict)):
                if isinstance(stale_tables, list):
                    for tbl_info in stale_tables[:3]:
                        if isinstance(tbl_info, dict):
                            tbl_name = tbl_info.get("table_name", "unknown")
                            age = tbl_info.get("age", "?")
                            target_rows.append(Text.from_markup(f"        [dim]•[/] {tbl_name} [{Y}]{age}[/]"))
                elif isinstance(stale_tables, dict):
                    for tbl_name, age_info in list(stale_tables.items())[:3]:
                        target_rows.append(Text.from_markup(f"        [dim]•[/] {tbl_name} [{Y}]{age_info}[/]"))
            if validation_status:
                target_rows.append(Text.from_markup(f"      [dim]Status:[/] {validation_status}"))

        elif phase_num == 2:  # Circuit Breakers
            if "any_triggered" not in phase_data:
                target_rows.append(Text.from_markup(f"      [{R}]ERROR: Missing circuit breaker status[/]"))
            else:
                any_triggered = phase_data["any_triggered"]
                dd = safe_float(phase_data.get("drawdown_pct"), default=None)
                dl = safe_float(phase_data.get("daily_loss_pct"), default=None)
                vix = safe_float(phase_data.get("vix_level"), default=None)
                var95 = safe_float(phase_data.get("var95"), default=None)

                triggered_status = "TRIGGERED" if any_triggered else "OK"
                triggered_color = R if any_triggered else G
                target_rows.append(Text.from_markup(f"      [dim]Status:[/] [{triggered_color}]{triggered_status}[/]"))

                if dd is not None:
                    dd_color = (
                        R
                        if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_HALT_PCT
                        else Y
                        if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_CAUTION_PCT
                        else G
                    )
                    target_rows.append(Text.from_markup(f"      [dim]Drawdown:[/] [{dd_color}]{dd:.1f}%[/]"))
                if dl is not None:
                    dl_color = (
                        R
                        if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_HALT_PCT
                        else Y
                        if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_CAUTION_PCT
                        else G
                    )
                    target_rows.append(Text.from_markup(f"      [dim]Daily Loss:[/] [{dl_color}]{dl:.1f}%[/]"))
                if vix is not None:
                    vix_color = (
                        R
                        if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_EXTREME
                        else Y
                        if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_HIGH
                        else CY
                        if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_ELEVATED
                        else G
                    )
                    target_rows.append(Text.from_markup(f"      [dim]VIX:[/] [{vix_color}]{vix:.1f}[/]"))
                if var95 is not None:
                    var_color = R if var95 >= 4 else Y if var95 >= 2 else G
                    target_rows.append(Text.from_markup(f"      [dim]VaR 95%:[/] [{var_color}]{var95:.2f}%[/]"))

        elif phase_num == 3:  # Position Monitor
            open_positions = safe_int(phase_data.get("open_positions"), default=None)
            oldest_days = safe_int(phase_data.get("oldest_days"), default=None)
            max_loss_pct = safe_float(phase_data.get("max_loss_pct"), default=None)
            total_unrealized = safe_float(phase_data.get("total_unrealized_pnl"), default=None)

            if open_positions is not None:
                pos_color = G if open_positions == 0 else Y if open_positions <= 5 else R
                target_rows.append(Text.from_markup(f"      [dim]Open positions:[/] [{pos_color}]{open_positions}[/]"))
            if oldest_days is not None:
                target_rows.append(Text.from_markup(f"      [dim]Oldest position:[/] {oldest_days}d"))
            if max_loss_pct is not None:
                loss_color = R if max_loss_pct <= -5 else Y if max_loss_pct <= -2 else G
                target_rows.append(Text.from_markup(f"      [dim]Max loss:[/] [{loss_color}]{max_loss_pct:.1f}%[/]"))
            if total_unrealized is not None:
                # MISLABELED 2026-08-23 (goal session): sourced from total_unrealized_pnl
                # (open-position P&L only, no closed trades in this Position Monitor phase) -
                # "Total P&L:" falsely implied it included realized gains too.
                pnl_color = G if total_unrealized >= 0 else R
                target_rows.append(
                    Text.from_markup(f"      [dim]Unrealized P&L:[/] [{pnl_color}]${total_unrealized:,.0f}[/]")
                )

        elif phase_num == 4:  # Broker Reconciliation
            sync_count = safe_int(phase_data.get("sync_count"), default=None)
            avg_match_pct = safe_float(phase_data.get("avg_match_pct"), default=None)
            errors_found = safe_int(phase_data.get("errors_found"), default=None)

            if sync_count is not None:
                target_rows.append(Text.from_markup(f"      [dim]Syncs attempted:[/] {sync_count}"))
            if avg_match_pct is not None:
                match_color = G if avg_match_pct >= 95 else Y if avg_match_pct >= 80 else R
                target_rows.append(
                    Text.from_markup(f"      [dim]Match rate:[/] [{match_color}]{avg_match_pct:.0f}%[/]")
                )
            if errors_found is not None and errors_found > 0:
                target_rows.append(Text.from_markup(f"      [dim]Errors found:[/] [{R}]{errors_found}[/]"))

        elif phase_num == 5:  # Exposure Policy
            required_keys: set[str] = {
                "market_regime",
                "entry_allowed",
                "halt_active",
                "max_new_entries",
                "halt_reason",
            }
            missing = required_keys - set(phase_data.keys() if phase_data else [])
            if missing:
                target_rows.append(
                    Text.from_markup(
                        f"      [dim]ERROR:[/] [{R}]Incomplete data - missing {', '.join(sorted(missing))}[/]"
                    )
                )
            else:
                market_regime = phase_data["market_regime"]
                entry_allowed = phase_data["entry_allowed"]
                halt_active = phase_data["halt_active"]
                max_new_entries = phase_data["max_new_entries"]
                halt_reason = phase_data["halt_reason"]

                if market_regime:
                    target_rows.append(Text.from_markup(f"      [dim]Market regime:[/] {market_regime}"))
                if entry_allowed is not None:
                    entry_status = "ALLOWED" if entry_allowed else "BLOCKED"
                    entry_color = G if entry_allowed else R
                    target_rows.append(Text.from_markup(f"      [dim]New entries:[/] [{entry_color}]{entry_status}[/]"))
                if max_new_entries is not None and entry_allowed:
                    target_rows.append(Text.from_markup(f"      [dim]Max slots available:[/] {max_new_entries}"))
                if halt_active:
                    halt_color = R if halt_active else G
                    target_rows.append(Text.from_markup(f"      [dim]Halt status:[/] [{halt_color}]ACTIVE[/]"))
                    if halt_reason:
                        target_rows.append(Text.from_markup(f"      [dim]Reason:[/] {halt_reason[:60]}"))

        elif phase_num == 6:  # Exit Execution
            exits_executed = safe_int(phase_data.get("exits_executed"), default=None)
            success_rate = safe_float(phase_data.get("success_rate"), default=None)
            avg_profit = safe_float(phase_data.get("avg_profit"), default=None)
            symbols_exited = phase_data.get("symbols_exited")

            if exits_executed is not None:
                target_rows.append(Text.from_markup(f"      [dim]Exits executed:[/] {exits_executed}"))
            if success_rate is not None and exits_executed is not None and exits_executed > 0:
                sr_color = G if success_rate >= 80 else Y if success_rate >= 50 else R
                target_rows.append(Text.from_markup(f"      [dim]Success rate:[/] [{sr_color}]{success_rate:.0f}%[/]"))
            if avg_profit is not None:
                profit_color = G if avg_profit > 0 else R
                target_rows.append(
                    Text.from_markup(f"      [dim]Avg profit/exit:[/] [{profit_color}]${avg_profit:,.0f}[/]")
                )
            if symbols_exited and isinstance(symbols_exited, (list, str)):
                if isinstance(symbols_exited, str):
                    target_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {symbols_exited[:50]}"))
                elif isinstance(symbols_exited, list):
                    target_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {', '.join(symbols_exited[:5])}"))

        elif phase_num == 7:  # Signal Generation
            signals_generated = safe_int(phase_data.get("signals_generated"), default=None)
            buy_signals = safe_int(phase_data.get("buy_signals"), default=None)
            sell_signals = safe_int(phase_data.get("sell_signals"), default=None)
            avg_strength = safe_float(phase_data.get("avg_strength"), default=None)
            symbols_with_signals = phase_data.get("symbols_with_signals")

            if signals_generated is not None:
                target_rows.append(Text.from_markup(f"      [dim]Signals generated:[/] [{G}]{signals_generated}[/]"))
            if buy_signals is not None or sell_signals is not None:
                bs = buy_signals if buy_signals is not None else 0
                ss = sell_signals if sell_signals is not None else 0
                target_rows.append(
                    Text.from_markup(f"      [dim]Buy signals:[/] [{G}]{bs}[/] [dim]Sell signals:[/] [{Y}]{ss}[/]")
                )
            if avg_strength is not None:
                strength_color = G if avg_strength >= 70 else Y if avg_strength >= 50 else R
                target_rows.append(
                    Text.from_markup(f"      [dim]Avg strength:[/] [{strength_color}]{avg_strength:.1f}[/]")
                )
            if symbols_with_signals and isinstance(symbols_with_signals, (list, str)):
                if isinstance(symbols_with_signals, str):
                    target_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {symbols_with_signals[:50]}"))
                elif isinstance(symbols_with_signals, list):
                    target_rows.append(
                        Text.from_markup(f"      [dim]Symbols:[/] {', '.join(symbols_with_signals[:5])}")
                    )

        elif phase_num == 8:  # Entry Execution
            entries_executed = safe_int(phase_data.get("entries_executed"), default=None)
            success_rate = safe_float(phase_data.get("success_rate"), default=None)
            avg_entry_price = safe_float(phase_data.get("avg_entry_price"), default=None)
            symbols_entered = phase_data.get("symbols_entered")

            if entries_executed is not None:
                target_rows.append(Text.from_markup(f"      [dim]Entries executed:[/] [{G}]{entries_executed}[/]"))
            if success_rate is not None and entries_executed is not None and entries_executed > 0:
                sr_color = G if success_rate >= 80 else Y if success_rate >= 50 else R
                target_rows.append(Text.from_markup(f"      [dim]Success rate:[/] [{sr_color}]{success_rate:.0f}%[/]"))
            if avg_entry_price is not None:
                target_rows.append(Text.from_markup(f"      [dim]Avg entry price:[/] ${avg_entry_price:,.2f}"))
            if symbols_entered and isinstance(symbols_entered, (list, str)):
                if isinstance(symbols_entered, str):
                    target_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {symbols_entered[:50]}"))
                elif isinstance(symbols_entered, list):
                    target_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {', '.join(symbols_entered[:5])}"))

        elif phase_num == 9:  # Portfolio Snapshot
            portfolio_value = safe_float(phase_data.get("portfolio_value"), default=None)
            cash_available = safe_float(phase_data.get("cash_available"), default=None)
            total_return_pct = safe_float(phase_data.get("total_return_pct"), default=None)
            latest_snapshot = phase_data.get("latest_snapshot")

            if portfolio_value is not None:
                target_rows.append(Text.from_markup(f"      [dim]Portfolio value:[/] ${portfolio_value:,.0f}"))
            if cash_available is not None:
                cash_color = G if cash_available > 0 else R
                target_rows.append(
                    Text.from_markup(f"      [dim]Cash available:[/] [{cash_color}]${cash_available:,.0f}[/]")
                )
            if total_return_pct is not None:
                ret_color = G if total_return_pct > 0 else R
                target_rows.append(
                    Text.from_markup(f"      [dim]Total return:[/] [{ret_color}]{total_return_pct:.2f}%[/]")
                )
            if latest_snapshot:
                target_rows.append(Text.from_markup(f"      [dim]Last snapshot:[/] {latest_snapshot[:19]}"))

        # Separator between phases
        target_rows.append(Text(""))

    # Build summary header
    summary = f"[dim]{executed}✓  {halted}~  {errored}✗  {skipped + not_run}⊘[/]"

    # Phases 1-5 / 6-9 in their own tight columns, loader-operational detail moved
    # over from the DATA FRESHNESS panel (see _build_loader_operational_detail_rows)
    # squeezed into a third, narrower column alongside them.
    loader_detail_rows = _build_loader_operational_detail_rows(hlth_items)
    body: Group | Layout
    if loader_detail_rows:
        three_col = Layout()
        three_col.split_row(
            Layout(Group(*left_phase_rows), ratio=3, name="left_phases"),
            Layout(Group(*right_phase_rows), ratio=3, name="right_phases"),
            Layout(Group(*loader_detail_rows), ratio=2, name="loader_detail"),
        )
        body = three_col
    else:
        two_col = Layout()
        two_col.split_row(
            Layout(Group(*left_phase_rows), ratio=1, name="left_phases"),
            Layout(Group(*right_phase_rows), ratio=1, name="right_phases"),
        )
        body = two_col

    # Build panel with all phases
    return Panel(
        body,
        title=f"[bold cyan]PHASE EXECUTION DETAILS[/]  {summary}",
        border_style="cyan",
        padding=(0, 1),
    )


def _extract_phase_metrics_from_pdata(pdata: dict[str, Any] | None) -> tuple[int, int, int]:
    """Extract signals_generated, entries_executed, exits_executed from phase data.

    Returns:
        (signals_gen, entries_exec, exits_exec) - all ints >= 0
        Returns (0, 0, 0) if metrics are missing (expected in local dev if orchestrator not fully run)

    Raises:
        ValueError: If phase data structure is fundamentally broken (e.g., wrong type)
    """
    if not pdata:
        # Phase data not available yet - return defaults instead of failing
        return 0, 0, 0

    # Metrics may not be present if orchestrator hasn't populated them yet
    sg = pdata.get("signals_generated")
    # CRITICAL: Check explicitly for None to avoid confusing 0 (no entries) with missing data
    # Do not use `or` which treats 0 as falsy and falls back to alternative field
    ee = pdata.get("entries_executed")
    if ee is None:
        ee = pdata.get("trades_executed")
    xe = pdata.get("exits_executed")

    # Missing metrics during partial orchestrator runs is expected; return defaults
    # Only fail on corrupted data (wrong types), not missing fields
    if sg is None or ee is None or xe is None:
        logger.debug(
            f"Phase metrics incomplete (expected during partial runs): "
            f"signals_generated={sg}, entries_executed={ee}, exits_executed={xe}"
        )
        return 0, 0, 0

    try:
        return int(sg), int(ee), int(xe)
    except (ValueError, TypeError) as e:
        raise ValueError(f"[DATA_TYPE_ERROR] Cannot convert phase metrics to int: {e}") from e


def _parse_phase_data_json(pdata_raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse phase data field (may be string or dict).

    Returns:
        dict: Parsed phase data OR marker dict with data_unavailable=True
    """
    if isinstance(pdata_raw, str):
        try:
            return cast(dict[str, Any], json.loads(pdata_raw))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[HEALTH] Failed to parse phase metrics data JSON: {e}")
            return {
                "data_unavailable": True,
                "reason": "phase_data_json_invalid",
            }
    elif isinstance(pdata_raw, dict):
        return pdata_raw
    logger.debug("[HEALTH] Phase data raw is None or invalid type, returning unavailability marker")
    return {
        "data_unavailable": True,
        "reason": "phase_data_missing",
    }


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
        name_val = p.get("name")
        phase_val = p.get("phase")
        if phase_val is None:
            phase_val = ""
        raw = (name_val if name_val is not None else phase_val).lower()
        parts_p = raw.split("_")
        base = "_".join(parts_p[:2]) if len(parts_p) >= 2 else raw
        short = PHASE_NAMES.get(base, base.replace("phase_", "P"))[:8]
        ps_raw = p.get("status")
        if ps_raw is None:
            ps_raw = ""
        ps = ps_raw
        # BUG FOUND 2026-08-10: same benign-stub exemption already applied at
        # _build_phase_execution_panel/_build_results_panel/panel_status (see any of
        # those for the full writeup) was missing here - a 4th, live, reachable call
        # site (panel_algo_health -> _build_phase_badges_and_metrics, wired into
        # dashboard/renderers/pipeline.py) that _format_phase_badge() alone can never
        # exempt, since it only receives the raw status string with no summary text.
        # Phase 6's dry_run branch reports status="degraded" unconditionally before any
        # real exit logic runs, so this exact literal "DRY-RUN" summary can never
        # coexist with a genuine exit error.
        is_dry_run_stub = ps.lower() == "degraded" and "DRY-RUN" in (p.get("summary") or "")
        if is_dry_run_stub:
            sc, si = (DIM, "⊘")
        else:
            sc, si = _format_phase_badge(ps)
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
        at_raw = p.get("action_type")
        if at_raw is None:
            at_raw = ""
        at = at_raw
        if not at.startswith("phase_"):
            continue
        parts_p = at.split("_")
        num = parts_p[1] if len(parts_p) > 1 else "?"
        if not num.isdigit():
            continue
        phase_key = f"phase_{num}"
        name_parts = parts_p[2:] if len(parts_p) > 2 else []
        default_short = "_".join(name_parts)[:7] if name_parts else f"P{num}"
        # CRITICAL: Explicit key check instead of .get() fallback
        # Missing phase name in PHASE_NAMES should be logged
        if phase_key in PHASE_NAMES:
            short = PHASE_NAMES[phase_key][:8]
        else:
            if phase_key not in ("", "unknown"):
                logger.debug(f"[HEALTH] Phase '{phase_key}' not in PHASE_NAMES, using: {default_short}")
            short = default_short[:8]
        st_raw = p.get("status")
        if st_raw is None:
            st_raw = ""
        st = st_raw
        # Same benign-stub exemption as _build_phase_badges_and_metrics (see that function's
        # 2026-08-10 writeup): Phase 6's dry_run branch reports status="degraded"
        # unconditionally before any real exit logic runs, so this literal "DRY-RUN" summary
        # can never coexist with a genuine exit error. _format_phase_badge() alone can't tell
        # the two apart - it only receives the raw status string, no summary text - so this
        # audit-log-format fallback path (panel_algo_health's non-exec_log branch) rendered
        # Phase 6 as a yellow "~" halted-looking badge on every dry-run, same bug class as the
        # 4 other call sites already fixed, missed here because this is a structurally
        # separate function reached via a different data-source branch.
        is_dry_run_stub = st.lower() == "degraded" and "DRY-RUN" in (p.get("summary") or "")
        if is_dry_run_stub:
            sc, si = (DIM, "⊘")
        else:
            sc, si = _format_phase_badge(st)
        phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
    return phase_badges


__all__ = [
    "_build_loader_operational_detail_rows",
    "_build_phase_badges_and_metrics",
    "_build_phase_badges_from_audit",
    "_build_phase_execution_panel",
    "_extract_phase_metrics_from_pdata",
    "_parse_phase_data_json",
]
