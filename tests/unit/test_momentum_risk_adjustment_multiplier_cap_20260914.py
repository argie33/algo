"""Risk-adjusted Momentum (added 2026-09-14) - the multiplier cap specifically. Live sanity-
check before shipping caught an uncapped near-floor vol_252d amplifying a raw return 10.7x
(TXNM, vol_252d=0.051) straight to curve saturation - see MAX_RISK_ADJUSTMENT_MULTIPLIER's own
docstring in momentum_scoring.py for the full incident. This locks that fix in place.
"""

from loaders.stock_scores.momentum_scoring import (
    MAX_RISK_ADJUSTMENT_MULTIPLIER,
    MEDIAN_UNIVERSE_VOL_252D,
    MIN_RISK_ADJUSTMENT_MULTIPLIER,
    MIN_VOL_252D_FOR_RISK_ADJUSTMENT,
    MomentumScoringMixin,
)


class TestRiskAdjustMultiplierCap:
    def test_near_floor_vol_does_not_blow_up_multiplier(self) -> None:
        # vol_252d just above the floor would otherwise imply a MEDIAN/vol multiplier far
        # beyond MAX_RISK_ADJUSTMENT_MULTIPLIER - the live TXNM incident this test locks in.
        vol_near_floor = MIN_VOL_252D_FOR_RISK_ADJUSTMENT + 0.001
        raw_pct = 10.0
        adjusted = MomentumScoringMixin._risk_adjust_pct(raw_pct, vol_near_floor)
        assert adjusted == raw_pct * MAX_RISK_ADJUSTMENT_MULTIPLIER

    def test_very_high_vol_does_not_dampen_below_floor_multiplier(self) -> None:
        vol_very_high = MEDIAN_UNIVERSE_VOL_252D * 100
        raw_pct = 10.0
        adjusted = MomentumScoringMixin._risk_adjust_pct(raw_pct, vol_very_high)
        assert adjusted == raw_pct * MIN_RISK_ADJUSTMENT_MULTIPLIER

    def test_exactly_median_vol_is_unchanged(self) -> None:
        raw_pct = 12.5
        adjusted = MomentumScoringMixin._risk_adjust_pct(raw_pct, MEDIAN_UNIVERSE_VOL_252D)
        assert adjusted == raw_pct

    def test_missing_vol_passes_through_unchanged(self) -> None:
        raw_pct = -7.5
        assert MomentumScoringMixin._risk_adjust_pct(raw_pct, None) == raw_pct

    def test_below_floor_vol_passes_through_unchanged(self) -> None:
        raw_pct = 5.0
        below_floor = MIN_VOL_252D_FOR_RISK_ADJUSTMENT - 0.001
        assert MomentumScoringMixin._risk_adjust_pct(raw_pct, below_floor) == raw_pct
