#!/usr/bin/env python3
"""Regression tests for PositionSizer._calculate_trading_days_elapsed - continuing the
2026-08-24 test-coverage-completeness sweep onto position_sizer.py (see
[[exit_engine_t1_t2_t3_verified_and_tested_20260824]] and
[[exit_strategies_new_stop_silently_dropped_fixed_20260824]] in memory, which found real bugs
via this same technique).

This function gates two CRITICAL fail-fast staleness checks: get_portfolio_value()'s snapshot
freshness (trading_age <= 1) and get_market_exposure_multiplier()'s exposure-data freshness
(trading_age > 1 raises). An off-by-one here could either let position sizing silently use
stale portfolio/exposure data (dangerous) or spuriously halt trading on fresh data (disruptive).

Uses the real MarketCalendar (pure calendar logic, no DB) against real known dates rather than
mocking, so these tests also implicitly verify the real 2026 holiday calendar for the dates used.
"""

from datetime import date

import pytest

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "max_position_size_pct": 10.0,
    "max_concentration_pct": 15.0,
    "max_total_invested_pct": 90.0,
    "max_total_risk_pct": 4.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _sizer():
    return PositionSizer(config=dict(CONFIG))


class TestTradingDaysElapsed:
    def test_same_day_is_zero(self):
        sizer = _sizer()
        d = date(2026, 8, 21)
        assert sizer._calculate_trading_days_elapsed(d, d) == 0

    def test_reversed_dates_returns_zero_not_negative(self):
        """A start_date after end_date (shouldn't happen in practice, but must not crash
        or return a negative count) returns 0."""
        sizer = _sizer()
        assert sizer._calculate_trading_days_elapsed(date(2026, 8, 24), date(2026, 8, 21)) == 0

    def test_consecutive_trading_days(self):
        """Thursday to Friday: exactly 1 trading day elapsed."""
        sizer = _sizer()
        assert sizer._calculate_trading_days_elapsed(date(2026, 8, 20), date(2026, 8, 21)) == 1

    def test_friday_to_monday_is_one_trading_day(self):
        """The exact example from this function's own docstring: weekend in between must
        not count as elapsed trading days."""
        sizer = _sizer()
        assert sizer._calculate_trading_days_elapsed(date(2026, 8, 21), date(2026, 8, 24)) == 1

    def test_friday_to_saturday_is_zero(self):
        """Start of a weekend gap: the very next calendar day is a non-trading Saturday."""
        sizer = _sizer()
        assert sizer._calculate_trading_days_elapsed(date(2026, 8, 21), date(2026, 8, 22)) == 0

    def test_holiday_monday_not_counted(self):
        """Friday 2026-09-04 to Tuesday 2026-09-08 spans a weekend AND Labor Day (Monday
        2026-09-07, a market holiday) - only Tuesday should count as an elapsed trading day."""
        sizer = _sizer()
        assert sizer._calculate_trading_days_elapsed(date(2026, 9, 4), date(2026, 9, 8)) == 1

    def test_full_trading_week(self):
        """Monday to the following Monday: 5 trading days elapsed (Tue/Wed/Thu/Fri/Mon)."""
        sizer = _sizer()
        assert sizer._calculate_trading_days_elapsed(date(2026, 8, 17), date(2026, 8, 24)) == 5
