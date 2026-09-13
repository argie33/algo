"""Regression test for tie_out_implausible_magnitude.py (added 2026-09-13, goal session:
quarterly-revenue-identity backlog).

Wires the hand-run implausible-value scan that found MKZR (REIT-exclusive-concept revenue
tagged 1,000,000x too large), INVE (NetIncomeLoss tagged 1,000,000x too large vs. its own
ProfitLoss sibling), and SKM/KT/TSM/IX (stale pre-FX-conversion legacy rows) into the
permanent DataPatrol suite, so this class of bug is caught automatically on every patrol run
instead of needing someone to remember to run a one-off script.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import INFO, WARN, PatrolConfig


def _checker() -> TieOutChecker:
    return TieOutChecker(PatrolConfig())


def _mock_cursor(fetchall_result: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = fetchall_result
    return cur


class TestRevenueImplausibleMagnitude:
    def test_mkzr_shaped_row_flagged(self) -> None:
        checker = _checker()
        cur = _mock_cursor([{"symbol": "MKZR", "fiscal_year": 2024, "revenue": 8_030_316_000_000.0}])

        checker.check_revenue_implausible_magnitude(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert checker.results[0].details["count"] == 1

    def test_real_mega_cap_revenue_not_flagged(self) -> None:
        """Walmart's real ~$680B FY2024 revenue - the largest real filer on record - must stay
        well under the $1T ceiling and never be flagged."""
        checker = _checker()
        cur = _mock_cursor([{"symbol": "WMT", "fiscal_year": 2024, "revenue": 680_000_000_000.0}])

        checker.check_revenue_implausible_magnitude(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO


class TestNetIncomeImplausibleMagnitude:
    def test_inve_shaped_row_flagged(self) -> None:
        checker = _checker()
        cur = _mock_cursor([{"symbol": "INVE", "fiscal_year": 2021, "net_income": 1_620_000_000_000.00}])

        checker.check_net_income_implausible_magnitude(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert checker.results[0].details["examples"][0]["symbol"] == "INVE"


class TestQuarterlyOperatingCashFlowImplausibleMagnitude:
    def test_ix_shaped_row_flagged(self) -> None:
        checker = _checker()
        cur = _mock_cursor(
            [
                {
                    "symbol": "IX",
                    "fiscal_year": 2024,
                    "fiscal_quarter": 3,
                    "operating_cash_flow": 579_624_000_000.00,
                }
            ]
        )

        checker.check_quarterly_operating_cash_flow_implausible_magnitude(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN

    def test_clean_data_logs_info_not_silent(self) -> None:
        checker = _checker()
        cur = _mock_cursor([])

        checker.check_quarterly_operating_cash_flow_implausible_magnitude(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
