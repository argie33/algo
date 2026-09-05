"""Data-freshness section-builder helpers (small, focused Rich-renderable chunks) used by
health_freshness_panel.py's _build_freshness_panel and by panel_data_freshness/
panel_data_freshness_expanded in health_freshness.py. Split out once health_freshness.py
grew past the file-size ratchet's cap.
"""

import logging
from datetime import datetime, timezone
from typing import Any, cast

from rich.rule import Rule
from rich.text import Text

from ..utilities import CY, G, R, Y
from .health_shared import _get_item_status

logger = logging.getLogger(__name__)


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


def _calc_data_completeness(hlth_items: list[Any]) -> dict[str, tuple[int, int]]:
    """Calculate data completeness by criticality (ready, total).

    Returns: {"CRIT": (8, 8), "IMP": (12, 13), "NORM": (32, 40)}
    """
    by_role = {}
    for r in hlth_items:
        if not isinstance(r, dict):
            continue
        role = r.get("role", "NORM")
        st = _get_item_status(r)
        if role not in by_role:
            by_role[role] = {"ready": 0, "total": 0}
        by_role[role]["total"] += 1
        if st == "ok":
            by_role[role]["ready"] += 1

    return {role: (data["ready"], data["total"]) for role, data in by_role.items()}


def _format_halt_age(trading_halt_at: Any) -> str:
    """Format how long ago the current halt was triggered, e.g. '(2h 15m ago)'.

    trading_halt_at now comes from algo_runtime_state.halt_triggered_at - the same flag
    HaltFlagManager gates every phase on - not the latest orchestrator_runs log row, so
    this age reflects how long the real block has been active, not how old the last run is.
    """
    if not trading_halt_at or not isinstance(trading_halt_at, str):
        return ""
    try:
        halt_dt = datetime.fromisoformat(trading_halt_at)
        if halt_dt.tzinfo is None:
            halt_dt = halt_dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - halt_dt
    except ValueError:
        return ""
    total_minutes = int(age.total_seconds() // 60)
    if total_minutes < 0:
        return ""
    hours, minutes = divmod(total_minutes, 60)
    return f" ({hours}h {minutes}m ago)" if hours else f" ({minutes}m ago)"


# Mirrors HaltFlagManager._check_halt_flag_rds's eligible_for_calendar_auto_expiry allowlist
# (algo/orchestration/halt_flag_manager.py) - anything outside it (governance/manual halts)
# requires an explicit human clear via scripts/manage_halt_flag.py and will NOT self-resolve
# just because a new trading day started.
_AUTO_EXPIRING_HALT_TRIGGERS = ("phase1_data_freshness", "phase2_circuit_breaker")


def _format_halt_manual_clear_note(triggered_by: Any) -> str:
    """Flag halts that will not self-clear and need scripts/manage_halt_flag.py."""
    if not triggered_by or triggered_by in _AUTO_EXPIRING_HALT_TRIGGERS:
        return ""
    return " [dim](requires manual clear)[/]"


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
    loading = sum(
        1 for r in hlth_items if isinstance(r, dict) and r.get("execution_started") and not r.get("execution_completed")
    )
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
        st = _get_item_status(r)
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
                coverage_gaps.append(
                    (r.get("tbl") or "unknown", coverage_pct, r.get("missing_symbols", []), r.get("coverage_status"))
                )

    if not coverage_gaps:
        return rows

    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[bold {Y}]Coverage Gaps:[/]"))

    for tbl_name, coverage_pct, missing_syms, status in coverage_gaps[:8]:
        status_color = R if status == "sparse" else Y if status == "partial" else G
        coverage_str = f"{coverage_pct:.1f}% coverage"
        missing_str = f" (missing: {', '.join(missing_syms)})" if missing_syms else ""
        rows.append(Text.from_markup(f"  [{status_color}]{tbl_name}:[/] [dim]{coverage_str}{missing_str}[/]"))

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
                failure_data.append(
                    (
                        r.get("tbl") or "unknown",
                        failure_rate,
                        r.get("failure_pattern"),
                        r.get("mttr_hours"),
                        r.get("recovery_trend"),
                        r.get("last_5_runs"),
                    )
                )

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
                api_issues.append(
                    (r.get("tbl") or "unknown", api_status, r.get("rate_limit_quota"), r.get("retry_strategy"))
                )

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
            system_issues.append(f"[bold {R}]Signal Freshness:[/] [dim]STALE ({signal_age_hours}h old)[/]")
        elif freshness_status == "OK" and signal_age_hours and signal_age_hours > 12:
            system_issues.append(f"[bold {Y}]Signal Freshness:[/] [dim]OK but aging ({signal_age_hours}h old)[/]")

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


def _build_loader_health_section(
    loader_health: list[Any] | None,
    total_unhealthy: int | None = None,
    total_tracked: int | None = None,
    hlth_items: list[Any] | None = None,
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
        hlth_items: Per-table freshness rows enriched by freshness_enhancements.py
            (data_quality_issues/quality_status, coverage_status). "Loader Health" here
            only measures job EXECUTION (did the run finish without error) - it says
            nothing about whether the resulting data is complete/correct. Without this,
            a table with an 11% NULL rate in a critical column, or a real coverage gap,
            still renders "All loaders healthy" - a real user-facing incident (2026-08-21:
            reported as "how is it saying data OK when I'm seeing real issues") caused by
            these two signals never being reconciled anywhere in the display.

    Returns list of Rich Text/Rule objects for display.
    """
    rows: list[Text | Rule] = []

    unhealthy = (
        [lh for lh in loader_health if isinstance(lh, dict) and lh.get("is_unhealthy")]
        if isinstance(loader_health, list)
        else []
    )
    # total_unhealthy is the authoritative count (computed backend-side before any
    # capping) - fall back to len(unhealthy) only when the backend didn't send it, e.g.
    # against an older cached response.
    unhealthy_count = total_unhealthy if total_unhealthy is not None else len(unhealthy)

    quality_issue_count = 0
    coverage_issue_count = 0
    if isinstance(hlth_items, list):
        quality_issue_count = sum(
            1
            for r in hlth_items
            if isinstance(r, dict) and r.get("quality_status") in ("warning", "error") and r.get("data_quality_issues")
        )
        coverage_issue_count = sum(
            1 for r in hlth_items if isinstance(r, dict) and r.get("coverage_status") in ("partial", "sparse")
        )

    rows.append(Rule(style="dim"))
    if unhealthy_count == 0:
        tracked_str = f" ({total_tracked} tracked)" if total_tracked is not None else ""
        if quality_issue_count == 0 and coverage_issue_count == 0:
            rows.append(Text.from_markup(f"[bold {G}]Loader Health:[/] All loaders healthy ✓{tracked_str}"))
        else:
            # Loaders ran fine (this line's actual scope) - but say so narrowly, and point
            # at the real problem instead of implying the data itself is fine too.
            issue_bits = []
            if quality_issue_count:
                issue_bits.append(f"{quality_issue_count} with data quality issues")
            if coverage_issue_count:
                issue_bits.append(f"{coverage_issue_count} with coverage gaps")
            rows.append(
                Text.from_markup(
                    f"[bold {G}]Loader Health:[/] All loaders executing normally ✓{tracked_str}  "
                    f"[bold {Y}]but {', '.join(issue_bits)}[/] [dim](see below)[/]"
                )
            )
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
        # Same caveat as the expanded panel (_build_freshness_panel) - READY TO TRADE is
        # freshness/halt-flag only, so surface known quality/coverage issues here too
        # instead of letting the compact badge read as an unqualified all-clear.
        issue_tables = sum(
            1
            for r in hlth_list
            if isinstance(r, dict)
            and (r.get("quality_status") in ("warning", "error") or r.get("coverage_status") in ("partial", "sparse"))
        )
        if issue_tables:
            rtt_badge += f"  [{Y}]⚠ {issue_tables} data issue(s)[/]"
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


__all__ = [
    "_AUTO_EXPIRING_HALT_TRIGGERS",
    "_age_fmt_c",
    "_age_h",
    "_build_api_diagnostics_section",
    "_build_coverage_section",
    "_build_data_coverage_section",
    "_build_data_quality_section",
    "_build_failure_pattern_section",
    "_build_loader_health_section",
    "_build_system_status_section",
    "_build_trend_summary_section",
    "_calc_data_completeness",
    "_calc_loader_queue_depth",
    "_calc_loader_success_rate",
    "_fmt_age",
    "_fmt_updated",
    "_format_halt_age",
    "_format_halt_manual_clear_note",
    "_format_health_data_fresh_section",
    "_format_health_data_stale_section",
    "_get_most_critical_issues",
]
