#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: Phase 7's buy_sell_daily BUY-signal lookback used a
flat `run_date - timedelta(days=1)` calendar-day subtraction to find "yesterday's" signals. On a
Monday (or the trading day after any market holiday), that lands on Sunday - a full trading day's
real EOD-generated signals fall outside the query's [lookback_date, run_date] window and get
silently treated as "no BUY signals found", which reads exactly like a legitimate no-signal
market day rather than the off-by-weekend bug it actually is.

Reproduced live 2026-07-27 (Monday): buy_sell_daily had 301 real BUY signals dated 2026-07-24
(the prior Friday), but the old lookback_date (2026-07-26, Sunday) excluded all of them -
Phase 7 found zero candidates and degraded with a misleading "check market regime" message.

Fixed via algo/orchestrator/phase7_signal_generation.py::_buysell_lookback_start_date(), which
uses MarketCalendar.get_previous_trading_day() instead of a flat calendar subtraction.
"""

from datetime import date

from algo.orchestrator.phase7_signal_generation import _buysell_lookback_start_date


class TestBuysellLookbackWeekendGap:
    def test_monday_lookback_reaches_back_to_friday(self):
        """Monday 2026-07-27's lookback must include Friday 2026-07-24, not Sunday 2026-07-26."""
        monday = date(2026, 7, 27)
        lookback_date = _buysell_lookback_start_date(monday)
        assert lookback_date == date(2026, 7, 24), (
            f"Expected lookback to reach Friday 2026-07-24 (the actual prior trading day), "
            f"got {lookback_date} - a Sunday calendar subtraction would silently exclude "
            f"real BUY signals sitting in buy_sell_daily for that Friday."
        )

    def test_day_after_holiday_reaches_back_to_prior_trading_day(self):
        """The day after a market holiday (2026-01-19 MLK Day) must skip the holiday itself."""
        day_after_holiday = date(2026, 1, 20)
        lookback_date = _buysell_lookback_start_date(day_after_holiday)
        assert lookback_date == date(2026, 1, 16), (
            f"Expected lookback to skip the 2026-01-19 holiday and land on the prior Friday "
            f"2026-01-16, got {lookback_date}"
        )

    def test_midweek_lookback_is_just_yesterday(self):
        """A normal Tuesday->Wednesday case should behave identically to the old flat -1 day math."""
        wednesday = date(2026, 7, 22)
        lookback_date = _buysell_lookback_start_date(wednesday)
        assert lookback_date == date(2026, 7, 21)

    def test_old_calendar_day_math_would_have_missed_the_monday_case(self):
        """Sanity check documenting the exact bug: proves the pre-fix formula lands on a date
        with zero real signals, confirming this test would have failed against pre-fix code."""
        from datetime import timedelta

        monday = date(2026, 7, 27)
        old_buggy_lookback = monday - timedelta(days=1)
        assert old_buggy_lookback == date(2026, 7, 26)  # Sunday - no trading, no signals
        assert old_buggy_lookback != _buysell_lookback_start_date(monday)
