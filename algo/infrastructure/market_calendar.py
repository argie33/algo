#!/usr/bin/env python3
"""
Market Calendar — Handle trading holidays and market hours

Prevents false alerts on market closures, early closes, and holidays.
Uses standard US market holidays. Can be extended for other markets.
"""

import logging
from datetime import datetime, date as _date, time
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)
# US market holidays (2025-2026)
US_HOLIDAYS = {
    _date(2025, 1, 1): "New Year's Day",
    _date(2025, 1, 20): "MLK Jr. Day",
    _date(2025, 2, 17): "Presidents' Day",
    _date(2025, 3, 28): "Good Friday",
    _date(2025, 5, 26): "Memorial Day",
    _date(2025, 6, 19): "Juneteenth",
    _date(2025, 7, 4): "Independence Day",
    _date(2025, 9, 1): "Labor Day",
    _date(2025, 11, 27): "Thanksgiving",
    _date(2025, 12, 25): "Christmas",
    # 2026
    _date(2026, 1, 1): "New Year's Day",
    _date(2026, 1, 19): "MLK Jr. Day",
    _date(2026, 2, 16): "Presidents' Day",
    _date(2026, 4, 10): "Good Friday",
    _date(2026, 5, 25): "Memorial Day",
    _date(2026, 6, 19): "Juneteenth",
    _date(2026, 7, 3): "Independence Day (observed)",
    _date(2026, 9, 7): "Labor Day",
    _date(2026, 11, 26): "Thanksgiving",
    _date(2026, 12, 25): "Christmas",
    # 2027
    _date(2027, 1, 1): "New Year's Day",
    _date(2027, 1, 18): "MLK Jr. Day",
    _date(2027, 2, 15): "Presidents' Day",
    _date(2027, 4, 2): "Good Friday",
    _date(2027, 5, 31): "Memorial Day",
    _date(2027, 6, 18): "Juneteenth (observed)",  # Jun 19 is Saturday
    _date(2027, 7, 5): "Independence Day (observed)",  # Jul 4 is Sunday
    _date(2027, 9, 6): "Labor Day",
    _date(2027, 11, 25): "Thanksgiving",
    _date(2027, 12, 24): "Christmas (observed)",  # Dec 25 is Saturday
    _date(2027, 12, 31): "New Year's Day 2028 (observed)",  # Jan 1 2028 is Saturday
}

# Days with early closes (1:00 PM instead of 4:00 PM ET)
EARLY_CLOSES = {
    _date(2025, 7, 3): "Day before Independence Day",
    _date(2025, 11, 28): "Day after Thanksgiving",
    _date(2025, 12, 24): "Christmas Eve",
    _date(2026, 7, 2): "Day before Independence Day",
    _date(2026, 11, 27): "Day after Thanksgiving",
    _date(2026, 12, 24): "Christmas Eve",
    # 2027
    _date(2027, 11, 26): "Day after Thanksgiving",
}


