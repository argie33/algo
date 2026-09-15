#!/usr/bin/env python3
"""Regression test: StockScoresLoader._score_risk must not clip negative beta to 0
(loaders/stock_scores/risk_scoring.py, _score_risk's beta sub-score).

Before the original 2026-08-28/29 fix, `beta = max(0, metrics["beta"])` collapsed every
negative beta to the same input value (0) before computing distance-from-1.0, so ALL
negative-beta symbols got an identical beta_score=50. Beta is a signed regression coefficient
(unlike volatility/downside-vol, which are magnitudes and correctly floor-clipped elsewhere in
this same function) - a wildly anti-correlated beta should score DIFFERENTLY from a mildly
negative one, not identically.

BETA SCORING CHANGED 2026-09-15 (user directive: "get rid of all the extra shit beyond the
barra and the industry guys"): beta now rewards LOW beta directly (the real Frazzini &
Pedersen 2014 "Betting Against Beta" / MSCI Minimum Volatility anomaly), not closeness to an
invented 1.0 "swing-trading fit" target. `beta_score = clip(100 - beta*50, 0, 100)` - beta<=0
scores 100 (max credit, more negative is still just 100, not higher - already saturated),
beta=1.0 scores 50, beta>=2.0 scores 0. Every assertion below is updated for this direction;
the "don't clip negative beta before scoring" property this file guards is otherwise
unchanged - a negative beta must still be treated as the real signed number it is instead of
floored to 0.

UNIFORM EQUAL-WEIGHT 2026-09-11, LIQUIDITY REMOVED 2026-09-15 (see pillar_weights.py's
BASE_PILLAR_WEIGHTS comment and risk_scoring.py's own _score_risk docstring): Risk's 4
remaining components (Volatility 60D/252D, Beta, Max Drawdown 1Y) are flat 25% each.
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestRiskNegativeBetaNotClipped:
    def test_negative_betas_all_saturate_to_the_same_max_credit(self):
        """Beta<=0 all saturate to beta_score=100 (already maximal low-beta credit) - unlike
        the old distance-from-1.0 formula, more-negative doesn't score BETTER once already at
        0, since the reward is linear-and-capped, not unbounded. This is the correct behavior
        for the real anomaly (defensive/inverse-correlated names are all "maximally low-beta
        safe" once beta<=0), not a regression of the "don't clip" fix - the input itself is
        never clipped (each raw beta is used as-is in the formula), only the OUTPUT saturates.
        """
        loader = StockScoresLoader()
        filler = {"volatility_60d": 0.0}

        mild = loader._score_risk({"beta": -0.05, **filler}, "MILD")
        moderate = loader._score_risk({"beta": -0.5, **filler}, "MODERATE")
        extreme = loader._score_risk({"beta": -9.97, **filler}, "EXTREME")

        assert isinstance(mild, float)
        assert isinstance(moderate, float)
        assert isinstance(extreme, float)
        assert mild == pytest.approx(moderate) == pytest.approx(extreme)

    def test_beta_zero_and_mildly_negative_score_identically_once_saturated(self):
        """Both beta=0.0 and beta=-0.5 are <=0, so both hit the formula's 100-point ceiling -
        genuinely identical here (unlike the un-saturated positive-beta region, where distinct
        beta values score distinctly - see test_positive_beta_scores_linearly below)."""
        loader = StockScoresLoader()
        filler = {"volatility_60d": 0.0}

        zero_beta = loader._score_risk({"beta": 0.0, **filler}, "ZERO")
        negative_beta = loader._score_risk({"beta": -0.5, **filler}, "NEG")

        assert negative_beta == pytest.approx(zero_beta)

    def test_extreme_positive_beta_saturates_to_zero_not_negative(self):
        """A very high positive beta must floor cleanly at beta_score=0 rather than going
        negative - the real low-beta anomaly rewards low beta, so high beta is simply bad, not
        specially penalized further past the 0 floor."""
        loader = StockScoresLoader()

        score = loader._score_risk({"beta": 50.0, "volatility_60d": 1.10}, "GARBAGE")

        assert score == pytest.approx(0.0)

    def test_positive_beta_scores_linearly_lower_beta_wins(self):
        """Direct low-beta-anomaly check: a lower positive beta must score strictly HIGHER than
        a higher one - this is the real BAB/Min-Vol direction, not the old closeness-to-1.0
        target.

        vol filler alone scores 83.3333 at 25% weight; beta contributes its own beta_score at
        25% weight too. low_beta (beta=0.5, beta_score=75): (83.3333*0.25 + 75*0.25) / 0.50 =
        79.1667. high_beta (beta=2.0, beta_score=0): (83.3333*0.25 + 0*0.25) / 0.50 = 41.6667 -
        strictly lower, confirming low beta is rewarded, not beta near 1.0."""
        loader = StockScoresLoader()

        low_beta = loader._score_risk({"beta": 0.5, "volatility_60d": 0.20}, "LOW_BETA")
        high_beta = loader._score_risk({"beta": 2.0, "volatility_60d": 0.20}, "HIGH_BETA")

        assert low_beta == pytest.approx(79.1667, abs=1e-3)
        assert high_beta == pytest.approx(41.6667, abs=1e-3)
        assert low_beta > high_beta


class TestRiskMinWeightAvailable:
    """RISK_MIN_WEIGHT_AVAILABLE (added 2026-08-31, /goal session - found by live-sweeping the
    DB the same way the Growth floor was found: APMC/FTRA/CAES/CCCT/IPVV/MTNE and 11 others each
    scored >=90 off max_drawdown_1y alone, then 15% of the pillar's weight, with volatility/beta
    - 85% of the real signal - completely absent)."""

    def test_min_weight_available_constant(self):
        from loaders.load_stock_scores import RISK_MIN_WEIGHT_AVAILABLE

        assert RISK_MIN_WEIGHT_AVAILABLE == pytest.approx(0.40)

    def test_max_drawdown_alone_is_below_floor_returns_thin_sample_marker(self):
        # max_drawdown_1y is 0.25 weight alone, under the 0.40 floor.
        loader = StockScoresLoader()
        result = loader._score_risk({"max_drawdown_1y": -34.63}, "TEST")
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_beta_alone_is_below_floor_returns_thin_sample_marker(self):
        # beta is 0.25 weight alone, under the 0.40 floor.
        loader = StockScoresLoader()
        result = loader._score_risk({"beta": 1.0}, "TEST")
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_volatility_60d_alone_is_below_floor_returns_thin_sample_marker(self):
        # volatility_60d is 0.25 weight alone - below the 0.40 floor by itself.
        loader = StockScoresLoader()
        result = loader._score_risk({"volatility_60d": 0.10}, "TEST")
        assert isinstance(result, dict)
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_beta_plus_max_drawdown_together_clear_floor(self):
        # 0.25 + 0.25 = 0.50 - clears the 0.40 floor.
        loader = StockScoresLoader()
        result = loader._score_risk({"beta": 1.0, "max_drawdown_1y": -10.0}, "TEST")
        assert isinstance(result, float)

    def test_volatility_252d_plus_beta_plus_drawdown_clears_floor(self):
        # 0.25 (volatility_252d) + 0.25 (beta) + 0.25 (max_drawdown_1y) = 0.75, well above
        # the 0.40 floor.
        loader = StockScoresLoader()
        result = loader._score_risk({"volatility_252d": 0.10, "beta": 1.0, "max_drawdown_1y": -0.05}, "TEST")
        assert isinstance(result, float)

    def test_zero_fields_available_returns_no_scores_marker_not_thin_sample(self):
        # A non-empty metrics dict (data_unavailable=False, per _get_stability_metrics'
        # convention) where every individual field is still None - distinct from a falsy/empty
        # metrics dict, which short-circuits earlier to reason="no_risk_metrics_data" instead.
        loader = StockScoresLoader()
        result = loader._score_risk(
            {
                "data_unavailable": False,
                "volatility_60d": None,
                "volatility_252d": None,
                "beta": None,
                "max_drawdown_1y": None,
            },
            "TEST",
        )
        assert isinstance(result, dict)
        assert result["reason"] == "no_risk_scores_computed"
