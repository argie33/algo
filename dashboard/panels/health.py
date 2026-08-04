"""Health and orchestration panel functions."""

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from algo.config.orchestrator_config import OrchestratorConfig
from ..utilities import R, G, Y, DIM

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


def _calc_critical_tables_status(hlth_items: list[Any]) -> tuple[int, int]:
    """Calculate how many critical tables are ready vs stale.

    Returns: (ready_count, stale_count)
    """
    critical_items = [r for r in hlth_items if isinstance(r, dict) and r.get("role") == "CRIT"]
    ready = sum(1 for r in critical_items if r.get("st") == "ok")
    stale = len(critical_items) - ready
    return ready, stale


def _calc_data_completeness(hlth_items: list[Any]) -> dict[str, tuple[int, int]]:
    """Calculate data completeness by criticality (ready, total).

    Returns: {"CRIT": (8, 8), "IMP": (12, 13), "NORM": (32, 40)}
    """
    by_role = {}
    for r in hlth_items:
        if not isinstance(r, dict):
            continue
        role = r.get("role", "NORM")
        st = r.get("st")
        if role not in by_role:
            by_role[role] = {"ready": 0, "total": 0}
        by_role[role]["total"] += 1
        if st == "ok":
            by_role[role]["ready"] += 1

    return {role: (data["ready"], data["total"]) for role, data in by_role.items()}


def _calc_loader_success_rate(hlth_items: list[Any]) -> tuple[int, int, float | None]:
    """Calculate loader success rate from failures.

    Returns: (succeeded_count, total_count, success_rate_pct or None)
    """
    total = 0
    with_failure_data = 0
    total_failures = 0

    for r in hlth_items:
        if not isinstance(r, dict):
            continue
        total += 1
        n_fail_raw = r.get("consecutive_failures")
        if n_fail_raw is not None:
            with_failure_data += 1
            if isinstance(n_fail_raw, (int, float)):
                total_failures += int(n_fail_raw)

    if with_failure_data == 0:
        return total, total, None

    succeeded = total - total_failures if total > 0 else 0
    success_rate = (succeeded / total * 100) if total > 0 else 0
    return max(0, succeeded), total, success_rate


def _calc_loader_queue_depth(hlth_items: list[Any]) -> tuple[int, int]:
    """Calculate how many loaders are loading vs queued.

    Returns: (loading_count, queued_count)
    """
    loading = sum(1 for r in hlth_items if isinstance(r, dict) and r.get("execution_started") and not r.get("execution_completed"))
    # Queued = those with execution_started but for which it's taking long (this is an estimate)
    queued = 0
    return loading, queued


def _get_most_critical_issues(hlth_items: list[Any]) -> list[str]:
    """Extract top 3 most critical blocking issues.

    Returns: List of issue descriptions
    """
    issues = []
    for r in hlth_items:
        if not isinstance(r, dict):
            continue
        role = r.get("role")
        if role != "CRIT":
            continue
        st = r.get("st")
        if st != "ok":
            tbl_name = r.get("tbl", "unknown")
            if st == "stale":
                age = r.get("age")
                threshold = r.get("stale_threshold_days")
                if age is not None and threshold is not None:
                    issues.append(f"{tbl_name} stale ({age}d > {threshold}d threshold)")
                else:
                    issues.append(f"{tbl_name} stale")
            elif st == "empty":
                issues.append(f"{tbl_name} has no data")
            elif st == "error":
                err = r.get("loader_error") or "unknown error"
                issues.append(f"{tbl_name} loading failed: {err[:40]}")
            else:
                issues.append(f"{tbl_name} unavailable ({st})")

    return issues[:3]


def _build_loader_operational_detail_rows(hlth_items: list[Any] | None) -> list[Text | Rule]:
    """Loader errors, repeated failures, and never-started loaders.

    Moved here (into PHASE EXECUTION DETAILS' right column) from the DATA FRESHNESS
    panel: narrowing the phase list into its own left column freed room on the right
    for this operational detail instead of it living in a fully separate panel.
    """
    rows: list[Text | Rule] = []
    if not hlth_items:
        return rows

    loader_errors = [
        (r.get("tbl") or "unknown", r.get("loader_error"), r.get("loader_run_status"))
        for r in hlth_items
        if isinstance(r, dict) and r.get("loader_error")
    ]
    repeated_failures: list[tuple[str, int, Any]] = []
    for r in hlth_items:
        if isinstance(r, dict):
            n_fail_raw = r.get("consecutive_failures")
            if isinstance(n_fail_raw, (int, float)) and n_fail_raw >= 2:
                repeated_failures.append((r.get("tbl") or "unknown", int(n_fail_raw), r.get("last_success_at")))
    never_started = [
        r.get("tbl") or "unknown"
        for r in hlth_items
        if isinstance(r, dict) and r.get("st") != "ok" and r.get("loader_run_status") == "NOT_STARTED"
    ]

    if not (loader_errors or repeated_failures or never_started):
        return rows

    rows.append(Text.from_markup("[bold cyan]Loader Health[/]"))

    if loader_errors:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[bold {R}]Loader errors:[/]"))
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
        rows.append(Text.from_markup(f"[bold {R}]Never run:[/]  " + "  ".join(f"[white]{n}[/]" for n in never_started[:6])))
        if len(never_started) > 6:
            rows.append(Text.from_markup(f"  [dim]...and {len(never_started) - 6} more[/]"))

    return rows


def _build_phase_execution_panel(
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
            # way this system is actually observed per start_dashboard_dev.py - showed "~
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
                    dd_color = R if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_HALT_PCT else Y if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_CAUTION_PCT else G
                    target_rows.append(Text.from_markup(f"      [dim]Drawdown:[/] [{dd_color}]{dd:.1f}%[/]"))
                if dl is not None:
                    dl_color = R if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_HALT_PCT else Y if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_CAUTION_PCT else G
                    target_rows.append(Text.from_markup(f"      [dim]Daily Loss:[/] [{dl_color}]{dl:.1f}%[/]"))
                if vix is not None:
                    vix_color = R if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_EXTREME else Y if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_HIGH else CY if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_ELEVATED else G
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
                pnl_color = G if total_unrealized >= 0 else R
                target_rows.append(Text.from_markup(f"      [dim]Total P&L:[/] [{pnl_color}]${total_unrealized:,.0f}[/]"))

        elif phase_num == 4:  # Broker Reconciliation
            sync_count = safe_int(phase_data.get("sync_count"), default=None)
            avg_match_pct = safe_float(phase_data.get("avg_match_pct"), default=None)
            errors_found = safe_int(phase_data.get("errors_found"), default=None)

            if sync_count is not None:
                target_rows.append(Text.from_markup(f"      [dim]Syncs attempted:[/] {sync_count}"))
            if avg_match_pct is not None:
                match_color = G if avg_match_pct >= 95 else Y if avg_match_pct >= 80 else R
                target_rows.append(Text.from_markup(f"      [dim]Match rate:[/] [{match_color}]{avg_match_pct:.0f}%[/]"))
            if errors_found is not None and errors_found > 0:
                target_rows.append(Text.from_markup(f"      [dim]Errors found:[/] [{R}]{errors_found}[/]"))

        elif phase_num == 5:  # Exposure Policy
            required_keys: set[str] = {"market_regime", "entry_allowed", "halt_active", "max_new_entries", "halt_reason"}
            missing = required_keys - set(phase_data.keys() if phase_data else [])
            if missing:
                target_rows.append(Text.from_markup(f"      [dim]ERROR:[/] [{R}]Incomplete data - missing {', '.join(sorted(missing))}[/]"))
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
                target_rows.append(Text.from_markup(f"      [dim]Avg profit/exit:[/] [{profit_color}]${avg_profit:,.0f}[/]"))
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
                target_rows.append(Text.from_markup(f"      [dim]Buy signals:[/] [{G}]{bs}[/] [dim]Sell signals:[/] [{Y}]{ss}[/]"))
            if avg_strength is not None:
                strength_color = G if avg_strength >= 70 else Y if avg_strength >= 50 else R
                target_rows.append(Text.from_markup(f"      [dim]Avg strength:[/] [{strength_color}]{avg_strength:.1f}[/]"))
            if symbols_with_signals and isinstance(symbols_with_signals, (list, str)):
                if isinstance(symbols_with_signals, str):
                    target_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {symbols_with_signals[:50]}"))
                elif isinstance(symbols_with_signals, list):
                    target_rows.append(Text.from_markup(f"      [dim]Symbols:[/] {', '.join(symbols_with_signals[:5])}"))

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
                target_rows.append(Text.from_markup(f"      [dim]Cash available:[/] [{cash_color}]${cash_available:,.0f}[/]"))
            if total_return_pct is not None:
                ret_color = G if total_return_pct > 0 else R
                target_rows.append(Text.from_markup(f"      [dim]Total return:[/] [{ret_color}]{total_return_pct:.2f}%[/]"))
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


def _build_data_quality_section(hlth_items: list[Any]) -> list[Text | Rule]:
    """Build data quality issues section showing NULLs, duplicates, constraint violations.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    quality_issues = []
    for r in hlth_items:
        if isinstance(r, dict):
            issues = r.get("data_quality_issues", [])
            if issues:
                quality_issues.append((r.get("tbl") or "unknown", issues, r.get("quality_status")))

    if not quality_issues:
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {R}]Data Quality Issues:[/]"))

    for tbl_name, issues, quality_status in quality_issues[:8]:
        status_color = R if quality_status == "error" else Y if quality_status == "warning" else G
        for issue in issues:
            rows.append(Text.from_markup(f"  [{status_color}]{tbl_name}:[/] [dim]{issue[:80]}[/]"))

    if len(quality_issues) > 8:
        rows.append(Text.from_markup(f"  [dim]...and {len(quality_issues) - 8} more tables with issues[/]"))

    return rows


def _build_coverage_section(hlth_items: list[Any]) -> list[Text | Rule]:
    """Build coverage completeness section showing symbol/date/sector gaps.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    coverage_gaps = []
    for r in hlth_items:
        if isinstance(r, dict):
            coverage_pct = r.get("symbol_coverage_pct")
            if coverage_pct is not None and coverage_pct < 100:
                coverage_gaps.append((
                    r.get("tbl") or "unknown",
                    coverage_pct,
                    r.get("missing_symbols", []),
                    r.get("coverage_status")
                ))

    if not coverage_gaps:
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {Y}]Coverage Gaps:[/]"))

    for tbl_name, coverage_pct, missing_syms, status in coverage_gaps[:8]:
        status_color = R if status == "sparse" else Y if status == "partial" else G
        coverage_str = f"{coverage_pct:.1f}% coverage"
        missing_str = f" (missing: {', '.join(missing_syms)})" if missing_syms else ""
        rows.append(
            Text.from_markup(
                f"  [{status_color}]{tbl_name}:[/] [dim]{coverage_str}{missing_str}[/]"
            )
        )

    if len(coverage_gaps) > 8:
        rows.append(Text.from_markup(f"  [dim]...and {len(coverage_gaps) - 8} more tables[/]"))

    return rows


