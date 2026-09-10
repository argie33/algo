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

    def test_sort_survives_ratio_rounding_to_zero(self) -> None:
        """2026-09-09: found live against JMKE (curr=$1.00, prior=$8.18B) - ratio rounds to
        0.0000 at the reported 4dp, and the sort key used to divide by that rounded value."""
        cur = _mock_cursor(
            [
                [
                    {"symbol": "MILDCO", "fiscal_year": 2025, "curr_value": 100_000_000.0, "prior_value": 2_000_000.0},
                    {"symbol": "JMKE", "fiscal_year": 2025, "curr_value": 1.0, "prior_value": 8_181_000_000.0},
                ]
            ]
        )
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        symbols = [ex["symbol"] for ex in checker.results[0].details["examples"]]
        assert symbols[0] == "JMKE"  # most extreme swing sorts first

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


class TestExtendedFieldCoverage20260909:
    """Added 2026-09-09: same generic helper, extended past revenue/total_assets to every
    other field tie_out.py already reads off annual_income_statement/annual_balance_sheet/
    annual_cash_flow - one representative flag + one representative no-flag per field is
    enough since _yoy_magnitude_jump itself is already covered above; these just confirm
    each new check wires the right (check_name, table, field) tuple."""

    def test_run_invokes_all_checks(self) -> None:
        checker = _checker()
        cur = _mock_cursor([[]] * 9)
        checker.run(cur)
        names = {r.check_name for r in checker.results}
        assert names == set()  # no rows flagged, but no errors either
        assert cur.execute.call_count == 9

    def test_gross_profit_flags_large_jump(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "GPCO", "fiscal_year": 2025, "curr_value": 80_000_000.0, "prior_value": 1_000_000.0}]]
        )
        checker = _checker()
        checker.check_gross_profit_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "gross_profit_yoy_magnitude_jump"

    def test_net_income_flags_large_jump(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "NICO", "fiscal_year": 2025, "curr_value": 90_000_000.0, "prior_value": 1_000_000.0}]]
        )
        checker = _checker()
        checker.check_net_income_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "net_income_yoy_magnitude_jump"

    def test_operating_income_does_not_flag_normal_change(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "OICO", "fiscal_year": 2025, "curr_value": 12_000_000.0, "prior_value": 10_000_000.0}]]
        )
        checker = _checker()
        checker.check_operating_income_yoy_magnitude_jump(cur)
        assert checker.results == []

    def test_pretax_income_flags_large_shrinkage(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "PTCO", "fiscal_year": 2025, "curr_value": 500_000.0, "prior_value": 200_000_000.0}]]
        )
        checker = _checker()
        checker.check_pretax_income_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "pretax_income_yoy_magnitude_jump"

    def test_total_liabilities_flags_large_jump(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "TLCO", "fiscal_year": 2025, "curr_value": 3_000_000_000.0, "prior_value": 40_000_000.0}]]
        )
        checker = _checker()
        checker.check_total_liabilities_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "total_liabilities_yoy_magnitude_jump"

    def test_stockholders_equity_flags_large_jump(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "SECO", "fiscal_year": 2025, "curr_value": 1_500_000_000.0, "prior_value": 20_000_000.0}]]
        )
        checker = _checker()
        checker.check_stockholders_equity_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "stockholders_equity_yoy_magnitude_jump"

    def test_operating_cash_flow_flags_large_jump(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "OCFCO", "fiscal_year": 2025, "curr_value": 500_000_000.0, "prior_value": 5_000_000.0}]]
        )
        checker = _checker()
        checker.check_operating_cash_flow_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "operating_cash_flow_yoy_magnitude_jump"
