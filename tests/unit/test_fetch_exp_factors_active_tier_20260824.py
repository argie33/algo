"""Regression: fetch_exp_factors() (dashboard/fetchers_market.py) never propagated
`active_tier` from the shared /api/algo/markets response, even though market.py's
_get_markets returns it as a sibling of "current" - same field that lambda/api/routes/
algo_handlers/signals.py's _TIER_CONFIG derives from EXPOSURE_TIERS. Without this, the
exposure panel's score/pillar breakdown had no way to show what the score actually DOES
to today's trading (max new positions, min composite score, max concentration, halt).
"""

from unittest.mock import patch

from dashboard.fetchers_market import fetch_exp_factors

_SAMPLE_TIER = {
    "name": "caution",
    "description": "Market under significant stress - reduced position size",
    "min_pct": 25,
    "max_pct": 45,
    "risk_mult": 0.35,
    "risk_multiplier": 0.35,
    "max_new": 2,
    "max_new_positions_today": 2,
    "halt": False,
    "halt_new_entries": False,
    "min_composite_score": 70.0,
    "max_concentration_pct": 12.0,
}


def _markets_response(active_tier: object) -> dict:
    return {
        "current": {
            "exposure_pct": 35.0,
            "raw_score": 40.0,
            "regime": "caution",
            "factors": {},
        },
        "active_tier": active_tier,
    }


def test_active_tier_propagated_when_present():
    with patch("dashboard.fetchers_market._get_markets_cached", return_value=_markets_response(_SAMPLE_TIER)):
        result = fetch_exp_factors(None)
    assert result.get("active_tier") == _SAMPLE_TIER
    assert "active_tier_unavailable" not in result


def test_active_tier_marked_unavailable_when_missing():
    with patch("dashboard.fetchers_market._get_markets_cached", return_value=_markets_response(None)):
        result = fetch_exp_factors(None)
    assert result.get("active_tier_unavailable") is True
    assert "active_tier" not in result
