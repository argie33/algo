"""Regression test for a live-reproduced bug in utils/data/age_validator.py.

2026-08-17: `DataAgeValidator.check()` computed `age_days` as raw calendar days
(`(current_date - max_date).days`) regardless of weekends/holidays sitting in between, then
only adjusted the *threshold* (not the age) based on whether *today* happened to be a trading
day. On a Monday with the most recent complete trading day being Friday, that's really 1
trading day old (nothing missed since Friday's close), but the old code computed age_days=3
(raw Sat/Sun/Mon count) against a threshold=1 rule and always failed it - this exact bug broke
`technical_data_daily`'s price_daily freshness precheck live in production use, cascading to
fail the whole `signals` pipeline behind it, with the log message
"[price_daily] Data is 3 days old (threshold 1d)" while the data was in fact current.

Fixed by computing age via `MarketCalendar.get_trading_days(max_date, current_date)` instead of
raw subtraction, which correctly treats a Friday-to-Monday gap as 1 elapsed trading day.
"""

from datetime import date
from unittest.mock import patch

from utils.data.age_validator import DataAgeValidator


def _check_with_mocked_max_date(table_name: str, max_date: date, current_date: date) -> dict:
    with patch("utils.data.age_validator.DatabaseContext") as MockDB:
        MockDB.return_value.__enter__.return_value.fetchone.return_value = (max_date,)
        return DataAgeValidator.check(table_name, current_date=current_date)


class TestTradingDayAwareAgeCalculation:
    def test_friday_data_checked_monday_is_fresh_not_3_days_stale(self):
        # 2026-08-14 was a Friday, 2026-08-17 is the following Monday (both real trading days
        # per the repo's calendar - no holiday in between). price_daily's rule is
        # max_age_days=1. Old behavior: age_days=3 (raw calendar count) > threshold=1 -> STALE,
        # hard-failing the precheck. Correct behavior: 1 trading day elapsed -> fresh.
        result = _check_with_mocked_max_date("price_daily", date(2026, 8, 14), date(2026, 8, 17))

        assert result["age_days"] == 1
        assert result["is_fresh"] is True

    def test_consecutive_weekday_check_is_unchanged(self):
        # Tuesday checking Monday's data: 1 raw day == 1 trading day either way. Guards against
        # the fix changing behavior on the common case, not just the weekend-gap case.
        result = _check_with_mocked_max_date("price_daily", date(2026, 8, 17), date(2026, 8, 18))

        assert result["age_days"] == 1
        assert result["is_fresh"] is True

    def test_genuinely_stale_data_across_a_weekend_is_still_caught(self):
        # Most recent data is the Friday *before* the one used above - 2 trading days behind by
        # Monday (Fri 08-07 -> Mon 08-17 skips the whole week of 08-10..08-14 too). Must still
        # correctly flag as stale, not silently pass everything just because a weekend touched it.
        result = _check_with_mocked_max_date("price_daily", date(2026, 8, 7), date(2026, 8, 17))

        assert result["age_days"] > 1
        assert result["is_fresh"] is False