def _build_failure_pattern_section(hlth_items: list[Any]) -> list[Text | Rule]:
    """Build failure pattern analysis section.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    failure_data = []
    for r in hlth_items:
        if isinstance(r, dict):
            failure_rate = r.get("failure_rate_30d")
            if failure_rate is not None and failure_rate > 0:
                failure_data.append((
                    r.get("tbl") or "unknown",
                    failure_rate,
                    r.get("failure_pattern"),
                    r.get("mttr_hours"),
                    r.get("recovery_trend"),
                    r.get("last_5_runs")
                ))

    if not failure_data:
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {Y}]Failure Patterns (30-day):[/]"))

    for tbl_name, rate, pattern, mttr, trend, last_5 in failure_data[:6]:
        rate_color = R if rate > 20 else Y if rate > 5 else G
        lines = [f"  [{rate_color}]{tbl_name}:[/] {rate:.1f}% failures"]

        if pattern:
            lines.append(f"    [dim]Pattern: {pattern}[/]")
        if mttr:
            lines.append(f"    [dim]MTTR: {mttr}h[/]")
        if last_5:
            lines.append(f"    [dim]Last 5: {last_5}[/]")
        if trend:
            trend_color = G if trend == "improving" else R if trend == "degrading" else Y
            lines.append(f"    [dim]Trend: [{trend_color}]{trend}[/][/]")

        for line in lines:
            rows.append(Text.from_markup(line))

    if len(failure_data) > 6:
        rows.append(Text.from_markup(f"  [dim]...and {len(failure_data) - 6} more tables[/]"))

    return rows


def _build_api_diagnostics_section(hlth_items: list[Any]) -> list[Text | Rule]:
    """Build API diagnostics section for rate limits and retry strategy.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    api_issues = []
    for r in hlth_items:
        if isinstance(r, dict):
            api_status = r.get("api_status")
            if api_status and api_status != "ok":
                api_issues.append((
                    r.get("tbl") or "unknown",
                    api_status,
                    r.get("rate_limit_quota"),
                    r.get("retry_strategy")
                ))

    if not api_issues:
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {Y}]API Diagnostics:[/]"))

    for tbl_name, status, quota, strategy in api_issues[:6]:
        status_color = R if status == "auth_failed" else Y if status == "rate_limited" else R
        status_label = status.replace("_", " ").title()
        lines = [f"  [{status_color}]{tbl_name}:[/] {status_label}"]

        if quota:
            lines.append(f"    [dim]Quota: {quota}[/]")
        if strategy:
            lines.append(f"    [dim]Action: {strategy}[/]")

        for line in lines:
            rows.append(Text.from_markup(line))

    if len(api_issues) > 6:
        rows.append(Text.from_markup(f"  [dim]...and {len(api_issues) - 6} more[/]"))

    return rows


def _build_data_coverage_section(data_coverage: dict[str, Any] | None) -> list[Text | Rule]:
    """Build data-quality coverage section from /api/data-coverage.

    Distinct from the per-table symbol coverage already shown elsewhere in this panel
    (which only covers 4 hardcoded tables via row-presence at the latest date): this
    surfaces column-level validity (zero-volume/invalid-price rows in price_daily,
    per-indicator null rates in technical_data_daily) and two tables never covered at
    all (market_health_daily, economic_data) - see dashboard/fetchers_config.py's
    fetch_data_coverage() and lambda/api/routes/data_coverage.py.

    Returns [] when data_coverage is unavailable or every check came back clean - this
    is a supplementary detail section, not a primary health indicator, so it stays quiet
    unless there's something to flag.
    """
    rows: list[Text | Rule] = []
    if not data_coverage or not isinstance(data_coverage, dict):
        return rows

    issues: list[str] = []

    price = data_coverage.get("price_data")
    if isinstance(price, dict):
        dq = price.get("data_quality") or {}
        zero_vol = dq.get("zero_volume_pct")
        invalid_px = dq.get("invalid_price_pct")
        if isinstance(zero_vol, (int, float)) and zero_vol > 1:
            issues.append(f"[{Y}]price_daily:[/] [dim]{zero_vol:.1f}% zero/null volume (7d window)[/]")
        if isinstance(invalid_px, (int, float)) and invalid_px > 0:
            issues.append(f"[{R}]price_daily:[/] [dim]{invalid_px:.2f}% rows with close<=0 (7d window)[/]")

    technical = data_coverage.get("technical_data")
    if isinstance(technical, dict):
        ind = technical.get("indicator_coverage") or {}
        min_cov = ind.get("min_coverage_pct")
        if isinstance(min_cov, (int, float)) and min_cov < 95:
            worst = min(
                (("rsi", ind.get("rsi_pct")), ("ema_12", ind.get("ema50_pct")), ("atr", ind.get("atr_pct"))),
                key=lambda t: t[1] if isinstance(t[1], (int, float)) else 100,
            )
            issues.append(
                f"[{Y}]technical_data_daily:[/] [dim]{worst[0]} only {worst[1]:.1f}% populated (7d window)[/]"
            )

    market = data_coverage.get("market_data")
    if isinstance(market, dict):
        mh = market.get("market_health") or {}
        econ = market.get("economic_data") or {}
        if mh.get("status") == "missing":
            issues.append(f"[{R}]market_health_daily:[/] [dim]no rows in last 7 days[/]")
        if econ.get("status") == "missing":
            issues.append(f"[{R}]economic_data:[/] [dim]no FRED series updated in last 30 days[/]")

    if not issues:
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {Y}]Data Coverage (column-level, 7d):[/]"))
    for line in issues[:8]:
        rows.append(Text.from_markup(f"  {line}"))

    return rows


