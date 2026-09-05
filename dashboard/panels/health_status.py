"""_pc / _format_exec_history_summary / _format_recent_trade_events / _format_data_health_summary /
_format_loader_status / _format_comprehensive_table_loader_health / _format_table_with_loader:
formatter helpers used by panel_status in health_status_panel.py. Split out once
health_status.py grew past the file-size ratchet's cap.
"""

import json
import logging
from typing import Any

from rich.text import Text

from dashboard.data_validation import safe_float

from ..error_boundary import has_error
from ..utilities import CY, DIM, G, R, Y
from ._helpers import _fmt_phases_halted
from .data_extractors import safe_get_list
from .health_shared import (
    ERROR_STATES,
    HALTED_STATES,
    LOADER_STATUS_ERROR,
    LOADER_STATUS_LOADING,
    PHASE_SUCCESS_STATES,
    SKIPPED_STATES,
    _format_phase_badge,
    _get_item_status,
    _get_status_safe,
)

logger = logging.getLogger(__name__)


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

    stale = [r for r in hlth_items if isinstance(r, dict) and _get_item_status(r) != "ok"]
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


def _format_comprehensive_table_loader_health(  # noqa: C901
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
        status = _get_item_status(hlth) or "unknown"
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
        truncation = (
            f" [dim](showing {display_count}/{len(categories['stale'])})[/]" if len(categories["stale"]) > 4 else ""
        )
        rows.append(Text.from_markup(f"[{Y}]STALE{truncation}:[/]"))
        for tbl, hlth, load in categories["stale"][:4]:
            rows.append(_format_table_with_loader(tbl, hlth, load, Y))

    # Show EMPTY tables (no data yet)
    if categories["empty"]:
        display_count = min(3, len(categories["empty"]))
        truncation = (
            f" [dim](showing {display_count}/{len(categories['empty'])})[/]" if len(categories["empty"]) > 3 else ""
        )
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
        badge = "[dim]∘[/]"
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


__all__ = [
    "_format_comprehensive_table_loader_health",
    "_format_data_health_summary",
    "_format_exec_history_summary",
    "_format_loader_status",
    "_format_recent_trade_events",
    "_format_table_with_loader",
    "_pc",
]