class MarketCalendar:
    """Check market status and trading hours."""

    @staticmethod
    def is_trading_day(check_date=None):
        """Check if market is open on given date."""
        if not check_date:
            check_date = _date.today()

        # Weekend
        if check_date.weekday() >= 5:
            return False

        # Holiday
        if check_date in US_HOLIDAYS:
            return False

        return True

    @staticmethod
    def is_early_close(check_date=None):
        """Check if market has early close on given date (1 PM ET instead of 4 PM).

        Returns:
            bool: True if early close, False otherwise
        """
        if not check_date:
            check_date = _date.today()

        return check_date in EARLY_CLOSES

    @staticmethod
    def get_market_close_time(check_date=None):
        """Get market close time for given date.

        Returns:
            str: '14:00' for half-days (early close), '16:00' for normal days
        """
        if not check_date:
            check_date = _date.today()

        # Early close (half-day): 2:00 PM ET
        if check_date in EARLY_CLOSES:
            return "14:00"

        # Normal close: 4:00 PM ET
        return "16:00"

    @staticmethod
    def is_market_open(check_datetime=None):
        """Check if market is currently open.

        US equities: 9:30 AM - 4:00 PM ET weekdays (except holidays)
        """
        if not check_datetime:
            check_datetime = datetime.now(_ET)

        check_date = check_datetime.date()
        check_time = check_datetime.time()

        # Not a trading day
        if not MarketCalendar.is_trading_day(check_date):
            return False

        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = time(9, 30)
        market_close = time(16, 0)

        # Early close: 3:00 PM
        if check_date in EARLY_CLOSES:
            market_close = time(15, 0)

        return market_open <= check_time < market_close

    @staticmethod
    def market_status(check_datetime=None):
        """Get detailed market status."""
        if not check_datetime:
            check_datetime = datetime.now(_ET)

        check_date = check_datetime.date()
        check_time = check_datetime.time()

        if not MarketCalendar.is_trading_day(check_date):
            if check_date in US_HOLIDAYS:
                return {
                    "status": "CLOSED",
                    "reason": f"Holiday: {US_HOLIDAYS[check_date]}",
                    "date": str(check_date),
                    "is_open": False,
                }
            else:
                return {
                    "status": "CLOSED",
                    "reason": "Weekend",
                    "date": str(check_date),
                    "is_open": False,
                }

        market_open = time(9, 30)
        market_close = time(16, 0)
        is_early_close = check_date in EARLY_CLOSES

        if is_early_close:
            market_close = time(15, 0)

        if check_time < market_open:
            mins_until = int(
                (
                    datetime.combine(check_date, market_open)
                    - datetime.combine(check_date, check_time)
                ).total_seconds()
                / 60
            )
            return {
                "status": "PRE_MARKET",
                "reason": f"Opens in {mins_until} minutes",
                "datetime": check_datetime.isoformat(),
                "is_open": False,
            }
        elif check_time >= market_close:
            return {
                "status": "AFTER_HOURS",
                "reason": f"Market closed at {market_close.strftime('%H:%M')}",
                "early_close": is_early_close,
                "datetime": check_datetime.isoformat(),
                "is_open": False,
            }
        else:
            mins_until_close = int(
                (
                    datetime.combine(check_date, market_close)
                    - datetime.combine(check_date, check_time)
                ).total_seconds()
                / 60
            )
            return {
                "status": "OPEN",
                "reason": f"Market open ({mins_until_close}m until close)",
                "early_close": is_early_close,
                "datetime": check_datetime.isoformat(),
                "is_open": True,
            }

    @staticmethod
    def get_next_trading_day(from_date=None):
        """Get next trading day after given date."""
        if not from_date:
            from_date = _date.today()

        next_date = from_date
        max_iterations = 10  # prevent infinite loop
        iterations = 0

        while (
            not MarketCalendar.is_trading_day(next_date) and iterations < max_iterations
        ):
            next_date = _date.fromordinal(next_date.toordinal() + 1)
            iterations += 1

        return next_date if iterations < max_iterations else None


if __name__ == "__main__":
    from datetime import timedelta

    logger.info("MARKET CALENDAR")

    today = _date.today()

    # Current status
    status = MarketCalendar.market_status()
    logger.info(f"Current status: {status['status']}")
    logger.info(f"  {status.get('reason', '')}")

    # Next 5 days
    logger.info("Next 5 days:")
    for i in range(5):
        check_date = today + timedelta(days=i)
        if MarketCalendar.is_trading_day(check_date):
            early = " (early close 3pm)" if check_date in EARLY_CLOSES else ""
            logger.info(f"  {check_date}: OPEN{early}")
        elif check_date in US_HOLIDAYS:
            logger.info(f"  {check_date}: CLOSED - {US_HOLIDAYS[check_date]}")
        else:
            logger.info(f"  {check_date}: CLOSED - Weekend")

    next_trading = MarketCalendar.get_next_trading_day(today)
    logger.info(f"Next trading day: {next_trading}")
