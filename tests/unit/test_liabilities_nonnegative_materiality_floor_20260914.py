"""Regression test: total_liabilities_nonnegative/current_liabilities_nonnegative (annual and
quarterly) must apply a 1%-of-total_assets materiality floor, not flag any negative value.

Live-caught (goal session 2026-09-14, DB-wide nonnegative-check sweep follow-up):
total_liabilities/current_liabilities are DERIVED PLUG values in this schema
(total_assets - stockholders_equity, not a directly-extracted XBRL fact), so a tiny negative
can be pure rounding noise between two independently-filed real numbers rather than a real
bug - live-confirmed SOS FY2021 Q2 (-$91,000 vs $559,695,000 total assets, 0.016%). The floor
must NOT suppress a real, large violation like TW FY2019 Q1 (-$4,597,978,900 against a real
but nominal $100 total_assets - a genuine pre-IPO shell-entity balance sheet, unboundedly over
any % floor) or any of the genuine sign-typo fixes landed this session (smallest one, ETR, was
9.6% of assets - a ~600x margin above the 1% floor).
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> TieOutChecker:
    return TieOutChecker(PatrolConfig())


def _mock_cursor(fetchall_results: list[list[dict]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.side_effect = fetchall_results
    return cur


class TestTotalLiabilitiesNonnegativeMaterialityFloor:
    def test_immaterial_negative_relative_to_assets_not_flagged(self) -> None:
        """SOS-shaped: -$91,000 vs $559,695,000 assets (0.016%) - below the 1% floor."""
        cur = _mock_cursor(
            [[{"symbol": "SOS", "fiscal_year": 2021, "total_liabilities": -91_000.0, "total_assets": 559_695_000.0}]]
        )
        checker = _checker()
        checker.check_total_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_material_negative_relative_to_tiny_assets_still_flagged(self) -> None:
        """TW-shaped: -$4,597,978,900 against $100 assets - unboundedly over any % floor."""
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "TW",
                        "fiscal_year": 2019,
                        "total_liabilities": -4_597_978_900.0,
                        "total_assets": 100.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_total_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"
        assert checker.results[0].details["examples"][0]["symbol"] == "TW"

    def test_real_sign_typo_magnitude_still_flagged(self) -> None:
        """ETR-shaped: 9.6% of assets - the smallest genuine violation fixed this session,
        well above the 1% floor (a ~600x margin over SOS's noise case)."""
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ETR",
                        "fiscal_year": 2008,
                        "total_liabilities": -3_765_894_000.0,
                        "total_assets": 36_616_818_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_total_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"

    def test_null_total_assets_falls_back_to_flagging(self) -> None:
        """No total_assets to compare against - can't apply a floor, so flag conservatively."""
        cur = _mock_cursor(
            [[{"symbol": "ZZZZ", "fiscal_year": 2020, "total_liabilities": -500.0, "total_assets": None}]]
        )
        checker = _checker()
        checker.check_total_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"


class TestQuarterlyTotalLiabilitiesNonnegativeMaterialityFloor:
    def test_immaterial_negative_not_flagged(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "SOS",
                        "fiscal_year": 2021,
                        "fiscal_quarter": 2,
                        "total_liabilities": -91_000.0,
                        "total_assets": 559_695_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_total_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_material_negative_still_flagged(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "TW",
                        "fiscal_year": 2019,
                        "fiscal_quarter": 1,
                        "total_liabilities": -4_597_978_900.0,
                        "total_assets": 100.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_total_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"


class TestCurrentLiabilitiesNonnegativeMaterialityFloor:
    def test_immaterial_negative_not_flagged(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "ZZZZ", "fiscal_year": 2020, "current_liabilities": -1_000.0, "total_assets": 100_000_000.0}]]
        )
        checker = _checker()
        checker.check_current_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_material_negative_still_flagged(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ETR",
                        "fiscal_year": 2008,
                        "current_liabilities": -3_765_894_000.0,
                        "total_assets": 36_616_818_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_current_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"


class TestQuarterlyCurrentLiabilitiesNonnegativeMaterialityFloor:
    def test_immaterial_negative_not_flagged(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ZZZZ",
                        "fiscal_year": 2020,
                        "fiscal_quarter": 2,
                        "current_liabilities": -1_000.0,
                        "total_assets": 100_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_material_negative_still_flagged(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ETR",
                        "fiscal_year": 2009,
                        "fiscal_quarter": 2,
                        "current_liabilities": -3_501_219_000.0,
                        "total_assets": 36_485_220_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_liabilities_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"
