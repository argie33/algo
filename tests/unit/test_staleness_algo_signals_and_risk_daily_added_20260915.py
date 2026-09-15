"""Regression test: StalenessChecker must cover algo_signals and algo_risk_daily.

Live-caught (goal session 2026-09-15, "right coverage in the patrols" sweep - re-diffing the
current 180-table schema against the 2026-09-14 exhaustive 176-table coverage audit surfaced 4
new tables, 2 of which are genuinely live and uncovered). Both had ZERO DataPatrol coverage of
any kind:

- algo_signals: phase8_entry_execution.py's live signal generation table (execution_status/
  rejection_reason columns feed real trade decisions, same criticality tier as buy_sell_daily).
  Real gaps of several calendar days are normal (a row only exists when a signal actually
  fires), so this gets a generous 5d/INFO threshold, matching vcp_patterns' identical
  "new/uncharacterized, real gaps expected" precedent.
- algo_risk_daily: algo/risk/var.py's daily VaR/CVaR/beta/concentration risk report
  (phase9_reporting.py's own INSERT), one row per trading day with no gaps live-observed - if
  Phase 9 silently stops running, nothing previously caught that (data_patrol_config.py's
  get_staleness_windows() name-drops this table but is DEAD CONFIG per
  config_defaults_data_quality.py's own comment, a different unconsumed legacy system). 3d/INFO
  matches market_exposure_daily/capital_routing_daily's identical daily-real-money-input
  precedent.

INFO severity (not WARN) since both are brand-new/uncharacterized checks still building their
real false-positive rate - same as every other addition in this file's history, so severity
alone doesn't distinguish stale from fresh (both log INFO); the message text does.
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


class TestStalenessAlgoSignalsAndRiskDailyAdded:
    def test_algo_signals_stale_beyond_5_days_fires(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-08-25"))

        signal_results = [r for r in results if r.target_table == "algo_signals" and "age_days" in r.details]
        assert len(signal_results) == 1
        assert signal_results[0].details["age_days"] == 13
        assert "stale" in signal_results[0].message

    def test_algo_signals_within_threshold_is_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-11"))

        signal_results = [r for r in results if r.target_table == "algo_signals" and "age_days" in r.details]
        assert len(signal_results) == 1
        assert signal_results[0].severity == "info"
        assert "stale" not in signal_results[0].message

    def test_algo_risk_daily_stale_beyond_3_days_fires(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-08-25"))

        risk_results = [r for r in results if r.target_table == "algo_risk_daily" and "age_days" in r.details]
        assert len(risk_results) == 1
        assert risk_results[0].details["age_days"] == 13
        assert "stale" in risk_results[0].message

    def test_algo_risk_daily_within_threshold_is_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-12"))

        risk_results = [r for r in results if r.target_table == "algo_risk_daily" and "age_days" in r.details]
        assert len(risk_results) == 1
        assert risk_results[0].severity == "info"
        assert "stale" not in risk_results[0].message
