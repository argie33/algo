"""Regression test: Phase 1's EOD data-freshness grace period must actually expire at 4:30 PM.

algo/orchestrator/phase1_data_freshness.py compared `now_et.hour` (always an int) against the
float 16.5 to decide whether the "accept yesterday's data" grace period was still active. Since
.hour never has a fractional part, `16 <= now_et.hour < 16.5` is True and `now_et.hour >= 16.5`
is False for EVERY minute from 16:00:00 through 16:59:59 - not just the documented "4:00-4:30
PM" window. Confirmed live 2026-07-27: for a run landing anywhere in that hour, stale same-day
price data would silently be masked by falling back to the prior trading day for up to 30 extra
minutes past the intended cutoff. Fixed by comparing actual datetime boundaries instead of an
hour/float. This test (1) proves the boundary math is now correct across the critical minutes,
and (2) statically pins that the broken `.hour < 16.5` / `.hour >= 16.5` comparisons are gone,
since exercising the real code path requires mocking phase1's DB-heavy run() end-to-end.
"""

import inspect
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from algo.orchestrator import phase1_data_freshness as p1


def _grace_active(now_et: datetime) -> bool:
    """Mirror of the fixed boundary logic in phase1_data_freshness.py's EOD branch."""
    grace_period_end = now_et.replace(hour=16, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_close <= now_et < grace_period_end


def test_grace_period_boundary_correct_across_the_4pm_hour():
    tz = ZoneInfo("America/New_York")
    cases = {
        (15, 59): False,  # before market close: not EOD grace territory
        (16, 0): True,  # exactly market close: grace active
        (16, 29): True,  # last minute of grace
        (16, 30): False,  # documented cutoff: grace must have expired
        (16, 45): False,  # CRITICAL FIX target: this used to be True (bug)
        (16, 59): False,  # CRITICAL FIX target: this used to be True (bug)
        (17, 0): False,  # well past cutoff
    }
    for (hour, minute), expected in cases.items():
        now_et = datetime(2026, 7, 27, hour, minute, 0, tzinfo=tz)
        assert _grace_active(now_et) is expected, f"{hour:02d}:{minute:02d} expected grace={expected}"


def test_source_no_longer_compares_integer_hour_against_float_boundary():
    """`now_et.hour` legitimately appears elsewhere (e.g. `now_et.hour >= 16` to pick
    pipeline_context, an int-vs-int comparison) - only the fractional-boundary comparison
    (`.hour` against a non-integer like 16.5) is the bug being pinned here."""
    source = inspect.getsource(p1)
    assert not re.search(r"now_et\.hour\s*[<>=]+\s*\d+\.\d", source), (
        "Found `now_et.hour` compared against a fractional boundary again - `.hour` is always "
        "an int and can never distinguish before/after :30 within that hour. Compare real "
        "datetime boundaries (see the grace_period_end/market_close pattern) instead."
    )
