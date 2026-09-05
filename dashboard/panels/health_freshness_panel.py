"""_build_freshness_panel: the full DATA FRESHNESS panel builder. Split out of
health_freshness.py to stay under the file-size ratchet's cap - its section-builder
helpers live in health_freshness_sections.py and are imported back here.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_int
from loaders.loader_timeout_config import get_loader_timeout

from ..error_boundary import has_error
from ..formatters import fmt_age
from ..utilities import DIM, G, R, Y
from .health_freshness_sections import (
    _build_api_diagnostics_section,
    _build_coverage_section,
    _build_data_coverage_section,
    _build_data_quality_section,
    _build_failure_pattern_section,
    _build_system_status_section,
    _fmt_age,
    _format_halt_age,
    _format_halt_manual_clear_note,
)
from .health_shared import _get_item_status

logger = logging.getLogger(__name__)


def _build_freshness_panel(  # noqa: C901
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
        halt_age = _format_halt_age(hlth_dict.get("trading_halt_at"))
        manual_note = _format_halt_manual_clear_note(hlth_dict.get("trading_halt_triggered_by"))
        left_rows.append(
            Text.from_markup(f"[{Y}]→ Trading halted:[/] {trading_halt_reason}[dim]{halt_age}[/]{manual_note}")
        )

    expected_date = hlth_dict.get("expected_date")
    if expected_date:
        left_rows.append(Text.from_markup(f"[dim]Expected data date:[/] {expected_date}"))

    if not hlth_items:
        msg = "⚠ Data health unavailable - loaders may not have run yet.\n"
        msg += "Check Phase 1 orchestrator status or monitor logs."
        left_rows.append(Text(msg, style="dim"))
        return Group(*left_rows)

    stale_count = sum(1 for r in hlth_items if isinstance(r, dict) and _get_item_status(r) != "ok")
    # BUG FIX: This used to flag ANY non-"ok" table (role CRIT/IMP/NORM alike) under the
    # "CRIT STALE" banner, even though the API already computes and attaches a "role" field
    # per table (see dashboard/fetchers_config.py). That meant known-non-critical,
    # intentionally-not-always-populated tables (e.g. equity_curve_daily, algo_untracked_positions
    # - see lambda/api/routes/algo_handlers/market.py's own comments on those two) triggered the
    # same red "CRIT STALE" alarm as an actually-critical table like price_daily, producing false
    # TRIGGERED/NOT READY-looking alarms. Filter to role == "CRIT" so the banner matches its label.
    crit_stale = [
        r for r in hlth_items if isinstance(r, dict) and _get_item_status(r) != "ok" and r.get("role") == "CRIT"
    ]

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
    loader_errors_genuine = 0
    loader_errors_reaped_only = 0
    if hlth_dict and isinstance(hlth_dict, dict):
        summary_data = hlth_dict.get("summary")
        if isinstance(summary_data, dict):
            loader_errors_count = summary_data.get("loaders_with_errors", 0)
            total_loader_failures = summary_data.get("total_loader_failures", 0)
            # Backend splits reaped-abandoned-process artifacts (self-heal automatically -
            # see market.py's _is_reaped_artifact) out of the raw count. Older cached API
            # responses won't have these keys - fall back to "assume all genuine" so this
            # degrades to the previous behavior instead of erroring.
            loader_errors_genuine = summary_data.get("loaders_with_errors_genuine", int(loader_errors_count))
            loader_errors_reaped_only = summary_data.get("loaders_with_errors_reaped_only", 0)

    # Check for execution guards that block trading (Phase 8 price check, market hours, etc)
    # CRITICAL: ready_to_trade=False can mean either:
    # 1. Data freshness issue (Phase 1 detected stale data at startup)
    # 2. Execution guard blocked entry (Phase 8 price too old, market closed, etc)
    # These are different problems with different actions. Show the actual blocker.
    rtt_part = ""
    if ready_to_trade:
        rtt_part = f"  [bold {G}]✓ READY TO TRADE[/]"
        # READY TO TRADE only reflects data freshness + halt-flag state (see market.py's
        # ready_to_trade = data_fresh_enough and not trading_halted) - it never looks at
        # the quality/coverage checks below, so it can read as an all-clear right next to
        # a real NULL-rate or coverage problem this same panel is about to list. Caveat it
        # rather than let the two disagree silently (2026-08-21 user-reported confusion).
        dq_tables = sum(
            1 for r in hlth_items if isinstance(r, dict) and r.get("quality_status") in ("warning", "error")
        )
        cov_tables = sum(
            1 for r in hlth_items if isinstance(r, dict) and r.get("coverage_status") in ("partial", "sparse")
        )
        if dq_tables or cov_tables:
            caveat_bits = []
            if dq_tables:
                caveat_bits.append(f"{dq_tables} quality")
            if cov_tables:
                caveat_bits.append(f"{cov_tables} coverage")
            rtt_part += f"  [{Y}]({'/'.join(caveat_bits)} issue(s) below)[/]"
    elif not ready_to_trade:
        # Check for orchestrator halt reason (from latest run)
        halt_reason = hlth_dict.get("trading_halt_reason") if hlth_dict else None
        if halt_reason:
            halt_str = str(halt_reason)[:90]
            if "PRICE" in halt_str.upper():
                rtt_part = f"  [{R}]Phase 8 Price Check BLOCKED[/]: {halt_str[:50]}"
            elif "MARKET HOURS" in halt_str.upper():
                rtt_part = f"  [{Y}]Phase 8 Market Hours BLOCKED[/]"
            elif "CIRCUIT" in halt_str.upper():
                rtt_part = f"  [{R}]Circuit Breaker HALTED[/]: {halt_str[:50]}"
            else:
                rtt_part = f"  [{R}]HALTED[/]: {halt_str[:60]}"
        else:
            rtt_part = f"  [bold {R}]✗ NOT READY (data stale)[/]"

    status_c = G if stale_count == 0 else (Y if stale_count <= 2 else R)
    freshness_line = f"[dim]Freshness:[/] [{status_c}]{len(hlth_items) - stale_count}/{len(hlth_items)} fresh[/]" + (
        f"  [{R}]{stale_count} stale[/]" if stale_count else ""
    )

    # Add loader error info if there are any. Colored (and counted for urgency) off the
    # GENUINE count, not the raw total - a loader whose only failure is an abandoned-process
    # reap artifact is lower-severity than an actually-broken loader, so it shouldn't read
    # as red-alert the same way.
    #
    # ACCURACY FIX 2026-08-17: this used to say "self-healing", implying a retry is already
    # in flight. Live-verified false: a batch of 11 tables reaped at 05:32:23 sat FAILED for
    # 5+ hours with no retry queued anywhere - the intended watcher chain
    # (logs/pipeline_watcher_chain.log) died silently after its first log line, and "reaped"
    # only means the stuck status row got cleared, not that anything is re-running it. The
    # only real auto-retry path locally is the orchestrator's Phase 1 failsafe sweep on its
    # next scheduled run (930AM/1PM/3PM tasks, market-hours-gated) or a human re-running the
    # owning pipeline - neither is guaranteed "soon". Don't claim healing that isn't
    # confirmed in flight.
    if loader_errors_count > 0:
        error_color = R if loader_errors_genuine >= 3 else (Y if loader_errors_genuine > 0 else "dim")
        freshness_line += (
            f"  [{error_color}]{loader_errors_genuine} loader(s) with errors ({total_loader_failures} total)[/]"
        )
        if loader_errors_reaped_only > 0:
            freshness_line += f"  [dim]({loader_errors_reaped_only} reaped - not yet retried)[/]"

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
            # A table can be fresh (st == "ok") while freshness_enhancements.py's separate
            # NULL-ratio/coverage checks found a real problem in it - quality_status/
            # coverage_status are populated independently of `st` (see market.py's
            # _get_data_status). Without this, this exact row shows a bare green ✓ "ok"
            # right next to the Data Quality Issues section calling out the same table
            # (2026-08-21 user-reported: "how is it saying data OK when I'm seeing real
            # issues" - trend_template_data showed ✓ ok here with weinstein_stage 11% NULL).
            has_quality_issue = ok and r.get("quality_status") in ("warning", "error")
            has_coverage_issue = ok and r.get("coverage_status") in ("partial", "sparse")
            if has_quality_issue or has_coverage_issue:
                ic = Y
                ii = "⚠"
            else:
                ic = G if ok else (Y if st == "empty" else R)
                ii = "✓" if ok else ("-" if st == "empty" else "✗")
            if st not in ("ok", "empty"):
                logger.debug(f"[HEALTH] Health item {nm} status '{st}' mapped to RED color indicator")
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

            if has_quality_issue or has_coverage_issue:
                st_label = "QA"
            else:
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
                Text(
                    st_label,
                    style=Y
                    if (has_quality_issue or has_coverage_issue)
                    else (G if ok else (Y if st == "empty" else R)),
                ),
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
        if _get_item_status(r) != "ok" and r.get("loader_run_status") == "NOT_STARTED"
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
            # Elapsed runtime + a timeout-risk flag against this table's own configured
            # timeout (loaders/loader_timeout_config.py - the same single source of truth
            # reap_stale_running_loaders() and phase1_failsafe_retry.py already use).
            #
            # ROOT-CAUSE FIX 2026-08-17: this used to flag ANY loader past a flat 90-minute
            # mark ("the dashboard has no per-process visibility into the actual configured
            # value" - no longer true, loader_timeout_config.py is a plain dict, safe to
            # import here) - same anti-pattern already fixed in reap_stale_running_loaders()
            # and mirrored in lambda/api/routes/algo_handlers/monitoring.py's loader_health
            # unhealthy-count (fixed alongside this). Real timeouts range ~10min-1440min
            # (price_daily=24h) - a healthy price_daily/company_info_sec run past 90min was
            # false-flagged "TIMEOUT RISK" here despite using a fraction of its real budget.
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
                    tbl_name_for_timeout = r.get("tbl")
                    timeout_min = (
                        get_loader_timeout(tbl_name_for_timeout, default_seconds=90 * 60) / 60
                        if tbl_name_for_timeout
                        else 90
                    )
                    if elapsed_min > timeout_min:
                        risk_s = f" [{R}]⚠ TIMEOUT RISK[/]"
            except (TypeError, ValueError):
                pass
            left_rows.append(
                Text.from_markup(
                    f"  [{Y}]⟳ {r.get('tbl') or 'unknown'}:[/] {pct_s}{cnt_s} [dim]running {elapsed_label}[/]{risk_s}"
                )
            )

    # Stale-table detail: each table's own configured cadence (stale_threshold_days), so
    # "STALE at 3 days old" (a 1-day table) reads differently from "STALE at 10 days old"
    # (a 7-day table already 3 days past its own threshold) instead of just a bare age.
    stale_detail = [
        (r.get("tbl") or "unknown", r.get("age"), r.get("stale_threshold_days"))
        for r in sorted_items
        if _get_item_status(r) == "stale" and r.get("age") is not None and r.get("stale_threshold_days") is not None
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
            left_rows.append(
                Text.from_markup(f"  [{Y}]{tbl_name}:[/] [dim]same row count across last 3+ runs{since_s}[/]")
            )
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


__all__ = [
    "_build_freshness_panel",
]
