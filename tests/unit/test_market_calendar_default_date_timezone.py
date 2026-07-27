#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: MarketCalendar.is_trading_day()/is_early_close()
defaulted their date argument to system-local `date.today()`, not Eastern Time, when called
with no argument. Unlike most other date.today()-default sites audited this session (which
turned out to have no real no-argument caller and weren't live-reachable), this one has
confirmed live callers: dashboard/fetchers_portfolio.py and dashboard/panels/portfolio.py both
call MarketCalendar.is_trading_day() with no argument. A server not running in
America/New_York (e.g. UTC in production) could answer "is today a trading day?" against the
wrong calendar day near the midnight-ET boundary, showing/hiding dashboard portfolio metrics
based on an incorrect trading-day determination.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from algo.infrastructure.market_calendar import MarketCalendar

ET = ZoneInfo("America/New_York")


class TestIsTradingDayDefaultsToEasternTime:
    def test_uses_eastern_date_not_system_local_date(self):
        """The core bug: system-local 'today' claims a weekend (would be non-trading if
        used), but the real Eastern-time 'now' is a weekday (a trading day) - the function
        must follow Eastern time, not system-local date.today()."""
        fake_system_today = date(2026, 8, 1)  # a Saturday - non-trading if this were used
        real_eastern_now = datetime(2026, 8, 3, 10, 0, tzinfo=ET)  # a Monday - trading day

        mock_datetime = MagicMock()
        mock_datetime.now.return_value = real_eastern_now

        with (
            patch("algo.infrastructure.market_calendar._date") as mock_date_cls,
            patch("algo.infrastructure.market_calendar.datetime", mock_datetime),
        ):
            mock_date_cls.today.return_value = fake_system_today
            # fromordinal must still work for real, in case is_trading_day's loop needs it
            mock_date_cls.fromordinal.side_effect = date.fromordinal

            result = MarketCalendar.is_trading_day()

        assert result is True, (
            "is_trading_day() with no argument must use the real Eastern-time date "
            "(a Monday, trading day), not the mocked system-local date (a Saturday)"
        )

    def test_uses_eastern_date_for_early_close_lookup(self):
        fake_system_today = date(2026, 1, 1)  # New Year's Day - not in EARLY_CLOSES
        real_eastern_now = datetime(2026, 7, 2, 10, 0, tzinfo=ET)  # a documented early-close day

        mock_datetime = MagicMock()
        mock_datetime.now.return_value = real_eastern_now

        with patch("algo.infrastructure.market_calendar.datetime", mock_datetime):
            result = MarketCalendar.is_early_close()

        assert result is True, (
            "is_early_close() with no argument must use the real Eastern-time date "
            "(a known early-close day), not an unrelated system-local date"
        )

    def test_explicit_date_argument_still_respected(self):
        """Sanity check: passing an explicit date must not be overridden by the new default."""
        saturday = date(2026, 8, 1)
        assert MarketCalendar.is_trading_day(saturday) is False
