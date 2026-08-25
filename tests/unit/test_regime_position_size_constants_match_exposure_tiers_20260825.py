"""Regression test: algo/infrastructure/constants.py's REGIME_POSITION_SIZE_* constants
(feeding RegimeManager.REGIME_PARAMS -> daily_report.py's "position_size_mult" report
field, generated and logged/persisted-to-algo_audit_log every trading day by Phase 9) had
drifted from algo/risk/exposure_policy.py's real EXPOSURE_TIERS risk_multiplier field -
a 4th independent hand-copy of the same values already found drifted twice this session
(lambda/api/routes/algo_handlers/signals.py's _TIER_CONFIG, fixed 2026-08-24;
lambda/api/routes/risk_dashboard.py's _TIER_RISK_MULTIPLIERS, fixed 2026-08-25 - see
risk_dashboard_position_size_multiplier_drift_fixed_20260825 in memory).

Old (wrong): confirmed_uptrend=1.0, uptrend_under_pressure=0.75, caution=0.5, correction=0.0
Real (EXPOSURE_TIERS): confirmed_uptrend=1.0, uptrend_under_pressure=0.65, caution=0.35,
correction=0.0 - 15% overstated for uptrend_under_pressure, 43% overstated for caution.

Not derived dynamically here (constants.py is a compile-time-only module with no DB/
business-logic imports by design) - this test is the manual-sync guard instead, so a
future EXPOSURE_TIERS retune (it's happened 3x in one day before) gets caught here rather
than silently drifting a 4th time.
"""

from algo.infrastructure.constants import (
    REGIME_POSITION_SIZE_CAUTION,
    REGIME_POSITION_SIZE_CONFIRMED_UPTREND,
    REGIME_POSITION_SIZE_CORRECTION,
    REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE,
)
from algo.risk.exposure_policy import EXPOSURE_TIERS

_REGIME_CONSTANT = {
    "confirmed_uptrend": REGIME_POSITION_SIZE_CONFIRMED_UPTREND,
    "uptrend_under_pressure": REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE,
    "caution": REGIME_POSITION_SIZE_CAUTION,
    "correction": REGIME_POSITION_SIZE_CORRECTION,
}


def test_regime_position_size_constants_match_exposure_tiers_risk_multiplier() -> None:
    for tier in EXPOSURE_TIERS:
        name = tier["name"]
        assert name in _REGIME_CONSTANT, (
            f"EXPOSURE_TIERS has tier {name!r} with no matching REGIME_POSITION_SIZE_* constant"
        )
        assert _REGIME_CONSTANT[name] == tier["risk_multiplier"], (
            f"REGIME_POSITION_SIZE_{name.upper()} ({_REGIME_CONSTANT[name]}) has drifted from "
            f"EXPOSURE_TIERS['{name}']['risk_multiplier'] ({tier['risk_multiplier']}) - this feeds "
            f"daily_report.py's real, human-facing daily report."
        )


def test_not_the_old_known_wrong_values() -> None:
    """Direct regression pin for the two regimes that were actually wrong."""
    assert REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE == 0.65
    assert REGIME_POSITION_SIZE_CAUTION == 0.35
