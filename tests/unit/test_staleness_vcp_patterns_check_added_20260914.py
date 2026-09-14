"""Regression test: StalenessChecker must cover vcp_patterns.

Live-caught (goal session 2026-09-14, systematic "are we covering all we should" sweep:
cross-referenced all 176 real DB tables against data_patrol_log's historical target_table
coverage). vcp_patterns had ZERO staleness coverage despite being actively written
(load_technical_indicators.py's _compute_and_insert_vcp_patterns, same daily run as
technical_data_daily) and actively consumed by live trading signal generation
(algo/orchestrator/phase7_signal_generation.py, loaders/load_signal_quality_scores.py).
Live-confirmed real per-symbol staleness tail: 161 active symbols with a >5-day-stale row, 37
with zero row at all, out of 10,828 symbols ever written. INFO severity (not WARN) since this
is a brand-new/uncharacterized check still building its real false-positive rate - same as
value_metrics/quality_metrics/momentum_metrics when they were first added, so severity alone
doesn't distinguish stale from fresh (both log INFO); the message text does.
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


class TestStalenessVcpPatternsCheckAdded:
    def test_vcp_patterns_stale_beyond_5_days_fires(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-08-25"))

        vcp_results = [r for r in results if r.target_table == "vcp_patterns" and "age_days" in r.details]
        assert len(vcp_results) == 1
        assert vcp_results[0].details["age_days"] == 13
        assert "stale" in vcp_results[0].message

    def test_vcp_patterns_within_threshold_is_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-11"))

        vcp_results = [r for r in results if r.target_table == "vcp_patterns" and "age_days" in r.details]
        assert len(vcp_results) == 1
        assert vcp_results[0].severity == "info"
        assert "stale" not in vcp_results[0].message