def _build_system_status_section(
    hlth_dict: dict[str, Any] | None, signal_freshness: dict[str, Any] | None = None
) -> list[Text | Rule]:
    """Build system status section showing signal freshness.

    Args:
        hlth_dict: Raw /api/algo/data-status response. Never carries "signal_freshness"
            itself (that field only exists on /api/health) - kept as a fallback lookup
            only in case a future caller merges it in directly.
        signal_freshness: /api/health's "freshness" block ({status, signal_age_hours}),
            fetched separately via fetch_signal_freshness() and passed through
            panel_data_freshness_expanded(). None if that fetch failed/is unavailable.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    if not hlth_dict or not isinstance(hlth_dict, dict):
        hlth_dict = {}

    system_issues = []

    # Check for signal freshness info
    resolved_freshness = signal_freshness if isinstance(signal_freshness, dict) else hlth_dict.get("signal_freshness")
    if resolved_freshness and isinstance(resolved_freshness, dict):
        freshness_status = resolved_freshness.get("status")
        signal_age_hours = resolved_freshness.get("signal_age_hours")
        if freshness_status == "STALE":
            system_issues.append(
                f"[bold {R}]Signal Freshness:[/] [dim]STALE ({signal_age_hours}h old)[/]"
            )
        elif freshness_status == "OK" and signal_age_hours and signal_age_hours > 12:
            system_issues.append(
                f"[bold {Y}]Signal Freshness:[/] [dim]OK but aging ({signal_age_hours}h old)[/]"
            )

    # A "degraded mode" (0.5x position-size multiplier) branch used to live here, reading
    # hlth_dict.get("degraded_mode_active"). Removed 2026-08-03: git-archaeology confirmed
    # the underlying feature (algo/algo_filter_pipeline.py's FilterPipeline(degraded=...))
    # was deleted in 183592aab (2026-06-09), and its DynamoDB remnant
    # (dynamo_health.get_phase1_degraded_mode_status(), key "degraded_mode_active") is
    # unreachable dead code on both ends - the write side (orchestrator.py) can never write
    # True since phase1_data_freshness.py stopped returning status="degraded" in 837c3172a,
    # and the read side has zero callers anywhere in the repo. Not reimplemented here since
    # changing position-sizing behavior is a trading-logic decision, not a dashboard fix.

    if system_issues:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[bold {Y}]System Status:[/]"))
        for issue in system_issues:
            rows.append(Text.from_markup(f"  {issue}"))

    return rows


def _build_freshness_panel(
    hlth_items: list[Any],
    ready_to_trade: bool | None,
    hlth_dict: dict[str, Any] | None = None,
    inventory: dict[str, Any] | None = None,
    data_coverage: dict[str, Any] | None = None,
    signal_freshness: dict[str, Any] | None = None,
) -> Group:
    """Build the DATA FRESHNESS - EXPANDED content: full table freshness detail.

    Args:
        hlth_items: Validated list of health status items
        ready_to_trade: Boolean ready state (True/False/None)
        hlth_dict: Raw health response dict, for as_of/trading_halted context (optional -
            only the caller building the full standalone expanded view has this)
        inventory: Table inventory data (/api/admin/inventory) - untracked/missing tables
            (optional - not fetched by every caller)
        data_coverage: /api/data-coverage response (optional) - price zero-volume/invalid-
            price %, per-indicator (rsi/ema/atr) null rates, market_health/economic_data
            presence. Distinct from the per-table symbol coverage already shown below,
            which only covers 4 hardcoded tables and never checks column-level validity.
        signal_freshness: /api/health's "freshness" block (optional) - see
            _build_system_status_section for why this can't come from hlth_dict.

    Returns:
        Rich renderable (Group) with the freshness table content, unwrapped - the caller
        is responsible for the outer Panel/title, since this content is also embedded
        inline inside panel_data_freshness_expanded's combined orchestrator+freshness
        panel and must not carry its own nested border/title there.
    """
    hlth_dict = hlth_dict if hlth_dict is not None else {}

    left_rows: list[Text | Table | Layout | Rule] = []

    # System status section (signal freshness, degraded mode)
    system_status = _build_system_status_section(hlth_dict, signal_freshness)
    left_rows.extend(system_status)

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
        return Group(*left_rows)

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

    # CRITICAL NEW: Loader error count summary (NEW FIX for error count propagation)
    # This shows infrastructure health independent of data staleness
    loader_errors_count = 0
    total_loader_failures = 0
    if hlth_dict and isinstance(hlth_dict, dict):
        summary_data = hlth_dict.get("summary")
        if isinstance(summary_data, dict):
            loader_errors_count = summary_data.get("loaders_with_errors", 0)
            total_loader_failures = summary_data.get("total_loader_failures", 0)

    rtt_part = ""
    if ready_to_trade:
        rtt_part = f"  [bold {G}]✓ READY TO TRADE[/]"
    elif not ready_to_trade:
        rtt_part = f"  [bold {R}]✗ NOT READY[/]"

    status_c = G if stale_count == 0 else (Y if stale_count <= 2 else R)
    freshness_line = (
        f"[dim]Freshness:[/] [{status_c}]{len(hlth_items) - stale_count}/{len(hlth_items)} fresh[/]"
        + (f"  [{R}]{stale_count} stale[/]" if stale_count else "")
    )

    # Add loader error info if there are any
    if loader_errors_count > 0:
        error_color = R if loader_errors_count >= 3 else Y
        freshness_line += f"  [{error_color}]{loader_errors_count} loader(s) with errors ({total_loader_failures} total)[/]"

    freshness_line += rtt_part
    left_rows.append(Text.from_markup(freshness_line))

    # NOTE: loader errors / repeated failures / never-started loaders are NOT itemized
    # here - that exact data is already itemized below (see the "Loader errors:"/
    # "Never run:"/"Repeated failures:" blocks after the per-table grid), with more
    # detail (retry counts, last-success age). Rendering it twice above the fold used to
    # push the actual per-table freshness grid - this panel's primary content - dozens of
    # lines down the screen for no new information.

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
        tbl.add_column("Duration", no_wrap=True, min_width=7, justify="right")
        tbl.add_column("Last Success", no_wrap=True, min_width=10, justify="right")
        tbl.add_column("Fails", no_wrap=True, min_width=4, justify="right")
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

            # Execution duration + throughput display, folded into one cell to avoid adding
            # a 7th column to an already-tight two-column layout.
            duration = r.get("execution_duration_sec")
            throughput = r.get("symbols_per_second")
            if duration is not None and duration > 0:
                duration_s = f"{duration:.0f}s"
                if throughput is not None and throughput > 0:
                    duration_s += f" ({throughput:.0f}/s)"
            else:
                duration_s = "--"

            # Last success display - when this loader last successfully completed
            last_success = r.get("last_success_at")
            if last_success is None:
                last_success_s = "never"
            elif hasattr(last_success, "strftime"):
                try:
                    last_success_s = last_success.strftime("%m/%d")
                except (AttributeError, TypeError):
                    last_success_s = "--"
            elif isinstance(last_success, str) and len(last_success) >= 10:
                last_success_s = last_success[5:10]
            else:
                last_success_s = "--"

            st_label = "ok" if ok else st.upper()[:3]

            # Consecutive-failure count as its own always-visible column - previously this
            # only showed up in a separate "Repeated failures" list further down the panel,
            # so a table with a fresh "ok" status (e.g. it succeeded again after failing all
            # day) gave zero indication in its own row that the loader had been failing
            # repeatedly. Surfacing it here means the loader's operational health and the
            # table's data freshness are both visible on the same row, instead of one
            # masking the other.
            cons_fail = r.get("consecutive_failures")
            cons_fail_n = cons_fail if isinstance(cons_fail, (int, float)) and cons_fail > 0 else None
            fails_s = str(int(cons_fail_n)) if cons_fail_n is not None else "-"

            tbl.add_row(
                Text.from_markup(f"[{ic}]{ii}[/] {nm}"),
                Text(_fmt_age(r), style=DIM if ok else Y),
                Text(rc_s, style="dim"),
                Text(duration_s, style="dim"),
                Text(last_success_s, style="dim"),
                Text(fails_s, style=R if cons_fail_n else "dim"),
                Text(st_label, style=G if ok else (Y if st == "empty" else R)),
            )
        return tbl

    left_tbl = build_column_table(left_items)
    right_tbl = build_column_table(right_items) if right_items else None

    # Two tables side by side via a Table.grid, not Layout: a Layout region always
    # stretches to fill its ENTIRE allotted height (this panel renders inside a
    # full-screen Live(screen=True) content region), so a 10-row table padded out to the
    # terminal's ~40-50 available lines pushed everything below it - loader errors, stale
    # detail, data quality/coverage/failure-pattern/API-diagnostics sections, inventory
    # gaps - down by that same amount, cropping much of it off-screen (Rich Layout
    # regions crop rather than scroll). A grid row sizes to its content's natural height
    # instead, while still splitting the two tables' width evenly like the old ratio=1/
    # ratio=1 Layout split did.
    if right_tbl is not None and len(right_items) > 0:
        grid = Table.grid(expand=True, padding=(0, 1, 0, 0))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(left_tbl, right_tbl)
        left_rows.append(grid)
    else:
        left_rows.append(left_tbl)

    # Loader run diagnostics: why a table is stale/empty (real error) and which loaders are
    # mid-run right now. This data is written by every loader (LoaderStatusManager) but a
    # bare "STALE"/"EMPTY" badge above gives no way to tell "loader never ran" from "loader
    # is failing every day with an auth/rate-limit error" without reading raw logs.
    # CRITICAL FIX 2026-08-03: previously gated on `st != "ok"`, so a table with a genuinely
    # fresh "ok" status (its last SUCCESSFUL run met the freshness window) still hid its own
    # error_message/loader_run_status even when other recent runs had been failing - the
    # freshness verdict and the loader's operational health are different signals (see the
    # last_success_at fix in lambda/api/routes/algo_handlers/market.py's _get_data_status);
    # a table can be "ok" and still have a real, current loader_error worth showing.
    loader_errors = [
        (r.get("tbl") or "unknown", r.get("loader_error"), r.get("loader_run_status"))
        for r in sorted_items
        if r.get("loader_error")
    ]
    if loader_errors:
        left_rows.append(Rule(style="dim"))
        left_rows.append(Text.from_markup(f"[bold {R}]Loader errors:[/]"))
        errs_by_name = {r.get("tbl"): r for r in sorted_items}
        for tbl_name, err, lrs in loader_errors[:8]:
            # TIMEOUT and FAILED both just populate error_message identically otherwise -
            # tag with the loader's own run-state enum so the two aren't indistinguishable.
            tag = f"[{lrs}] " if lrs in ("TIMEOUT", "FAILED") else ""
            retries = errs_by_name.get(tbl_name, {}).get("retry_count")
            retry_s = f" ({retries}x retried)" if isinstance(retries, (int, float)) and retries > 0 else ""
            left_rows.append(Text.from_markup(f"  [{R}]{tbl_name}:[/] [dim]{tag}{str(err)[:90]}{retry_s}[/]"))
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
            # Elapsed runtime + a heuristic timeout-risk flag. LOADER_TIMEOUT_MINUTES
            # (loaders/runner.py) defaults to 120min; flag past 90min (75% of default) since
            # the dashboard has no per-process visibility into the actual configured value.
            started_raw = r.get("execution_started")
            elapsed_s = fmt_age(started_raw)
            elapsed_label = elapsed_s.replace(" ago", "") if elapsed_s != "--" else "?"
            risk_s = ""
            try:
                ts = started_raw
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                if isinstance(ts, datetime):
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    elapsed_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
                    if elapsed_min > 90:
                        risk_s = f" [{R}]⚠ TIMEOUT RISK[/]"
            except (TypeError, ValueError):
                pass
            left_rows.append(
                Text.from_markup(f"  [{Y}]⟳ {r.get('tbl') or 'unknown'}:[/] {pct_s}{cnt_s} [dim]running {elapsed_label}[/]{risk_s}")
            )

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
    repeated_failures: list[tuple[str, int, Any]] = []
    for r in sorted_items:
        n_fail_raw = r.get("consecutive_failures")
        if isinstance(n_fail_raw, (int, float)) and n_fail_raw >= 2:
            repeated_failures.append((r.get("tbl") or "unknown", int(n_fail_raw), r.get("last_success_at")))
    if repeated_failures:
        repeated_failures.sort(key=lambda t: t[1], reverse=True)
        left_rows.append(Rule(style="dim"))
        left_rows.append(Text.from_markup(f"[bold {R}]Repeated failures:[/]"))
        for tbl_name, n_fail, last_ok in repeated_failures[:8]:
            last_ok_s = f"last ok {fmt_age(last_ok)}" if last_ok else "never succeeded"
            left_rows.append(Text.from_markup(f"  [{R}]{tbl_name}:[/] [dim]{n_fail}x in a row, {last_ok_s}[/]"))
        if len(repeated_failures) > 8:
            left_rows.append(Text.from_markup(f"  [dim]...and {len(repeated_failures) - 8} more[/]"))

    # Row-count stall detector: a loader reporting normal runs (fresh timestamp, no error)
    # while row_count hasn't moved across its last 3+ archived runs, spanning 24h+ - a
    # silent-failure mode invisible to every other section above, since nothing here looks
    # "stale" or "erroring". See dashboard/freshness_enhancements.py::_check_row_count_stall.
    stalled = [
        (r.get("tbl") or "unknown", r.get("row_count_stalled_since"))
        for r in sorted_items
        if r.get("row_count_stalled") is True
    ]
    if stalled:
        left_rows.append(Rule(style="dim"))
        left_rows.append(Text.from_markup(f"[bold {Y}]Row count stalled (reports OK, data unchanged):[/]"))
        for tbl_name, since in stalled[:8]:
            since_s = f" since {fmt_age(since)}" if since else ""
            left_rows.append(Text.from_markup(f"  [{Y}]{tbl_name}:[/] [dim]same row count across last 3+ runs{since_s}[/]"))
        if len(stalled) > 8:
            left_rows.append(Text.from_markup(f"  [dim]...and {len(stalled) - 8} more[/]"))

    # ── DATA QUALITY METRICS (NEW) ──────────────────────────────
    # Display NULLs, duplicates, and constraint violations that make data unusable
    quality_section = _build_data_quality_section(sorted_items)
    left_rows.extend(quality_section)

    # ── COVERAGE COMPLETENESS (NEW) ──────────────────────────────
    # Show missing symbols, dates, sectors that create blind spots
    coverage_section = _build_coverage_section(sorted_items)
    left_rows.extend(coverage_section)

    # ── FAILURE PATTERN ANALYSIS (NEW) ───────────────────────────
    # Distinguish transient failures from systemic issues with pattern detection
    failure_section = _build_failure_pattern_section(sorted_items)
    left_rows.extend(failure_section)

    # ── API DIAGNOSTICS (NEW) ────────────────────────────────────
    # Show rate limits, auth issues, retry strategies for clear action items
    api_section = _build_api_diagnostics_section(sorted_items)
    left_rows.extend(api_section)

    # ── DATA COVERAGE (NEW, /api/data-coverage) ──────────────────
    # Column-level validity (zero-volume/invalid-price, per-indicator null rates) and
    # market_health_daily/economic_data presence - none of which the sections above cover.
    coverage_detail_section = _build_data_coverage_section(data_coverage)
    left_rows.extend(coverage_detail_section)

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

    return Group(*left_rows)


def _build_run_history_section(run_history: list[Any] | None) -> list[Text | Rule]:
    """Build run history timeline section showing last N orchestrator runs.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    if not run_history or not isinstance(run_history, list):
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {CY}]Run History (Last {len(run_history)} Runs):[/]"))

    for run in run_history[:15]:
        if not isinstance(run, dict):
            continue

        run_id = run.get("run_id", "unknown")
        status = run.get("status", "unknown").lower()
        started_at = run.get("started_at")
        completed_at = run.get("completed_at")
        halt_reason = run.get("halt_reason")

        # Format status with color and icon
        if status in ("success", "ok"):
            status_icon = "[bold green]✓[/]"
            status_text = "OK"
            status_color = G
        elif status in ("halt", "halted"):
            status_icon = "[bold yellow]~[/]"
            status_text = "HALTED"
            status_color = Y
        elif status == "degraded":
            status_icon = "[dim]⊘[/]"
            status_text = "DEGRADED"
            status_color = Y
        else:
            status_icon = "[bold red]✗[/]"
            status_text = "ERROR"
            status_color = R

        # Phase summary
        phase_summary = run.get("phase_summary", {})
        phases_str = f"[{status_color}]{phase_summary.get('completed', 0)}✓[/]"
        if phase_summary.get("halted", 0) > 0:
            phases_str += f" [{Y}]{phase_summary.get('halted')}~[/]"
        if phase_summary.get("errored", 0) > 0:
            phases_str += f" [{R}]{phase_summary.get('errored')}✗[/]"

        # Format time info
        time_str = ""
        if started_at:
            try:
                if hasattr(started_at, "strftime"):
                    time_str = started_at.strftime("%m/%d %H:%M:%S")
                elif isinstance(started_at, str) and len(started_at) >= 19:
                    time_str = started_at[5:10] + " " + started_at[11:19]
            except (AttributeError, TypeError):
                pass

        # Duration
        duration_str = ""
        if started_at and completed_at:
            try:
                from datetime import datetime as dt

                if isinstance(started_at, str):
                    start_dt = dt.fromisoformat(started_at)
                else:
                    start_dt = started_at
                if isinstance(completed_at, str):
                    end_dt = dt.fromisoformat(completed_at)
                else:
                    end_dt = completed_at
                duration = (end_dt - start_dt).total_seconds()
                duration_str = f" [{DIM}]{duration:.1f}s[/]"
            except (AttributeError, TypeError, ValueError):
                pass

        # Build line
        line = f"  {status_icon} [{status_color}]{status_text}[/] {phases_str}{duration_str} [dim]{time_str}[/]"
        if halt_reason and status in ("halt", "halted"):
            line += f" [yellow]← {halt_reason[:40]}[/]"

        rows.append(Text.from_markup(line))

    return rows


