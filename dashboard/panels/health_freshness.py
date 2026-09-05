"""Per-table data freshness panels (panel_data_freshness, panel_data_freshness_expanded).

The section-builder helpers that feed them and _build_freshness_panel itself live in
health_freshness_sections.py / health_freshness_panel.py (split out once this file grew
past the file-size ratchet's cap) and are re-exported here so existing
`from .health_freshness import ...` call sites (this package's own health.py aggregator,
plus tests) keep working unchanged.
"""

import logging
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ..formatters import fmt_age
from ..utilities import DIM, G, R, Y
from ._helpers import _error_panel
from .data_extractors import extract_health_items
from .health_freshness_panel import _build_freshness_panel
from .health_freshness_sections import (
    _build_loader_health_section,
    _build_trend_summary_section,
    _calc_data_completeness,
    _calc_loader_queue_depth,
    _calc_loader_success_rate,
    _format_halt_age,
    _format_halt_manual_clear_note,
    _get_most_critical_issues,
)
from .health_shared import _get_item_status

logger = logging.getLogger(__name__)


def panel_data_freshness(hlth: dict[str, Any] | list[Any] | None) -> Panel:  # noqa: C901
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
    stale_count = sum(1 for r in hlth_items if isinstance(r, dict) and _get_item_status(r) != "ok")
    total_count = len([r for r in hlth_items if isinstance(r, dict)])

    ready_color = G if ready_to_trade else R
    ready_text = "✓ READY" if ready_to_trade else "✗ NOT READY"
    rows.append(
        Text.from_markup(f"[{ready_color}]{ready_text}[/]  [dim]{total_count - stale_count}/{total_count} fresh[/]")
    )

    # Trading halted status (if applicable)
    trading_halted = hlth_dict.get("trading_halted")
    trading_halt_reason = hlth_dict.get("trading_halt_reason")
    if trading_halted and trading_halt_reason:
        halt_age = _format_halt_age(hlth_dict.get("trading_halt_at"))
        manual_note = _format_halt_manual_clear_note(hlth_dict.get("trading_halt_triggered_by"))
        rows.append(
            Text.from_markup(
                f"  [{Y}]→ Trading halted:[/] {str(trading_halt_reason)[:70]}[dim]{halt_age}[/]{manual_note}"
            )
        )

    # ── Loader success rate (NEW) ────────────────────────────────────────────
    if hlth_items:
        succeeded, total, success_rate = _calc_loader_success_rate(hlth_items)
        if success_rate is not None and total > 0:
            rate_color = G if success_rate >= 90 else Y if success_rate >= 70 else R
            rows.append(
                Text.from_markup(
                    f"  [dim]Loader health:[/] [{rate_color}]{success_rate:.0f}% success ({succeeded}/{total})[/]"
                )
            )

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
        if isinstance(r, dict)
        and _get_item_status(r) == "stale"
        and r.get("age") is not None
        and r.get("stale_threshold_days") is not None
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
        return bool(_get_item_status(r) != "ok" and r.get("loader_run_status") == "NOT_STARTED")

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
            rows.append(
                Text.from_markup(
                    f"[dim]Loader queue:[/] [{Y}]{loading_count} active[/]  {queued + loading_count} items pending"
                )
            )

    # ── CURRENTLY LOADING ──────────────────────────────────────
    # Show what's in progress
    in_progress = [
        r for r in hlth_items if isinstance(r, dict) and r.get("execution_started") and not r.get("execution_completed")
    ]
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
    rows.append(Text.from_markup("[dim]→ Press [l] to view full table details and coverage analysis[/]"))

    return Panel(
        Group(*rows),
        title=rf"[bold yellow]DATA FRESHNESS[/]{age_s}  [dim]\[l] expand[/]",
        border_style="yellow",
        padding=(0, 1),
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
            hlth_items=hlth_items,
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
    "panel_data_freshness",
    "panel_data_freshness_expanded",
]
