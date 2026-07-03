"""Formatting and utility functions for dashboard display."""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, cast

from .error_boundary import has_error
from .formatter_strategies import (
    DataAgeFormatter,
    GradeFormatter,
    MoneyFormatter,
    SignFormatter,
    TierFormatter,
)
from .utilities import (
    CY,
    DIM,
    ET,
    SPARKLINE_CHARS,
    TIER_COLOR,
    G,
    R,
    Y,
)

logger = logging.getLogger(__name__)

_schedule_cache: dict[str, Any] = {"result": None, "timestamp": 0}
_SCHEDULE_CACHE_TTL = 300

_age_formatter = DataAgeFormatter()
_money_formatter = MoneyFormatter(short=False)
_money_short_formatter = MoneyFormatter(short=True)
_grade_formatter = GradeFormatter()
_tier_formatter = TierFormatter()
_sign_formatter = SignFormatter()


def fmt_age(ts: Any) -> str:
    """Format timestamp as age string."""
    return _age_formatter.format(ts)


def fmt_money(v: Any) -> str:
    """Format value as currency: $1.23, $12.34K, $1.23M."""
    return _money_formatter.format(v)


def fmt_money_short(v: Any) -> str:
    """Compact dollar format: $45K, $1.2M, $850 - for narrow table columns."""
    return _money_short_formatter.format(v)


def is_open() -> bool:
    """Check if market is currently open. Uses MarketCalendar for accurate trading hours."""
    try:
        from algo.infrastructure import MarketCalendar

        return MarketCalendar.is_market_open()
    except (ImportError, AttributeError):
        n = datetime.now(ET)
        if n.weekday() >= 5:
            return False
        t = n.hour * 60 + n.minute
        return 570 <= t <= 960


def mkt_hours_str() -> tuple[str, str]:
    """Returns (status_markup, countdown_str) reflecting pre-mkt/open/after-hrs/closed.

    Uses MarketCalendar for accurate trading hours including holidays and early closes.
    Falls back to hardcoded hours if calendar unavailable.

    After-hours status shows "[orange1]⊘ MARKET CLOSED[/]" to make it clear the market
    is not trading while all data (VIX, hi/lo, etc.) remains fully visible and relevant.
    """
    try:
        from algo.infrastructure import MarketCalendar

        status = MarketCalendar.market_status()
        status_val = status.get("status", "UNKNOWN")
        reason = status.get("reason", "")

        if status_val == "OPEN":
            return "[bold bright_green]◆ OPEN[/]", reason
        elif status_val == "PRE_MARKET":
            return "[yellow]◇ PRE-MKT[/]", reason
        elif status_val == "AFTER_HOURS":
            return "[orange1]⊘ AFTER-HRS[/]", reason
        else:
            return "[orange1]⊘ CLOSED[/]", reason
    except Exception as market_err:
        import logging

        logging.critical(  # noqa: LOG015
            f"MarketCalendar unavailable: {market_err} — cannot determine market status safely"
        )
        raise RuntimeError(
            "Market calendar required for accurate market status; refusing to trade based on hardcoded hours"
        ) from market_err


def next_run_str() -> str:
    """Return next orchestrator run time. Fetches schedule from API if available, falls back to hardcoded."""
    now = time.time()
    if (
        _schedule_cache["result"] is not None
        and _schedule_cache["timestamp"] is not None
        and (now - _schedule_cache["timestamp"]) < _SCHEDULE_CACHE_TTL
    ):
        return cast(str, _schedule_cache["result"])

    try:
        from .api_data_layer import api_call

        resp = api_call("/api/algo/schedule")
        if not has_error(resp) and "schedule" in resp:
            schedule = resp.get("schedule")
            if schedule and isinstance(schedule, list):
                result = _next_run_from_schedule(schedule)
                _schedule_cache["result"] = result
                _schedule_cache["timestamp"] = now
                return result
    except Exception as sched_err:
        import logging

        logging.warning(f"Schedule API unavailable: {sched_err}. Dashboard showing fallback times.")  # noqa: LOG015

    # Schedule fetch failed: indicate to user that times shown are not live
    try:
        result = _next_run_hardcoded()
        result = f"[yellow]{result}[/yellow] (offline schedule)"
    except Exception as e:
        logger.warning(f"Hardcoded schedule calculation failed: {e}. Using minimal fallback.")
    _schedule_cache["result"] = result
    _schedule_cache["timestamp"] = now
    return result