def _build_phase_health_section(phase_health: dict[str, Any] | None) -> list[Text | Rule]:
    """Build phase-level health breakdown showing success rates for all 9 phases.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    if not phase_health or not isinstance(phase_health, dict):
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {CY}]Phase Health (30-Day Success Rates):[/]"))

    phase_names = {
        "1": "Data Freshness",
        "2": "Circuit Breakers",
        "3": "Position Monitor",
        "4": "Reconciliation",
        "5": "Exposure Policy",
        "6": "Exit Execution",
        "7": "Signal Generation",
        "8": "Entry Execution",
        "9": "Portfolio Snapshot",
    }

    for phase_num in ["1", "2", "3", "4", "5", "6", "7", "8", "9"]:
        phase_data = phase_health.get(phase_num)
        if not phase_data:
            continue

        total_runs = phase_data.get("total_runs", 0)
        success_rate = phase_data.get("success_rate", 0)

        # Color based on success rate
        if success_rate >= 95:
            rate_color = G
            rate_icon = "✓"
        elif success_rate >= 80:
            rate_color = CY
            rate_icon = "~"
        else:
            rate_color = R
            rate_icon = "✗"

        phase_name = phase_names.get(phase_num, f"Phase {phase_num}")
        line = (
            f"  {rate_icon} P{phase_num} [{rate_color}]{success_rate:.0f}%[/] "
            f"[dim]({total_runs} runs)[/] {phase_name}"
        )
        rows.append(Text.from_markup(line))

    return rows


def _build_halt_reason_pattern_section(failure_patterns: list[Any] | None) -> list[Text | Rule]:
    """Build failure pattern section showing most common halt reasons.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    if not failure_patterns or not isinstance(failure_patterns, list):
        return rows

    failure_patterns_list = [f for f in failure_patterns if isinstance(f, dict) and f.get("reason")]
    if not failure_patterns_list:
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {Y}]Failure Patterns (30-Day Top Reasons):[/]"))

    for i, pattern in enumerate(failure_patterns_list[:8], 1):
        reason = pattern.get("reason", "unknown")
        occurrences = pattern.get("occurrences", 0)

        # Highlight frequently recurring failures
        if occurrences >= 5:
            color = R
            icon = "!"
        elif occurrences >= 3:
            color = Y
            icon = "•"
        else:
            color = DIM
            icon = "◦"

        line = f"  [{color}]{icon}[/] [{color}]{occurrences}x[/] [dim]{reason[:70]}[/]"
        rows.append(Text.from_markup(line))

    return rows


