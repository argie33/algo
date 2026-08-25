"""Regression test: lambda/api/routes/algo_handlers/signals.py's _TIER_CONFIG must be
derived from algo/risk/exposure_policy.py's EXPOSURE_TIERS, not an independent
hand-maintained copy.

BUG FOUND 2026-08-24 (real-money-readiness goal, position-sizing re-verification pass):
_TIER_CONFIG had drifted from the real EXPOSURE_TIERS values - wrong risk_mult
(0.6/0.3/0.2 vs real 0.65/0.35/0.0), wrong max_new (5 vs real 4 for confirmed_uptrend; 1 vs
real 2 for caution), and most seriously `caution` showed `halt: True` when the live system
does not halt entries in that tier (only `correction` halts). This dict backs
market.py's `active_tier` API response, rendered directly by
webapp/frontend/src/pages/MarketsHealth.jsx as risk_mult/max_new/a HALTED-ALLOWED badge -
the drift meant a real, live dashboard was showing an operator the wrong risk posture.

Same double-source-of-truth bug class already fixed once in position_sizer.py's
regime_mult - fixed here the same way: derive from the one real source instead of a second
hand-maintained copy that can silently drift again.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))

from routes.algo_handlers.signals import _TIER_CONFIG

from algo.risk.exposure_policy import EXPOSURE_TIERS


class TestTierConfigMatchesExposureTiers:
    def test_same_tier_names(self):
        assert set(_TIER_CONFIG.keys()) == {tier["name"] for tier in EXPOSURE_TIERS}

    def test_risk_mult_and_max_new_and_halt_match_exposure_tiers(self):
        for tier in EXPOSURE_TIERS:
            conf = _TIER_CONFIG[tier["name"]]
            assert conf["risk_mult"] == tier["risk_multiplier"]
            assert conf["risk_multiplier"] == tier["risk_multiplier"]
            assert conf["max_new"] == tier["max_new_positions_today"]
            assert conf["max_new_positions_today"] == tier["max_new_positions_today"]
            assert conf["halt"] == tier["halt_new_entries"]
            assert conf["halt_new_entries"] == tier["halt_new_entries"]

    def test_min_composite_score_and_max_concentration_match_exposure_tiers(self):
        # BUG FOUND 2026-08-25 (money-% goal-session audit, exposure_policy_tier_dashboard_gap
        # follow-up): _TIER_CONFIG never carried min_composite_score/max_concentration_pct at
        # all, so neither the TUI nor the web frontend had a path to them despite
        # min_composite_score alone being retuned 3x in one day (see
        # exposure_tier_min_composite_score_selectivity_raised_20260824 in memory).
        for tier in EXPOSURE_TIERS:
            conf = _TIER_CONFIG[tier["name"]]
            assert conf["min_composite_score"] == tier["min_composite_score"]
            assert conf["max_concentration_pct"] == tier["max_concentration_pct"]

    def test_caution_tier_is_not_halted(self):
        # The specific live-dashboard-facing regression this fix was found from: caution
        # must show halt=False (only "correction" halts entries in the real system).
        assert _TIER_CONFIG["caution"]["halt"] is False
        assert _TIER_CONFIG["caution"]["halt_new_entries"] is False
