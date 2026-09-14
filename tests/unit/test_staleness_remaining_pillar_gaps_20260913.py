"""Regression test: StalenessChecker must cover stability_metrics/sec_valuations/
analyst_upgrade_downgrade/analyst_earnings_estimates.

Live-caught (goal session 2026-09-13, follow-up to the naaim fix): the new `cadence` field on
/api/scores/correctness-coverage (sourced from build_staleness_sources()) surfaced these four
real, actively-loaded pillar-input tables as having no staleness entry at all - same structural
blind spot as the value_metrics/quality_metrics/momentum_metrics gaps fixed earlier this session.

Adding the sec_valuations entry also caught a real bug before it shipped: its watermark column
`computed_at` wasn't in utils/db/sql_safety.py's SAFE_COLUMNS whitelist, so the check raised
"Unknown column 'computed_at' (not in whitelist)" and logged a generic ERROR instead of a real
freshness result - the same first-run gap as ex_dividend_date/report_date/filing_date before it.
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


class TestStalenessRemainingPillarGaps:
    def test_stability_metrics_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        rows = [r for r in results if r.target_table == "stability_metrics" and "age_days" in r.details]
        assert len(rows) == 1
        assert rows[0].severity == "info"

    def test_sec_valuations_watermark_column_is_whitelisted_and_fresh(self):
        """The specific bug this test guards: computed_at must be a valid safe column, not
        just a valid table config entry - a whitelist gap here silently downgrades every run
        to a generic ERROR ("Check failed: ...") instead of a real freshness result."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        rows = [r for r in results if r.target_table == "sec_valuations"]
        assert len(rows) == 1
        assert rows[0].severity == "info"
        assert "age_days" in rows[0].details, rows[0].message

    def test_analyst_upgrade_downgrade_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        rows = [r for r in results if r.target_table == "analyst_upgrade_downgrade" and "age_days" in r.details]
        assert len(rows) == 1
        assert rows[0].severity == "info"

    def test_analyst_earnings_estimates_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        rows = [r for r in results if r.target_table == "analyst_earnings_estimates" and "age_days" in r.details]
        assert len(rows) == 1
        assert rows[0].severity == "info"