def _build_loader_health_section(
    loader_health: list[Any] | None,
    total_unhealthy: int | None = None,
    total_tracked: int | None = None,
) -> list[Text | Rule]:
    """Build loader reliability section showing tables with failure streaks.

    Args:
        loader_health: Unhealthy-loader rows from /api/algo/freshness/extended - the
            backend already filters to unhealthy-only and caps the list (see
            lambda/api/routes/algo_handlers/monitoring.py), so this is a page, not the
            full picture.
        total_unhealthy: True count of unhealthy loaders before capping - lets this
            section report an honest "...and N more" instead of silently under-reporting
            once there are more issues than fit in loader_health.
        total_tracked: Total tables tracked in data_loader_status - shown alongside the
            healthy-state message so "all healthy" reads as "all N tracked tables", not
            an unscoped claim.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    unhealthy = [lh for lh in loader_health if isinstance(lh, dict) and lh.get("is_unhealthy")] if isinstance(loader_health, list) else []
    # total_unhealthy is the authoritative count (computed backend-side before any
    # capping) - fall back to len(unhealthy) only when the backend didn't send it, e.g.
    # against an older cached response.
    unhealthy_count = total_unhealthy if total_unhealthy is not None else len(unhealthy)

    rows.append(Rule(style="dim"))
    if unhealthy_count == 0:
        tracked_str = f" ({total_tracked} tracked)" if total_tracked is not None else ""
        rows.append(Text.from_markup(f"[bold {G}]Loader Health:[/] All loaders healthy ✓{tracked_str}"))
        return rows

    # Deliberately a one-line summary, not an itemized per-table list: the same tables
    # (with more detail - retry counts, last-success age) are already itemized in the
    # "Loader errors:"/"Repeated failures:"/"Never run:" sections of the Data Freshness
    # Table below. Listing them again here just duplicated that content above the fold,
    # burying the actual per-table freshness grid under two copies of the same failures.
    health_color = R if unhealthy_count >= 5 else Y
    rows.append(
        Text.from_markup(
            f"[bold {health_color}]Loader Health:[/] {unhealthy_count} table(s) with issues [dim](see Data Freshness Table below)[/]"
        )
    )

    return rows


def _build_trend_summary_section(trend_summary: dict[str, Any] | None) -> list[Text | Rule]:
    """Build system trend summary section.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    if not trend_summary or not isinstance(trend_summary, dict):
        return rows

    rows.append(Rule(style="dim"))

    trend = trend_summary.get("trend", "stable")
    success_7d = trend_summary.get("success_rate_7d", 0)
    success_30d = trend_summary.get("success_rate_30d", 0)

    # Trend icon
    if trend == "improving":
        trend_icon = "↗"
        trend_color = G
    elif trend == "degrading":
        trend_icon = "↘"
        trend_color = R
    else:
        trend_icon = "→"
        trend_color = Y

    line = (
        f"[bold {trend_color}]{trend_icon} {trend.upper()}[/] "
        f"[dim]7-day:[/] [{CY}]{success_7d:.1f}%[/] "
        f"[dim]30-day:[/] [{CY}]{success_30d:.1f}%[/]"
    )
    rows.append(Text.from_markup(line))

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


def _format_execution_stats(exec_stats: dict[str, Any] | None) -> Text | None:
    """Format 24-hour execution statistics prominently.

    Shows failure rate, error/halt counts to make recent failures visible.
    Returns None if data unavailable so callers can skip this section.
    """
    if not exec_stats or has_error(exec_stats):
        return None

    total = exec_stats.get("total_runs")
    by_status = exec_stats.get("by_status", {})
    error_rate_str = exec_stats.get("error_rate")
    halt_rate_str = exec_stats.get("halt_rate")
    success_rate_str = exec_stats.get("success_rate")

    if total is None or total == 0:
        return None

    # Parse rates (they come as strings like "2.3%")
    # CRITICAL: Validate status counts exist - default to 0 only if structure exists
    if not isinstance(by_status, dict):
        logger.error("[STATUS SUMMARY] by_status is not a dict or missing - cannot compute status summary")
        return None

    error_count = by_status.get("error", 0)
    halt_count = by_status.get("halted", 0)
    ok_count = by_status.get("ok", 0) + by_status.get("success", 0)

    if error_count == 0 and halt_count == 0 and ok_count == 0:
        logger.warning("[STATUS SUMMARY] All status counts are 0 or missing - data may be incomplete")

    # Determine alert level
    try:
        error_rate_val = float(error_rate_str.strip("%")) if error_rate_str else 0
    except (ValueError, AttributeError):
        error_rate_val = 0

    if error_rate_val > 20:
        alert_color = R
        alert_icon = "⚠⚠⚠"
    elif error_rate_val > 5:
        alert_color = R
        alert_icon = "⚠⚠"
    elif error_rate_val > 0:
        alert_color = Y
        alert_icon = "⚠"
    else:
        alert_color = G
        alert_icon = "✓"

    return Text.from_markup(
        f"[bold {alert_color}]{alert_icon} Last 24h:[/] "
        f"[{G}]{ok_count} ok[/] "
        f"[{Y if halt_count else DIM}]{halt_count} halted[/] "
        f"[{R if error_count else DIM}]{error_count} error[/] "
        f"({total} total) "
        f"[{alert_color}]{error_rate_str or '0%'} failure rate[/]"
    )


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
            rows.append(Text.from_markup(f"  [{Y}]→ {body[:55]}[/]{ph_s}"))
        elif body == "[dim]-[/] halt reason unavailable":
            rows.append(Text.from_markup(f"  [{Y}]→ {body}[/]"))

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


def _format_comprehensive_table_loader_health(
    hlth_items: list[Any] | None, loader: list[Any] | None
) -> list[Text]:
    """Format comprehensive table and loader health showing ALL tables with loader status.

    Groups tables by health status (HEALTHY, STALE, CRITICAL, EMPTY) and shows:
    - Table name with loader status badge (OK, RUNNING, FAILED, etc.)
    - Row count and age
    - Loader-specific details for problem loaders

    This unified view eliminates the need for separate data health and loader status sections.
    """
    rows: list[Text] = []

    # Parse health items (table freshness data)
    hlth_dict: dict[str, dict[str, Any]] = {}
    if hlth_items:
        try:
            for item in hlth_items:
                if isinstance(item, dict):
                    tbl_name = item.get("tbl")
                    if tbl_name:
                        hlth_dict[tbl_name] = item
        except (ValueError, TypeError):
            logger.warning("[TABLE_LOADER_HEALTH] Failed to parse health items")

    # Parse loader status (loader execution data)
    loader_dict: dict[str, dict[str, Any]] = {}
    if loader:
        try:
            valid_loader = safe_get_list(loader)
            if isinstance(valid_loader, list):
                for item in valid_loader:
                    if isinstance(item, dict):
                        tbl_name = item.get("table_name")
                        if tbl_name:
                            loader_dict[tbl_name] = item
        except (ValueError, TypeError):
            logger.warning("[TABLE_LOADER_HEALTH] Failed to parse loader items")

    # Merge all known tables (union of health items and loader items)
    all_tables: set[str] = set()
    all_tables.update(hlth_dict.keys())
    all_tables.update(loader_dict.keys())

    if not all_tables:
        rows.append(Text.from_markup("[dim]No table data available[/]"))
        return rows

    # Categorize tables by health status
    categories: dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]] = {
        "healthy": [],
        "stale": [],
        "critical": [],
        "empty": [],
        "error": [],
    }

    for tbl in sorted(all_tables):
        hlth = hlth_dict.get(tbl, {})
        load = loader_dict.get(tbl, {})

        # CRITICAL FIX 2026-08-03: freshness status (hlth's "st": ok/stale/critical/empty) and
        # loader operational health (consecutive_failures, loader run status) are independent
        # signals - a table can be freshness-"ok" (its last SUCCESSFUL run met the freshness
        # window) while the loader has failed on every attempt since. This used to
        # short-circuit straight into "healthy" whenever status == "ok" with no look at
        # consecutive_failures/loader status at all, so a table with dozens of consecutive
        # failures (live-confirmed: price_daily at consecutive_failures=42) could render as a
        # plain "healthy" entry with zero indication anything was wrong. Check loader health
        # up front, independent of the status branch below.
        cons_failures = hlth.get("consecutive_failures")
        if not isinstance(cons_failures, (int, float)):
            cons_failures = load.get("consecutive_failures")
        loader_run_status = str(hlth.get("loader_run_status") or load.get("status") or "").lower()
        loader_unhealthy = (isinstance(cons_failures, (int, float)) and cons_failures > 0) or loader_run_status in (
            "error",
            "failed",
            "timeout",
        )

        # Determine primary status from health data
        status = hlth.get("st", "unknown")
        if status == "critical":
            categories["critical"].append((tbl, hlth, load))
        elif status == "empty":
            categories["empty"].append((tbl, hlth, load))
        elif loader_unhealthy:
            categories["error"].append((tbl, hlth, load))
        elif status == "ok":
            categories["healthy"].append((tbl, hlth, load))
        elif status == "stale":
            categories["stale"].append((tbl, hlth, load))
        else:
            # Loader-only tables (orchestrator-generated) with unclear freshness status
            if loader_run_status in ("running", "loading", "not_started"):
                categories["stale"].append((tbl, hlth, load))
            else:
                categories["healthy"].append((tbl, hlth, load))

    # Display by category with counts
    summary_parts = []
    if categories["healthy"]:
        summary_parts.append(f"[{G}]{len(categories['healthy'])}✓[/]")
    if categories["stale"]:
        summary_parts.append(f"[{Y}]{len(categories['stale'])}~[/]")
    if categories["critical"]:
        summary_parts.append(f"[{R}]{len(categories['critical'])}![/]")
    if categories["empty"]:
        summary_parts.append(f"[dim]{len(categories['empty'])}○[/]")
    if categories["error"]:
        summary_parts.append(f"[{R}]{len(categories['error'])}✗[/]")

    if summary_parts:
        rows.append(Text.from_markup(f"  {' '.join(summary_parts)}"))

    # Show CRITICAL tables first (need immediate attention)
    if categories["critical"]:
        rows.append(Text.from_markup(f"[{R}]CRITICAL ({len(categories['critical'])}):[/]"))
        for tbl, hlth, load in categories["critical"][:5]:
            rows.append(_format_table_with_loader(tbl, hlth, load, R))

    # Show ERROR loaders (real failures)
    if categories["error"]:
        rows.append(Text.from_markup(f"[{R}]FAILED LOADERS ({len(categories['error'])}):[/]"))
        for tbl, hlth, load in categories["error"][:5]:
            rows.append(_format_table_with_loader(tbl, hlth, load, R, show_error=True))

    # Show STALE tables (aged but not critical yet)
    if categories["stale"]:
        display_count = min(4, len(categories["stale"]))
        truncation = f" [dim](showing {display_count}/{len(categories['stale'])})[/]" if len(categories["stale"]) > 4 else ""
        rows.append(Text.from_markup(f"[{Y}]STALE{truncation}:[/]"))
        for tbl, hlth, load in categories["stale"][:4]:
            rows.append(_format_table_with_loader(tbl, hlth, load, Y))

    # Show EMPTY tables (no data yet)
    if categories["empty"]:
        display_count = min(3, len(categories["empty"]))
        truncation = f" [dim](showing {display_count}/{len(categories['empty'])})[/]" if len(categories["empty"]) > 3 else ""
        rows.append(Text.from_markup(f"[dim]EMPTY{truncation}:[/]"))
        for tbl, hlth, load in categories["empty"][:3]:
            rows.append(_format_table_with_loader(tbl, hlth, load, DIM))

    return rows


