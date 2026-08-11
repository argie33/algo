#!/usr/bin/env python3
"""Regression test for MarketCalendar's hardcoded US_HOLIDAYS table.

Session 2026-07-21: every Good Friday entry in US_HOLIDAYS was wrong (miscalculated
Easter offset) - e.g. 2026 listed April 10 instead of the real April 3. This meant
is_trading_day() returned True on the actual market holiday (no data would be
published, risking false "stale data" alerts) and returned False on a real trading
day that happened to be mislabeled as Good Friday (orchestrator/signal generation
would silently skip a normal trading day). Verifies every configured Good Friday
against the actual Easter computation (Gauss's algorithm), not just hardcoded values,
so this can't silently drift again when new years are added to the table.
"""

from datetime import date, timedelta

from algo.infrastructure.market_calendar import US_HOLIDAYS, MarketCalendar


def _computus_easter(year: int) -> date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher) for Easter Sunday."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    calc_l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * calc_l) // 451
    month = (h + calc_l - 7 * m + 114) // 31
    day = ((h + calc_l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def test_good_friday_matches_computed_easter() -> None:
    """Every 'Good Friday' entry in the holiday table must be Easter Sunday minus 2 days."""
    good_fridays = {d: name for d, name in US_HOLIDAYS.items() if "Good Friday" in name}
    assert good_fridays, "No Good Friday entries found in US_HOLIDAYS - table may have been restructured"

    for holiday_date in good_fridays:
        expected = _computus_easter(holiday_date.year) - timedelta(days=2)
        assert holiday_date == expected, (
            f"Good Friday {holiday_date.year} is listed as {holiday_date} but should be {expected} "
            f"(Easter Sunday {holiday_date.year} minus 2 days)"
        )


def test_good_friday_is_not_a_trading_day() -> None:
    for holiday_date in (d for d, name in US_HOLIDAYS.items() if "Good Friday" in name):
        assert not MarketCalendar.is_trading_day(holiday_date), (
            f"{holiday_date} (Good Friday) must not be a trading day"
        )


def test_previously_wrong_good_friday_dates_are_real_trading_days() -> None:
    """The dates the table incorrectly used to list as Good Friday were real trading days."""
    formerly_mislabeled = [date(2025, 3, 28), date(2026, 4, 10), date(2027, 4, 2)]
    for d in formerly_mislabeled:
        assert d not in US_HOLIDAYS, f"{d} should not be in US_HOLIDAYS (it is not Good Friday)"
        if d.weekday() < 5:
            assert MarketCalendar.is_trading_day(d), f"{d} is a weekday and not a holiday - should be a trading day"
