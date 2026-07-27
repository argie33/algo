"""Health and orchestration panel functions."""

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

logger = logging.getLogger(__name__)

# Phase status constants to prevent shotgun surgery changes
# "skipped" (skip_if_halted=YES phases that never ran because an earlier phase halted)
# is intentionally separate from a genuine halt/warn/degraded - see SKIPPED_STATES below
# and its longer explanation next to the module-level HALTED_STATES constant.
# "blocked" (a safety guard - e.g. Phase 8's market-hours/stale-signal/pending-order guards -
# correctly preventing execution; see PhaseResult.ok in algo/orchestrator/phase_result.py,
# which treats it as a successful outcome) belongs here too: every one of these status
# buckets defaults anything unrecognized to a red ERROR badge, so before this fix a
# perfectly healthy guard block rendered identically to a genuine phase crash on the
# dashboard - exactly the false alarm this system can't afford once real money is on the line.
PHASE_SUCCESS_STATES = ("success", "completed", "ok")
PHASE_HALTED_STATES = ("halt", "halted", "warn", "degraded", "blocked")
PHASE_SKIPPED_STATES = ("skipped",)


# Phase status determination strategy (replaces long if/elif chains)
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


def _var_color(var95: float | None) -> str:
    """Choose color for VaR 95% value: red if ≥4%, yellow if ≥2%, white otherwise."""
    from ..utilities import R, Y

    if var95 is None:
        return "dim"
    if var95 >= 4:
        return R
    if var95 >= 2:
        return Y
    return "white"


def _fmt_age(r: dict[str, Any]) -> str:
    """Format age from health item dict."""
    from dashboard.data_validation import StrictValidationError, safe_float

    ah = r.get("age_hours")
    ad = r.get("age")
    if ah is not None:
        try:
            ah_f = safe_float(ah, field_name="age_hours", strict=True)
            return (
                f"{ah_f:.0f}h" if ah_f is not None and ah_f < 24 else (f"{ah_f / 24:.1f}d" if ah_f is not None else "?")
            )
        except (StrictValidationError, ValueError, TypeError):
            return "?"
    elif ad is not None:
        try:
            ad_f = safe_float(ad, None, field_name="age")
            return f"{ad_f:.1f}d"
        except (StrictValidationError, ValueError, TypeError):
            return "?"
    return "?"


def _fmt_updated(r: dict[str, Any]) -> str:
    """Format last_updated/latest timestamp from health item dict."""
    lat = r.get("last_updated")
    if lat is None:
        lat = r.get("latest")
    if lat is not None and hasattr(lat, "strftime"):
        return str(lat.strftime("%m/%d"))
    if isinstance(lat, str) and len(lat) >= 10:
        return lat[5:10]
    # CRITICAL: Explicit None check instead of OR fallback
    # Timestamp missing should not silently default to empty string
    if lat is None:
        return "-"
    return str(lat)[:5]


def _pc(v: list[Any] | int | None) -> int:
    """Count phases: convert list or int to count. Explicit: return 0 only for early-stage runs with no phase data yet."""
    if isinstance(v, list):
        return len(v)
    if isinstance(v, int):
        return v
    if v is None:
        # Early-stage runs may not have phase data yet - this is expected, not an error
        # Returning 0 here indicates "no phases recorded yet", not "data unavailable"
        # This is appropriate for initialization, not for stale/corrupted data
        return 0
    raise TypeError(
        f"[HEALTH] Phase count has invalid type {type(v).__name__} (expected list or int). Data corruption detected."
    )


if TYPE_CHECKING:
    from dashboard.panel_registry import register_panel as register_panel