def _format_table_with_loader(
    table_name: str, hlth: dict[str, Any], load: dict[str, Any], color: str, show_error: bool = False
) -> Text:
    """Format single table line with loader status badge and details."""
    # Table name (left-aligned, 16 chars)
    tbl_display = table_name[:16].ljust(16)

    # Loader status badge - fall back to hlth's own loader_run_status when the separate
    # `load` lookup has no entry for this table (it's sourced from a different fetch than
    # hlth_items, so isn't guaranteed to cover every table hlth_items does).
    loader_status_raw = (load.get("status") if load else None) or hlth.get("loader_run_status") or ""
    loader_status = str(loader_status_raw).lower()
    if loader_status in ("running", "loading"):
        badge = f"[{CY}]●[/]"
        completion = load.get("completion_pct")
        status_text = f" {int(completion)}%" if completion else ""
    elif loader_status in ("failed", "error"):
        badge = f"[{R}]✗[/]"
        status_text = ""
    elif loader_status == "timeout":
        badge = f"[{Y}]⏱[/]"
        status_text = ""
    elif loader_status == "not_started":
        badge = f"[dim]∘[/]"
        status_text = ""
    elif loader_status == "completed":
        badge = f"[{G}]✓[/]"
        status_text = ""
    else:
        badge = ""
        status_text = ""

    # Age information
    age_hours = safe_float(hlth.get("age_hours"), default=None)
    age_days = safe_float(hlth.get("age"), default=None)
    if age_hours is not None and age_hours < 24:
        age_text = f"{age_hours:.0f}h"
    elif age_days is not None:
        age_text = f"{age_days:.1f}d"
    else:
        age_text = "--"

    # Row count
    row_count = hlth.get("row_count") or load.get("row_count")
    if row_count is not None:
        try:
            row_text = f" n={int(row_count)}"
        except (ValueError, TypeError):
            row_text = ""
    else:
        row_text = ""

    # Build line
    line = f"  {badge} [{color}]{tbl_display}[/] [dim]{age_text}{row_text}[/]"

    # Add error/loader details if showing errors - same load-then-hlth fallback as the badge
    # above, so a table only present in hlth_items still shows its real failure reason/count.
    if show_error:
        error_msg = load.get("error_message") or hlth.get("loader_error") or ""
        if error_msg:
            line += f" [dim]{str(error_msg)[:30]}[/]"

        # Show consecutive failures for repeated failures
        consecutive = load.get("consecutive_failures")
        if not isinstance(consecutive, (int, float)):
            consecutive = hlth.get("consecutive_failures")
        if isinstance(consecutive, (int, float)) and consecutive > 1:
            line += f" [yellow]({int(consecutive)} failures)[/]"

    if status_text:
        line += f"[{CY}]{status_text}[/]"

    return Text.from_markup(line)


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


def panel_algo_health(
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
    hlth_dict = hlth if isinstance(hlth, dict) else {}
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
        failed_loaders = sum(1 for r in hlth_items if isinstance(r, dict) and r.get("st") in ("error", "stale"))
        succeeded_loaders = total_loaders - failed_loaders
        if loading_count > 0:
            rows.append(Text.from_markup(f"  [dim]Loaders:[/] [{G}]{succeeded_loaders} ok[/] [{Y}]{loading_count} loading[/]"))
        elif failed_loaders > 0:
            rows.append(Text.from_markup(f"  [dim]Loaders:[/] [{G}]{succeeded_loaders} ok[/] [{R}]{failed_loaders} failed[/]"))

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


def panel_data_freshness(hlth: dict[str, Any] | list[Any] | None) -> Panel:
    """Summary-focused data freshness panel: ready/not-ready status + key diagnostics.

    Shows overall data readiness, critical issues, Phase 1 gate result, and key diagnostic
    sections (stale tables, loader errors, repeated failures, coverage gaps).
    Expanded full table view available via [l] for complete per-table breakdown.
    """
    hlth_err = _error_panel("health", hlth, "DATA FRESHNESS")
    if hlth_err is not None:
        return hlth_err

    rows: list[Text | Rule] = []
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

    # Summary status line: overall readiness indicator
    stale_count = sum(1 for r in hlth_items if isinstance(r, dict) and r.get("st") != "ok")
    total_count = len([r for r in hlth_items if isinstance(r, dict)])

    ready_color = G if ready_to_trade else R
    ready_text = "✓ READY" if ready_to_trade else "✗ NOT READY"
    rows.append(Text.from_markup(f"[{ready_color}]{ready_text}[/]  [dim]{total_count - stale_count}/{total_count} fresh[/]"))

    # Trading halted status (if applicable)
    trading_halted = hlth_dict.get("trading_halted")
    trading_halt_reason = hlth_dict.get("trading_halt_reason")
    if trading_halted and trading_halt_reason:
        rows.append(Text.from_markup(f"  [{Y}]→ Trading halted:[/] {str(trading_halt_reason)[:70]}"))

    # ── Loader success rate (NEW) ────────────────────────────────────────────
    if hlth_items:
        succeeded, total, success_rate = _calc_loader_success_rate(hlth_items)
        if success_rate is not None and total > 0:
            rate_color = G if success_rate >= 90 else Y if success_rate >= 70 else R
            rows.append(Text.from_markup(f"  [dim]Loader health:[/] [{rate_color}]{success_rate:.0f}% success ({succeeded}/{total})[/]"))

    # Summary counts by status
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
            rows.append(Text.from_markup("[dim]Summary:[/]  " + "  ".join(parts)))

    # ── Data completeness by criticality (NEW) ───────────────────────────────
    if hlth_items:
        completeness = _calc_data_completeness(hlth_items)
        if completeness:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[bold cyan]Data Coverage:[/]"))
            for role in ["CRIT", "IMP", "NORM"]:
                if role in completeness:
                    ready, total = completeness[role]
                    pct = (ready / total * 100) if total > 0 else 0
                    role_name = "Critical" if role == "CRIT" else "Important" if role == "IMP" else "Normal"
                    pct_color = G if pct == 100 else Y if pct >= 80 else R
                    rows.append(Text.from_markup(f"  [{pct_color}]{role_name:9}:[/] {ready:2}/{total:2} ({pct:5.1f}%)"))

    # ── Most critical blocking issues (NEW - replaces bare critical stale alert) ──
    critical_stale = hlth_dict.get("critical_stale")
    if critical_stale:
        names = "  ".join(f"[bold {R}]{n}[/]" for n in critical_stale[:3])
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[{R}]⚠ CRITICAL BLOCKING:[/]  {names}"))

    # Extract top 3 issues from items if available
    if hlth_items:
        top_issues = _get_most_critical_issues(hlth_items)
        if top_issues and not critical_stale:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup(f"[{R}]⚠ CRITICAL ISSUES:[/]"))
            for issue in top_issues:
                rows.append(Text.from_markup(f"  [{R}]•[/] {issue[:70]}"))
        elif top_issues and critical_stale:
            rows.append(Text.from_markup("[dim]Top issues:[/]"))
            for issue in top_issues[:2]:
                rows.append(Text.from_markup(f"  [{R}]•[/] {issue[:65]}"))

    # Phase 1 data freshness check result (orchestrator's view at last run)
    execution_health = hlth_dict.get("execution_health")
    if isinstance(execution_health, dict):
        p1 = execution_health.get("phase_1_data_check")
        if p1:
            rows.append(Rule(style="dim"))
            vs = p1.get("validation_status")
            vc = G if vs == "pass" else (Y if vs == "warn" else (R if vs == "fail" else DIM))
            tf = p1.get("tables_fresh")
            tv = p1.get("tables_validated")
            counts_s = f"  [dim]{tf}/{tv} fresh[/]" if tf is not None and tv is not None else ""
            rows.append(Text.from_markup(f"[dim]Phase 1 gate:[/] [{vc}]{vs or '?'}[/]{counts_s}"))

            # Show stale table list if there are any
            stale_tables = p1.get("stale_tables")
            if stale_tables and isinstance(stale_tables, (list, dict)):
                stale_list = []
                if isinstance(stale_tables, list):
                    stale_list = [tbl.get("table_name", "?") for tbl in stale_tables[:5] if isinstance(tbl, dict)]
                elif isinstance(stale_tables, dict):
                    stale_list = list(stale_tables.keys())[:5]
                if stale_list:
                    rows.append(Text.from_markup(f"  [dim]Stale:[/] {', '.join(stale_list)}"))

    # ── STALE TABLE DETAIL ──────────────────────────────────────
    # Show which tables are stale and by how much relative to their thresholds
    stale_detail = [
        (r.get("tbl") or "unknown", r.get("age"), r.get("stale_threshold_days"))
        for r in hlth_items
        if isinstance(r, dict) and r.get("st") == "stale" and r.get("age") is not None and r.get("stale_threshold_days") is not None
    ]
    if stale_detail:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[bold {Y}]Stale tables (age vs threshold):[/]"))
        for tbl_name, age, threshold in stale_detail[:5]:
            rows.append(Text.from_markup(f"  [{Y}]{tbl_name}:[/] [dim]{age}d old, threshold {threshold}d[/]"))
        if len(stale_detail) > 5:
            rows.append(Text.from_markup(f"  [dim]...and {len(stale_detail) - 5} more[/]"))

    # Loader errors / repeated failures / never-started loaders moved to the ALGO HEALTH
    # panel's PHASE EXECUTION DETAILS right column (see _build_loader_operational_detail_rows)
    # so that panel could narrow its phase list into a left column without losing content.
    def _has_loader_detail(r: Any) -> bool:
        if not isinstance(r, dict):
            return False
        if r.get("loader_error"):
            return True
        n_fail = r.get("consecutive_failures")
        if isinstance(n_fail, (int, float)) and n_fail >= 2:
            return True
        return bool(r.get("st") != "ok" and r.get("loader_run_status") == "NOT_STARTED")

    has_loader_detail = any(_has_loader_detail(r) for r in hlth_items)
    if has_loader_detail:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Loader errors, repeated failures & never-run → ALGO HEALTH panel[/]"))

    # ── LOADER QUEUE DEPTH & ETA (NEW) ─────────────────────────────────────────
    # Show pipeline status and estimated completion
    if hlth_items:
        loading_count, queued = _calc_loader_queue_depth(hlth_items)
        if loading_count > 0:
            rows.append(Rule(style="dim"))
            eta_s = f"{queued + loading_count} more loaders to complete"
            rows.append(Text.from_markup(f"[dim]Loader queue:[/] [{Y}]{loading_count} active[/]  {queued + loading_count} items pending"))

    # ── CURRENTLY LOADING ──────────────────────────────────────
    # Show what's in progress
    in_progress = [r for r in hlth_items if isinstance(r, dict) and r.get("execution_started") and not r.get("execution_completed")]
    if in_progress:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup(f"[bold {Y}]Loading now:[/]"))
        for r in in_progress[:4]:
            pct = r.get("completion_pct")  # type: ignore[assignment]
            pct_s = f"{float(pct):.0f}%" if pct is not None else "?"
            sl, sc = r.get("symbols_loaded"), r.get("symbol_count")
            cnt_s = f" ({sl}/{sc} symbols)" if sl is not None and sc is not None else ""
            rows.append(Text.from_markup(f"  [{Y}]⟳ {r.get('tbl') or 'unknown'}:[/] {pct_s}{cnt_s}"))
        if len(in_progress) > 4:
            rows.append(Text.from_markup(f"  [dim]...and {len(in_progress) - 4} more[/]"))

    # Link to expanded view for complete table details
    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[dim]→ Press [l] to view full table details and coverage analysis[/]"))

    return Panel(
        Group(*rows),
        title=rf"[bold yellow]DATA FRESHNESS[/]{age_s}  [dim]\[l] expand[/]",
        border_style="yellow",
        padding=(0, 1),
    )


