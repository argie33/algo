"""Regression test: StalenessChecker's daily-freq staleness check must age data in trading
days, not raw calendar days.

Live-caught (goal session score-sanity sweep, 2026-09-08): price_daily/technical_data_daily/
buy_sell_daily/trend_template_data/market_health_daily all have threshold_days=1 and used
`age = (today - latest).days` - pure calendar-day math. On Tuesday 2026-09-08 (the trading day
right after Labor Day, 2026-09-07), the actually-correct latest trading day is Friday
2026-09-04 - but (2026-09-08 - 2026-09-04).days == 4, which exceeds the 1-day threshold and
would fire CRIT, potentially halting Phase 1 (CLAUDE.md's _check_data_patrol_results rule)
despite the data being exactly as fresh as it should be. Any single weekend already produces
the same false alarm (Friday->Monday is 3 calendar days). Fixed by delegating to
MarketCalendar.trading_days_elapsed for freq == "daily" rows, matching this codebase's existing
MarketCalendar-for-date-math convention (see algo/orchestrator/phase1_data_freshness.py).
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _cursor_with_latest_date(latest_date_str: str) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        sql = cursor._last_sql
        if "MAX(" in sql:
            return (1, latest_date_str)
        # Frozen-symbol/frozen-price sub-checks issue plain COUNT(*) queries.
        return (0,)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessDailyFreqTradingDayAware:
    def test_friday_data_not_stale_on_tuesday_after_labor_day(self):
        """Fri 2026-09-04 -> Tue 2026-09-08 spans Labor Day (2026-09-07); 4 calendar days
        but only 1 trading day elapsed - must NOT fire CRIT for a daily-freq table."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 8)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-04"))

        price_results = [r for r in results if r.target_table == "price_daily" and "age_days" in r.details]
        assert len(price_results) == 1
        assert price_results[0].severity == "info", (
            f"expected fresh (trading-day-aware), got {price_results[0].severity}: {price_results[0].details}"
        )
        assert price_results[0].details["age_days"] == 1

    def test_genuinely_stale_daily_table_still_fires_critical(self):
        """A real multi-trading-day gap (not just a weekend/holiday) must still fire CRIT -
        this fix must not silence real staleness."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 8)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-08-28"))

        price_results = [r for r in results if r.target_table == "price_daily" and "age_days" in r.details]
        assert len(price_results) == 1
        assert price_results[0].severity == "critical"
        assert price_results[0].details["age_days"] > 1

    def test_weekly_freq_table_still_uses_calendar_days(self):
        """aaii_sentiment (weekly) has no trading-day periodicity - must keep calendar-day math."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 8)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-01"))

        sentiment_results = [r for r in results if r.target_table == "aaii_sentiment" and "age_days" in r.details]
        assert len(sentiment_results) == 1
        assert sentiment_results[0].details["age_days"] == 7
