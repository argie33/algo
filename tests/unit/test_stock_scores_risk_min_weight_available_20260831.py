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

AQR PIVOT 2026-09-17, then REVERTED 2026-09-19 (see risk_scoring.py's own module docstring for
the full evidence trail - live TOP/BVC bad-print Safety-leaderboard inversion, explicit user
directive to put every pillar back on one consistent MSCI/Barra methodology). Risk is back to
its pre-pivot 3-component construction: volatility_60d/cmra_12m/beta, UNIFORM EQUAL-WEIGHT
(1/3 each, RISK_COMPONENT_WEIGHT). Pass-1 (`_score_risk`, exercised here) is PROVISIONAL ONLY
post-revert - each present, reliable field contributes a flat NEUTRAL_PLACEHOLDER_SCORE (50.0)
rather than a hand-tuned curve, matching value_metrics.py's own post-revert Pass-1 convention;
the real score comes from update_risk_absolute_zscore_scores's batch z-score pass. A single
component alone (weight 1/3 ~= 0.333) no longer clears the 0.40 floor - >=2 of 3 are required,
restoring the original "combine thin components" scenario this file was written to guard.
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

    def test_beta_bab_alone_returns_no_scores_marker(self):
        """beta_bab is informational only post-revert (not a scoring input at all) - providing
        only it is equivalent to providing nothing."""
        result = self._score({"beta_bab": 1.0})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_risk_scores_computed"

    def test_single_component_alone_returns_thin_sample_marker(self):
        """Any single one of the 3 real components (weight 1/3 ~= 0.333) falls below the 0.40
        floor on its own - withheld as insufficient_risk_inputs_thin_sample, not silently
        promoted to a full score."""
        result = self._score({"beta": 1.0})
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_two_of_three_components_clears_floor(self):
        """2 of 3 components (weight 2/3 ~= 0.667) clears RISK_MIN_WEIGHT_AVAILABLE (0.40)."""
        result = self._score({"volatility_60d": 0.20, "beta": 1.0})
        assert isinstance(result, float)

    def test_full_coverage_still_returns_real_score(self):
        result = self._score(
            {"volatility_60d": 0.20, "cmra_12m": 0.20, "beta": 1.0, "beta_bab": 1.0, "max_drawdown_1y": -10.0}
        )
        assert isinstance(result, float)

    def test_zero_fields_available_returns_no_scores_marker_not_thin_sample(self):
        result = self._score({})
        assert isinstance(result, dict)
        assert result["reason"] == "no_risk_scores_computed"
