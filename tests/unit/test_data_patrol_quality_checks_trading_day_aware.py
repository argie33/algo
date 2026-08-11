"""Regression test for the 2026-08-11 fix: QualityChecker.check_zero_or_identical() and
check_volume_sanity() both computed "yesterday" as `MAX(date) - 1 calendar day` in SQL. On a
Monday (or the day after any holiday), that lands on a weekend/holiday date with zero rows in
price_daily at all, so the "yesterday" comparison set came back empty - misclassifying every
persistently zero/low-volume symbol (SPACs at NAV, thinly-traded shells) as "new" instead of
"recurring" and inflating the alert count toward "basically the whole universe" (confirmed
live: zero_data's new-symbol count dropped 56 -> 19 and volume_sanity's dropped 3171 -> 193
after the fix, both against thresholds far below the pre-fix inflated counts). Same bug class
already fixed for signal-age checks in Phase 8 - date math must use the market calendar, not
raw calendar-day arithmetic.
"""

import inspect

from algo.monitoring.data_patrol.checks.quality import QualityChecker


class TestQualityChecksTradingDayAware:
    def test_zero_or_identical_uses_market_calendar_for_previous_day(self):
        source = inspect.getsource(QualityChecker.check_zero_or_identical)
        assert "MarketCalendar" in source, (
            "must resolve 'yesterday' via MarketCalendar.get_previous_trading_day(), not raw "
            "calendar-day subtraction, or it silently returns an empty comparison set on the "
            "first trading day after every weekend/holiday"
        )
        assert "get_previous_trading_day" in source

    def test_volume_sanity_uses_market_calendar_for_previous_day(self):
        source = inspect.getsource(QualityChecker.check_volume_sanity)
        assert "MarketCalendar" in source, (
            "the 'new low volume' exclusion subquery must resolve the previous TRADING day, "
            "not `MAX(date) - 1 calendar day` (empty on Mondays/post-holiday, which silently "
            "counted every low-volume symbol as 'new')"
        )
        assert "get_previous_trading_day" in source
