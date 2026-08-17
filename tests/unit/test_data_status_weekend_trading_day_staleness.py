"""Regression test for the 2026-08-16 fix: _get_data_status's weekly/biweekly staleness
branch (lambda/api/routes/algo_handlers/market.py) used raw `(today - data_date).days`,
which counts weekends. Tables updated once per trading day with stale_threshold_days=2
(market_exposure_daily, market_health_daily, algo_risk_daily, algo_portfolio_snapshots)
falsely flipped to "stale" every weekend even though 0 trading days were missed.

Live-confirmed 2026-08-16: market_exposure_daily/market_health_daily both had correct,
current Friday 2026-08-14 data (the most recent trading day, direct DB query) but the
dashboard showed CRIT STALE - because a Monday `today` minus that Friday is 3 calendar
days, which is > the configured 2-day threshold, even though the weekend cost 0 trading
days. Fixed by counting actual elapsed trading days via MarketCalendar instead.
"""

import importlib
from datetime import date

market_module = importlib.import_module("lambda.api.routes.algo_handlers.market")


def test_fridays_data_not_stale_on_monday():
    """The core bug: Friday's data is current on a Monday check - must not be stale."""
    friday = date(2026, 8, 14)
    monday = date(2026, 8, 17)

    assert market_module._is_stale_by_trading_days(friday, monday, max_age=2) is False


def test_fridays_data_not_stale_on_sunday():
    friday = date(2026, 8, 14)
    sunday = date(2026, 8, 16)

    assert market_module._is_stale_by_trading_days(friday, sunday, max_age=2) is False


def test_genuinely_stale_data_still_flagged_on_monday():
    """Sanity check: the fix must not silently disable the check - data from the Friday
    before last (a full extra week stale) must still be flagged."""
    week_before_friday = date(2026, 8, 7)
    monday = date(2026, 8, 17)

    assert market_module._is_stale_by_trading_days(week_before_friday, monday, max_age=2) is True


def test_normal_midweek_gap_within_threshold_not_stale():
    """A 2-trading-day-old table (well within a max_age=2 threshold) on a normal
    Wednesday, no weekend involved."""
    monday = date(2026, 8, 17)
    wednesday = date(2026, 8, 19)

    assert market_module._is_stale_by_trading_days(monday, wednesday, max_age=2) is False


def test_normal_midweek_gap_exceeding_threshold_is_stale():
    monday = date(2026, 8, 17)
    thursday = date(2026, 8, 20)

    assert market_module._is_stale_by_trading_days(monday, thursday, max_age=2) is True
