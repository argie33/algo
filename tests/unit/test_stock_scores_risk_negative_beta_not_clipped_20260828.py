#!/usr/bin/env python3
"""Regression test: StockScoresLoader._score_risk must not clip negative beta to 0
(loaders/load_stock_scores.py, _score_risk's beta sub-score).

Before this fix, `beta = max(0, metrics["beta"])` collapsed every negative beta to the same
input value (0) before computing distance-from-1.0, so ALL negative-beta symbols got an
identical beta_score=50 before this fix. Beta is a signed regression coefficient (unlike
volatility/downside-vol, which are magnitudes and correctly floor-clipped elsewhere in this same
function) - a wildly anti-correlated beta should score worse than a mildly negative one, not
identically.

UPDATED 2026-08-31 (/goal session, RISK_MIN_WEIGHT_AVAILABLE): _score_risk now withholds a score
below a minimum available-weight floor (see that constant's docstring - found the same
thin-sample-saturation problem in Risk that Growth already had: APMC/FTRA/CAES and others were
landing a near-100 risk_score off max_drawdown_1y alone, 15% of the pillar's weight). Beta alone
is only 20% weight, below the 40% floor, so every test below now supplies a `volatility_60d`
filler to clear it. `_vol_curve_score` is a simple 4-segment piecewise curve (see that method) -
each filler value below was chosen so its OWN score exactly matches what the test wants to
demonstrate about beta, since a weighted average of two IDENTICAL values equals that same value
regardless of their weights - this keeps every original exact-value assertion true, not just the
ordering ones.
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestRiskNegativeBetaNotClipped:
    def test_negative_betas_score_differently_by_magnitude(self):
        loader = StockScoresLoader()
        # volatility_60d=0.0 -> v60_score=100.0 (weight 0.45), just a floor-clearing filler here;
        # ordering among the three beta cases holds regardless of the filler's own value.
        filler = {"volatility_60d": 0.0}

        mild = loader._score_risk({"beta": -0.05, **filler}, "MILD")
        moderate = loader._score_risk({"beta": -0.5, **filler}, "MODERATE")
        extreme = loader._score_risk({"beta": -9.97, **filler}, "EXTREME")

        assert isinstance(mild, float)
        assert isinstance(moderate, float)
        assert isinstance(extreme, float)
        # Farther from the 1.0 target must score strictly worse, not identically.
        assert mild > moderate > extreme

    def test_beta_zero_and_mildly_negative_are_not_conflated(self):
        loader = StockScoresLoader()
        filler = {"volatility_60d": 0.0}

        zero_beta = loader._score_risk({"beta": 0.0, **filler}, "ZERO")
        negative_beta = loader._score_risk({"beta": -0.5, **filler}, "NEG")

        assert negative_beta < zero_beta

    def test_extreme_negative_beta_saturates_to_zero_not_negative(self):
        """diff is capped at 2.0 before the score formula, so very negative beta still
        floors cleanly at beta_score=0 rather than going out of the 0-100 range.

        beta_score=0 at this extreme: (83.3333*0.45 + 0*0.15) / 0.60 = 62.5 - the vol
        filler's own contribution, not a bare 0.0 (which the pre-floor version of this test
        pinned when beta was the only input). Beta's weight is 15% (was 20% before the
        2026-09-01 Liquidity reweight - see _score_risk's docstring)."""
        loader = StockScoresLoader()

        score = loader._score_risk({"beta": -50.0, "volatility_60d": 1.10}, "GARBAGE")

        assert score == pytest.approx(62.5, abs=1e-3)

    def test_positive_beta_symmetric_around_target_unaffected(self):
        """Sanity check the fix didn't change behavior for the common positive-beta case.

        vol filler alone scores 83.3333 (see test_volatility_60d_alone_at_0_20_is_neutral_baseline)
        at 45% weight; beta contributes its own beta_score at 15% weight (was 20% before the
        2026-09-01 Liquidity reweight). at_target (beta=1.0, beta_score=100):
        (83.3333*0.45 + 100*0.15) / 0.60 = 87.5. high_beta (beta=2.0, beta_score=50):
        (83.3333*0.45 + 50*0.15) / 0.60 = 75.0 - strictly lower, same ordering the
        pre-floor version of this test pinned (100.0 > 50.0)."""
        loader = StockScoresLoader()

        at_target = loader._score_risk({"beta": 1.0, "volatility_60d": 0.0}, "TARGET")
        high_beta = loader._score_risk({"beta": 2.0, "volatility_60d": 0.30}, "HIGH")

        assert at_target == pytest.approx(87.5, abs=1e-3)
        assert high_beta == pytest.approx(75.0, abs=1e-3)


class TestRiskMinWeightAvailable:
    """RISK_MIN_WEIGHT_AVAILABLE (added 2026-08-31, /goal session - found by live-sweeping the
    DB the same way the Growth floor was found: APMC/FTRA/CAES/CCCT/IPVV/MTNE and 11 others each
    scored >=90 off max_drawdown_1y alone, 15% of the pillar's weight, with volatility/beta - 85%
    of the real signal - completely absent)."""

    def test_min_weight_available_constant(self):
        from loaders.load_stock_scores import RISK_MIN_WEIGHT_AVAILABLE

        assert RISK_MIN_WEIGHT_AVAILABLE == pytest.approx(0.40)

    def test_max_drawdown_alone_is_below_floor_returns_thin_sample_marker(self):
        # max_drawdown_1y is 0.15 weight alone, well under the 0.40 floor.
        loader = StockScoresLoader()
        result = loader._score_risk({"max_drawdown_1y": -34.63}, "TEST")
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_beta_alone_is_below_floor_returns_thin_sample_marker(self):
        # beta is 0.20 weight alone, still under the 0.40 floor.
        loader = StockScoresLoader()
        result = loader._score_risk({"beta": 1.0}, "TEST")
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_volatility_60d_alone_clears_floor_on_its_own(self):
        # volatility_60d is 0.45 weight alone, already above the 0.40 floor by itself.
        loader = StockScoresLoader()
        result = loader._score_risk({"volatility_60d": 0.10}, "TEST")
        assert isinstance(result, float)

    def test_beta_plus_max_drawdown_together_clear_floor(self):
        # 0.20 + 0.15 = 0.35, still just under 0.40 - must NOT clear the floor.
        loader = StockScoresLoader()
        result = loader._score_risk({"beta": 1.0, "max_drawdown_1y": -10.0}, "TEST")
        assert isinstance(result, dict)
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_volatility_252d_plus_beta_exactly_at_floor_returns_real_score(self):
        # 0.20 (volatility_252d) + 0.20 (beta) = 0.40, exactly at the floor - must clear it.
        loader = StockScoresLoader()
        result = loader._score_risk({"volatility_252d": 0.10, "beta": 1.0}, "TEST")
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