def _validate_schedule_entry(s: dict[str, Any]) -> tuple[int, int]:
    """Validate schedule entry has required fields. Fail fast if corrupted."""
    if "hour" not in s or "minute" not in s:
        raise ValueError(
            f"Schedule entry missing required fields: {s}. "
            f"All schedule entries must have 'hour' and 'minute' fields. "
            f"Corrupted configuration prevents safe scheduling."
        )
    hour = s["hour"]
    minute = s["minute"]
    if not isinstance(hour, int) or not isinstance(minute, int):
        raise ValueError(
            f"Schedule entry has invalid types: hour={type(hour).__name__}, minute={type(minute).__name__}. "
            f"Both must be integers. Entry: {s}"
        )
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise ValueError(
            f"Schedule entry has invalid time values: {hour:02d}:{minute:02d}. "
            f"Hour must be 0-23, minute must be 0-59. Entry: {s}"
        )
    return hour, minute


def _next_run_from_schedule(schedule: list[dict[str, Any]]) -> str:
    """Calculate next run from dynamic schedule (list of {hour, minute} dicts).

    CRITICAL: Validates that all schedule entries have required hour/minute fields.
    Missing fields indicate corrupted configuration — raise error instead of defaulting.
    """
    now = datetime.now(ET)
    wd = now.weekday()
    t = now.hour * 60 + now.minute

    def fmt(dt: datetime) -> str:
        diff = dt - now
        mins = int(diff.total_seconds() / 60)
        if mins < 60:
            return f"in {mins}m"
        if mins < 1440:
            return f"in {mins // 60}h{mins % 60:02d}m"
        return f"{dt.strftime('%a %I:%M %p')}"

    def next_wkd(dt: datetime, off: int = 1) -> datetime:
        d = dt + timedelta(days=off)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    if wd >= 5:
        next_day = next_wkd(now)
        if schedule:
            sched = sorted(schedule, key=lambda s: _validate_schedule_entry(s)[0] * 60 + _validate_schedule_entry(s)[1])
            first_run = sched[0]
            hour, minute = _validate_schedule_entry(first_run)
            run_dt = next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return f"orch {fmt(run_dt)}"
        return f"orch {fmt(next_day.replace(hour=9, minute=30, second=0, microsecond=0))}"

    today_runs = sorted(schedule, key=lambda s: _validate_schedule_entry(s)[0] * 60 + _validate_schedule_entry(s)[1])
    for run in today_runs:
        hour, minute = _validate_schedule_entry(run)
        run_t = hour * 60 + minute
        if run_t > t:
            run_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return f"orch {fmt(run_dt)}"

    next_day = next_wkd(now)
    if today_runs:
        first_run = today_runs[0]
        hour, minute = _validate_schedule_entry(first_run)
        run_dt = next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return f"orch {fmt(run_dt)}"
    return f"orch {fmt(next_day.replace(hour=9, minute=30, second=0, microsecond=0))}"


