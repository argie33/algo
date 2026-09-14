"""Regression test: StalenessChecker must cover score_realized_ic_log.

Live-caught (goal session 2026-09-14, "make sure we are tracking all we should" follow-up):
scripts/score_realized_ic_monitor.py is the only mechanism in this repo that continuously
answers whether the live scoring methodology is still predicting anything - it was wired into
neither an automated schedule nor DataPatrol staleness coverage, so if nobody happened to run
it by hand this quality-measurement blind spot would itself go silently undetected. Now
scheduled daily (scripts/setup_windows_schedule.ps1's score-realized-ic-monitor task); this
staleness entry (2-day threshold, generous slack above the daily cadence) surfaces it if that
schedule ever breaks.
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
        return (0,)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessScoreRealizedIcLogCheckAdded:
    def test_score_realized_ic_log_stale_beyond_threshold_fires_warn(self):
        """Missed several daily runs - age_days is trading-day-aware (see
        test_staleness_daily_freq_trading_day_aware_20260908.py), so 2026-09-09 (Wed) to
        2026-09-14 (Mon) is 3 elapsed trading days (Thu/Fri/Mon), not 5 calendar days."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-09"))

        ic_results = [r for r in results if r.target_table == "score_realized_ic_log" and "age_days" in r.details]
        assert len(ic_results) == 1
        assert ic_results[0].severity == "warn"
        assert ic_results[0].details["age_days"] == 3

    def test_score_realized_ic_log_within_threshold_is_fresh(self):
        """2026-09-13 (Sun) to 2026-09-14 (Mon) is 0 elapsed trading days - still fresh."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        ic_results = [r for r in results if r.target_table == "score_realized_ic_log" and "age_days" in r.details]
        assert len(ic_results) == 1
        assert ic_results[0].severity == "info"
        assert ic_results[0].details["age_days"] == 0
