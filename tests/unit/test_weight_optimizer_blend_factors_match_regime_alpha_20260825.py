"""Regression guard: algo/orchestration/weight_optimizer.py's WeightOptimizer.BLEND_FACTORS
(the REAL, live-consumed "how fast to adapt component weights per regime" values - used
directly in actual weight-blending math) and algo/infrastructure/constants.py's
REGIME_WEIGHT_UPDATE_ALPHA_* constants (feeding RegimeManager.REGIME_PARAMS's
"weight_update_alpha" key, which flows into daily_report.py's report display) are two
independently hand-maintained copies of the same regime->alpha mapping. They currently
agree exactly (0.10/0.05/0.05/0.0), but nothing enforces that - the exact same
duplicate-source-of-truth shape already found ACTUALLY DRIFTED three separate times this
session for the sibling "regime -> position-size multiplier" mapping (signals.py's
_TIER_CONFIG, risk_dashboard.py's _TIER_RISK_MULTIPLIERS, constants.py's
REGIME_POSITION_SIZE_*, all vs algo/risk/exposure_policy.py's EXPOSURE_TIERS).

Found 2026-08-25 (money-% goal session) while sweeping every remaining regime-keyed
numeric constant for the same risk. No live bug today (both sides agree) - this test
exists purely so a future edit to one side without the other (exactly how the other three
drifted) gets caught here instead of silently making daily_report.py's displayed
"weight_update_alpha" wrong, same class as the already-fixed position_size_mult bug.
"""

from algo.infrastructure.constants import (
    REGIME_WEIGHT_UPDATE_ALPHA_CAUTION,
    REGIME_WEIGHT_UPDATE_ALPHA_CONFIRMED_UPTREND,
    REGIME_WEIGHT_UPDATE_ALPHA_CORRECTION,
    REGIME_WEIGHT_UPDATE_ALPHA_UPTREND_UNDER_PRESSURE,
)
from algo.orchestration.weight_optimizer import WeightOptimizer

_ALPHA_CONSTANT = {
    "confirmed_uptrend": REGIME_WEIGHT_UPDATE_ALPHA_CONFIRMED_UPTREND,
    "uptrend_under_pressure": REGIME_WEIGHT_UPDATE_ALPHA_UPTREND_UNDER_PRESSURE,
    "caution": REGIME_WEIGHT_UPDATE_ALPHA_CAUTION,
    "correction": REGIME_WEIGHT_UPDATE_ALPHA_CORRECTION,
}


def test_regime_weight_update_alpha_constants_match_live_blend_factors() -> None:
    for regime, alpha_const in _ALPHA_CONSTANT.items():
        assert regime in WeightOptimizer.BLEND_FACTORS, (
            f"REGIME_WEIGHT_UPDATE_ALPHA_* has regime {regime!r} with no matching WeightOptimizer.BLEND_FACTORS entry"
        )
        assert alpha_const == WeightOptimizer.BLEND_FACTORS[regime], (
            f"REGIME_WEIGHT_UPDATE_ALPHA_{regime.upper()} ({alpha_const}) has drifted from "
            f"WeightOptimizer.BLEND_FACTORS[{regime!r}] ({WeightOptimizer.BLEND_FACTORS[regime]}) - "
            f"the constant feeds daily_report.py's real, human-facing daily report; "
            f"BLEND_FACTORS is what actually drives live weight-blending."
        )
