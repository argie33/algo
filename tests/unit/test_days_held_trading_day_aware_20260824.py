#!/usr/bin/env python3
"""Regression test for days_held using calendar days instead of trading days.

/goal session 2026-08-24: user noticed a large batch of positions all time-exiting
together on a quiet trading day and asked us to verify the exit/stop-loss logic was
sound. Root cause: algo/trading/exit_engine.py's `days_held = (current_date -
trade_date).days` (and the identical line in algo/monitoring/position_monitor.py's
_evaluate_position) counted raw calendar days, not trading sessions. Both files
already use MarketCalendar.get_trading_days()-based trading-day counting elsewhere
(exit_engine.py's market_dist_days staleness check, explicitly commented "so
weekends/holidays don't false-trigger") - the days_held computation was the one spot
that didn't follow that convention.

Effect: with algo_config.max_hold_days=5 (live value as of 2026-08-24), a cohort of
positions entered on the same Wednesday all crossed the 5-calendar-day threshold on
the following Monday - after only 3 real trading sessions (Thu, Fri, Mon) - and were
force-exited together regardless of market conditions that day. This explains
apparent "mass exit on a quiet day" clusters as a real (if subtle) bug, not test
data or a broken stop-loss: entries cluster because signal generation runs in
batches, and calendar-day math over a weekend then makes their time-stops expire in
lockstep, 2 trading sessions earlier than the config value implies.

Fixed via MarketCalendar.trading_days_elapsed(), used by both call sites.
"""

from datetime import date

from algo.infrastructure.market_calendar import MarketCalendar


def test_same_day_entry_and_eval_is_zero_days_held() -> None:
    assert MarketCalendar.trading_days_elapsed(date(2026, 8, 24), date(2026, 8, 24)) == 0


def test_consecutive_trading_days_count_one_day_held() -> None:
    # Monday -> Tuesday, no weekend in between
    assert MarketCalendar.trading_days_elapsed(date(2026, 8, 17), date(2026, 8, 18)) == 1


def test_weekend_does_not_inflate_days_held() -> None:
    """The exact scenario from the live incident: entered Wed 2026-08-19, evaluated
    Mon 2026-08-24. Naive calendar subtraction gives 5 (matching max_hold_days=5 and
    triggering an early TIME exit); trading-day-aware counting correctly gives 3
    (Thu, Fri, Mon - the weekend doesn't count as 2 extra "days held").
    """
    entry = date(2026, 8, 19)
    evaluated = date(2026, 8, 24)

    naive_calendar_days = (evaluated - entry).days
    assert naive_calendar_days == 5, "sanity check on the incident dates"

    assert MarketCalendar.trading_days_elapsed(entry, evaluated) == 3


def test_holiday_does_not_inflate_days_held() -> None:
    # Labor Day 2026-09-07 falls between these two Fridays/Mondays
    before = date(2026, 9, 4)  # Friday
    after = date(2026, 9, 8)  # Tuesday (Mon 9/7 is Labor Day)
    naive_calendar_days = (after - before).days
    assert naive_calendar_days == 4

    # Only one real session elapsed: Friday -> Tuesday, skipping the weekend + holiday
    assert MarketCalendar.trading_days_elapsed(before, after) == 1


def test_end_before_start_is_negative_not_raising() -> None:
    """Callers (exit_engine.py, position_monitor.py) clamp negative days_held to 0 and
    log a data-corruption warning rather than crash - trading_days_elapsed must keep
    returning a negative number here, not raise, to preserve that safeguard.
    """
    result = MarketCalendar.trading_days_elapsed(date(2026, 8, 24), date(2026, 8, 19))
    assert result < 0
