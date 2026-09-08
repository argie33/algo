#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's VALUE_MIN_WEIGHT floor
(loaders/stock_scores/value_score.py) - same bug class as Growth's
GROWTH_MIN_FIELDS_AVAILABLE and Quality's 40-point minimum-available-weight floor.

Before this fix, `if total_weight > 0: return weighted_sum / total_weight` treated ANY
nonzero weight as a fully-confident score - live-verified 71 universe symbols got a
value_score built from <=20% of nominal weight (most often dividend_yield=0.0 alone, 10%
of nominal weight, for a non-dividend-paying stock with every multiple missing).
"""

from loaders.load_stock_scores import StockScoresLoader
from loaders.stock_scores.value_score import VALUE_MIN_WEIGHT


class TestValueMinWeightThinSample:
    def test_dividend_only_below_floor_returns_marker(self):
        """dividend_yield alone is 0.10 of nominal weight, below VALUE_MIN_WEIGHT (0.40) -
        must return a data_unavailable marker, not a confident float."""
        loader = StockScoresLoader()

        result = loader._score_value({"dividend_yield": 0.0}, "THIN")

        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_value_inputs_thin_sample"

    def test_at_or_above_floor_returns_float(self):
        """PE + PB together are 0.54 of nominal weight, at/above VALUE_MIN_WEIGHT - must
        return a real score."""
        loader = StockScoresLoader()

        result = loader._score_value({"pe_ratio": 18.0, "pb_ratio": 2.0}, "COVERED")

        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_no_inputs_at_all_still_returns_no_value_scores_computed_marker(self):
        """Zero weight (no scoreable fields at all) must keep its own pre-existing,
        distinct marker reason rather than being folded into the new thin-sample one."""
        loader = StockScoresLoader()

        result = loader._score_value({"pe_ratio": None}, "EMPTY")

        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_value_scores_computed"

    def test_min_weight_constant_matches_growth_quality_convention(self):
        """0.40 mirrors Growth's ~42% (5/12) and Quality's ~40% (40/101) minimum-coverage
        floors - not re-litigating that convention here, just pinning the value."""
        assert VALUE_MIN_WEIGHT == 0.40
