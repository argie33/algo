"""Regression/documentation test for a 2026-08-25 STRUCTURAL FINDING (real-money-readiness
goal session, position-sizing audit) in algo/trading/position_sizer.py::
_calculate_with_external_cursor(): live-confirmed via direct DB query that
algo_config.max_position_size_pct=4.75 and max_concentration_pct=50.0 (both stamped with the
identical updated_at timestamp - set once at initial seed, never independently reasoned about
together).

Phase 8 overrides max_concentration_pct per exposure-tier regime
(algo/risk/exposure_policy.py EXPOSURE_TIERS: 10%/12%/22%/28% across
correction/caution/normal/aggressive), specifically so concentration risk SHRINKS in risk-off
regimes - but every one of those tier values (10-28%) is looser than the STATIC
max_position_size_pct cap already enforced unconditionally, every call, regardless of regime.
Since position_value is capped to <= max_position_size_pct of portfolio_value BEFORE the
concentration check runs, the concentration scale-down branch (and the entire regime-driven
concentration dial it exists to enforce) is unreachable dead code under real production
config, for EVERY real exposure tier.

This is currently SAFE (the tighter static cap means no position can ever exceed
max_position_size_pct regardless of regime - the failure mode is "the regime dial does
nothing," not "a position gets oversized"), so the numeric values were deliberately left
unchanged rather than picking a new absolute ceiling unilaterally for a live-money account -
see position_sizer.py's own comment at the concentration-check site for the full writeup and
the two concrete remediation options for a future session (or the user) to choose between.

This test exists so that relationship is asserted explicitly rather than only narrated in a
comment - if either value ever changes such that a real exposure tier becomes the binding
constraint, this test's assumptions should be revisited (not silently left describing a
now-stale reality).
"""

from decimal import Decimal
from unittest.mock import patch

from algo.risk.exposure_policy import EXPOSURE_TIERS
from algo.trading.position_sizer import PositionSizer

# Real production values, live-confirmed via direct algo_config query 2026-08-25 (not schema
# defaults, which happen to tell the same story: 5.0 vs 50.0).
REAL_MAX_POSITION_SIZE_PCT = 4.75
REAL_MAX_CONCENTRATION_PCT_BASE = 50.0

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": REAL_MAX_POSITION_SIZE_PCT,
    "max_concentration_pct": REAL_MAX_CONCENTRATION_PCT_BASE,
    "max_total_invested_pct": 95.0,
    "max_total_risk_pct": 8.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _patched(sizer):
    return (
        patch.object(sizer, "get_position_count", return_value=0),
        patch.object(sizer, "get_active_positions_value", return_value=Decimal("0")),
        patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
        patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
        patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
    )


class TestConcentrationDialInertUnderRealConfig:
    def test_every_exposure_tier_concentration_value_looser_than_static_position_cap(self):
        """The precondition for the whole finding: no real exposure tier's
        max_concentration_pct is ever tighter than the static max_position_size_pct."""
        tier_values = [tier["max_concentration_pct"] for tier in EXPOSURE_TIERS]
        assert tier_values, "expected at least one exposure tier to check against"
        assert min(tier_values) > REAL_MAX_POSITION_SIZE_PCT, (
            f"expected every exposure tier's max_concentration_pct to exceed the static "
            f"{REAL_MAX_POSITION_SIZE_PCT}% cap (the condition that makes the concentration "
            f"scale-down branch unreachable) - tiers: {tier_values}. If this now fails, a real "
            f"exposure tier may have become the binding constraint - re-verify the finding in "
            f"position_sizer.py's comment before assuming it's stale."
        )

    def test_concentration_branch_never_binds_at_any_real_tier_value(self):
        """Even sizing a position that would be 100% of the portfolio absent any cap, the
        resulting position is bound by max_position_size_pct alone - the concentration branch
        never further reduces it, for every real exposure tier's max_concentration_pct."""
        for tier in EXPOSURE_TIERS:
            tier_name = tier["name"]
            config = dict(CONFIG)
            config["max_concentration_pct"] = tier["max_concentration_pct"]
            sizer = PositionSizer(config=config)
            patches = _patched(sizer)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                result = sizer._calculate_with_external_cursor(
                    symbol="LARGE_BET",
                    entry_price=Decimal("50"),
                    # $1 risk/share (entry-stop) against a 1% risk budget on a $100k portfolio
                    # sizes to 1000 shares = $50,000 = 50% of portfolio before any cap - well
                    # over every real max_position_size_pct/max_concentration_pct value, so
                    # whichever cap is actually reached first is unambiguous.
                    stop_loss_price=Decimal("49"),
                    portfolio_value=Decimal("100000"),
                    enforce_total_risk_limit=False,
                )

            assert result["status"] == "ok", f"[{tier_name}] unexpected status: {result}"
            # The position must land at (or just under, due to whole-share rounding)
            # max_position_size_pct - never below it due to the supposedly-tighter tier
            # concentration cap, since that cap (10-28%) is always looser than 4.75%.
            assert result["position_size_pct"] <= REAL_MAX_POSITION_SIZE_PCT, (
                f"[{tier_name}] position_size_pct={result['position_size_pct']} unexpectedly "
                f"exceeds the static cap {REAL_MAX_POSITION_SIZE_PCT}%"
            )
            assert result["position_size_pct"] > REAL_MAX_POSITION_SIZE_PCT - 1.0, (
                f"[{tier_name}] position_size_pct={result['position_size_pct']} landed well "
                f"below the static {REAL_MAX_POSITION_SIZE_PCT}% cap - the concentration branch "
                f"(tier value {tier['max_concentration_pct']}%) may have started binding, which "
                f"would mean this finding is stale and position_sizer.py's comment should be "
                f"revisited."
            )
