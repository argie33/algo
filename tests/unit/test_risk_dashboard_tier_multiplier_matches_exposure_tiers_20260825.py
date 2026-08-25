"""Regression test: lambda/api/routes/risk_dashboard.py's _fetch_exposure_tier_info() used
to compute position_size_multiplier from an independent, hand-copied dict
(confirmed_uptrend=1.0, uptrend_under_pressure=0.75, caution=0.50, correction=0.0) instead
of algo/risk/exposure_policy.py's real EXPOSURE_TIERS (risk_multiplier: 1.0/0.65/0.35/0.0).
Wrong by 15% on uptrend_under_pressure and 43% on caution - same double-source-of-truth bug
class already found and fixed once in lambda/api/routes/algo_handlers/signals.py's
_TIER_CONFIG (see tier_config_derived_from_exposure_tiers_20260824 in memory).

Fixed 2026-08-25 (money-% goal session): _TIER_RISK_MULTIPLIERS is now derived directly
from EXPOSURE_TIERS at module load, so it can't silently drift again.

'lambda' is a Python keyword, so modules under test are loaded via importlib.
"""

import importlib
from unittest.mock import MagicMock, patch

risk_dashboard_module = importlib.import_module("lambda.api.routes.risk_dashboard")

from algo.risk.exposure_policy import EXPOSURE_TIERS


def _fetch_tier(regime: str) -> dict:
    cur = MagicMock()
    with patch.object(
        risk_dashboard_module,
        "execute_with_timeout",
        return_value=[
            {
                "exposure_pct": 55.0,
                "regime": regime,
                "halt_reasons": None,
                "data_unavailable": False,
                "reason": None,
            }
        ],
    ):
        return risk_dashboard_module._fetch_exposure_tier_info(cur)


def test_position_size_multiplier_matches_real_exposure_tiers_for_every_regime() -> None:
    real_multipliers = {tier["name"]: tier["risk_multiplier"] for tier in EXPOSURE_TIERS}
    for regime, expected_mult in real_multipliers.items():
        result = _fetch_tier(regime)
        assert result["position_size_multiplier"] == expected_mult, (
            f"regime={regime}: expected risk_multiplier {expected_mult} from EXPOSURE_TIERS, "
            f"got {result['position_size_multiplier']}"
        )


def test_caution_and_uptrend_under_pressure_are_not_the_old_wrong_values() -> None:
    """Direct regression pin for the two regimes that were actually wrong: caution was
    hardcoded to 0.50 (real: 0.35) and uptrend_under_pressure to 0.75 (real: 0.65)."""
    assert _fetch_tier("caution")["position_size_multiplier"] == 0.35
    assert _fetch_tier("uptrend_under_pressure")["position_size_multiplier"] == 0.65
