#!/usr/bin/env python3
"""NYSE/NASDAQ early closes (day before Independence Day, day after Thanksgiving,
Christmas Eve) close the market at 1:00 PM ET, not 3:00 PM. Two real bugs:

1. MarketCalendar.is_market_open()/market_status() hardcoded the early-close time as
   15:00 instead of 13:00 - a 2-hour window (1-3 PM ET) on early-close days was treated
   as market-open when the market was actually already closed.
2. phase8_entry_execution.py's own market-hours guard didn't consult early closes (or
   MarketCalendar) at all - it compared against the fixed 9:30 AM-4:00 PM constants
   unconditionally, so it would have let live entry orders through from 1-4 PM ET on an
   early-close day, a window the market is genuinely closed.

EARLY_CLOSES currently lists 2026-07-02 (day before Independence Day) as an early close.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from algo.infrastructure.market_calendar import MarketCalendar

ET = ZoneInfo("America/New_York")
EARLY_CLOSE_DATE = date(2026, 7, 2)


def test_market_closed_at_2pm_on_early_close_day():
    dt = datetime(2026, 7, 2, 14, 0, tzinfo=ET)
    assert MarketCalendar.is_early_close(EARLY_CLOSE_DATE)
    assert not MarketCalendar.is_market_open(dt), (
        "Market actually closes at 1:00 PM ET on early-close days - 2:00 PM must read as closed"
    )


def test_market_open_at_noon_on_early_close_day():
    dt = datetime(2026, 7, 2, 12, 0, tzinfo=ET)
    assert MarketCalendar.is_market_open(dt), "Market is still open before 1:00 PM ET on an early-close day"


def test_market_status_after_hours_at_2pm_on_early_close_day():
    dt = datetime(2026, 7, 2, 14, 0, tzinfo=ET)
    status = MarketCalendar.market_status(dt)
    assert status["status"] == "AFTER_HOURS"
    assert status["early_close"] is True


def test_regular_trading_day_still_closes_at_4pm():
    dt = datetime(2026, 7, 6, 15, 0, tzinfo=ET)  # a normal Monday, 3 PM ET
    assert MarketCalendar.is_market_open(dt)
    dt_after_close = datetime(2026, 7, 6, 16, 30, tzinfo=ET)
    assert not MarketCalendar.is_market_open(dt_after_close)
