"""Regression test: Phase 8's per-signal staleness gate must count TRADING days elapsed,
not raw calendar days.

BUG FOUND 2026-08-10 (live-reproduced via a real forced afternoon orchestrator run):
signals generated Friday 2026-08-07 were REJECTED as "too old" when entry was attempted
Monday 2026-08-10, because signal_age_days = (run_date - sig_date).days counted the
intervening weekend (3 calendar days = 72h), exceeding the 24h max_signal_age_hours gate -
even though this is exactly the normal EOD-Friday-to-Monday-open gap the gate's own comment
says it's meant to allow ("yesterday at 4:05 PM -> today at 1:00 PM = 16+ hours" is the
*intended* rejection case, not a weekend-spanning next trading session). Every signal
generated on a Friday was therefore permanently unenterable the following Monday.
"""

from datetime import date

from algo.orchestrator.phase8_entry_execution import _signal_age_trading_days


def test_friday_to_monday_is_one_trading_day_not_three_calendar_days():
    assert _signal_age_trading_days(date(2026, 8, 7), date(2026, 8, 10)) == 1


def test_same_day_signal_is_zero_trading_days_old():
    assert _signal_age_trading_days(date(2026, 8, 10), date(2026, 8, 10)) == 0


def test_thursday_to_friday_is_one_trading_day():
    assert _signal_age_trading_days(date(2026, 8, 6), date(2026, 8, 7)) == 1


def test_genuinely_stale_signal_spanning_two_trading_days_is_still_caught():
    # Friday signal entered the following Tuesday (2 trading days later: Mon + Tue) -
    # the gate must still reject genuinely stale signals, just not weekend-spanning fresh ones.
    assert _signal_age_trading_days(date(2026, 8, 7), date(2026, 8, 11)) == 2