def _build_algo_metrics_table(metrics: list[Any]) -> Table | None:
    """Build table of today's trading metrics and history."""
    if not metrics or not isinstance(metrics, list):
        return None

    valid_metrics = [m for m in metrics if isinstance(m, dict)]
    if not valid_metrics:
        return None

    tbl = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="dim",
        padding=(0, 1),
        expand=False,
    )
    tbl.add_column("Date", no_wrap=True, min_width=12)
    tbl.add_column("Entries", no_wrap=True, justify="right", min_width=7)
    tbl.add_column("Exits", no_wrap=True, justify="right", min_width=7)
    tbl.add_column("Actions", no_wrap=True, justify="right", min_width=7)
    tbl.add_column("Sig Score", no_wrap=True, justify="right", min_width=9)

    for m in valid_metrics[:7]:
        dt = m.get("date", "-")
        ent = m.get("entries")
        ext = m.get("exits")
        act = m.get("total_actions")
        sig = m.get("avg_signal_score")

        # Safe conversion with type checking
        try:
            ent_val = int(ent) if ent is not None and isinstance(ent, (int, float, str)) else None
        except (ValueError, TypeError):
            ent_val = None
        try:
            ext_val = int(ext) if ext is not None and isinstance(ext, (int, float, str)) else None
        except (ValueError, TypeError):
            ext_val = None
        try:
            act_val = int(act) if act is not None and isinstance(act, (int, float, str)) else None
        except (ValueError, TypeError):
            act_val = None
        try:
            sig_val = float(sig) if sig is not None and isinstance(sig, (int, float, str)) else None
        except (ValueError, TypeError):
            sig_val = None

        ent_s = f"{ent_val}" if ent_val is not None else "-"
        ext_s = f"{ext_val}" if ext_val is not None else "-"
        act_s = f"{act_val}" if act_val is not None else "-"
        sig_s = f"{sig_val:.1f}" if sig_val is not None else "-"

        tbl.add_row(
            Text(str(dt)[:10], style="dim"),
            Text(ent_s, style=G if ent_val and ent_val > 0 else DIM),
            Text(ext_s, style=Y if ext_val and ext_val > 0 else DIM),
            Text(act_s, style=CY if act_val and act_val > 0 else DIM),
            Text(sig_s, style=G if sig_val and sig_val > 0.5 else (Y if sig_val and sig_val > 0.3 else DIM)),
        )

    return tbl


# The orchestrator always runs the same 9 phases (see algo/orchestrator/phase*.py) -
# used to render "N/9 phases completed" per past run without a second data source.
TOTAL_ORCHESTRATOR_PHASES = 9


def _fmt_run_duration(started_at: Any, completed_at: Any) -> str | None:
    """Compute wall-clock run duration from started_at/completed_at timestamps.

    Returns None (not "?") when either timestamp is missing/unparseable/still-running
    (completed_at null) so callers can omit the field instead of showing a fake value.
    """
    if started_at is None or completed_at is None:
        return None
    try:
        from datetime import datetime

        def _to_dt(v: Any) -> datetime | None:
            if isinstance(v, datetime):
                return v
            if isinstance(v, str):
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            return None

        start_dt = _to_dt(started_at)
        end_dt = _to_dt(completed_at)
        if start_dt is None or end_dt is None:
            return None
        secs = (end_dt - start_dt).total_seconds()
        if secs < 0:
            return None
        if secs < 60:
            return f"{secs:.0f}s"
        mins, s = divmod(int(secs), 60)
        if mins < 60:
            return f"{mins}m{s:02d}s"
        hrs, m = divmod(mins, 60)
        return f"{hrs}h{m:02d}m"
    except (ValueError, TypeError):
        return None


def _build_past_runs_section(exec_hist: list[Any]) -> list[Text | Rule]:
    """Build past runs section: status, age, duration, and phase-level outcome for
    each recent run - not just the overall badge.

    exec_hist rows already carry phases_completed/phases_halted/phases_errored (per-run
    arrays of "P<n>" phase tags computed server-side, see
    lambda/api/routes/algo_handlers/orchestration.py's _get_orchestrator_execution_recent)
    and completed_at, but this section previously only used started_at + halt_reason/summary
    and threw the rest away. Surfacing them here answers "how far did THIS run get, and
    which phase(s) stopped it" without opening a separate view per run.

    Shows up to 8 most recent runs with:
    - Status indicator (✓/~/✗)
    - Age + run duration
    - N/9 phases completed, and which phase(s) halted/errored if any
    - Brief failure reason if applicable

    Returns list of Rich Text/Rule objects for display in health panel footer.
    """
    rows: list[Text | Rule] = []

    valid_hist = safe_get_list(exec_hist)
    if not isinstance(valid_hist, list) or not valid_hist:
        return rows

    # Show last 8 runs (deeper than the 5 shown previously - exec_hist now fetches
    # a 14d/20-run window instead of 7d/10, so there's history to show)
    recent_runs = valid_hist[:8]

    # Build row with status badges and details
    for run in recent_runs:
        if not isinstance(run, dict):
            continue

        status = _get_status_safe(run)
        color, icon = _format_phase_badge(status)

        # API returns "started_at", not "run_at"
        run_at = run.get("started_at") or run.get("run_at")
        timestamp_str = fmt_age(run_at) if run_at else "?"
        duration_str = _fmt_run_duration(run.get("started_at"), run.get("completed_at"))
        duration_part = f" [{DIM}]({duration_str})[/]" if duration_str else ""

        # Get failure details
        halt_reason = run.get("halt_reason", "")
        summary = run.get("summary", "")

        # Determine what reason to show based on status
        reason = ""
        if status in HALTED_STATES and halt_reason:
            reason = halt_reason[:40]
        elif status in ERROR_STATES and summary:
            reason = summary[:40]

        # Phase-level breakdown: how far this specific run got, and which phase(s)
        # stopped it - distinct from the aggregate 30-day trend in the reliability section.
        phase_part = ""
        completed_list = run.get("phases_completed")
        halted_list = run.get("phases_halted")
        errored_list = run.get("phases_errored")
        if isinstance(completed_list, list):
            n_done = len(completed_list)
            phase_color = G if n_done >= TOTAL_ORCHESTRATOR_PHASES else (Y if n_done > 0 else DIM)
            phase_part = f"  [{phase_color}]{n_done}/{TOTAL_ORCHESTRATOR_PHASES}[/]"
            bad_bits = []
            if isinstance(halted_list, list) and halted_list:
                bad_bits.append(f"[{Y}]{','.join(halted_list)} halted[/]")
            if isinstance(errored_list, list) and errored_list:
                bad_bits.append(f"[{R}]{','.join(errored_list)} error[/]")
            if bad_bits:
                phase_part += " " + " ".join(bad_bits)

        # Format the run line
        reason_part = f" • {reason}" if reason else ""
        run_line = f"  [{color}]{icon}[/] [{DIM}]{timestamp_str}[/]{duration_part}{phase_part}{reason_part}"
        rows.append(Text.from_markup(run_line))

    if rows:
        rows.insert(0, Rule(style="dim"))
        rows.insert(0, Text.from_markup(f"[bold dim]Past runs:[/]"))

    return rows


