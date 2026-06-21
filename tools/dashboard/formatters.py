"""Formatting and utility functions for dashboard display."""

import time
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any, cast

from .error_boundary import has_error
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


_schedule_cache: dict[str, Any] = {"result": None, "timestamp": 0}
_SCHEDULE_CACHE_TTL = 300


def fmt_age(ts):
    if ts is None:
        return "--"
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if isinstance(ts, _date) and not isinstance(ts, datetime):
        ts = datetime(ts.year, ts.month, ts.day, tzinfo=ET)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    m = int((datetime.now(ET) - ts).total_seconds() / 60)
    if m < 60:
        return f"{m}m ago"
    if m < 1440:
        return f"{m // 60}h{m % 60:02d}m ago"
    return f"{m // 1440}d ago"


def fmt_money(v):
    if v is None:
        return "--"
    from decimal import ROUND_HALF_UP, Decimal
    if isinstance(v, Decimal):
        is_neg = v < 0
        av = abs(v)
        if av >= 1e6:
            result = (av / Decimal("1e6")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"{'-' if is_neg else ''}${result}M"
        if av >= 1e3:
            result = av.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return f"{'-' if is_neg else ''}${result:,}"
        result = av.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{'-' if is_neg else ''}${result}"
    v = float(v)
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6:
        return f"{s}${av / 1e6:.2f}M"
    if av >= 1e3:
        return f"{s}${av:,.0f}"
    return f"{s}${av:.2f}"


def fmt_money_short(v):
    """Compact dollar format: $45K, $1.2M, $850 - for narrow table columns."""
    if v is None:
        return "--"
    from decimal import ROUND_HALF_UP, Decimal
    if isinstance(v, Decimal):
        is_neg = v < 0
        av = abs(v)
        if av >= 1e6:
            result = (av / Decimal("1e6")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            return f"{'-' if is_neg else ''}${result}M"
        if av >= 1e3:
            result = (av / Decimal("1e3")).quantize(Decimal("0"), rounding=ROUND_HALF_UP)
            return f"{'-' if is_neg else ''}${result}K"
        result = av.quantize(Decimal("0"), rounding=ROUND_HALF_UP)
        return f"{'-' if is_neg else ''}${result}"
    v = float(v)
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6:
        return f"{s}${av / 1e6:.1f}M"
    if av >= 1e3:
        return f"{s}${av / 1e3:.0f}K"
    return f"{s}${av:.0f}"


def grade(s):
    s = float(s)
    if s >= 90:
        return "A+"
    if s >= 80:
        return "A"
    if s >= 70:
        return "B"
    if s >= 60:
        return "C"
    return "D"


def tier_from_pct(p) -> str:
    if p is None:
        return "unknown"
    p = float(p)
    if p >= 80:
        return "confirmed_uptrend"
    if p >= 60:
        return "healthy_uptrend"
    if p >= 40:
        return "pressure"
    if p >= 20:
        return "caution"
    return "correction"


def is_open() -> bool:
    """Check if market is currently open. Uses MarketCalendar for accurate trading hours."""
    try:
        from algo.infrastructure import MarketCalendar

        return cast(bool, MarketCalendar.is_market_open())
    except Exception:
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

        logging.debug(  # noqa: LOG015
            f"Could not get market status from calendar: {market_err}, using fallback"
        )

    n = datetime.now(ET)
    wd = n.weekday()
    t = n.hour * 60 + n.minute

    def _fmt_mins(m):
        h, mm = divmod(m, 60)
        return f"{h}h{mm:02d}m" if h > 0 else f"{mm}m"

    if wd >= 5:
        days_ahead = 7 - wd
        open_dt = (n + timedelta(days=days_ahead)).replace(hour=9, minute=30, second=0, microsecond=0)
        diff_m = max(0, int((open_dt - n).total_seconds() / 60))
        return (
            "[orange1]⊘ CLOSED[/]",
            f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}",
        )

    PRE_OPEN = 4 * 60  # noqa: N806
    OPEN = 9 * 60 + 30  # noqa: N806
    CLOSE = 16 * 60  # noqa: N806
    AH_END = 20 * 60  # noqa: N806

    if t < PRE_OPEN:
        diff_m = OPEN - t
        return "[orange1]⊘ CLOSED[/]", f"opens in {_fmt_mins(diff_m)}"
    if t < OPEN:
        diff_m = OPEN - t
        return "[yellow]◇ PRE-MKT[/]", f"opens in {_fmt_mins(diff_m)}"
    if t < CLOSE:
        diff_m = CLOSE - t
        return "[bold bright_green]◆ OPEN[/]", f"closes in {_fmt_mins(diff_m)}"
    if t < AH_END:
        next_days = 3 if wd == 4 else 1
        open_dt = (n + timedelta(days=next_days)).replace(hour=9, minute=30, second=0, microsecond=0)
        diff_m = max(0, int((open_dt - n).total_seconds() / 60))
        return (
            "[orange1]⊘ AFTER-HRS[/]",
            f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}",
        )
    next_days = 3 if wd == 4 else 1
    open_dt = (n + timedelta(days=next_days)).replace(hour=9, minute=30, second=0, microsecond=0)
    diff_m = max(0, int((open_dt - n).total_seconds() / 60))
    return "[orange1]⊘ CLOSED[/]", f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}"


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

        logging.debug(  # noqa: LOG015
            f"Could not fetch next run schedule: {sched_err}, using fallback"
        )

    result = _next_run_hardcoded()
    _schedule_cache["result"] = result
    _schedule_cache["timestamp"] = now
    return result


