#!/usr/bin/env python3
"""Regression tests for the 5-input equal-weighted Growth blend (rebuilt 2026-08-28).

Covers the behavior the saturation-focused test_stock_scores_growth_saturation_returns_float.py
doesn't: renormalization over a partial subset of the 5 inputs, and the all-5-missing marker
path. See loaders/load_stock_scores.py's _score_growth docstring for the full evidence trail
(growth_multi_input_blend_test_20260828.py) behind replacing the single-input architecture.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestGrowthMultiInputBlend:
    def _score(self, **growth_fields: float | None) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False, **growth_fields}
        return loader._score_growth(metrics, "TEST")

    def test_all_five_inputs_averages_their_individual_scores(self):
        # All 5 at exactly 0% growth -> each component curve scores 40.0 -> average is 40.0,
        # not some other value a bug (e.g. summing instead of averaging) would produce.
        result = self._score(
            revenue_growth_1y=0.0,
            eps_growth_1y=0.0,
            ocf_growth_yoy=0.0,
            book_value_growth=0.0,
            sustainable_growth_rate=0.0,
        )
        assert isinstance(result, float)
        assert result == 40.0

    def test_partial_availability_renormalizes_over_present_components_only(self):
        # Only 2 of 5 present (both at 0% growth, each scoring 40.0) - the average must be
        # 40.0 (over the 2 available), NOT 16.0 (40*2/5, i.e. NOT silently dividing by 5 as
        # if the missing 3 counted as zero-score - that would be the exact "renormalization
        # bug" this test guards against).
        result = self._score(revenue_growth_1y=0.0, eps_growth_1y=0.0)
        assert isinstance(result, float)
        assert result == 40.0

    def test_single_input_available_matches_that_components_own_score(self):
        # Only sustainable_growth_rate present, at a value that doesn't saturate (cap=25):
        # the average-of-one must equal that single component's own curve score.
        result = self._score(sustainable_growth_rate=-12.5)
        assert isinstance(result, float)
        # sign-flipped: -(-12.5) = 12.5 > 0 -> min(100, 40 + (12.5/25)*60) = 70.0
        assert result == 70.0

    def test_mixed_availability_is_a_true_average_not_a_sum(self):
        # revenue_growth_1y=0.0 -> 40.0; book_value_growth=-39.71 -> saturates at 100.0
        # (same value as the saturation test file). Average of the two present components
        # must be 70.0, not 140.0 (a sum) and not 20.0 (dividing the sum by 5 anyway).
        result = self._score(revenue_growth_1y=0.0, book_value_growth=-39.71)
        assert isinstance(result, float)
        assert result == 70.0

    def test_all_five_inputs_none_returns_marker_dict(self):
        result = self._score(
            revenue_growth_1y=None,
            eps_growth_1y=None,
            ocf_growth_yoy=None,
            book_value_growth=None,
            sustainable_growth_rate=None,
        )
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_growth_inputs_available"

    def test_metrics_missing_entirely_returns_no_growth_metrics_data_marker(self):
        loader = StockScoresLoader.__new__(StockScoresLoader)
        result = loader._score_growth(None, "TEST")
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_growth_metrics_data"