def _build_phase_reliability_section(exec_patterns: dict[str, Any] | None) -> list[Text | Rule]:
    """Build PHASE RELIABILITY section: which phases halt/error most often over a
    30-day window, with example reasons - answers "is this phase failing all the time,
    or was this a one-off?", which a single run's status (or even 8 past runs) can't
    show on its own since it's an aggregate across a much longer window.

    Backed by /api/algo/execution/patterns - already implemented server-side
    (GROUP BY phase, COUNT halts, array_agg reasons) but never wired to the dashboard
    before now.

    Returns [] when there's no pattern data - either the fetch failed/is pending, or
    (the common, healthy case) zero phases halted/errored in the window.
    """
    rows: list[Text | Rule] = []
    if not exec_patterns or not isinstance(exec_patterns, dict):
        return rows

    patterns = exec_patterns.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        return rows

    period_days = exec_patterns.get("period_days", 30)

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {Y}]Phase Reliability ({period_days}d):[/]"))

    for p in patterns[:6]:
        if not isinstance(p, dict):
            continue
        phase_name = p.get("phase")
        if phase_name is None:
            phase_name = "unknown"
        total_halts = p.get("total_halts")
        if total_halts is None:
            continue
        reasons = p.get("example_reasons")
        if not isinstance(reasons, list):
            reasons = []
        # Thresholds are relative to a 30d window, not daily - >=10 events in 30d is
        # roughly "every 3rd run", the "failing all the time" case; 3-9 is intermittent.
        sev_color = R if total_halts >= 10 else Y if total_halts >= 3 else DIM
        rows.append(Text.from_markup(f"  [{sev_color}]{phase_name}:[/] {total_halts} halts/errors"))
        for reason in reasons[:2]:
            if reason:
                rows.append(Text.from_markup(f"    [dim]• {str(reason)[:70]}[/]"))

    if len(patterns) > 6:
        rows.append(Text.from_markup(f"  [dim]...and {len(patterns) - 6} more phases[/]"))

    return rows


def _build_results_panel(
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
                phase_header = Text.from_markup(f"{status_icon} [bold {color}]{phase_name}[/] [{color}]{status_label}[/]")

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
                        target_rows.append(Text.from_markup(f"  Tables: {phase_data.get('tables_validated')} validated"))
                    if phase_data.get("tables_fresh") is not None:
                        fresh_color = G if phase_data.get("tables_fresh") == phase_data.get("tables_validated") else Y
                        target_rows.append(Text.from_markup(f"  [{fresh_color}]Fresh: {phase_data.get('tables_fresh')}[/]"))
                    if phase_data.get("tables_stale") is not None:
                        stale_color = R if phase_data.get("tables_stale", 0) > 0 else G
                        target_rows.append(Text.from_markup(f"  [{stale_color}]Stale: {phase_data.get('tables_stale')}[/]"))
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
                        dd_color = R if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_HALT_PCT else Y if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_CAUTION_PCT else G
                        dd_status = "TRIGGERED" if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_HALT_PCT else "CAUTION" if dd >= OrchestratorConfig.CIRCUIT_BREAKER_DRAWDOWN_CAUTION_PCT else "OK"
                        target_rows.append(Text.from_markup(f"  Drawdown: [{dd_color}]{dd:.1f}% ({dd_status})[/]"))
                    if "daily_loss_pct" in phase_data and phase_data["daily_loss_pct"] is not None:
                        dl = phase_data["daily_loss_pct"]
                        dl_color = R if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_HALT_PCT else Y if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_CAUTION_PCT else G
                        dl_status = "TRIGGERED" if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_HALT_PCT else "CAUTION" if dl >= OrchestratorConfig.CIRCUIT_BREAKER_DAILY_LOSS_CAUTION_PCT else "OK"
                        target_rows.append(Text.from_markup(f"  Daily Loss: [{dl_color}]{dl:.1f}% ({dl_status})[/]"))
                    if "vix_level" in phase_data and phase_data["vix_level"] is not None:
                        vix = phase_data["vix_level"]
                        vix_color = R if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_EXTREME else Y if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_HIGH else G
                        vix_status = "EXTREME" if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_EXTREME else "HIGH" if vix >= OrchestratorConfig.CIRCUIT_BREAKER_VIX_HIGH else "NORMAL"
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
                        pnl_color = G if total_pnl >= 0 else R
                        target_rows.append(Text.from_markup(f"  Total P&L: [{pnl_color}]${total_pnl:,.0f}[/]"))

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
                        failed_count = int(exits_count * (100 - sr) / 100) if sr < 100 else 0
                        fail_text = f" ({int(100-sr)}% failed)" if sr < 100 else ""
                        target_rows.append(Text.from_markup(f"  Success: [{sr_color}]{sr:.0f}%{fail_text}[/]"))
                    profit = phase_data.get("avg_profit")
                    if profit is not None:
                        profit_color = G if profit > 0 else R if profit < 0 else Y
                        profit_text = "LOSS" if profit < 0 else "PROFIT"
                        target_rows.append(Text.from_markup(f"  Avg Profit: [{profit_color}]${profit:,.0f} ({profit_text})[/]"))
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
                        failed_count = int(entries_count * (100 - sr) / 100) if sr < 100 else 0
                        fail_text = f" ({int(100-sr)}% failed)" if sr < 100 else ""
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


def panel_data_freshness_expanded(
    hlth: dict[str, Any] | list[Any] | None,
    inventory: dict[str, Any] | None = None,
    data_coverage: dict[str, Any] | None = None,
    orch_extended: dict[str, Any] | None = None,
    signal_freshness: dict[str, Any] | None = None,
) -> Panel:
    """Full-screen data freshness: loader metrics + existing per-table freshness detail.

    Run history / phase health / failure patterns moved to panel_algo_health_expanded
    (the [h] panel) - that's phase/run health, not per-table data freshness, and having
    it prepended here was crowding out the per-table freshness detail this panel exists
    to show.

    Args:
        hlth: Health/data-status response (per-table freshness)
        inventory: Optional table inventory (/api/admin/inventory) - untracked/missing tables
        data_coverage: Optional /api/data-coverage response (zero-volume/invalid-price %)
        orch_extended: Optional extended orchestrator data (run_history, phase_health, etc.)
        signal_freshness: Optional /api/health "freshness" block (status/signal_age_hours)
    """
    hlth_err_exp = _error_panel("health", hlth, "DATA FRESHNESS EXPANDED")
    if hlth_err_exp is not None:
        return hlth_err_exp

    hlth_dict = hlth if isinstance(hlth, dict) else {}
    hlth_items, ready_to_trade = extract_health_items(hlth if hlth is not None else {})

    # Get the freshness content (preserves all existing data) - a raw Group, not a Panel,
    # so it can be embedded below without a redundant nested border/title.
    freshness_content = _build_freshness_panel(
        hlth_items,
        ready_to_trade,
        hlth_dict,
        inventory=inventory,
        data_coverage=data_coverage,
        signal_freshness=signal_freshness,
    )

    as_of = hlth_dict.get("as_of")
    age_s = f"  [dim]{fmt_age(as_of)}[/]" if as_of else ""

    # If we have extended orchestrator data, prepend the new sections
    # (run history / phase health / failure patterns live on the [h] panel now - see
    # panel_algo_health_expanded - since they're phase/run health, not table freshness)
    if orch_extended and isinstance(orch_extended, dict):
        rows: list[Any] = []

        # Add loader health
        loader_health = orch_extended.get("loader_health", [])
        loader_health_rows = _build_loader_health_section(
            loader_health,
            total_unhealthy=orch_extended.get("loader_health_total_unhealthy"),
            total_tracked=orch_extended.get("loader_health_total_tracked"),
        )
        if loader_health_rows:
            rows.extend(loader_health_rows)

        # Add trend summary
        trend_summary = orch_extended.get("trend_summary", {})
        trend_rows = _build_trend_summary_section(trend_summary)
        if trend_rows:
            rows.extend(trend_rows)

        # Combine new sections with the freshness content in a single bordered panel -
        # no nested Panel-in-Panel, so the two sections share one title/border.
        if rows:
            rows.append(Rule(style="dim"))
            rows.append(freshness_content)

            all_content = Group(*rows)
            return Panel(
                all_content,
                title=rf"[bold yellow]ORCHESTRATOR & DATA FRESHNESS[/]{age_s}  [dim]\[l] return[/]",
                border_style="yellow",
                padding=(0, 1),
            )

    # If no extended data, wrap the freshness content in its own panel (no data loss)
    return Panel(
        freshness_content,
        title=rf"[bold yellow]DATA FRESHNESS - EXPANDED[/]{age_s}  [dim]\[l] return[/]",
        border_style="yellow",
        padding=(0, 1),
    )


__all__ = [
    "panel_algo_health",
    "panel_algo_health_expanded",
    "panel_data_freshness",
    "panel_data_freshness_expanded",
    "panel_orch",
    "panel_status",
]
