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
BASE_PILLAR_WEIGHTS comment): _score_risk's components were flat 20% each instead of
45/15/15/10/15, so RISK_MIN_WEIGHT_AVAILABLE=0.40 always requires >=2 of 5 components (no
single component can clear the floor alone).

MAX_DRAWDOWN_1Y REMOVED FROM SCORING 2026-09-16 (factor-purity sweep - see _score_risk's own
docstring: never a real Barra/MSCI risk descriptor, era-flipped sign with no stable predictive
power). max_drawdown_1y values passed into `_score()` below are now inert (no vote in the
score) - expected values updated accordingly.

AQR PIVOT 2026-09-17 (see risk_scoring.py's own module docstring): Risk's scored input is now
`beta_bab` alone (RISK_COMPONENT_WEIGHT=1.0) - volatility_60d/cmra_12m/beta are informational
only, no longer scoring inputs at all. A symbol either has beta_bab (weight 1.0, clears the
0.40 floor outright) or doesn't (weight 0) - the "combine 2 of N thin components to clear the
floor" scenario this file was originally written to guard no longer exists, since there is only
one component to have or not have. Assertions below are updated for that binary gate.
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

    def test_max_drawdown_alone_returns_no_scores_marker(self):
        """max_drawdown_1y is no longer a scoreable input (removed 2026-09-16) - providing only
        it must behave identically to providing nothing at all."""
        result = self._score({"max_drawdown_1y": -3.08})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_risk_scores_computed"

    def test_beta_alone_returns_no_scores_marker(self):
        """Plain `beta` is no longer read by _score_risk at all (superseded by beta_bab for
        scoring, AQR PIVOT 2026-09-17) - providing only it is equivalent to providing nothing."""
        result = self._score({"beta": 1.0})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_risk_scores_computed"

    def test_beta_bab_alone_clears_floor(self):
        """beta_bab is the pillar's sole scored input (weight 1.0) - alone, it clears the 0.40
        floor outright. max_drawdown_1y/beta are passed too but must not contribute."""
        result = self._score({"beta_bab": 1.0, "beta": 1.0, "max_drawdown_1y": -10.0})
        assert isinstance(result, float)

    def test_volatility_60d_alone_returns_no_scores_marker(self):
        """volatility_60d is informational only now (not a scoring input at all, AQR PIVOT
        2026-09-17) - providing only it is equivalent to providing nothing."""
        result = self._score({"volatility_60d": 0.20})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_risk_scores_computed"

    def test_cmra_12m_alone_returns_no_scores_marker(self):
        """cmra_12m is informational only now (not a scoring input at all, AQR PIVOT
        2026-09-17)."""
        result = self._score({"cmra_12m": 0.20, "max_drawdown_1y": -10.0})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_risk_scores_computed"

    def test_full_coverage_still_returns_real_score(self):
        result = self._score(
            {"volatility_60d": 0.20, "cmra_12m": 0.20, "beta": 1.0, "beta_bab": 1.0, "max_drawdown_1y": -10.0}
        )
        assert isinstance(result, float)

    def test_zero_fields_available_returns_no_scores_marker_not_thin_sample(self):
        result = self._score({})
        assert isinstance(result, dict)
        assert result["reason"] == "no_risk_scores_computed"
