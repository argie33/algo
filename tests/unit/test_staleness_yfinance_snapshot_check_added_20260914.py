"""Regression test: StalenessChecker must cover yfinance_snapshot.

Live-caught (goal session 2026-09-14, quarterly_revenue_sum_vs_annual_extreme quarantine-
backlog continuation): yfinance_snapshot had ZERO DataPatrol coverage of any kind despite
being a real, still-actively-read pillar-input table (load_sec_valuations.py reads market_cap/
pe_ratio, load_company_profile.py reads sector). Live-confirmed 4,683 rows, MAX(updated_at)
2026-07-12 (~64 days stale as of this fix). Root cause is permanent: loaders/loader_registry.py's
own module docstring cites load_yfinance_snapshot.py as a loader DELETED (Session 295) after
being deprecated (Session 275, "SEC data now primary") - the table's writer is gone by design
and will never refresh again. WARN (not INFO) since this is an already-characterized, permanent
condition worth surfacing on every run, same reasoning as the naaim fix this mirrors.
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


class TestStalenessYfinanceSnapshotCheckAdded:
    def test_yfinance_snapshot_64_days_stale_fires_warn(self):
        """The live-confirmed shape: last row 2026-07-12, checked on 2026-09-14 (64 days)."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-07-12"))

        yf_results = [r for r in results if r.target_table == "yfinance_snapshot" and "age_days" in r.details]
        assert len(yf_results) == 1
        assert yf_results[0].severity == "warn"
        assert yf_results[0].details["age_days"] == 64

    def test_yfinance_snapshot_within_threshold_is_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-01"))

        yf_results = [r for r in results if r.target_table == "yfinance_snapshot" and "age_days" in r.details]
        assert len(yf_results) == 1
        assert yf_results[0].severity == "info"
        assert yf_results[0].details["age_days"] == 13