def _next_run_hardcoded() -> str:
    """Fallback: Calculate next run using configured schedule when API unavailable.

    Uses default schedule from MarketSymbolsConfig (configurable via algo_config table).
    """
    from utils.market_symbols_config import MarketSymbolsConfig

    now = datetime.now(ET)
    wd = now.weekday()
    t = now.hour * 60 + now.minute

    def fmt(dt: datetime) -> str:
        diff = dt - now
        mins = int(diff.total_seconds() / 60)
        if mins < 60:
            return f"in {mins}m"
        if mins < 1440:
            return f"in {mins // 60}h{mins % 60:02d}m"
        return f"{dt.strftime('%a %I:%M %p')}"

    def next_wkd(dt: datetime, off: int = 1) -> datetime:
        d = dt + timedelta(days=off)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    # Get schedule from configuration (or defaults if not configured)
    try:
        schedule = MarketSymbolsConfig.get_orchestrator_schedule()
    except Exception as e:
        logger.warning(f"Failed to load orchestrator schedule from config: {e}. Using defaults.")
        schedule = None

    if not schedule:
        # Safety fallback if config is empty or failed to load
        schedule = [{"hour": 2, "minute": 0}, {"hour": 9, "minute": 30}]

    # Find next scheduled run
    if wd < 5:
        # Weekday: find next run today
        today_runs = []
        for run in schedule:
            hour, minute = _validate_schedule_entry(run)
            run_t = hour * 60 + minute
            if run_t > t:
                run_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                today_runs.append((run_t, run_dt))

        if today_runs:
            next_run_dt = sorted(today_runs)[0][1]
            run_type = "orch" if next_run_dt.hour >= 9 else "prep"
            return f"{run_type} {fmt(next_run_dt)}"

    # No run today (or past market close on weekday) - show first run tomorrow
    if schedule:
        first_run = schedule[0]
        hour, minute = _validate_schedule_entry(first_run)
        tgt = next_wkd(now).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        run_type = "prep" if tgt.hour < 9 else "orch"
        return f"{run_type} {fmt(tgt)}"

    # Absolute fallback (should never reach here)
    return "schedule unavailable"


def hbar(cur: Any, thr: Any, w: int = 6) -> str:
    if thr is None:
        return f"[red]{'✗' * w}[/]"
    if cur is None:
        return f"[red]{'✗' * w}[/]"
    thr_f = float(thr)
    cur_f = float(cur)
    if thr_f > 0:
        r = min(cur_f / thr_f, 1.0) if thr_f != 0 else 0
    elif thr_f < 0 and cur_f < 0:
        r = min(cur_f / thr_f, 1.0) if thr_f != 0 else 0
    else:
        r = 0
    f = int(r * w)
    c = R if r >= 1 else (Y if r >= 0.75 else G)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"


def exp_bar(pct: Any, w: int = 12) -> str:
    if pct is None:
        # Missing data: show error indicator
        return f"[red]{'✗' * w}[/]"
    f = int(min(float(pct), 100) / 100 * w)
    tc = TIER_COLOR.get(_tier_formatter.format(pct), "dim")
    return f"[{tc}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"


def mini_bar(pts: Any, max_pts: Any, w: int = 5) -> str:
    if pts is None or max_pts is None:
        # Missing data: show error indicator
        return f"[red]{'✗' * w}[/]"
    r = min(float(pts) / float(max_pts) if float(max_pts) > 0 else 0, 1.0)
    f = int(r * w)
    c = G if r >= 0.75 else (Y if r >= 0.35 else R)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"


def sign(v: Any) -> str:
    """Return '+' for non-negative values, empty string for negative."""
    return _sign_formatter.format(v)


def sparkline(values: list[Any], width: int = 24) -> str:
    if values is None:
        logger.warning("Sparkline formatter received None values, upstream metric data unavailable")
        raise ValueError(
            "Sparkline formatter received None values, upstream metric data unavailable. "
            "Dashboard must distinguish empty data from unavailable data."
        )

    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return f"[{DIM}]No data[/]"
    mn, mx = min(vals), max(vals)
    if mx == mn:
        return f"[{CY}]{'▄' * width}[/]"
    rng = mx - mn
    if len(vals) > width:
        idxs = [int(i * (len(vals) - 1) / (width - 1)) for i in range(width)]
        sampled = [vals[i] for i in idxs]
    else:
        sampled = [vals[0]] * (width - len(vals)) + vals
    sampled = sampled[:width]
    chars = "".join(SPARKLINE_CHARS[min(7, int((v - mn) / rng * 7.9999))] for v in sampled)
    c = G if sampled[-1] >= sampled[0] else R
    return f"[{c}]{chars}[/]"
