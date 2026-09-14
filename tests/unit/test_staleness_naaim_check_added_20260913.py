"""Regression test: StalenessChecker must cover naaim (NAAIM Exposure Index).

Live-caught (goal session 2026-09-13, "patrols and checks" quarantine-backlog audit):
naaim had ZERO staleness coverage despite load_naaim.py's own docstring calling it "CRITICAL
for market regime detection". Live-confirmed 46 days stale (last row 2026-07-29) with
data_loader_status still reporting status=COMPLETED, consecutive_failures=0 - invisible to
every existing check. Root cause is permanent: NAAIM put its Exposure Index behind a paywall
2026-08-01, so the loader gracefully returns a no-op data_unavailable marker forever instead
of erroring. WARN (not INFO) since this is a known-permanent condition worth surfacing on
every run, unlike a brand-new/uncharacterized check still building a false-positive record.
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


class TestStalenessNaaimCheckAdded:
    def test_naaim_46_days_stale_fires_warn(self):
        """The live-confirmed shape: last row 2026-07-29, checked on 2026-09-13 (46 days)."""
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-07-29"))

        naaim_results = [r for r in results if r.target_table == "naaim" and "age_days" in r.details]
        assert len(naaim_results) == 1
        assert naaim_results[0].severity == "warn"
        assert naaim_results[0].details["age_days"] == 46

    def test_naaim_within_threshold_is_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-05"))

        naaim_results = [r for r in results if r.target_table == "naaim" and "age_days" in r.details]
        assert len(naaim_results) == 1
        assert naaim_results[0].severity == "info"
        assert naaim_results[0].details["age_days"] == 8
