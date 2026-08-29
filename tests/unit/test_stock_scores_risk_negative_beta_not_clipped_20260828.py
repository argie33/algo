#!/usr/bin/env python3
"""Regression test: StockScoresLoader._score_risk must not clip negative beta to 0
(loaders/load_stock_scores.py, _score_risk's beta sub-score).

Before this fix, `beta = max(0, metrics["beta"])` collapsed every negative beta to the same
input value (0) before computing distance-from-1.0, so ALL negative-beta symbols got an
identical beta_score=50 regardless of magnitude - live-DB-confirmed 2026-08-28: 548/5,009
symbols (~11% of the universe) have beta < 0, ranging from a mild -0.05 to an extreme -9.97,
and every single one scored the same 50 before this fix. Beta is a signed regression
coefficient (unlike volatility/downside-vol, which are magnitudes and correctly floor-clipped
elsewhere in this same function) - a wildly anti-correlated beta should score worse than a
mildly negative one, not identically.
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestRiskNegativeBetaNotClipped:
    def test_negative_betas_score_differently_by_magnitude(self):
        loader = StockScoresLoader()

        mild = loader._score_risk({"beta": -0.05}, "MILD")
        moderate = loader._score_risk({"beta": -0.5}, "MODERATE")
        extreme = loader._score_risk({"beta": -9.97}, "EXTREME")

        assert isinstance(mild, float)
        assert isinstance(moderate, float)
        assert isinstance(extreme, float)
        # Farther from the 1.0 target must score strictly worse, not identically.
        assert mild > moderate > extreme

    def test_beta_zero_and_mildly_negative_are_not_conflated(self):
        loader = StockScoresLoader()

        zero_beta = loader._score_risk({"beta": 0.0}, "ZERO")
        negative_beta = loader._score_risk({"beta": -0.5}, "NEG")

        assert negative_beta < zero_beta

    def test_extreme_negative_beta_saturates_to_zero_not_negative(self):
        """diff is capped at 2.0 before the score formula, so very negative beta still
        floors cleanly at beta_score=0 rather than going out of the 0-100 range."""
        loader = StockScoresLoader()

        score = loader._score_risk({"beta": -50.0}, "GARBAGE")

        assert score == pytest.approx(0.0)

    def test_positive_beta_symmetric_around_target_unaffected(self):
        """Sanity check the fix didn't change behavior for the common positive-beta case."""
        loader = StockScoresLoader()

        at_target = loader._score_risk({"beta": 1.0}, "TARGET")
        high_beta = loader._score_risk({"beta": 2.0}, "HIGH")

        assert at_target == pytest.approx(100.0)
        assert high_beta == pytest.approx(50.0)
