"""Regression test: revenue_yoy_magnitude_jump (and the 7 sibling YoY magnitude checks sharing
the same _yoy_magnitude_jump helper) must skip symbol/years recorded in
yoy_magnitude_jump_dismissed.json - the same "triage once, persist the verdict" pattern already
proven for quarterly_revenue_sum_vs_annual_extreme (tie_out_shared.py's
load_revenue_extreme_dismissed).

Added 2026-09-14 (goal session: dismiss-list coverage sweep). This checker's own module
docstring already names QXO's real $56.9M->$6.8422B FY2025 revenue jump (a genuine roll-up
acquisition) as the original motivating example for treating YoY magnitude jumps as a review
queue - before this fix, nothing ever recorded that verdict, so every patrol run re-flagged an
already-reviewed case forever.
"""

from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.statistical_anomaly import StatisticalAnomalyChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> StatisticalAnomalyChecker:
    return StatisticalAnomalyChecker(PatrolConfig())


def _mock_cursor(fetchall_results: list[list[dict]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.side_effect = fetchall_results
    return cur


class TestYoyMagnitudeJumpDismissList:
    def test_dismissed_symbol_year_is_not_flagged(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "QXO", "fiscal_year": 2025, "curr_value": 6_842_200_000.0, "prior_value": 56_900_000.0}]]
        )
        checker = _checker()
        with patch(
            "algo.monitoring.data_patrol.checks.statistical_anomaly.load_yoy_magnitude_jump_dismissed",
            return_value={"revenue_yoy_magnitude_jump:QXO:2025": "genuine real event"},
        ):
            checker.check_revenue_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_same_symbol_year_different_check_name_still_flagged(self) -> None:
        """The dismiss key is scoped by check_name - a QXO:2025 dismissal for revenue must NOT
        suppress a genuinely different field (e.g. total_assets) for the same symbol/year."""
        cur = _mock_cursor(
            [[{"symbol": "QXO", "fiscal_year": 2025, "curr_value": 6_842_200_000.0, "prior_value": 56_900_000.0}]]
        )
        checker = _checker()
        with patch(
            "algo.monitoring.data_patrol.checks.statistical_anomaly.load_yoy_magnitude_jump_dismissed",
            return_value={"revenue_yoy_magnitude_jump:QXO:2025": "genuine real event"},
        ):
            checker.check_total_assets_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"

    def test_real_dismiss_file_suppresses_qxo(self) -> None:
        """End-to-end against the real checked-in dismiss file, not a mock."""
        cur = _mock_cursor(
            [[{"symbol": "QXO", "fiscal_year": 2025, "curr_value": 6_842_200_000.0, "prior_value": 56_900_000.0}]]
        )
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_undismissed_symbol_year_still_flagged(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "JUMPCO", "fiscal_year": 2025, "curr_value": 60_000_000.0, "prior_value": 2_000_000.0}]]
        )
        checker = _checker()
        checker.check_revenue_yoy_magnitude_jump(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"
        assert checker.results[0].details["examples"][0]["symbol"] == "JUMPCO"
