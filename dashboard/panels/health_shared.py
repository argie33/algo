"""Shared constants and small helpers used across the health/orchestration panel modules.

health.py (health_orch.py, health_status.py, health_algo.py, health_freshness.py,
health_results.py) all draw on this module for state-classification constants (SUCCESS_STATES/
HALTED_STATES/etc.) and a handful of helpers that are genuinely used by 2+ of those panel
groups (e.g. _get_item_status is used by the freshness, status, and algo panels alike). Keeping
these here avoids the alternative of two independently-maintained copies drifting apart, or an
awkward cross-import between sibling panel modules.
"""

import logging
from typing import Any

from rich.text import Text

from ..error_boundary import has_error
from ..utilities import CY, DIM, G, R, Y

logger = logging.getLogger(__name__)


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

# Aliases for the PHASE_-prefixed call sites elsewhere in this file - see the comment on
# the old PHASE_SUCCESS_STATES/PHASE_HALTED_STATES/PHASE_SKIPPED_STATES definitions above
# for why these are aliases now instead of a second, independently-maintained tuple.
PHASE_SUCCESS_STATES = SUCCESS_STATES
PHASE_HALTED_STATES = HALTED_STATES
PHASE_SKIPPED_STATES = SKIPPED_STATES

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
# BUG FOUND 2026-08-24 (real-money-readiness goal session, dashboard test-coverage sweep):
# live-measured against all 2472 real notification titles in the local dev DB, 71.8% (1774)
# didn't match any key here and fell through to raw_t[:24] at each call site below. Most of
# that 71.8% is harmless (ENTRY: SYMBOL / EXIT ORDER FAILED: SYMBOL titles are already short
# and fully informative even truncated), but a real subset of the MOST CRITICAL alerts -
# exactly the ones a user most needs to notice - were getting garbled past the point of
# meaning: "[ALGO ALERT] HALT_FLAG_ACTIVE: PORTFOLIO" (trading is halted RIGHT NOW) truncated
# to "[ALGO ALERT] HALT_FLAG_A" with no indication of what's wrong; "Reconciliation
# Initialization Failed - Production Blocker" truncated to "Reconciliation Initializ" (doesn't
# even convey "Failed"); "Phase 9: Exit recording failed - permanent audit gap risk" truncated
# to "Phase 9: Exit recording " (loses "failed" entirely - reads as a routine status line, not
# a compliance-audit-gap alert). Added entries for every real title format found producing a
# meaning-losing truncation. Root cause of the underscore-separated ones never matching: these
# titles use SNAKE_CASE ("ACCOUNT_CIRCUIT_BREAKER"), not the space-separated phrasing the
# existing "circuit breaker"/"trading halted by circuit" keys expected.
NOTIF_SHORT_NAMES = {
    "halt_flag_active": "HALTED NOW",
    "account_circuit_breaker": "Halted: CB",
    "exit_check_failures": "ExitCheck Fail",
    "reconciliation initialization failed": "ReconInit Fail",
    "exit recording failed": "AuditGap!",
    "quantity mismatch": "QtyMismatch",
    "position drift": "PosDrift",
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


def _get_item_status(item: dict[str, Any] | None) -> str | None:
    """Get status from health item, checking both 'st' and 'status' fields.

    API returns 'status' field, but code often uses 'st' shorthand. This handles both.
    """
    if not isinstance(item, dict):
        return None
    return item.get("st") or item.get("status")


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


_last_status_summary_warning_key: tuple[Any, ...] | None = None


def _warn_status_summary_once(key: tuple[Any, ...], message: str) -> None:
    """Log a [STATUS SUMMARY] warning only when the underlying condition actually changes.

    ROOT-CAUSE FIX 2026-08-16: _format_execution_stats() runs on every render tick, not
    every data fetch (watch mode's Live loop redraws far more often than load_all()
    refreshes - live-confirmed: 52,000+ identical warnings logged in a single 12-minute
    session for one unchanging exec_stats snapshot, ~18 duplicate lines per tick). An
    unconditional logger.warning() here re-logs the same finding every single redraw
    instead of once when it first appears, drowning out real signal in the log file.
    """
    global _last_status_summary_warning_key
    if key == _last_status_summary_warning_key:
        return
    _last_status_summary_warning_key = key
    logger.warning(message)


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
    # "skipped"/"degraded"/"running" are legitimate statuses (e.g. every run today was
    # skipped for non_trading_day on a weekend) - they must be tallied before deciding
    # data is actually missing, or every quiet weekend spams this warning on every
    # refresh tick even though by_status correctly reflects reality.
    skipped_count = by_status.get("skipped", 0)
    degraded_count = by_status.get("degraded", 0)
    running_count = by_status.get("running", 0)
    accounted = error_count + halt_count + ok_count + skipped_count + degraded_count + running_count

    if accounted == 0 and total:
        _warn_status_summary_once(
            ("zero", total), "[STATUS SUMMARY] All status counts are 0 or missing - data may be incomplete"
        )
    elif accounted != total:
        _warn_status_summary_once(
            ("mismatch", total, accounted, tuple(sorted(by_status.items()))),
            f"[STATUS SUMMARY] by_status counts ({accounted}) don't sum to total_runs ({total}) - "
            f"unrecognized status value present: {by_status}",
        )

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

    skipped_str = f" [{DIM}]{skipped_count} skipped[/]" if skipped_count else ""
    return Text.from_markup(
        f"[bold {alert_color}]{alert_icon} Last 24h:[/] "
        f"[{G}]{ok_count} ok[/] "
        f"[{Y if halt_count else DIM}]{halt_count} halted[/] "
        f"[{R if error_count else DIM}]{error_count} error[/]"
        f"{skipped_str} "
        f"({total} total) "
        f"[{alert_color}]{error_rate_str or '0%'} failure rate[/]"
    )


__all__ = [
    "ERROR_STATES",
    "HALTED_STATES",
    "LOADER_STATUS_ERROR",
    "LOADER_STATUS_LOADING",
    "NOTIF_SHORT_NAMES",
    "PHASE_DATA_KEYS",
    "PHASE_HALTED_STATES",
    "PHASE_SKIPPED_STATES",
    "PHASE_SUCCESS_STATES",
    "ROLE_ORDER",
    "SEV_COLORS",
    "SKIPPED_STATES",
    "SUCCESS_STATES",
    "HealthFormatter",
    "_format_execution_stats",
    "_format_phase_badge",
    "_get_item_status",
    "_get_status_safe",
    "_var_color",
    "_warn_status_summary_once",
]
