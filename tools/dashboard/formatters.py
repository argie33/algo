"""Formatting and utility functions for dashboard display."""

from datetime import date as _date, datetime, timedelta, timezone

from utilities import (
    TIER_COLOR, SPARKLINE_CHARS, ET,
    G, R, Y, CY, DIM,
)


def fmt_age(ts):
    if ts is None: return "--"
    if isinstance(ts, str): ts = datetime.fromisoformat(ts)
    if isinstance(ts, _date) and not isinstance(ts, datetime):
        ts = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
    if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
    m = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
    if m < 60:   return f"{m}m ago"
    if m < 1440: return f"{m // 60}h{m % 60:02d}m ago"
    return f"{m // 1440}d ago"

def fmt_money(v):
    if v is None: return "--"
    v = float(v)
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6: return f"{s}${av / 1e6:.2f}M"
    if av >= 1e3: return f"{s}${av:,.0f}"
    return f"{s}${av:.2f}"

def fmt_money_short(v):
    """Compact dollar format: $45K, $1.2M, $850 - for narrow table columns."""
    if v is None: return "--"
    v = float(v)
    s = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e6: return f"{s}${av/1e6:.1f}M"
    if av >= 1e3: return f"{s}${av/1e3:.0f}K"
    return f"{s}${av:.0f}"

def grade(s):
    s = float(s)
    if s >= 90: return "A+"
    if s >= 80: return "A"
    if s >= 70: return "B"
    if s >= 60: return "C"
    return "D"

def tier_from_pct(p) -> str:
    if p is None: return "unknown"
    p = float(p)
    if p >= 80: return "confirmed_uptrend"
    if p >= 60: return "healthy_uptrend"
    if p >= 40: return "pressure"
    if p >= 20: return "caution"
    return "correction"

def is_open() -> bool:
    n = datetime.now(ET)
    if n.weekday() >= 5: return False
    t = n.hour * 60 + n.minute
    return 570 <= t <= 960

def mkt_hours_str() -> tuple:
    """Returns (status_markup, countdown_str) reflecting pre-mkt/open/after-hrs/closed."""
    n  = datetime.now(ET)
    wd = n.weekday()
    t  = n.hour * 60 + n.minute

    def _fmt_mins(m):
        h, mm = divmod(m, 60)
        return f"{h}h{mm:02d}m" if h > 0 else f"{mm}m"

    if wd >= 5:
        days_ahead = 7 - wd
        open_dt = (n + timedelta(days=days_ahead)).replace(
            hour=9, minute=30, second=0, microsecond=0)
        diff_m = max(0, int((open_dt - n).total_seconds() / 60))
        return "[dim]- CLOSED[/]", f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}"

    PRE_OPEN  = 4 * 60
    OPEN      = 9 * 60 + 30
    CLOSE     = 16 * 60
    AH_END    = 20 * 60

    if t < PRE_OPEN:
        diff_m = OPEN - t
        return "[dim]- CLOSED[/]", f"opens in {_fmt_mins(diff_m)}"
    if t < OPEN:
        diff_m = OPEN - t
        return "[yellow]- PRE-MKT[/]", f"opens in {_fmt_mins(diff_m)}"
    if t < CLOSE:
        diff_m = CLOSE - t
        return "[bold bright_green]- OPEN[/]", f"closes in {_fmt_mins(diff_m)}"
    if t < AH_END:
        next_days = 3 if wd == 4 else 1
        open_dt = (n + timedelta(days=next_days)).replace(
            hour=9, minute=30, second=0, microsecond=0)
        diff_m = max(0, int((open_dt - n).total_seconds() / 60))
        return "[dim]- AFTER-HRS[/]", f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}"
    next_days = 3 if wd == 4 else 1
    open_dt = (n + timedelta(days=next_days)).replace(
        hour=9, minute=30, second=0, microsecond=0)
    diff_m = max(0, int((open_dt - n).total_seconds() / 60))
    return "[dim]- CLOSED[/]", f"opens {open_dt.strftime('%a')} in {_fmt_mins(diff_m)}"

def next_run_str() -> str:
    now = datetime.now(ET)
    wd  = now.weekday()
    t   = now.hour * 60 + now.minute

    def fmt(dt):
        diff = dt - now
        mins = int(diff.total_seconds() / 60)
        if mins < 60:   return f"in {mins}m"
        if mins < 1440: return f"in {mins//60}h{mins%60:02d}m"
        return f"{dt.strftime('%a %I:%M %p')}"

    def next_wkd(dt, off=1):
        d = dt + timedelta(days=off)
        while d.weekday() >= 5: d += timedelta(days=1)
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
    r = min(float(cur) / float(thr), 1.0) if thr and float(thr) > 0 else 0
    f = int(r * w)
    c = R if r >= 1 else (Y if r >= 0.75 else G)
    return f"[{c}]{'#' * f}[/][dim]{'-' * (w - f)}[/]"

def exp_bar(pct, w=12):
    f = int(min(float(pct or 0), 100) / 100 * w)
    tc = TIER_COLOR.get(tier_from_pct(pct), "dim")
    return f"[{tc}]{'#' * f}[/][dim]{'-' * (w - f)}[/]"

def mini_bar(pts, max_pts, w=5):
    r = min(float(pts or 0) / float(max_pts or 1), 1.0)
    f = int(r * w)
    c = G if r >= 0.75 else (Y if r >= 0.35 else R)
    return f"[{c}]{'#' * f}[/][dim]{'-' * (w - f)}[/]"

def sign(v) -> str:
    return "+" if float(v) >= 0 else ""

def sparkline(values: list, width: int = 24) -> str:
    vals = [v for v in (values or []) if v is not None and float(v) > 0]
    if len(vals) < 2:
        return f"[{DIM}]{'#' * width}[/]"
    mn, mx = min(vals), max(vals)
    if mx == mn:
        return f"[{CY}]{'#' * width}[/]"
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
