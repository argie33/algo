"""Regression tests for PillarScoreReconciliationChecker
(algo/monitoring/data_patrol/checks/pillar_score_reconciliation.py).

Added 2026-09-08 (goal: score sanity audit follow-up to composite_score_reconciliation.py).
Covers: exact match, a real divergence (flagged WARN), a divergence beyond the rounding budget
(flagged ERROR), and exception handling.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.pillar_score_reconciliation import (
    PillarScoreReconciliationChecker,
)
from algo.monitoring.data_patrol.config import ERROR, WARN, PatrolConfig


def _checker() -> PillarScoreReconciliationChecker:
    return PillarScoreReconciliationChecker(PatrolConfig())


def _mock_cursor(rows: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


def _row(symbol: str, stock_scores_quality_score: float, quality_metrics_quality_score: float) -> dict:
    return {
        "symbol": symbol,
        "date": "2026-09-08",
        "stock_scores_quality_score": stock_scores_quality_score,
        "quality_metrics_quality_score": quality_metrics_quality_score,
    }


class TestPillarScoreReconciliation:
    def test_matching_scores_not_flagged(self) -> None:
        cur = _mock_cursor([_row("MATCH", 72.5, 72.5)])
        results = _checker().run(cur)
        assert results == []

    def test_rounding_noise_not_flagged(self) -> None:
        cur = _mock_cursor([_row("ROUND", 72.50, 72.505)])
        results = _checker().run(cur)
        assert results == []

    def test_stale_stock_scores_flagged_warn(self) -> None:
        # stock_scores.quality_score is 0.5 points behind a since-updated quality_metrics.
        cur = _mock_cursor([_row("STALE", 70.0, 70.5)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == WARN
        assert results[0].details["examples"][0]["symbol"] == "STALE"

    def test_large_divergence_flagged_error(self) -> None:
        # 30 points off - a real, unreloaded rewrite (e.g. broker-dealer fcf_margin exclusion
        # landing in quality_metrics without stock_scores being reloaded from it).
        cur = _mock_cursor([_row("GS", 30.0, 60.0)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == ERROR

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.fetchall.side_effect = RuntimeError("schema drift")
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == ERROR
        assert "schema drift" in results[0].message
