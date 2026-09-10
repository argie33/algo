"""Regression tests for CompositeScoreReconciliationChecker
(algo/monitoring/data_patrol/checks/composite_score_reconciliation.py).

Added 2026-09-08 (goal: score sanity audit found no tie-out check covers the pillar-score layer
itself). Covers: exact match, the legitimate value/risk interaction shift (not flagged), a real
divergence (flagged WARN), a divergence beyond the rounding budget (flagged ERROR), a missing
pillar (contributes zero, not flagged), and exception handling.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.composite_score_reconciliation import (
    CompositeScoreReconciliationChecker,
)
from algo.monitoring.data_patrol.config import ERROR, INFO, WARN, PatrolConfig


def _checker() -> CompositeScoreReconciliationChecker:
    return CompositeScoreReconciliationChecker(PatrolConfig())


def _mock_cursor(rows: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


def _row(
    symbol: str,
    composite_score: float,
    quality: float | None = 50.0,
    growth: float | None = 50.0,
    value: float | None = 50.0,
    risk: float | None = 50.0,
    momentum: float | None = 50.0,
) -> dict:
    return {
        "symbol": symbol,
        "date": "2026-09-08",
        "quality_score": quality,
        "growth_score": growth,
        "value_score": value,
        "risk_score": risk,
        "momentum_score": momentum,
        "composite_score": composite_score,
    }


class TestCompositeScoreReconciliation:
    def test_all_pillars_at_50_with_risk_50_reconciles_exactly(self) -> None:
        # risk_score=50 is the interaction's own midpoint - base weights apply unmodified, so
        # a uniform 50 across every pillar must reconcile to exactly 50.0 composite.
        # FIXED 2026-09-10: a clean pass still logs one INFO result (not []) so a prior WARN/
        # ERROR finding can be superseded/resolved on the next patrol run.
        cur = _mock_cursor([_row("FLAT", composite_score=50.0)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == INFO

    def test_legitimate_value_risk_interaction_shift_not_flagged(self) -> None:
        # risk_score=0 (riskiest) shifts weight from Risk to Value by the full
        # VALUE_RISK_INTERACTION_MAX_SHIFT - a real, deterministic effect, not a bug. Value=100
        # scored with the *shifted* (higher) weight while Risk=0 scored with the shifted (lower)
        # weight must still reconcile exactly against the checker's own recompute.
        from loaders.stock_scores.pillar_weights import _value_risk_adjusted_weights

        weights = _value_risk_adjusted_weights(0.0)
        composite = (
            weights["quality"] * 50.0
            + weights["growth"] * 50.0
            + weights["value"] * 100.0
            + weights["risk"] * 0.0
            + weights["momentum"] * 50.0
        )
        cur = _mock_cursor([_row("RISKY", composite_score=round(composite, 2), value=100.0, risk=0.0)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == INFO

    def test_missing_pillar_contributes_zero_not_flagged(self) -> None:
        # momentum missing (None) - contributes 0 to the weighted sum, not redistributed to the
        # other 4 pillars (GOVERNANCE: no weight redistribution).
        from loaders.stock_scores.pillar_weights import _value_risk_adjusted_weights

        weights = _value_risk_adjusted_weights(50.0)
        composite = (
            weights["quality"] * 50.0 + weights["growth"] * 50.0 + weights["value"] * 50.0 + weights["risk"] * 50.0
        )
        cur = _mock_cursor([_row("NOMOM", composite_score=round(composite, 2), momentum=None)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == INFO

    def test_real_divergence_flagged_warn(self) -> None:
        # Stored composite is 0.5 points off the true recompute - beyond the 0.10 rounding
        # budget but well under the 1.0 ERROR threshold.
        cur = _mock_cursor([_row("DRIFT", composite_score=50.5)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == WARN
        assert results[0].details["examples"][0]["symbol"] == "DRIFT"

    def test_large_divergence_flagged_error(self) -> None:
        # 20 points off - not explainable by rounding, near-certain bug severity.
        cur = _mock_cursor([_row("BROKEN", composite_score=70.0)])
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
