"""Run-history / phase-health / failure-pattern / past-runs / phase-reliability section
helpers used by health_results_panel.py's _build_results_panel (moved there to stay under
the file-size ratchet's cap).
"""

import logging
from typing import Any

from rich import box
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_int

from ..formatters import fmt_age
from ..utilities import CY, DIM, G, R, Y
from .data_extractors import safe_get_list
from .health_shared import (
    ERROR_STATES,
    HALTED_STATES,
    SKIPPED_STATES,
    SUCCESS_STATES,
    _format_phase_badge,
    _get_status_safe,
)

logger = logging.getLogger(__name__)


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

        status = run.get("status", "unknown").lower()
        started_at = run.get("started_at")
        completed_at = run.get("completed_at")
        halt_reason = run.get("halt_reason")

        # Format status with color and icon.
        # BUG FOUND 2026-08-17 (live-reproduced via LOCAL-MORNING-20260814-120000-000000):
        # this classifier reimplemented its own status buckets instead of using the
        # SUCCESS_STATES/HALTED_STATES/SKIPPED_STATES constants above, and its version never
        # learned "skipped" or "blocked" - both fell into the else clause and rendered as a red
        # ERROR badge. A run that was correctly skipped by the outside-market-hours guard
        # (overall_status="skipped", not a crash) showed up in Run History identical to a
        # genuine phase failure - a false alarm, the exact bug class already fixed in
        # _format_phase_badge/_get_phase_status_badge above but missed here.
        if status in SUCCESS_STATES:
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
        elif status in SKIPPED_STATES or status == "blocked":
            status_icon = "[dim]⊘[/]"
            status_text = "SKIPPED"
            status_color = DIM
        elif status in ERROR_STATES:
            status_icon = "[bold red]✗[/]"
            status_text = "ERROR"
            status_color = R
        else:
            status_icon = "[bold red]✗[/]"
            status_text = "ERROR"
            status_color = R

        # Phase summary
        phase_summary = run.get("phase_summary", {})
        phases_str = f"[{status_color}]{phase_summary.get('completed', 0)}✓[/]"
        if (safe_int(phase_summary.get("halted"), default=0) or 0) > 0:
            phases_str += f" [{Y}]{phase_summary.get('halted')}~[/]"
        if (safe_int(phase_summary.get("errored"), default=0) or 0) > 0:
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
            f"  {rate_icon} P{phase_num} [{rate_color}]{success_rate:.0f}%[/] [dim]({total_runs} runs)[/] {phase_name}"
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

    for pattern in failure_patterns_list[:8]:
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
        rows.insert(0, Text.from_markup("[bold dim]Past runs:[/]"))

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


__all__ = [
    "TOTAL_ORCHESTRATOR_PHASES",
    "_build_algo_metrics_table",
    "_build_halt_reason_pattern_section",
    "_build_past_runs_section",
    "_build_phase_health_section",
    "_build_phase_reliability_section",
    "_build_run_history_section",
    "_fmt_run_duration",
]