else:
    try:
        from dashboard.panel_registry import register_panel
    except ImportError as e:
        logger.warning(f"Panel registry not available: {e} - panels will not auto-register")

        def register_panel(
            name: str,
            endpoint_deps: list[str],
            render_fn: Callable[..., Any] | None = None,
            optional: bool = False,
            description: str = "",
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            if render_fn is not None:
                return cast(Callable[[Callable[..., Any]], Callable[..., Any]], render_fn)

            def passthrough_decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                return fn

            return passthrough_decorator


from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float, safe_int

from ..error_boundary import has_error
from ..formatters import fmt_age, next_run_str
from ..utilities import CY, DIM, PHASE_NAMES, G, R, Y
from ._helpers import _best_halt_reason, _error_panel, _fmt_phases_halted
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
# "skipped" was previously lumped into HALTED_STATES, rendering skip_if_halted=YES phases
# (4,5,7,8 per GOVERNANCE.md's Orchestrator Phases spec) with the identical "~ HALTED"
# yellow badge as the phase that actually triggered the halt (e.g. Phase 2). That's the
# likely source of "why do so many stages show halted" confusion when only one phase
# genuinely halted and the rest were skipped as a downstream consequence - the
# orchestrator itself already emits a distinct status="skipped" (see
# algo/orchestrator/phase_executor.py), the dashboard just wasn't using the distinction.
# "blocked" (a safety guard correctly stopped execution, e.g. Phase 8's market-hours guard -
# see PhaseResult.ok) belongs in this cautionary bucket too, not ERROR_STATES: every call
# site below defaults unrecognized statuses to a red ERROR badge, so a guard working exactly
# as designed used to render identically to a genuine phase crash.
HALTED_STATES = ("halt", "halted", "warn", "degraded", "blocked")
SKIPPED_STATES = ("skipped",)
ERROR_STATES = ("error", "failed")

# Role priority ordering for health items
ROLE_ORDER = {"CRIT": 0, "IMP": 1, "NORM": 2}


def _format_phase_badge(phase_status: str | None) -> tuple[str, str]:
    """Format phase status string to (color, icon) badge tuple."""
    # Ensure phase_status is a string (handle malformed data)
    if not isinstance(phase_status, str):
        phase_status = ""

    # Normalize to lowercase for comparison
    status_lower = phase_status.lower()

    # Map status to (color, icon) tuple
    if status_lower in SUCCESS_STATES:
        return (G, "✓")
    elif status_lower in HALTED_STATES:
        return (Y, "~")
    elif status_lower in SKIPPED_STATES:
        return (DIM, "⊘")
    elif status_lower in ERROR_STATES:
        return (R, "✗")
    else:
        # Default to error state for unknown statuses
        return (R, "✗")


# Severity to color mapping
SEV_COLORS = {"critical": R, "warning": Y, "info": CY, "debug": DIM}


class HealthFormatter:
    """Format health metrics to color-coded display values."""

    @staticmethod
    def var_color(value: float | None) -> str:
        """Map VaR/VIX numeric values to Rich color style strings."""
        if value is None:
            return DIM  # Gray for unknown/missing data
        if value >= 35.0:
            return R  # Red for critical (VIX >= 35)
        elif value >= 25.0:
            return Y  # Yellow for warning (VIX 25-35)
        elif value >= 15.0:
            return CY  # Cyan for caution (VIX 15-25)
        else:
            return G  # Green for normal (VIX < 15)


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


def _build_phase_execution_panel(
    execution_health: dict[str, Any] | None,
    run: dict[str, Any] | None = None,
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

    # Build phase rows showing ALL 9 phases with expanded details
    phase_rows: list[Text | Rule] = []

    for phase_num, phase_name, _phase_key, phase_data in phases_def:
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
        phase_rows.append(Text.from_markup(phase_header))

        # NOT RUN means this specific orchestrator run's phase_results has no entry for this
        # phase (e.g. an earlier phase halted before it started). The detail rows below,
        # though, come from execution_health - a live, independent query of each phase's
        # underlying table (e.g. circuit_breaker_status) - not from this run. Without this
        # note, "Circuit Breakers NOT RUN" next to a detail line reading "Status: TRIGGERED"
        # reads as self-contradictory instead of "didn't run this time, but here's the
        # latest live reading regardless."
        if status_str == "not_run" and phase_data is not None:
            phase_rows.append(Text.from_markup("      [dim](live check, not from this run)[/]"))

        # Phase details - expand each phase with all relevant info
        if phase_data is None:
            phase_rows.append(Text.from_markup("      [dim]─ no data available[/]"))
        elif phase_num == 1:  # Data Freshness Check
            tables_validated = phase_data.get("tables_validated")
            tables_fresh = phase_data.get("tables_fresh")
            tables_stale = phase_data.get("tables_stale")
            validation_status = phase_data.get("validation_status")
            stale_tables = phase_data.get("stale_tables")

            if tables_validated is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Tables validated:[/] {tables_validated}"))
            if tables_fresh is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Tables fresh:[/] [{G}]{tables_fresh}[/]"))
            if tables_stale is not None:
                stale_color = R if tables_stale >= 3 else Y if tables_stale > 0 else G
                phase_rows.append(Text.from_markup(f"      [dim]Tables stale:[/] [{stale_color}]{tables_stale}[/]"))
            if stale_tables and isinstance(stale_tables, (list, dict)):
                if isinstance(stale_tables, list):
                    for tbl_info in stale_tables[:3]:
                        if isinstance(tbl_info, dict):
                            tbl_name = tbl_info.get("table_name", "unknown")
                            age = tbl_info.get("age", "?")
                            phase_rows.append(Text.from_markup(f"        [dim]•[/] {tbl_name} [{Y}]{age}[/]"))
                elif isinstance(stale_tables, dict):
                    for tbl_name, age_info in list(stale_tables.items())[:3]:
                        phase_rows.append(Text.from_markup(f"        [dim]•[/] {tbl_name} [{Y}]{age_info}[/]"))
            if validation_status:
                phase_rows.append(Text.from_markup(f"      [dim]Status:[/] {validation_status}"))

        elif phase_num == 2:  # Circuit Breakers
            any_triggered = phase_data.get("any_triggered", False)
            dd = phase_data.get("drawdown_pct")
            dl = phase_data.get("daily_loss_pct")
            vix = phase_data.get("vix_level")
            var95 = phase_data.get("var95")

            triggered_status = "TRIGGERED" if any_triggered else "OK"
            triggered_color = R if any_triggered else G
            phase_rows.append(Text.from_markup(f"      [dim]Status:[/] [{triggered_color}]{triggered_status}[/]"))

            if dd is not None:
                dd_color = R if dd >= 20 else Y if dd >= 10 else G
                phase_rows.append(Text.from_markup(f"      [dim]Drawdown:[/] [{dd_color}]{dd:.1f}%[/]"))
            if dl is not None:
                dl_color = R if dl >= 2 else Y if dl >= 1 else G
                phase_rows.append(Text.from_markup(f"      [dim]Daily Loss:[/] [{dl_color}]{dl:.1f}%[/]"))
            if vix is not None:
                vix_color = R if vix >= 35 else Y if vix >= 25 else CY if vix >= 15 else G
                phase_rows.append(Text.from_markup(f"      [dim]VIX:[/] [{vix_color}]{vix:.1f}[/]"))
            if var95 is not None:
                var_color = R if var95 >= 4 else Y if var95 >= 2 else G
                phase_rows.append(Text.from_markup(f"      [dim]VaR 95%:[/] [{var_color}]{var95:.2f}%[/]"))

        elif phase_num == 3:  # Position Monitor
            open_positions = phase_data.get("open_positions")
            oldest_days = phase_data.get("oldest_days")
            max_loss_pct = phase_data.get("max_loss_pct")
            total_unrealized = phase_data.get("total_unrealized_pnl")

            if open_positions is not None:
                pos_color = G if open_positions == 0 else Y if open_positions <= 5 else R
                phase_rows.append(Text.from_markup(f"      [dim]Open positions:[/] [{pos_color}]{open_positions}[/]"))
            if oldest_days is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Oldest position:[/] {oldest_days}d"))
            if max_loss_pct is not None:
                loss_color = R if max_loss_pct <= -5 else Y if max_loss_pct <= -2 else G
                phase_rows.append(Text.from_markup(f"      [dim]Max loss:[/] [{loss_color}]{max_loss_pct:.1f}%[/]"))
            if total_unrealized is not None:
                pnl_color = G if total_unrealized >= 0 else R
                phase_rows.append(Text.from_markup(f"      [dim]Total P&L:[/] [{pnl_color}]${total_unrealized:,.0f}[/]"))

        elif phase_num == 4:  # Broker Reconciliation
            sync_count = phase_data.get("sync_count")
            avg_match_pct = phase_data.get("avg_match_pct")
            errors_found = phase_data.get("errors_found")

            if sync_count is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Syncs attempted:[/] {sync_count}"))
            if avg_match_pct is not None:
                match_color = G if avg_match_pct >= 95 else Y if avg_match_pct >= 80 else R
                phase_rows.append(Text.from_markup(f"      [dim]Match rate:[/] [{match_color}]{avg_match_pct:.0f}%[/]"))
            if errors_found is not None and errors_found > 0:
                phase_rows.append(Text.from_markup(f"      [dim]Errors found:[/] [{R}]{errors_found}[/]"))

        elif phase_num == 5:  # Exposure Policy
            market_regime = phase_data.get("market_regime")
            entry_allowed = phase_data.get("entry_allowed")
            halt_active = phase_data.get("halt_active", False)
            max_new_entries = phase_data.get("max_new_entries")
            halt_reason = phase_data.get("halt_reason")

            if market_regime:
                phase_rows.append(Text.from_markup(f"      [dim]Market regime:[/] {market_regime}"))
            if entry_allowed is not None:
                entry_status = "ALLOWED" if entry_allowed else "BLOCKED"
                entry_color = G if entry_allowed else R
                phase_rows.append(Text.from_markup(f"      [dim]New entries:[/] [{entry_color}]{entry_status}[/]"))
            if max_new_entries is not None and entry_allowed:
                phase_rows.append(Text.from_markup(f"      [dim]Max slots available:[/] {max_new_entries}"))
            if halt_active:
                halt_color = R if halt_active else G
                phase_rows.append(Text.from_markup(f"      [dim]Halt status:[/] [{halt_color}]ACTIVE[/]"))
                if halt_reason:
                    phase_rows.append(Text.from_markup(f"      [dim]Reason:[/] {halt_reason[:60]}"))

        elif phase_num == 6:  # Exit Execution
            exits_executed = phase_data.get("exits_executed")
            success_rate = phase_data.get("success_rate")
            avg_profit = phase_data.get("avg_profit")
            symbols_exited = phase_data.get("symbols_exited")

            if exits_executed is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Exits executed:[/] {exits_executed}"))
            if success_rate is not None and exits_executed and exits_executed > 0:
                sr_color = G if success_rate >= 80 else Y if success_rate >= 50 else R
                phase_rows.append(Text.from_markup(f"      [dim]Success rate:[/] [{sr_color}]{success_rate:.0f}%[/]"))
            if avg_profit is not None:
                profit_color = G if avg_profit > 0 else R
                phase_rows.append(Text.from_markup(f"      [dim]Avg profit/exit:[/] [{profit_color}]${avg_profit:,.0f}[/]"))
            if symbols_exited and isinstance(symbols_exited, (list, str)):
                if isinstance(symbols_exited, str):
                    phase_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {symbols_exited[:50]}"))
                elif isinstance(symbols_exited, list):
                    phase_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {', '.join(symbols_exited[:5])}"))

        elif phase_num == 7:  # Signal Generation
            signals_generated = phase_data.get("signals_generated")
            buy_signals = phase_data.get("buy_signals")
            sell_signals = phase_data.get("sell_signals")
            avg_strength = phase_data.get("avg_strength")
            symbols_with_signals = phase_data.get("symbols_with_signals")

            if signals_generated is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Signals generated:[/] [{G}]{signals_generated}[/]"))
            if buy_signals is not None or sell_signals is not None:
                bs = buy_signals if buy_signals is not None else 0
                ss = sell_signals if sell_signals is not None else 0
                phase_rows.append(Text.from_markup(f"      [dim]Buy signals:[/] [{G}]{bs}[/] [dim]Sell signals:[/] [{Y}]{ss}[/]"))
            if avg_strength is not None:
                strength_color = G if avg_strength >= 70 else Y if avg_strength >= 50 else R
                phase_rows.append(Text.from_markup(f"      [dim]Avg strength:[/] [{strength_color}]{avg_strength:.1f}[/]"))
            if symbols_with_signals and isinstance(symbols_with_signals, (list, str)):
                if isinstance(symbols_with_signals, str):
                    phase_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {symbols_with_signals[:50]}"))
                elif isinstance(symbols_with_signals, list):
                    phase_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {', '.join(symbols_with_signals[:5])}"))

        elif phase_num == 8:  # Entry Execution
            entries_executed = phase_data.get("entries_executed")
            success_rate = phase_data.get("success_rate")
            avg_entry_price = phase_data.get("avg_entry_price")
            symbols_entered = phase_data.get("symbols_entered")

            if entries_executed is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Entries executed:[/] [{G}]{entries_executed}[/]"))
            if success_rate is not None and entries_executed and entries_executed > 0:
                sr_color = G if success_rate >= 80 else Y if success_rate >= 50 else R
                phase_rows.append(Text.from_markup(f"      [dim]Success rate:[/] [{sr_color}]{success_rate:.0f}%[/]"))
            if avg_entry_price is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Avg entry price:[/] ${avg_entry_price:,.2f}"))
            if symbols_entered and isinstance(symbols_entered, (list, str)):
                if isinstance(symbols_entered, str):
                    phase_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {symbols_entered[:50]}"))
                elif isinstance(symbols_entered, list):
                    phase_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {', '.join(symbols_entered[:5])}"))

        elif phase_num == 9:  # Portfolio Snapshot
            portfolio_value = phase_data.get("portfolio_value")
            cash_available = phase_data.get("cash_available")
            total_return_pct = phase_data.get("total_return_pct")
            latest_snapshot = phase_data.get("latest_snapshot")

            if portfolio_value is not None:
                phase_rows.append(Text.from_markup(f"      [dim]Portfolio value:[/] ${portfolio_value:,.0f}"))
            if cash_available is not None:
                cash_color = G if cash_available > 0 else R
                phase_rows.append(Text.from_markup(f"      [dim]Cash available:[/] [{cash_color}]${cash_available:,.0f}[/]"))
            if total_return_pct is not None:
                ret_color = G if total_return_pct > 0 else R
                phase_rows.append(Text.from_markup(f"      [dim]Total return:[/] [{ret_color}]{total_return_pct:.2f}%[/]"))
            if latest_snapshot:
                phase_rows.append(Text.from_markup(f"      [dim]Last snapshot:[/] {latest_snapshot[:19]}"))

        # Separator between phases
        phase_rows.append(Text(""))

    # Build summary header
    summary = f"[dim]{executed}✓  {halted}~  {errored}✗  {skipped + not_run}⊘[/]"

    # Build panel with all phases
    return Panel(
        Group(*phase_rows),
        title=f"[bold cyan]PHASE EXECUTION DETAILS[/]  {summary}",
        border_style="cyan",
        padding=(0, 1),
    )


def _format_phase_execution_health(execution_health: dict[str, Any] | None) -> list[Text]:
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
            recon_color = G if sync_count > 0 and (match_pct is None or match_pct >= 95) else Y if sync_count > 0 else DIM
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


def _build_freshness_panel(
    hlth_items: list[Any],
    ready_to_trade: bool | None,
    hlth_dict: dict[str, Any] | None = None,
    inventory: dict[str, Any] | None = None,
) -> Panel:
    """Build the standalone DATA FRESHNESS - EXPANDED panel: full table freshness detail.

    Args:
        hlth_items: Validated list of health status items
        ready_to_trade: Boolean ready state (True/False/None)
        hlth_dict: Raw health response dict, for as_of/trading_halted context (optional -
            only the caller building the full standalone expanded view has this)
        inventory: Table inventory data (/api/admin/inventory) - untracked/missing tables
            (optional - not fetched by every caller)

    Returns:
        Rich Panel with freshness table
    """
    hlth_dict = hlth_dict if hlth_dict is not None else {}
    as_of = hlth_dict.get("as_of")
    age_s = f"  [dim]{fmt_age(as_of)}[/]" if as_of else ""
    title = rf"[bold yellow]DATA FRESHNESS - EXPANDED[/]{age_s}  [dim]\[l] return[/]"

    left_rows: list[Text | Table | Layout | Rule] = []

    trading_halted = hlth_dict.get("trading_halted")
    trading_halt_reason = hlth_dict.get("trading_halt_reason")
    if trading_halted and trading_halt_reason:
        left_rows.append(Text.from_markup(f"[{Y}]→ Trading halted:[/] {trading_halt_reason}"))

    expected_date = hlth_dict.get("expected_date")
    if expected_date:
        left_rows.append(Text.from_markup(f"[dim]Expected data date:[/] {expected_date}"))

    if not hlth_items:
        msg = "⚠ Data health unavailable - loaders may not have run yet.\n"
        msg += "Check Phase 1 orchestrator status or monitor logs."
        left_rows.append(Text(msg, style="dim"))
        return Panel(
            Group(*left_rows),
            title=title,
            border_style="yellow",
            padding=(0, 1),
        )

    stale_count = sum(1 for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok")
    # BUG FIX: This used to flag ANY non-"ok" table (role CRIT/IMP/NORM alike) under the
    # "CRIT STALE" banner, even though the API already computes and attaches a "role" field
    # per table (see dashboard/fetchers_config.py). That meant known-non-critical,
    # intentionally-not-always-populated tables (e.g. equity_curve_daily, algo_untracked_positions
    # - see lambda/api/routes/algo_handlers/market.py's own comments on those two) triggered the
    # same red "CRIT STALE" alarm as an actually-critical table like price_daily, producing false
    # TRIGGERED/NOT READY-looking alarms. Filter to role == "CRIT" so the banner matches its label.
    crit_stale = [r for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok" and r.get("role") == "CRIT"]

    if crit_stale:
        # CRITICAL: Explicit None check instead of OR fallback
        # Critical table name missing should be logged, not silently fallback
        def get_crit_table_name(r: dict[str, Any]) -> str:
            tbl_val = r.get("tbl")
            if tbl_val is None:
                logger.warning(f"[HEALTH] Critical table missing 'tbl' field. Keys: {list(r.keys())}")
                return "unknown"
            return str(tbl_val)

        crit_names = "  ".join(f"[bold white]{get_crit_table_name(r)[:18]}[/]" for r in crit_stale)
        left_rows.append(Text.from_markup(f"[bold {R}]⚠ CRIT STALE:[/]  {crit_names}"))

    rtt_part = ""
    if ready_to_trade:
        rtt_part = f"  [bold {G}]✓ READY TO TRADE[/]"
    elif not ready_to_trade:
        rtt_part = f"  [bold {R}]✗ NOT READY[/]"

    status_c = G if stale_count == 0 else (Y if stale_count <= 2 else R)
    left_rows.append(
        Text.from_markup(
            f"[dim]Freshness:[/] [{status_c}]{len(hlth_items) - stale_count}/{len(hlth_items)} fresh[/]"
            + (f"  [{R}]{stale_count} stale[/]" if stale_count else "")
            + rtt_part
        )
    )

    def sort_key(r: dict[str, Any]) -> str:
        tbl = r.get("tbl")
        # CRITICAL: Explicit None check - missing table name indicates incomplete data
        if tbl is None:
            logger.warning(f"[HEALTH] Health item missing 'tbl' field. Keys: {list(r.keys())}")
            tbl_str = "unknown_table"
        else:
            tbl_str = str(tbl)
        return tbl_str

    sorted_items = sorted(
        [r for r in hlth_items if isinstance(r, dict)],
        key=sort_key,
    )

    # Build two-column table layout for better use of horizontal space
    mid = (len(sorted_items) + 1) // 2
    left_items = sorted_items[:mid]
    right_items = sorted_items[mid:]

    def build_column_table(items: list[Any]) -> Table:
        tbl = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="dim",
            padding=(0, 1),
            expand=True,
            row_styles=["", "dim"],
        )
        tbl.add_column("Table", no_wrap=True, min_width=18)
        tbl.add_column("Age", no_wrap=True, min_width=5, justify="right")
        tbl.add_column("Rows", no_wrap=True, min_width=7, justify="right")
        tbl.add_column("Status", no_wrap=True, min_width=5)

        for r in items:
            tbl_val = r.get("tbl")
            nm = str(tbl_val if tbl_val is not None else "--")
            # CRITICAL: Explicit None check - missing status indicates data quality issue
            st_raw = r.get("st")
            if st_raw is None:
                logger.warning(
                    f"[HEALTH] Health item missing 'st' (status) field - data corrupted. Table: {tbl_val}, Keys: {list(r.keys())}"
                )
                # Log as warning but use default for display (don't silently assume "ok")
                st = "unknown"
            elif not isinstance(st_raw, str):
                logger.warning(
                    f"[HEALTH] Status field has invalid type {type(st_raw).__name__} (expected str). Table: {tbl_val}."
                )
                st = "error"
            else:
                st = st_raw
            ok = st == "ok"
            ic = G if ok else (Y if st == "empty" else R)
            if st not in ("ok", "empty"):
                logger.debug(f"[HEALTH] Health item {nm} status '{st}' mapped to RED color indicator")
            ii = "✓" if ok else ("-" if st == "empty" else "✗")
            row_count = safe_int(r.get("row_count"), default=None)
            rc_s = f"{row_count:,}" if row_count is not None else "--"
            st_label = "ok" if ok else st.upper()[:3]
            tbl.add_row(
                Text.from_markup(f"[{ic}]{ii}[/] {nm}"),
                Text(_fmt_age(r), style=DIM if ok else Y),
                Text(rc_s, style="dim"),
                Text(st_label, style=G if ok else (Y if st == "empty" else R)),
            )
        return tbl

    left_tbl = build_column_table(left_items)
    right_tbl = build_column_table(right_items) if right_items else None

    # Create a two-column layout if there are enough items, otherwise use single column
    if right_tbl is not None and len(right_items) > 0:
        # Two-column layout
        two_col = Layout()
        two_col.split_row(
            Layout(left_tbl, ratio=1, name="left_col"),
            Layout(right_tbl, ratio=1, name="right_col"),
        )
        left_rows.append(two_col)
    else:
        # Single column layout
        left_rows.append(left_tbl)

    # Loader run diagnostics: why a table is stale/empty (real error) and which loaders are
    # mid-run right now. This data is written by every loader (LoaderStatusManager) but a
    # bare "STALE"/"EMPTY" badge above gives no way to tell "loader never ran" from "loader
    # is failing every day with an auth/rate-limit error" without reading raw logs.
    loader_errors = [
        (r.get("tbl") or "unknown", r.get("loader_error"), r.get("loader_run_status"))
        for r in sorted_items
        if r.get("st") != "ok" and r.get("loader_error")
    ]
    if loader_errors:
        left_rows.append(Rule(style="dim"))
        left_rows.append(Text.from_markup(f"[bold {R}]Loader errors:[/]"))
        for tbl_name, err, lrs in loader_errors[:8]:
            # TIMEOUT and FAILED both just populate error_message identically otherwise -
            # tag with the loader's own run-state enum so the two aren't indistinguishable.
            tag = f"[{lrs}] " if lrs in ("TIMEOUT", "FAILED") else ""
            left_rows.append(Text.from_markup(f"  [{R}]{tbl_name}:[/] [dim]{tag}{str(err)[:90]}[/]"))
        if len(loader_errors) > 8:
            left_rows.append(Text.from_markup(f"  [dim]...and {len(loader_errors) - 8} more[/]"))

    # Loaders that have literally never run (status row exists but no execution has ever
    # started) - distinct from "ran and produced 0 rows" (status=empty). Without this, both
    # looked identical on the freshness table (row_count=0/"--", no age), giving no signal
    # that the loader itself has never been invoked at all.
    never_started = [
        r.get("tbl") or "unknown"
        for r in sorted_items
        if r.get("st") != "ok" and r.get("loader_run_status") == "NOT_STARTED"
    ]
    if never_started:
        left_rows.append(Rule(style="dim"))
        left_rows.append(
            Text.from_markup(f"[bold {R}]Never run:[/]  " + "  ".join(f"[white]{n}[/]" for n in never_started[:10]))
        )
        if len(never_started) > 10:
            left_rows.append(Text.from_markup(f"  [dim]...and {len(never_started) - 10} more[/]"))

    in_progress = [r for r in sorted_items if r.get("execution_started") and not r.get("execution_completed")]
    if in_progress:
        left_rows.append(Rule(style="dim"))
        left_rows.append(Text.from_markup(f"[bold {Y}]Loading now:[/]"))
        for r in in_progress[:8]:
            pct = r.get("completion_pct")
            pct_s = f"{float(pct):.0f}%" if pct is not None else "?"
            sl, sc = r.get("symbols_loaded"), r.get("symbol_count")
            cnt_s = f" ({sl}/{sc} symbols)" if sl is not None and sc is not None else ""
            left_rows.append(Text.from_markup(f"  [{Y}]⟳ {r.get('tbl') or 'unknown'}:[/] {pct_s}{cnt_s}"))

    # Stale-table detail: each table's own configured cadence (stale_threshold_days), so
    # "STALE at 3 days old" (a 1-day table) reads differently from "STALE at 10 days old"
    # (a 7-day table already 3 days past its own threshold) instead of just a bare age.
    stale_detail = [
        (r.get("tbl") or "unknown", r.get("age"), r.get("stale_threshold_days"))
        for r in sorted_items
        if r.get("st") == "stale" and r.get("age") is not None and r.get("stale_threshold_days") is not None
    ]
    if stale_detail:
        left_rows.append(Rule(style="dim"))
        left_rows.append(Text.from_markup(f"[bold {Y}]Stale detail (age vs. own threshold):[/]"))
        for tbl_name, age, threshold in stale_detail[:8]:
            left_rows.append(Text.from_markup(f"  [{Y}]{tbl_name}:[/] [dim]{age}d old, threshold {threshold}d[/]"))
        if len(stale_detail) > 8:
            left_rows.append(Text.from_markup(f"  [dim]...and {len(stale_detail) - 8} more[/]"))

    # Repeated-failure streaks (migration 1163: consecutive_failures/last_success_at) - a
    # loader that failed once and one that's failed every run for a week both show up
    # identically as bare "STALE"/error text above; this distinguishes a transient blip
    # from a genuinely stuck loader, which is a very different response ("wait" vs
    # "investigate now").
    repeated_failures = [
        (r.get("tbl") or "unknown", r.get("consecutive_failures"), r.get("last_success_at"))
        for r in sorted_items
        if isinstance(r.get("consecutive_failures"), (int, float)) and r.get("consecutive_failures", 0) >= 2
    ]
    if repeated_failures:
        repeated_failures.sort(key=lambda t: t[1], reverse=True)
        left_rows.append(Rule(style="dim"))
        left_rows.append(Text.from_markup(f"[bold {R}]Repeated failures:[/]"))
        for tbl_name, n_fail, last_ok in repeated_failures[:8]:
            last_ok_s = f"last ok {fmt_age(last_ok)}" if last_ok else "never succeeded"
            left_rows.append(Text.from_markup(f"  [{R}]{tbl_name}:[/] [dim]{int(n_fail)}x in a row, {last_ok_s}[/]"))
        if len(repeated_failures) > 8:
            left_rows.append(Text.from_markup(f"  [dim]...and {len(repeated_failures) - 8} more[/]"))

    # Table inventory gaps (from /api/admin/inventory) - untracked tables exist in the DB but
    # have no data_loader_status row at all (never wired into monitoring), and missing tables
    # are tracked in data_loader_status but no longer exist (schema drift / dropped table).
    # Neither is visible anywhere else on the dashboard - the per-table list above only ever
    # shows what IS tracked.
    if inventory and isinstance(inventory, dict) and not has_error(inventory):
        untracked = inventory.get("untracked_tables")
        missing = inventory.get("missing_tables")
        if untracked:
            left_rows.append(Rule(style="dim"))
            names = "  ".join(str(n) for n in untracked[:10])
            left_rows.append(Text.from_markup(f"[bold {Y}]Untracked tables ({len(untracked)}):[/]  [dim]{names}[/]"))
            if len(untracked) > 10:
                left_rows.append(Text.from_markup(f"  [dim]...and {len(untracked) - 10} more[/]"))
        if missing:
            left_rows.append(Rule(style="dim"))
            names = "  ".join(str(n) for n in missing[:10])
            left_rows.append(
                Text.from_markup(f"[bold {R}]Tracked but missing from DB ({len(missing)}):[/]  [dim]{names}[/]")
            )
            if len(missing) > 10:
                left_rows.append(Text.from_markup(f"  [dim]...and {len(missing) - 10} more[/]"))

    return Panel(
        Group(*left_rows),
        title=title,
        border_style="yellow",
        padding=(0, 1),
    )


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
        beta_c = "dim" if (not has_positions or beta_val <= 0) else (R if beta_val >= 1.2 else (Y if beta_val >= 0.8 else G))
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


def panel_orch(
    run: dict[str, Any] | None,
    cfg: dict[str, Any],
    risk: dict[str, Any] | None = None,
    hlth: dict[str, Any] | list[Any] | None = None,
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
        if exec_health_rows:
            body_rows: list[Text | Rule] = [
                Text.from_markup(
                    f"{sts}  [dim]{age}[/]\n"
                    f"[{mc2}]{mode}[/]  [{ec}]{en}[/]\n"
                    f"[dim]{config_line}[/]\n"
                    f"[dim]Next run:[/] [white]{next_run}[/]\n"
                    f"{phases_str}" + extra + var_line
                ),
                Rule(style="dim"),
            ]
            body_rows.extend(exec_health_rows)
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


def _get_status_safe(run: dict[str, Any]) -> str:
    """Get overall_status with explicit validation (fail-fast on missing field)."""
    status = run.get("overall_status")
    if status is None:
        logger.error(
            f"[DASHBOARD] Execution history missing 'overall_status' field. "
            f"Available: {list(run.keys())}. "
            f"Cannot classify run status without explicit field."
        )
        return "unknown"
    return str(status).lower()


def _format_exec_history_summary(exec_hist: list[Any] | None) -> list[Text]:
    """Format last N runs summary (used in panel_status and panel_algo_health)."""
    rows: list[Text] = []
    valid_hist_raw = safe_get_list(exec_hist)
    # Check if marker dict (data_unavailable) was returned instead of list
    if isinstance(valid_hist_raw, dict) and valid_hist_raw.get("data_unavailable"):
        logger.warning(
            "[HEALTH_FORMAT] Execution history unavailable for summary display. "
            "Data may be empty or API returned None. Cannot show run health metrics."
        )
        return rows
    if not valid_hist_raw or not isinstance(valid_hist_raw, list):
        logger.warning(
            "[HEALTH_FORMAT] Execution history unavailable for summary display. "
            "Data may be empty or API returned None. Cannot show run health metrics."
        )
        return rows

    # Type guard: valid_hist_raw is now guaranteed to be a list
    valid_hist: list[Any] = valid_hist_raw
    n_ok = sum(1 for r in valid_hist if _get_status_safe(r) in PHASE_SUCCESS_STATES)
    # Use the same HALTED_STATES/SKIPPED_STATES buckets as _format_phase_badge() - a
    # run-level "degraded" (e.g. every DRY-RUN's Phase 6, see execution_tracker.py) or
    # "blocked"/"skipped" run used to fall into neither n_hlt nor n_err (only the exact
    # literal "halted" counted), yet still rendered as a red X badge below - a run
    # correctly handled by a guard looked identical to a genuine crash, with no matching
    # tally to explain the red mark.
    n_hlt = sum(1 for r in valid_hist if _get_status_safe(r) in HALTED_STATES)
    n_skip = sum(1 for r in valid_hist if _get_status_safe(r) in SKIPPED_STATES)
    n_err = sum(1 for r in valid_hist if _get_status_safe(r) in ERROR_STATES)
    total_h = len(valid_hist)
    if total_h == 0:
        logger.warning(
            "[HEALTH_PANEL] Win rate calculation failed: no execution history available. "
            "Cannot calculate health metrics without prior runs."
        )
        wr_h = None
    else:
        wr_h = n_ok / total_h * 100
    # DIM (not R) when unavailable, matching the same guard applied elsewhere in this file -
    # total_h==0 can't currently reach here (the empty-list early-return above already
    # catches it), but wr_h is None whenever it can't be computed, so this stays a safe
    # default rather than defaulting an unknown value to "bad" (red).
    wc_h = DIM if wr_h is None else (G if wr_h >= 80 else (Y if wr_h >= 50 else R))

    badges = []
    for r in valid_hist[:7]:
        s = _get_status_safe(r)
        color, icon = _format_phase_badge(s)
        badges.append(f"[{color}]{icon}[/]")

    rows.append(
        Text.from_markup(
            f"[dim]Last {total_h} runs:[/] {''.join(badges)}"
            f"  [{wc_h}]{n_ok}/{total_h} success[/]"
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
        # CRITICAL: Missing halt_reason when algo last halted is MISSION-CRITICAL data loss
        if lhr is None:
            logger.error(
                f"[HEALTH] CRITICAL: Last halt event missing 'halt_reason'. "
                f"Available: {list(last_halt.keys())}. "
                f"Cannot diagnose why algo last halted - critical diagnostic data lost."
            )
        lph = _fmt_phases_halted(last_halt.get("phases_halted"))
        # CRITICAL: Explicit conditional instead of OR fallback
        # Missing halt reason must be distinguished from empty phases
        if lhr:
            body = lhr
        elif lph:
            body = lph
        else:
            body = "[dim]-[/] halt reason unavailable"  # Explicit marker
        if body and body != "[dim]-[/] halt reason unavailable":
            # CRITICAL: Explicit None check instead of OR fallback
            # Only compare if both lhr and lph exist
            if lph and lhr and lph not in lhr:
                ph_s = f"  [dim]({lph})[/]"
            else:
                ph_s = ""
            rows.append(Text.from_markup(f"  [{Y}]a†³ {body[:55]}[/]{ph_s}"))
        elif body == "[dim]-[/] halt reason unavailable":
            rows.append(Text.from_markup(f"  [{Y}]a†³ {body}[/]"))

    return rows


def _format_recent_trade_events(act: dict[str, Any] | None) -> list[Text]:
    """Format recent trade events (entry/exit/order).

    Returns empty list gracefully when data unavailable or errors occur.
    Never raises - all errors handled to prevent panel crashes.
    """
    rows: list[Text] = []

    # Handle None or empty data gracefully
    if not act or not isinstance(act, dict):
        logger.debug(
            "[HEALTH_FORMAT] Activity data unavailable for trade events. "
            "No recent actions to display - algo may not have executed any trades yet."
        )
        return rows

    # Log error responses but don't raise - allows panel to render without trade rows
    if has_error(act):
        logger.debug(f"[HEALTH_FORMAT] Recent actions API error: {act.get('_error')}. Cannot format trade events.")
        return rows

    # Missing recent_actions field is normal (no recent activity)
    if "recent_actions" not in act:
        return rows
    recent = act["recent_actions"]
    if not isinstance(recent, list):
        logger.warning(
            f"[HEALTH_FORMAT] Recent actions field must be list, got {type(recent).__name__}. "
            "Skipping trade events display."
        )
        return rows

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
        at_raw = a.get("action_type")
        # CRITICAL: Missing action_type means cannot classify trade event
        if at_raw is None:
            logger.error(
                f"[HEALTH] Trade event missing 'action_type'. Keys: {list(a.keys())}. Cannot classify trade event."
            )
            continue  # Skip this event entirely - cannot render without type
        at = at_raw
        det = a.get("details")
        if isinstance(det, str):
            try:
                det = json.loads(det)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse action details JSON: {e}")
                det = None
        elif not isinstance(det, dict) and det is not None:
            det = None
        sym_raw = det.get("symbol") if det else None
        # CRITICAL: Missing symbol is critical for identifying which position was affected
        if sym_raw is None:
            logger.warning(
                f"[HEALTH] Trade event missing symbol in details. Action: {at}. Cannot identify affected position."
            )
            sym = "-"  # Explicit marker for unavailable data
        else:
            sym = sym_raw
        ic = G if ("executed" in at or at == "position_exited") else (Y if "placed" in at else R)
        lbl = at.replace("_", " ").title()[:20]
        # Show symbol availability status clearly
        sym_display = f" ({sym})" if sym != "-" else " (symbol unavailable)"
        rows.append(Text.from_markup(f"  [{ic}]{lbl}{sym_display}[/]"))

    return rows


def _format_data_health_summary(hlth_items: list[Any]) -> list[Text]:
    """Format data health section (stale tables only)."""
    rows: list[Text] = []
    if not hlth_items:
        logger.warning(
            "[HEALTH_FORMAT] Data health items unavailable for display. "
            "Cannot assess table freshness - health check may not have completed yet."
        )
        return rows

    stale = [r for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok"]
    if not stale:
        rows.append(Text.from_markup(f"[{G}]OK Data OK[/]  [dim]{len(hlth_items)} tables[/]"))
    else:
        for r in stale[:4]:
            tbl_val = r.get("tbl")
            if tbl_val is None:
                tbl_val = ""
            nm = str((tbl_val if tbl_val else "--")[:13])
            age_hours = safe_float(r.get("age_hours"), default=None)
            age_days = safe_float(r.get("age"), default=None)
            if age_hours is not None:
                age_s = f"{age_hours:.0f}h" if age_hours < 24 else f"{age_hours / 24:.1f}d"
            elif age_days is not None:
                age_s = f"{age_days:.1f}d"
            else:
                age_s = "?"
            cc = "bold white"
            lat = r.get("last_updated")
            if lat is None:
                lat = r.get("latest")
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
    try:
        valid_loader_raw = safe_get_list(loader)
    except (ValueError, TypeError) as e:
        logger.error(
            f"[LOADER_FORMAT] Loader data parsing failed: {str(e)[:100]}. "
            "Cannot validate data loader health - corrupted or missing status records."
        )
        rows.append(Text.from_markup(f"[red]Loader data error: {str(e)[:60]}[/]"))
        return rows
    if not isinstance(valid_loader_raw, list):
        logger.error(
            f"[LOADER_FORMAT] Loader status data is not a list: {type(valid_loader_raw).__name__}. "
            "Cannot display loader health - API returned invalid data structure."
        )
        rows.append(Text.from_markup("[red]Loader data unavailable (invalid format)[/]"))
        return rows
    valid_loader: list[Any] = valid_loader_raw
    if valid_loader is None:
        logger.error(
            "[LOADER_FORMAT] Loader status data is None. "
            "Cannot display loader health - status API may have failed or returned null."
        )
        rows.append(Text.from_markup("[red]Loader data unavailable (None)[/]"))
        return rows
    if len(valid_loader) == 0:
        logger.warning(
            "[LOADER_FORMAT] No loaders configured in system. "
            "Loader status display skipped - check system configuration for data feed definitions."
        )
        rows.append(Text.from_markup("[dim]No loaders configured[/]"))
        return rows

    # CRITICAL: Do NOT fallback missing status to "" - it masks broken loaders
    # Explicit validation: status must be one of known values
    unknown_status = [r for r in valid_loader if r.get("status") is None]
    if unknown_status:
        logger.error(
            f"[HEALTH] {len(unknown_status)} loaders have missing status field. "
            f"Cannot determine loader health. Available keys: {list(unknown_status[0].keys()) if unknown_status else []}"
        )
        # Mark loaders with missing status as problem loaders
        for r in unknown_status:
            r["status"] = "unknown"

    # CRITICAL: Explicit status check instead of implicit OR fallback
    # Missing status should be detected as error state, not silently bypassed
    problem_loader = [
        r
        for r in valid_loader
        if (r.get("status") is not None and r.get("status") in LOADER_STATUS_ERROR) or r.get("status") == "unknown"
    ]
    running_loader = [r for r in valid_loader if r.get("status") == LOADER_STATUS_LOADING]
    ok_count = len(valid_loader) - len(problem_loader) - len(running_loader)

    if problem_loader:
        ok_s = f"  [dim]{ok_count} ok[/]" if ok_count > 0 else ""
        display_count = min(3, len(problem_loader))
        truncation_note = f" [dim](showing {display_count}/{len(problem_loader)})[/]" if len(problem_loader) > 3 else ""
        rows.append(Text.from_markup(f"[{Y}]Loaders ({len(problem_loader)} issues){truncation_note}{ok_s}:[/]"))
        for r in problem_loader[:3]:
            table_name_val = r.get("table_name")
            if table_name_val is None:
                table_name_val = ""
            nm = str((table_name_val if table_name_val else "--")[:14])
            status_val = r.get("status")
            st = status_val if status_val is not None else "?"
            age = r.get("age_days")
            age_s = str(f"{int(age)}d" if age is not None else "--")
            sc = R if st in ("error", "failed") else Y
            error_msg_val = r.get("error_message")
            # CRITICAL: Explicit None check instead of nested ternary fallback
            # Missing error message indicates incomplete loader status record
            if error_msg_val is None:
                error_msg_val = ""
            else:
                error_msg_val = str(error_msg_val)
            err = error_msg_val[:20]
            rows.append(Text.from_markup(f"  [{sc}]{nm:<14}[/] [dim]{age_s}[/]" + (f" [dim]{err}[/]" if err else "")))
    elif valid_loader:
        if running_loader:
            for r in running_loader[:3]:
                table_name_val = r.get("table_name")
                if table_name_val is None:
                    table_name_val = ""
                # CRITICAL: Explicit value check - table_name_val already validated above
                nm = table_name_val[:12]
                pct = r.get("completion_pct")
                pct_s = f" {float(pct):.0f}%" if pct is not None else ""
                rows.append(Text.from_markup(f"[{CY}]Loading:[/][dim] {nm}{pct_s}[/]"))
        elif ok_count > 0:
            rows.append(Text.from_markup(f"[{G}]OK Loaders[/]  [dim]{ok_count} feeds healthy[/]"))

    return rows


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


def _age_h(r: dict[str, Any]) -> float | dict[str, Any]:
    """Extract age in hours from health item dict.

    Returns:
        float: Age in hours
        dict: Marker dict with data_unavailable=True if age data missing
    """
    ah = r.get("age_hours")
    if ah is not None:
        return float(ah)
    ad = r.get("age")
    if ad is not None:
        return float(ad) * 24
    logger.debug("[HEALTH] Health item missing age_hours and age fields")
    return {
        "data_unavailable": True,
        "reason": "age_data_missing",
    }


def _age_fmt_c(r: dict[str, Any]) -> str:
    """Format age with hours/days suffix."""
    h = _age_h(r)
    if h is None or isinstance(h, dict):
        return "?"
    return f"{h:.0f}h" if h < 24 else f"{h / 24:.1f}d"


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


def _format_health_data_stale_section(stale: list[Any], hlth_list: list[Any] | None) -> str:
    """Format data health when stale tables exist."""
    rtt_pfx = f"[bold {R}]✗ STALE[/]  "

    stale_parts = []
    ordered = stale
    for r in ordered[:4]:
        tbl_val = r.get("tbl")
        nm = (tbl_val if tbl_val else "--")[:16]
        cc = f"bold {R}"
        stale_parts.append(f"[{R}]✗[/][{cc}]{nm}[/] [dim]{_age_fmt_c(r)}[/]")
    return f"{rtt_pfx}" + "  ".join(stale_parts)


def _format_health_data_fresh_section(
    hlth_list: list[Any], crit: list[Any], ready_to_trade: bool | None, ages: list[float | None]
) -> str:
    """Format data health when all tables are fresh."""
    if not ready_to_trade:
        rtt_badge = f"[bold {R}]✗ NOT READY[/]"
    elif ready_to_trade:
        rtt_badge = f"[{G}]✓ READY TO TRADE[/]"
    else:
        rtt_badge = f"[{G}]✓ Data OK[/]"

    n_total = len(hlth_list)
    n_crit = len(crit)
    valid_ages = [r for r in hlth_list if _age_h(r) is not None]
    # CRITICAL: Explicit length check instead of falsy fallback
    # Missing age data should be logged, not silently hidden
    if valid_ages:
        oldest_s = f"  [dim]oldest: {_age_fmt_c(max(valid_ages, key=lambda r: cast(float, _age_h(r))))}[/]"
    else:
        oldest_s = ""
    # CRITICAL: Explicit length check instead of falsy fallback
    if n_crit:
        crit_s = f"  [dim]crit {n_crit}[/][{G}] ok[/]"
    else:
        crit_s = ""
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
        sc, si = _format_phase_badge(st)
        phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")
    return phase_badges


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
                rows.append(Text.from_markup(f"[{Y}]a†³ {prefix}{detail[:60]}[/]"))
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
            sc = (
                G
                if ps in PHASE_SUCCESS_STATES
                else (Y if ps in ("halt", "halted", "warn", "degraded", "skipped") else R)
            )
            si = (
                "✓"
                if ps in PHASE_SUCCESS_STATES
                else ("~" if ps in ("halt", "halted", "warn", "degraded", "skipped") else "✗")
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
                rows.append(Text.from_markup(f"  [{sc}]a†³ {err[:62]}[/]"))
            elif ps in ("halt", "halted") and pdata:
                halt_reason_val = pdata.get("halt_reason")
                if halt_reason_val is None:
                    halt_reason_val = ""
                reason_val = pdata.get("reason")
                if reason_val is None:
                    reason_val = ""
                reason = (halt_reason_val if halt_reason_val else (reason_val if reason_val else ""))[:55]
                if reason:
                    rows.append(Text.from_markup(f"  [{Y}]a†³ {reason}[/]"))
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

    # Data health (stale tables only)
    if hlth_items:
        rows.append(Rule(style="dim"))
        health_rows = _format_data_health_summary(hlth_items)
        rows.extend(health_rows)

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

    # Data loader status (errors/stale from data_loader_status table)
    valid_loader: list[Any] | None = None
    if loader is None:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[red]Loader status unavailable (data is None)[/]"))
    else:
        try:
            valid_loader_raw = safe_get_list(loader)
            # Type guard: convert dict (error marker) to None for consistency
            if isinstance(valid_loader_raw, dict):
                valid_loader = None
            else:
                valid_loader = valid_loader_raw
        except (ValueError, TypeError) as e:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup(f"[red]Loader data error: {str(e)[:60]}[/]"))
        if valid_loader is None:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[red]Loader data unavailable[/]"))
    if valid_loader is not None:
        problem_loader = [r for r in valid_loader if r.get("status") in ("error", "failed", "stale")]
        running_loader = [r for r in valid_loader if r.get("status") == "loading"]
        # Count loaders with missing/unknown status separately for diagnostics
        unknown_status = [r for r in valid_loader if r.get("status") is None]
        if unknown_status:
            logger.warning(f"[HEALTH] {len(unknown_status)} loaders with missing status field")
        ok_count = len(valid_loader) - len(problem_loader) - len(running_loader) - len(unknown_status)
    else:
        problem_loader = []
        running_loader = []
        ok_count = 0
    if problem_loader:
        rows.append(Rule(style="dim"))
        ok_s = f"  [dim]{ok_count} ok[/]" if ok_count > 0 else ""
        display_count = min(3, len(problem_loader))
        truncation_note = f" [dim](showing {display_count}/{len(problem_loader)})[/]" if len(problem_loader) > 3 else ""
        rows.append(Text.from_markup(f"[{Y}]Loaders ({len(problem_loader)} issues){truncation_note}{ok_s}:[/]"))
        for r in problem_loader[:3]:
            table_name_val = r.get("table_name")
            if table_name_val is None:
                table_name_val = ""
            nm = str((table_name_val if table_name_val else "--")[:14])
            status_val = r.get("status")
            st = status_val if status_val is not None else "?"
            age = r.get("age_days")
            age_s = str(f"{int(age)}d" if age is not None else "--")
            sc = R if st in ("error", "failed") else Y
            error_msg_val = r.get("error_message")
            # CRITICAL: Explicit None check instead of nested ternary fallback
            # Missing error message indicates incomplete loader status record
            if error_msg_val is None:
                error_msg_val = ""
            else:
                error_msg_val = str(error_msg_val)
            err = error_msg_val[:20]
            rows.append(Text.from_markup(f"  [{sc}]{nm:<14}[/] [dim]{age_s}[/]" + (f" [dim]{err}[/]" if err else "")))
    elif valid_loader:
        if running_loader:
            rows.append(Rule(style="dim"))
            for r in running_loader[:3]:
                table_name_val = r.get("table_name")
                if table_name_val is None:
                    table_name_val = ""
                # CRITICAL: Explicit value check - table_name_val already validated above
                nm = table_name_val[:12]
                pct = r.get("completion_pct")
                pct_s = f" {float(pct):.0f}%" if pct is not None else ""
                rows.append(Text.from_markup(f"[{CY}]Loading:[/][dim] {nm}{pct_s}[/]"))
        elif ok_count > 0:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup(f"[{G}]OK Loaders[/]  [dim]{ok_count} feeds healthy[/]"))

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
            phase_panel = _build_phase_execution_panel(execution_health, run)
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


def panel_data_freshness(hlth: dict[str, Any] | list[Any] | None) -> Panel:
    """Focused 'is our data current and complete?' panel: per-table freshness, critical
    gaps, and the orchestrator's own Phase 1 freshness gate.

    Split out of ALGO HEALTH so table-by-table staleness detail (row counts, ages, which
    loaders are behind) has its own real estate instead of competing with run/execution
    history for space in one crowded panel.
    """
    hlth_err = _error_panel("health", hlth, "DATA FRESHNESS")
    if hlth_err is not None:
        return hlth_err

    rows: list[Text | Rule | Table] = []
    hlth_dict = hlth if isinstance(hlth, dict) else {}
    hlth_items, ready_to_trade = extract_health_items(hlth if hlth is not None else {})

    as_of = hlth_dict.get("as_of")
    age_s = f"  [dim]{fmt_age(as_of)}[/]" if as_of else ""

    if not hlth_items:
        rows.append(Text("⚠ No data health info available - loaders may not have run yet.", style="yellow"))
        return Panel(
            Group(*rows),
            title=rf"[bold yellow]DATA FRESHNESS[/]{age_s}  [dim]\[l] expand[/]",
            border_style="yellow",
            padding=(0, 1),
        )

    stale = [r for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok"]
    if stale:
        rows.append(Text.from_markup(_format_health_data_stale_section(stale, hlth_items)))
    else:
        crit = [r for r in hlth_items if isinstance(r, dict) and r.get("role") == "CRIT"]
        ages_raw = [_age_h(r) for r in hlth_items if isinstance(r, dict)]
        ages: list[float | None] = [a if isinstance(a, float) else None for a in ages_raw]
        rows.append(Text.from_markup(_format_health_data_fresh_section(hlth_items, crit, ready_to_trade, ages)))

    # ready_to_trade folds BOTH data freshness AND the latest orchestrator run's halt state
    # together (see lambda/api/routes/algo_handlers/market.py::_get_data_status), so a bare
    # "NOT READY" could otherwise be mistaken for a data problem when the real cause was a
    # circuit-breaker halt unrelated to staleness. Surface the actual reason when it's known.
    trading_halted = hlth_dict.get("trading_halted")
    trading_halt_reason = hlth_dict.get("trading_halt_reason")
    if trading_halted and trading_halt_reason:
        rows.append(Text.from_markup(f"  [{Y}]→ Trading halted:[/] {str(trading_halt_reason)[:70]}"))

    summary = hlth_dict.get("summary")
    if isinstance(summary, dict) and summary:
        parts = []
        ok_n = summary.get("ok")
        stale_n = summary.get("stale")
        empty_n = summary.get("empty")
        error_n = summary.get("error")
        if ok_n:
            parts.append(f"[{G}]{ok_n} ok[/]")
        if stale_n:
            parts.append(f"[{Y}]{stale_n} stale[/]")
        if empty_n:
            parts.append(f"[{Y}]{empty_n} empty[/]")
        if error_n:
            parts.append(f"[{R}]{error_n} error[/]")
        if parts:
            rows.append(Text.from_markup("[dim]By status:[/]  " + "  ".join(parts)))

    critical_stale = hlth_dict.get("critical_stale")
    if critical_stale:
        names = "  ".join(f"[bold {R}]{n}[/]" for n in critical_stale[:5])
        rows.append(Text.from_markup(f"[{R}]⚠ CRIT STALE:[/]  {names}"))

    rows.append(Rule(style="dim"))

    # Per-table breakdown: not-ok tables first, CRIT role first within each group
    def sort_key(r: dict[str, Any]) -> tuple[int, int, str]:
        not_ok = 0 if r.get("st") != "ok" else 1
        role_val = r.get("role")
        role_rank = ROLE_ORDER.get(role_val, 3) if isinstance(role_val, str) else 3
        name = str(r.get("tbl") or "")
        return (not_ok, role_rank, name)

    sorted_items = sorted([r for r in hlth_items if isinstance(r, dict)], key=sort_key)
    shown = sorted_items[:10]

    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim",
        padding=(0, 1),
        expand=True,
        row_styles=["", "dim"],
    )
    tbl.add_column("Table", no_wrap=True, min_width=16)
    tbl.add_column("Age", no_wrap=True, justify="right", min_width=5)
    tbl.add_column("Rows", no_wrap=True, justify="right", min_width=7)
    tbl.add_column("St", no_wrap=True, min_width=4)
    for r in shown:
        nm = str(r.get("tbl") or "--")
        st = r.get("st") or "unknown"
        ok = st == "ok"
        ic = G if ok else (Y if st == "empty" else R)
        row_count = safe_int(r.get("row_count"), default=None)
        rc_s = f"{row_count:,}" if row_count is not None else "--"
        tbl.add_row(
            Text.from_markup(f"[{ic}]{'✓' if ok else ('-' if st == 'empty' else '✗')}[/] {nm}"),
            Text(_fmt_age(r), style=DIM if ok else Y),
            Text(rc_s, style="dim"),
            Text("ok" if ok else st.upper()[:3], style=ic),
        )
    rows.append(tbl)
    if len(sorted_items) > len(shown):
        rows.append(Text.from_markup(f"[dim]...and {len(sorted_items) - len(shown)} more (see expanded view)[/]"))

    # Phase 1: the orchestrator's own freshness gate result from the last run (distinct from
    # the live per-table snapshot above - this is what the run actually evaluated at Phase 1).
    execution_health = hlth_dict.get("execution_health")
    p1 = execution_health.get("phase_1_data_check") if isinstance(execution_health, dict) else None
    if p1:
        vs = p1.get("validation_status")
        vc = G if vs == "pass" else (Y if vs == "warn" else (R if vs == "fail" else DIM))
        tf = p1.get("tables_fresh")
        tv = p1.get("tables_validated")
        counts_s = f"  [dim]{tf}/{tv} fresh[/]" if tf is not None and tv is not None else ""
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[dim]Phase 1 gate:[/] [{vc}]{vs or '?'}[/]{counts_s}"))

    return Panel(
        Group(*rows),
        title=rf"[bold yellow]DATA FRESHNESS[/]{age_s}  [dim]\[l] expand[/]",
        border_style="yellow",
        padding=(0, 1),
    )


def _build_results_panel(
    run: dict[str, Any] | None,
    act: dict[str, Any] | None,
    algo_metrics: list[Any],
    exec_hist: list[Any],
    risk: dict[str, Any] | None,
    notifs: list[Any],
    hlth: dict[str, Any] | list[Any] | None = None,
) -> Panel:
    """Build RIGHT panel: execution status, run results, history, and alerts.

    Args:
        run: Run data (validated for errors)
        act: Activity data (fallback if run missing)
        algo_metrics: Today's metrics + 5d history
        exec_hist: Full run execution history
        risk: Risk metrics (VaR, beta, concentration)
        notifs: Notification items
        hlth: Health data containing execution_health

    Returns:
        Rich Panel with execution status and health
    """
    right_rows: list[Text | Rule | Panel] = [
        Text.from_markup("[dim]press [/][bold yellow]h[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    run_valid = run and isinstance(run, dict) and not has_error(run)
    act_valid = act and isinstance(act, dict) and not has_error(act)
    run_at = (
        (run.get("run_at") if isinstance(run, dict) else None)
        if run_valid
        else (act.get("run_at") if isinstance(act, dict) and act_valid else None)
    )
    age_s = f"  [dim]{fmt_age(run_at)}[/]" if run_at else ""

    if run_valid and isinstance(run, dict):
        sts = (
            f"[bold {G}]OK COMPLETED[/]"
            if run.get("success") and not run.get("halted")
            else (f"[bold {Y}]~ HALTED[/]" if run.get("halted") else f"[bold {R}]X ERROR[/]")
        )
        rid_raw = run.get("run_id")
        if rid_raw is None:
            rid_raw = ""
        rid = rid_raw
        right_rows.append(Text.from_markup(f"{sts}{age_s}  [dim]{rid}[/]"))
        halt_r = run.get("halt_reason")
        if halt_r is None:
            halt_r = ""
        summary = run.get("summary")
        if summary is None:
            summary = ""
        if run.get("halted") or halt_r:
            phase_results_val = run.get("phase_results")
            phase_results_list = phase_results_val if phase_results_val is not None else []
            for label, detail in _best_halt_reason(halt_r, phase_results_list):
                prefix = f"{label}: " if label else ""
                right_rows.append(Text.from_markup(f"  [{Y}]-> {prefix}{detail}[/]"))
        elif summary:
            right_rows.append(Text.from_markup(f"  [dim]{summary}[/]"))

    # Portfolio risk snapshot: `risk` was already fetched and passed into this panel (see
    # renderers/pipeline.py's `risk=ctx.risk`) but never read - the fullscreen ALGO HEALTH
    # view showed no VaR/CVaR/beta/concentration at all, even though the compact panel
    # shows it (see panel_algo_health's own D2 section, same root cause, fixed prior
    # session). Reuse the same formatter so both views stay consistent.
    risk_line = _extract_orch_risk_metrics_string(risk).strip()
    if risk_line:
        right_rows.append(Text.from_markup(risk_line))

    right_rows.append(Rule(style="dim"))

    # Phase execution health panel (if available)
    if hlth and isinstance(hlth, dict):
        execution_health = hlth.get("execution_health")
        phase_exec_panel = _build_phase_execution_panel(execution_health, run)
        if phase_exec_panel:
            right_rows.append(phase_exec_panel)
            right_rows.append(Rule(style="dim"))

    valid_hist_e = exec_hist if (exec_hist and not (isinstance(exec_hist, dict) and has_error(exec_hist))) else []
    if valid_hist_e:
        n_ok = sum(1 for r in valid_hist_e if _get_status_safe(r) in PHASE_SUCCESS_STATES)
        wc = G if n_ok == len(valid_hist_e) else (Y if n_ok > 0 else R)
        right_rows.append(
            Text.from_markup(f"[dim]Run history ({len(valid_hist_e)}):[/]  [{wc}]{n_ok}/{len(valid_hist_e)} success[/]")
        )
        # fetch_exec_history() requests up to 10 runs (see fetchers_external.py), but this
        # fullscreen expanded panel only ever showed the first 3 - the compact panel_algo_health
        # tile (far less screen real estate) already shows a 7-run badge summary, so the
        # dedicated expanded view showing FEWER detailed rows than the compact view's badge
        # count was an under-use of the extra space, not a deliberate design choice.
        for r in valid_hist_e[:10]:
            s = _get_status_safe(r)
            dt = r.get("started_at")
            if dt is None:
                dt_s = "-"
            elif hasattr(dt, "strftime"):
                dt_s = dt.strftime("%b %d  %I:%M %p")
            elif isinstance(dt, str):
                try:
                    from datetime import datetime as dt_cls
                    dt_obj = dt_cls.fromisoformat(dt.replace('Z', '+00:00'))
                    dt_s = dt_obj.strftime("%b %d  %I:%M %p")
                except (ValueError, AttributeError):
                    logger.debug(f"[HEALTH] Could not parse started_at timestamp: {dt}")
                    dt_s = "-"
            else:
                logger.debug(f"[HEALTH] Unexpected started_at type: {type(dt).__name__}")
                dt_s = "-"
            # Same HALTED_STATES/SKIPPED_STATES buckets as _format_phase_badge() - a run-level
            # "degraded"/"blocked"/"skipped" status (e.g. every DRY-RUN, see
            # execution_tracker.py) must not fall through to the red error styling below.
            if s in PHASE_SUCCESS_STATES:
                ic, ii = G, "v"
            elif s in HALTED_STATES:
                ic, ii = Y, "~"
            elif s in SKIPPED_STATES:
                ic, ii = DIM, "o"
            else:
                ic, ii = R, "x"
            hr = r.get("halt_reason")
            if hr is None:
                hr = ""
            lph = _fmt_phases_halted(r.get("phases_halted"))
            body = hr or lph
            # HIGH-003 FIX: Remove redundant OR fallback - hr is already guaranteed to be string
            ph_s = f"  [dim]({lph})[/]" if lph and lph not in hr else ""
            hr_s = f"  [{Y}]-> {body}[/]{ph_s}" if body else ""
            right_rows.append(Text.from_markup(f"  [{ic}]{ii}[/] [dim]{dt_s}[/]  [{ic}]{s}[/]{hr_s}"))


    valid_notifs_raw = safe_get_list(notifs)
    if isinstance(valid_notifs_raw, list) and valid_notifs_raw:
        right_rows.append(Rule(style="dim"))
        right_rows.append(Text.from_markup("[dim]Notifications:[/]"))
        # Compact panel_algo_health already shows 5 - this fullscreen panel showing only 3
        # was fewer than the compact tile despite having far more room. Bump to 10.
        for n in valid_notifs_raw[:10]:
            if not isinstance(n, dict):
                continue
            severity_val = n.get("severity")
            if severity_val is None:
                logger.warning("[RESULTS_PANEL] Notification missing severity - defaulting to 'info' for color")
                severity_val = "info"
            sc = SEV_COLORS.get(severity_val, DIM)
            if severity_val not in SEV_COLORS:
                logger.debug(
                    f"[RESULTS_PANEL] Notification severity '{severity_val}' not in SEV_COLORS - using DIM default"
                )
            title_val = n.get("title")
            if title_val is None:
                logger.warning("[RESULTS_PANEL] Notification missing title - defaulting to empty string")
                title_val = ""
            title = title_val if title_val else ""
            age = fmt_age(n.get("created_at"))
            seen_val = n.get("seen")
            if seen_val is None:
                seen_val = True
            unread = "-" if not seen_val else "."
            right_rows.append(Text.from_markup(f"  [{sc}]{unread} {title}[/] [dim]{age}[/]"))

    return Panel(
        Group(*right_rows),
        title=r"[bold yellow]ALGO HEALTH - EXPANDED[/]  [dim]\[h] return[/]",
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
) -> Panel:
    """Full-screen algo health: run outcome, phase execution detail, run history, alerts.

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
    return _build_results_panel(run, act, algo_metrics_display, exec_hist_display, risk, notifs, hlth)


def panel_data_freshness_expanded(
    hlth: dict[str, Any] | list[Any] | None,
    inventory: dict[str, Any] | None = None,
) -> Panel:
    """Full-screen data freshness: every tracked table's status, age, row count, and the
    orchestrator's Phase 1 freshness-gate result, in one place.

    Args:
        hlth: Health/data-status response (per-table freshness)
        inventory: Optional table inventory (/api/admin/inventory) - untracked/missing
            tables. Not required; panel degrades gracefully without it.
    """
    hlth_err_exp = _error_panel("health", hlth, "DATA FRESHNESS EXPANDED")
    if hlth_err_exp is not None:
        return hlth_err_exp

    hlth_dict = hlth if isinstance(hlth, dict) else {}
    hlth_items, ready_to_trade = extract_health_items(hlth if hlth is not None else {})
    return _build_freshness_panel(hlth_items, ready_to_trade, hlth_dict, inventory=inventory)


__all__ = [
    "panel_algo_health",
    "panel_algo_health_expanded",
    "panel_data_freshness",
    "panel_data_freshness_expanded",
    "panel_orch",
    "panel_status",
]
