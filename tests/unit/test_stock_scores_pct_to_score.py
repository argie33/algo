#!/usr/bin/env python3
"""Regression test for StockScoresLoader._pct_to_score (loaders/load_stock_scores.py).

momentum_1m/3m/6m/12m are computed and stored as percentage NUMBERS (e.g. 20.0 for +20%),
per load_risk_metrics_daily.py's ret_pct = (price_new - price_old) / price_old * 100.

WEAK-MOMENTUM "DEAD ZONE" REMOVED 2026-09-16 (factor-purity sweep, see _pct_to_score's own
docstring in momentum_scoring.py): the old -3%..+3% "insufficient conviction" exclusion had no
counterpart in any published momentum construction (MSCI/Carhart/Jegadeesh-Titman all
z-score/rank the full continuous distribution, including near-zero returns) - it was an
invented threshold, not industry methodology, so it's gone. This file used to also guard
against a bug where that band was checked on the wrong scale (-0.03..0.03 instead of -3..3,
making it never actually fire) - that history is moot now that the band itself is removed;
every pct_return, however small, gets a real linear score.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestPctToScoreScale:
    def test_plus_20_pct_maps_to_100(self):
        assert StockScoresLoader._pct_to_score(20.0) == 100

    def test_minus_20_pct_maps_to_0(self):
        assert StockScoresLoader._pct_to_score(-20.0) == 0

    def test_zero_return_scores_exactly_center(self):
        assert StockScoresLoader._pct_to_score(0.0) == 50.0

    def test_small_returns_score_linearly_not_excluded(self):
        for pct in (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0):
            score = StockScoresLoader._pct_to_score(pct)
            assert score is not None, f"{pct}% must be scored, not excluded (dead zone removed 2026-09-16)"
            assert score == 50.0 + pct / 0.4

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