def _next_run_from_schedule(schedule: list) -> str:
    """Calculate next run from dynamic schedule (list of {hour, minute} dicts)."""
    now = datetime.now(ET)
    wd = now.weekday()
    t = now.hour * 60 + now.minute

    def fmt(dt):
        diff = dt - now
        mins = int(diff.total_seconds() / 60)
        if mins < 60:
            return f"in {mins}m"
        if mins < 1440:
            return f"in {mins // 60}h{mins % 60:02d}m"
        return f"{dt.strftime('%a %I:%M %p')}"

    def next_wkd(dt, off=1):
        d = dt + timedelta(days=off)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    if wd >= 5:
        next_day = next_wkd(now)
        if schedule:
            sched = sorted(schedule, key=lambda s: s.get("hour", 0) * 60 + s.get("minute", 0))
            first_run = sched[0]
            run_dt = next_day.replace(
                hour=first_run.get("hour", 9),
                minute=first_run.get("minute", 30),
                second=0,
                microsecond=0,
            )
            return f"orch {fmt(run_dt)}"
        return f"orch {fmt(next_day.replace(hour=9, minute=30, second=0, microsecond=0))}"

    today_runs = sorted(schedule, key=lambda s: s.get("hour", 0) * 60 + s.get("minute", 0))
    for run in today_runs:
        run_t = run.get("hour", 9) * 60 + run.get("minute", 30)
        if run_t > t:
            run_dt = now.replace(
                hour=run.get("hour", 9),
                minute=run.get("minute", 30),
                second=0,
                microsecond=0,
            )
            return f"orch {fmt(run_dt)}"

    next_day = next_wkd(now)
    if today_runs:
        first_run = today_runs[0]
        run_dt = next_day.replace(
            hour=first_run.get("hour", 9),
            minute=first_run.get("minute", 30),
            second=0,
            microsecond=0,
        )
        return f"orch {fmt(run_dt)}"
    return f"orch {fmt(next_day.replace(hour=9, minute=30, second=0, microsecond=0))}"


def _next_run_hardcoded() -> str:
    """Fallback: Calculate next run using hardcoded schedule (9:30 AM, 1 PM, 3 PM, 5:30 PM ET)."""
    now = datetime.now(ET)
    wd = now.weekday()
    t = now.hour * 60 + now.minute

    def fmt(dt):
        diff = dt - now
        mins = int(diff.total_seconds() / 60)
        if mins < 60:
            return f"in {mins}m"
        if mins < 1440:
            return f"in {mins // 60}h{mins % 60:02d}m"
        return f"{dt.strftime('%a %I:%M %p')}"

    def next_wkd(dt, off=1):
        d = dt + timedelta(days=off)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    if wd < 5:
        if t < 120:
            return f"prep {fmt(now.replace(hour=2, minute=0, second=0, microsecond=0))}"
        if t < 570:
            return f"orch {fmt(now.replace(hour=9, minute=30, second=0, microsecond=0))}"
        tgt = next_wkd(now).replace(hour=2, minute=0, second=0, microsecond=0)
        return f"prep {fmt(tgt)}"
    tgt = next_wkd(now).replace(hour=2, minute=0, second=0, microsecond=0)
    return f"prep {fmt(tgt)}"


def hbar(cur, thr, w=6):
    thr_f = float(thr) if thr else 0
    cur_f = float(cur) if cur is not None else 0
    if thr_f > 0:
        r = min(cur_f / thr_f, 1.0) if thr_f != 0 else 0
    elif thr_f < 0 and cur_f < 0:
        r = min(cur_f / thr_f, 1.0) if thr_f != 0 else 0
    else:
        r = 0
    f = int(r * w)
    c = R if r >= 1 else (Y if r >= 0.75 else G)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"


def exp_bar(pct, w=12):
    f = int(min(float(pct or 0), 100) / 100 * w)
    tc = TIER_COLOR.get(tier_from_pct(pct), "dim")
    return f"[{tc}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"


def mini_bar(pts, max_pts, w=5):
    r = min(float(pts or 0) / float(max_pts or 1), 1.0)
    f = int(r * w)
    c = G if r >= 0.75 else (Y if r >= 0.35 else R)
    return f"[{c}]{'█' * f}[/][dim]{'░' * (w - f)}[/]"


def sign(v) -> str:
    return "+" if float(v) >= 0 else ""


def sparkline(values: list, width: int = 24) -> str:
    vals = [v for v in (values or []) if v is not None and float(v) > 0]
    if len(vals) < 2:
        return f"[{DIM}]{'▁' * width}[/]"
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
