"""Regression test for a 2026-09-07 fix (goal session: "none of the scores are right" sweep,
direct extrapolation of the same-day fixes already applied to Value/Growth/Risk) to
loaders/stock_scores/momentum_scoring.py's _score_momentum().

_score_momentum's `if total_weight > 0: return weighted_sum / total_weight` accepted ANY
nonzero weight as a fully-confident momentum score - the identical bug already fixed for Value
(VALUE_MIN_WEIGHT), Growth (GROWTH_MIN_FIELDS_AVAILABLE), and Risk (RISK_MIN_WEIGHT_AVAILABLE),
just never applied to this pillar.

Live-confirmed: NCPL (and 7 similar symbols - XLAB/CURX/PAAI/SGLD/BOXL/PSQL/VAI) had NO
price-return momentum and NO RSI, yet scored momentum_score=70.00 flat off a single near-zero
MACD value (0.0207 - indistinguishable from noise) at 0.37/1.00 nominal weight alone.
VOGX/BLSM/TP/LTGO scored 74-83 off RSI+MACD alone (also 0.37 weight), also with zero
price-return momentum.
"""

from loaders.stock_scores.momentum_scoring import MOMENTUM_MIN_WEIGHT, MomentumScoringMixin


class _Loader(MomentumScoringMixin):
    pass


class TestMomentumMinWeightGate:
    def test_macd_sign_alone_is_withheld_not_scored(self) -> None:
        # NCPL-shaped input: no price-return momentum, no RSI, no SMA - only a near-zero MACD
        # sign. UPDATED 2026-09-15 (WEIGHTS REBALANCED, see momentum_scoring.py's own
        # docstring): MACD/RSI are no longer scored inputs at all (demoted to informational-
        # only), so this now hits the "zero scoreable fields" branch rather than the "thin but
        # nonzero" one MACD alone used to produce - a stronger, more precise version of the
        # same "insufficient data, don't fabricate a score" protection the other three pillars
        # already use.
        assert MOMENTUM_MIN_WEIGHT == 0.40  # pin the constant this test's math depends on
        loader = _Loader()
        metrics = {
            "momentum_1m": None,
            "momentum_3m": None,
            "momentum_6m": None,
            "momentum_12m": None,
            "rsi_14": None,
            "macd": 0.0207,
            "price_vs_sma_50": None,
            "price_vs_sma_200": None,
        }

        result = loader._score_momentum(metrics, "NCPL")

        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_momentum_scores_computed"

    def test_rsi_and_macd_together_still_below_floor_is_withheld(self) -> None:
        # VOGX-shaped input: RSI + MACD together contribute zero scored weight now (both
        # demoted to informational-only 2026-09-15) - same "no scoreable fields" outcome as
        # MACD alone above, confirming RSI doesn't rescue it either.
        loader = _Loader()
        metrics = {
            "momentum_1m": None,
            "momentum_3m": None,
            "momentum_6m": None,
            "momentum_12m": None,
            "rsi_14": 86.4,
            "macd": 3.02,
            "price_vs_sma_50": None,
            "price_vs_sma_200": None,
        }

        result = loader._score_momentum(metrics, "VOGX")

        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_momentum_scores_computed"

    def test_full_coverage_at_or_above_floor_still_scores(self) -> None:
        # Sanity counterpart: mom_3m (0.20) + 12-1 (0.35) = 0.55, clears MOMENTUM_MIN_WEIGHT -
        # must still produce a real float, not be swept up by the new gate.
        loader = _Loader()
        metrics = {
            "momentum_1m": 2.0,
            "momentum_3m": 8.0,
            "momentum_6m": None,
            "momentum_12m": 15.0,
            "rsi_14": None,
            "macd": None,
            "price_vs_sma_50": None,
            "price_vs_sma_200": None,
        }

        result = loader._score_momentum(metrics, "FULLCOV")

        assert isinstance(result, float)
