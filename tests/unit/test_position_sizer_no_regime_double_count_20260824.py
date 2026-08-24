"""Regression test for a 2026-08-24 fix in algo/trading/position_sizer.py::
_calculate_with_external_cursor(): the risk cascade used to multiply by BOTH exposure_mult
(get_market_exposure_multiplier() - continuous market_exposure_daily.exposure_pct/100) AND
regime_mult (get_position_size_multiplier_from_regime() -> RegimeManager ->
REGIME_POSITION_SIZE_* keyed by market_exposure_daily.regime). regime IS
tier_for_exposure(exposure_pct)["name"] - a coarse re-bucketing of the exact same
exposure_pct exposure_mult already reads continuously - so the cascade counted one market
read twice (e.g. exposure_pct=35% in "caution": 0.35 exposure_mult x 0.5 regime_mult =
0.175x combined, roughly half the intended single-application reduction).

Fixed by removing regime_mult from the cascade entirely (exposure_mult alone is the
documented mechanism - see market_exposure.py's module docstring) and deleting
get_position_size_multiplier_from_regime(), its only call site.

This test locks in that shares scale with exposure_mult alone, matching a hand-computed
expected value, and that no live RegimeManager/database call is made for position sizing
(the method no longer exists on PositionSizer).
"""

from decimal import Decimal
from unittest.mock import patch

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.1,
    "max_position_size_pct": 100.0,
    "max_concentration_pct": 100.0,
    "max_total_invested_pct": 100.0,
    "max_total_risk_pct": 100.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _make_sizer():
    return PositionSizer(config=dict(CONFIG))


class TestPositionSizerHasNoRegimeMultiplier:
    def test_get_position_size_multiplier_from_regime_removed(self):
        sizer = _make_sizer()
        assert not hasattr(sizer, "get_position_size_multiplier_from_regime"), (
            "get_position_size_multiplier_from_regime must be deleted - it was the sole "
            "call site that double-applied the exposure signal via RegimeManager."
        )

    def test_shares_scale_with_exposure_mult_alone_not_squared(self):
        """$100k portfolio, 1% base risk, entry=$100/stop=$90 (risk_per_share=$10) ->
        unscaled risk_dollars = $1000 -> unscaled shares = 100. With exposure_mult=0.5 and
        no other reduction, risk_dollars should scale to exactly $500 -> 50 shares. Before
        the fix, an equal-weighted regime_mult would have compounded this further (e.g.
        0.5 x 0.5 = 0.25x -> 25 shares) for a mid-tier exposure regime - this test fails if
        any such second exposure-derived multiplier is reintroduced."""
        sizer = _make_sizer()
        with (
            patch.object(sizer, "get_position_count", return_value=0),
            patch.object(sizer, "get_active_positions_value", return_value=Decimal("0")),
            patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
            patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("0.5")),
            patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
            patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
        ):
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("100000"),
                enforce_total_risk_limit=False,
            )

        assert result["status"] == "ok"
        assert result["shares"] == 50, (
            f"Expected exactly 50 shares (0.5x exposure_mult applied once to the 100-share "
            f"unscaled base), got {result['shares']} - a regime-multiplier reintroduction "
            f"would compound this further, e.g. to 25."
        )
