"""Regression test for a 2026-08-23 fix in algo/trading/position_sizer.py::
_calculate_with_external_cursor(): the concentration-limit scale-down branch used to `return`
immediately with the scaled position ("status": "ok") instead of falling through to the
remaining checks - unlike its sibling scaling branch (max_position_size_pct cap, fixed
2026-08-10 - see test_position_sizer_max_position_pct_zero_share_cap.py), which updates
shares/position_value/risk_dollars in place and lets execution continue.

This meant a concentration-scaled entry never went through the total_invested_pct check or the
enforce_total_risk_limit block - the latter explicitly documented in this same function as "the
single most important portfolio-level guardrail" (the aggregate open-risk hard cap), specifically
evaluated per-symbol because Phase 8 sizes multiple symbols per cycle and needs a live,
cumulative check as it goes. A symbol whose OWN concentration limit triggered scaling could
still push the portfolio's aggregate invested percentage or open risk past its configured cap,
completely unchecked.

Fixed by updating the working variables (shares/position_value/position_pct_of_portfolio/
risk_dollars) in place instead of returning early, matching the max_position_size_pct branch's
established pattern.
"""

from decimal import Decimal
from unittest.mock import patch

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": 60.0,  # deliberately high - isolate the concentration branch alone
    "max_concentration_pct": 20.0,
    "max_total_invested_pct": 90.0,
    "max_total_risk_pct": 4.0,
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


def _patched(sizer, active_position_value):
    return (
        patch.object(sizer, "get_position_count", return_value=1),
        patch.object(sizer, "get_active_positions_value", return_value=Decimal(str(active_position_value))),
        patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
        patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
        patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_position_size_multiplier_from_regime", return_value=1.0),
    )


class TestConcentrationScaleChecksRemainingLimits:
    def test_concentration_scaled_entry_still_rejected_by_total_invested_limit(self):
        """$10k portfolio, already 85% invested ($8,500). Base sizing wants 50% of portfolio
        (way over the 20% concentration cap), so it scales down to the ~19% effective
        concentration limit ($1,900) - but $8,500 + $1,900 = $10,400 = 104% of portfolio,
        blowing through the 90% max_total_invested_pct cap. Must be rejected with
        status='no_room', not reported as a fake 'ok' success at the concentration-scaled size."""
        sizer = _make_sizer()
        patches = _patched(sizer, active_position_value=8500)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            result = sizer._calculate_with_external_cursor(
                symbol="OVERINVESTED",
                entry_price=Decimal("50"),
                stop_loss_price=Decimal("49"),
                portfolio_value=Decimal("10000"),
                enforce_total_risk_limit=False,
            )

        assert result["status"] == "no_room", (
            f"A concentration-scaled position that still breaches max_total_invested_pct must "
            f"be rejected, not silently reported as 'ok'. Got: {result}"
        )
        assert result["shares"] == 0

    def test_concentration_scaled_entry_within_remaining_limits_still_succeeds(self):
        """Sanity check: concentration scaling that does NOT breach any other limit must still
        succeed at the scaled size - the fix must not turn every concentration-scaled entry
        into a rejection, only ones that genuinely violate a subsequent check."""
        sizer = _make_sizer()
        patches = _patched(sizer, active_position_value=0)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            result = sizer._calculate_with_external_cursor(
                symbol="ROOM_TO_SPARE",
                entry_price=Decimal("50"),
                stop_loss_price=Decimal("49"),
                portfolio_value=Decimal("10000"),
                enforce_total_risk_limit=False,
            )

        assert result["status"] == "ok"
        # Concentration cap (20%, ~19% effective) must still have bound the size down from the
        # base risk-sized 100 shares ($5,000 = 50% of portfolio) to ~38 shares (~19%).
        assert 0 < result["shares"] < 100
        assert result["position_size_pct"] <= 20.0
