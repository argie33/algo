"""Regression test: circuit breaker drawdown re-engagement's `days_elapsed` must be
trading-day-aware, not raw calendar-day subtraction.

BUG FOUND 2026-09-01 (/goal session, risk-mgmt fringe-case sweep):
`_check_drawdown_re_engagement()` computed `days_elapsed = (current_date - halt_date).days` -
plain calendar-day subtraction - unlike every other date-sensitive check in this same file
(which all use `MarketCalendar.is_trading_day`/equivalent) and the repo-wide load-bearing rule
("Date math via MarketCalendar only").

This matters in the dangerous direction for a SAFETY recovery window: calendar days pass
FASTER than trading days across a weekend/holiday. A halt on a Thursday would count 5 calendar
days elapsed by the following Tuesday - a real trading-day span of only 3 sessions - letting
the circuit breaker re-engage up to 2 trading sessions earlier than `re_engage_min_days` was
actually meant to require, i.e. resuming live trading with less proven post-drawdown recovery
time than the configured safety margin demands.

Fixed by switching to `MarketCalendar.trading_days_elapsed`, matching this file's own
convention elsewhere and exit_engine.py's identical days_held calculation.
"""

from datetime import date
from unittest.mock import Mock

from algo.infrastructure import MarketCalendar
from algo.risk import CircuitBreaker


def _cb(min_days: int = 5):
    return CircuitBreaker(
        config={
            "circuit_breaker_enabled": True,
            "halt_drawdown_pct": -20.0,
            "re_engage_recovery_pct": 5.0,
            "re_engage_min_days": min_days,
            "require_ftd_to_re_engage": False,
        }
    )


def test_re_engagement_uses_trading_days_not_calendar_days_across_a_weekend():
    """A halt on a Thursday, checked the following Tuesday: 5 calendar days have passed
    but only a handful of real trading sessions. If real market holidays ever shrink this
    specific window to exactly min_days trading sessions, the test's own live
    MarketCalendar computation (not a hardcoded assumption) still keeps the assertion
    correct - only the direction of the inequality matters, not a magic number."""
    halt_thursday = date(2026, 8, 6)
    current_tuesday = date(2026, 8, 11)
    calendar_days = (current_tuesday - halt_thursday).days
    real_trading_days = MarketCalendar.trading_days_elapsed(halt_thursday, current_tuesday)
    assert real_trading_days < calendar_days, "test setup must span a weekend to be meaningful"

    cb = _cb(min_days=calendar_days)  # old buggy code would consider this exactly satisfied
    mock_cur = Mock()
    mock_cur.fetchone.side_effect = [
        (100_000.0, 99_000.0),  # (peak, current) - recovery_pct=1% clears the 5% threshold
        (halt_thursday,),  # most recent drawdown-halt audit log row
    ]

    result = cb._check_drawdown_re_engagement(current_tuesday, mock_cur)

    assert result["halted"] is True, (
        "using calendar days instead of trading days would let re-engagement proceed here - "
        "the fix must still block it, since real trading-day elapsed time is short of min_days"
    )
    assert str(real_trading_days) in result["reason"]


def test_re_engagement_allowed_once_real_trading_days_elapsed():
    """Sanity check: once enough REAL trading sessions have passed, re-engagement must
    still proceed normally - this fix must not make the gate permanently stricter than
    intended, only correct which unit of time it counts in."""
    halt_thursday = date(2026, 8, 6)
    current_date = date(2026, 8, 6)
    # Walk forward via the real calendar until 3 genuine trading sessions have elapsed.
    from datetime import timedelta

    while MarketCalendar.trading_days_elapsed(halt_thursday, current_date) < 3:
        current_date += timedelta(days=1)

    cb = _cb(min_days=3)
    mock_cur = Mock()
    mock_cur.fetchone.side_effect = [
        (100_000.0, 99_000.0),
        (halt_thursday,),
    ]

    result = cb._check_drawdown_re_engagement(current_date, mock_cur)

    assert result["halted"] is False
