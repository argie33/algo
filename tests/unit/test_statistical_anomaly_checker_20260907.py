"""Regression tests for StatisticalAnomalyChecker (algo/monitoring/data_patrol/checks/statistical_anomaly.py).

Added 2026-09-07 (goal session: build out the "statistical peer/history deviation" layer
identified as the next-highest-leverage XBRL validation gap after automating new-concept
detection - see [[xbrl_new_concept_automation_landed_20260907]] in memory).
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.statistical_anomaly import StatisticalAnomalyChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> StatisticalAnomalyChecker:
    return StatisticalAnomalyChecker(PatrolConfig())


def _mock_cursor(fetchall_results: list[list[dict]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.side_effect = fetchall_results
    return cur


class TestRevenueYoyMagnitudeJump:
    def test_flags_large_jump_above_floor(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {"symbol": "JUMPCO", "fiscal_year": 2025, "curr_value": 60_000_000.0, "prior_value": 2_000_000.0},
                ]
            ]
        )
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "revenue_yoy_magnitude_jump"
        assert checker.results[0].severity == "warn"
        assert checker.results[0].details["examples"][0]["symbol"] == "JUMPCO"

    def test_flags_large_shrinkage(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {"symbol": "SHRINKCO", "fiscal_year": 2025, "curr_value": 500_000.0, "prior_value": 300_000_000.0},
                ]
            ]
        )
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1

    def test_does_not_flag_normal_growth(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "NORMALCO",
                        "fiscal_year": 2025,
                        "curr_value": 12_000_000.0,
                        "prior_value": 10_000_000.0,
                    },
                ]
            ]
        )
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert checker.results == []

    def test_ignores_sub_floor_swings(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {"symbol": "TINYCO", "fiscal_year": 2025, "curr_value": 300_000.0, "prior_value": 10_000.0},
                ]
            ]
        )
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert checker.results == []

    def test_scan_failure_logs_error_not_raise(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "error"


class TestTotalAssetsYoyMagnitudeJump:
    def test_flags_large_jump(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ASSETCO",
                        "fiscal_year": 2025,
                        "curr_value": 2_000_000_000.0,
                        "prior_value": 50_000_000.0,
                    },
                ]
            ]
        )
        checker = _checker()
        checker.check_total_assets_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "total_assets_yoy_magnitude_jump"
