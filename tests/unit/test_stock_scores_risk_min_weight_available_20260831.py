#!/usr/bin/env python3
"""Regression test: RISK_MIN_WEIGHT_AVAILABLE (added 2026-08-31, /goal session - "review our
scores for each of the factors... make sure the results are making sense").

Bug found by sanity-checking stock_scores' Risk pillar top ranks: MYSZ ranked #1 by risk_score
(ahead of Royal Bank of Canada) and MVIS ranked in the top-12, despite both having only 6-7 days
of real price history - volatility_60d/252d and beta all NULL ("insufficient_returns"/
"spy_price_data_insufficient" in stability_metrics). _score_risk's weighted blend had no
minimum-coverage floor, so a symbol with only one thin component available renormalized that
single, thin-sample reading up to the FULL weight and produced a real 0-100 score
indistinguishable from a genuinely well-covered symbol's score.

Same bug class GROWTH_MIN_FIELDS_AVAILABLE fixed in _score_growth (see
test_stock_scores_growth_saturation_returns_float.py) and the pre-existing ~40%-of-101 floor in
_score_quality - 0.40 mirrors both.

UNIFORM EQUAL-WEIGHT 2026-09-11 (see loaders/stock_scores/pillar_weights.py's
BASE_PILLAR_WEIGHTS comment): _score_risk's 5 components are now flat 20% each instead of
45/15/15/10/15, so RISK_MIN_WEIGHT_AVAILABLE=0.40 now always requires >=2 of 5 components (no
single component can clear the floor alone anymore) - expected values below updated accordingly.
"""

from loaders.load_stock_scores import RISK_MIN_WEIGHT_AVAILABLE, StockScoresLoader


class TestRiskMinWeightAvailable:
    def _score(self, metrics: dict) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        return loader._score_risk({"data_unavailable": False, **metrics}, "TEST")

    def test_min_weight_available_constant_is_0_40(self):
        # Pinned explicitly - if this constant is ever retuned, this test should be updated
        # deliberately, not silently pass with a different threshold.
        assert RISK_MIN_WEIGHT_AVAILABLE == 0.40

    def test_max_drawdown_alone_returns_thin_sample_marker(self):
        """MYSZ/MVIS-shaped case: only max_drawdown_1y available (20% of nominal weight, below
        the 0.40 floor) - must withhold a score rather than renormalize one thin-sample reading
        up to a full 0-100 score."""
        result = self._score({"max_drawdown_1y": -3.08})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_beta_alone_returns_thin_sample_marker(self):
        """Beta alone is 20% of nominal weight, still below the 0.40 floor."""
        result = self._score({"beta": 1.0})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_beta_and_max_drawdown_together_clear_floor(self):
        """20% + 20% = 40% of nominal weight - exactly clears the 0.40 floor under equal
        weighting (previously 35%, below the floor, under the old 45/15/15/10/15 split)."""
        result = self._score({"beta": 1.0, "max_drawdown_1y": -10.0})
        assert isinstance(result, float)

    def test_volatility_60d_alone_returns_thin_sample_marker(self):
        """volatility_60d alone is 20% of nominal weight under equal weighting - no longer
        clears the 0.40 floor on its own (previously 45%, cleared it, under the old split)."""
        result = self._score({"volatility_60d": 0.20})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_volatility_252d_beta_and_drawdown_together_clear_floor(self):
        """20% + 20% + 20% = 60% of nominal weight - clears the 0.40 floor."""
        result = self._score({"volatility_252d": 0.20, "beta": 1.0, "max_drawdown_1y": -10.0})
        assert isinstance(result, float)

    def test_full_coverage_still_returns_real_score(self):
        result = self._score({"volatility_60d": 0.20, "volatility_252d": 0.20, "beta": 1.0, "max_drawdown_1y": -10.0})
        assert isinstance(result, float)

    def test_zero_fields_available_returns_no_scores_marker_not_thin_sample(self):
        result = self._score({})
        assert isinstance(result, dict)
        assert result["reason"] == "no_risk_scores_computed"
