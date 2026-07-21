#!/usr/bin/env python3
"""Regression test for StockScoresLoader._pct_to_score (loaders/load_stock_scores.py).

momentum_1m/3m/6m/12m are computed and stored as percentage NUMBERS (e.g. 20.0 for +20%),
per load_risk_metrics_daily.py's ret_pct = (price_new - price_old) / price_old * 100. This
guards against a bug where the "weak momentum" exclusion band was checked on the wrong scale
(-0.03..0.03 instead of -3..3), making it match essentially no real momentum value - the
exclusion never actually fired, so tests/test_formula_accuracy.py's TestMomentumCalculation
(which re-implements the ±3 threshold inline rather than calling this function) kept passing
throughout.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestPctToScoreScale:
    def test_plus_20_pct_maps_to_100(self):
        assert StockScoresLoader._pct_to_score(20.0) == 100

    def test_minus_20_pct_maps_to_0(self):
        assert StockScoresLoader._pct_to_score(-20.0) == 0

    def test_zero_return_is_weak_signal_excluded(self):
        assert StockScoresLoader._pct_to_score(0.0) is None

    def test_within_weak_band_excluded(self):
        for pct in (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0):
            assert StockScoresLoader._pct_to_score(pct) is None, f"{pct}% should be excluded as weak signal"

    def test_just_outside_weak_band_scored(self):
        assert StockScoresLoader._pct_to_score(3.01) is not None
        assert StockScoresLoader._pct_to_score(-3.01) is not None

    def test_moderate_positive_return_scores_above_50(self):
        # +5% is a real, moderate momentum signal - must not be silently excluded or
        # collapsed near 50 (the symptom of checking the weak-band on the wrong scale)
        score = StockScoresLoader._pct_to_score(5.0)
        assert score is not None
        assert score > 55, f"expected a meaningfully above-center score, got {score}"

    def test_moderate_negative_return_scores_below_50(self):
        score = StockScoresLoader._pct_to_score(-5.0)
        assert score is not None
        assert score < 45, f"expected a meaningfully below-center score, got {score}"

    def test_extreme_return_clamped_to_bounds(self):
        assert StockScoresLoader._pct_to_score(200.0) == 100
        assert StockScoresLoader._pct_to_score(-200.0) == 0
