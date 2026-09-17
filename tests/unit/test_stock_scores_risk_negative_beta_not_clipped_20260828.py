#!/usr/bin/env python3
"""Regression test: StockScoresLoader._score_risk must not clip negative beta_bab to 0
(loaders/stock_scores/risk_scoring.py, _score_risk's beta_bab sub-score).

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

AQR PIVOT 2026-09-17 (user: "i want the aqr and not the mess we have... no ai slop only what
is best in the industry proven", then "get the aqr down to its purest form... extra shit mixing
with msci" - see risk_scoring.py's own top-of-file docstring for the full citation/evidence
trail). Risk's scored input is now `beta_bab` (Frazzini & Pedersen 2014's own published
shrinkage estimator: beta_ts = rho*(sigma_i/sigma_m), beta_bab = 0.6*beta_ts + 0.4*1.0 -
computed in loaders/load_risk_metrics_daily.py's `_calculate_beta_bab`), not the naive-OLS
`beta` column this file's fixtures used to pass directly. `_score_risk` no longer shrinks
anything itself - beta_bab arrives already shrunk from the loader, so the formula here is the
SAME linear clip as before (`100 - beta_bab*50`, clipped [0, 100]), just fed a pre-shrunk input.
RISK_COMPONENT_WEIGHT is now 1.0 (beta_bab is the pillar's ONLY scored component - volatility_60d
and cmra_12m are computed/persisted informational only, no longer scoring inputs) - a symbol
with only beta_bab available now clears RISK_MIN_WEIGHT_AVAILABLE on its own, no filler field
needed the way the pre-pivot 3-component version required one.
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestRiskNegativeBetaBabNotClipped:
    def test_negative_beta_bab_all_saturate_to_the_same_max_credit(self):
        """beta_bab<=0 all saturate to beta_score=100 (already maximal low-beta credit) - more
        negative doesn't score BETTER once already at 0, since the reward is linear-and-capped,
        not unbounded. The input itself is never pre-clipped (each beta_bab is used as-is in
        the formula), only the OUTPUT saturates - this is the actual property under test.
        """
        loader = StockScoresLoader()

        mild = loader._score_risk({"beta_bab": -0.05}, "MILD")
        moderate = loader._score_risk({"beta_bab": -0.5}, "MODERATE")
        extreme = loader._score_risk({"beta_bab": -9.97}, "EXTREME")

        assert isinstance(mild, float)
        assert isinstance(moderate, float)
        assert isinstance(extreme, float)
        assert mild == pytest.approx(moderate) == pytest.approx(extreme) == pytest.approx(100.0)

    def test_beta_bab_zero_and_negative_score_identically_once_saturated(self):
        """Both beta_bab=0.0 and beta_bab=-0.5 are <=0, so both hit the formula's 100-point
        ceiling - genuinely identical here (unlike the un-saturated positive region, where
        distinct beta_bab values score distinctly - see test_positive_beta_bab_scores_linearly
        below)."""
        loader = StockScoresLoader()

        zero_beta_bab = loader._score_risk({"beta_bab": 0.0}, "ZERO")
        negative_beta_bab = loader._score_risk({"beta_bab": -0.5}, "NEG")

        assert negative_beta_bab == pytest.approx(zero_beta_bab) == pytest.approx(100.0)

    def test_extreme_positive_beta_bab_saturates_to_zero_not_negative(self):
        """A very high positive beta_bab must floor cleanly at beta_score=0 rather than going
        negative - the real low-beta anomaly rewards low beta, so high beta is simply bad, not
        specially penalized further past the 0 floor. beta_bab alone is enough weight
        (RISK_COMPONENT_WEIGHT=1.0, the pillar's sole scored input) to clear
        RISK_MIN_WEIGHT_AVAILABLE - no filler field needed."""
        loader = StockScoresLoader()

        score = loader._score_risk({"beta_bab": 50.0}, "GARBAGE")

        assert score == pytest.approx(0.0)

    def test_positive_beta_bab_scores_linearly_lower_beta_wins(self):
        """Direct low-beta-anomaly check: a lower positive beta_bab must score strictly HIGHER
        than a higher one - this is the real BAB/Min-Vol direction, not the old closeness-to-1.0
        target. low_beta_bab=0.5 -> beta_score=75.0; high_beta_bab=2.0 -> beta_score=0.0."""
        loader = StockScoresLoader()

        low_beta_bab = loader._score_risk({"beta_bab": 0.5}, "LOW_BETA")
        high_beta_bab = loader._score_risk({"beta_bab": 2.0}, "HIGH_BETA")

        assert low_beta_bab == pytest.approx(75.0)
        assert high_beta_bab == pytest.approx(0.0)
        assert low_beta_bab > high_beta_bab


class TestRiskMinWeightAvailable:
    """RISK_MIN_WEIGHT_AVAILABLE (added 2026-08-31, /goal session - found by live-sweeping the
    DB the same way the Growth floor was found: APMC/FTRA/CAES/CCCT/IPVV/MTNE and 11 others each
    scored >=90 off max_drawdown_1y alone, then 15% of the pillar's weight, with volatility/beta
    - 85% of the real signal - completely absent).

    AQR PIVOT 2026-09-17: beta_bab is now the pillar's ONLY scored input at weight 1.0, so any
    real beta_bab value alone clears the 0.40 floor on its own - the multi-field "clears the
    floor together" tests from the pre-pivot 3-component version no longer apply and are
    removed rather than kept as dead scaffolding."""

    def test_min_weight_available_constant(self):
        from loaders.load_stock_scores import RISK_MIN_WEIGHT_AVAILABLE

        assert RISK_MIN_WEIGHT_AVAILABLE == pytest.approx(0.40)

    def test_max_drawdown_alone_returns_no_scores_marker(self):
        # max_drawdown_1y is no longer a scoreable input (removed 2026-09-16, factor-purity
        # sweep - never a real Barra/MSCI risk descriptor). Providing only it is equivalent to
        # providing nothing.
        loader = StockScoresLoader()
        result = loader._score_risk({"max_drawdown_1y": -34.63}, "TEST")
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_risk_scores_computed"

    def test_beta_bab_alone_clears_floor(self):
        # beta_bab is the pillar's sole scored input (weight 1.0) - alone, it clears the 0.40
        # floor on its own.
        loader = StockScoresLoader()
        result = loader._score_risk({"beta_bab": 1.0}, "TEST")
        assert isinstance(result, float)

    def test_volatility_60d_alone_returns_no_scores_marker(self):
        # volatility_60d is informational only now (not a scoring input at all) - providing
        # only it is equivalent to providing nothing.
        loader = StockScoresLoader()
        result = loader._score_risk({"volatility_60d": 0.10}, "TEST")
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_risk_scores_computed"

    def test_zero_fields_available_returns_no_scores_marker_not_thin_sample(self):
        # A non-empty metrics dict (data_unavailable=False, per _get_stability_metrics'
        # convention) where every individual field is still None - distinct from a falsy/empty
        # metrics dict, which short-circuits earlier to reason="no_risk_metrics_data" instead.
        loader = StockScoresLoader()
        result = loader._score_risk(
            {
                "data_unavailable": False,
                "volatility_60d": None,
                "cmra_12m": None,
                "beta_bab": None,
                "max_drawdown_1y": None,
            },
            "TEST",
        )
        assert isinstance(result, dict)
        assert result["reason"] == "no_risk_scores_computed"
