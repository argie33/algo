"""Regression test for a 2026-08-24 redesign of algo/risk/exposure_policy.py: every tier's
tighten_winners_at_r/force_partial_at_r/force_exit_negative_r used to fire real
tighten_stop/partial_exit/force_exit actions on OPEN positions purely off the market-wide
exposure tier - e.g. "correction" tier's force_exit_negative_r force-exited ANY red
position the moment exposure_pct dropped below 25%, regardless of what that position's own
stop-loss/target/trend-break logic (exit_engine.py's 11-step hierarchy) said about it.

User-directed fix: market exposure is a lever on FUTURE buying only (halt_new_entries,
max_new_positions_today, max_concentration_pct, and position_sizer.py's continuous
exposure_pct/100 sizing multiplier) - never a reason to trim or exit a position already
held. Confirmed via live code read (not assumption) that this was the actual wired
behavior: Phase 5 (phase5_exposure_policy.py) called review_existing_positions() every
run and Phase 6 (phase6_exit_execution.py) executed any resulting force_exit/partial_exit/
tighten_stop as real orders.

This test locks in the new behavior: review_existing_positions() must return no actions
for ANY tier, even a deeply negative-R position that would have force-exited under the old
correction-tier config.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.risk.exposure_policy import EXPOSURE_TIERS, ExposurePolicy


class TestExposureTiersNeverTriggerPositionActions:
    def test_all_tiers_have_exit_triggers_disabled(self):
        """EXPOSURE_TIERS itself must never re-enable exposure-driven position selling -
        the config, not just current call behavior, is the thing that must stay fixed."""
        for tier in EXPOSURE_TIERS:
            assert tier["tighten_winners_at_r"] is None, (
                f"{tier['name']}: tighten_winners_at_r must be None - exposure must not "
                f"ratchet stops on existing positions."
            )
            assert tier["force_partial_at_r"] is None, (
                f"{tier['name']}: force_partial_at_r must be None - exposure must not "
                f"force partial exits on existing positions."
            )
            assert tier["force_exit_negative_r"] is False, (
                f"{tier['name']}: force_exit_negative_r must be False - exposure must not "
                f"force-exit losing positions; that's the stop-loss's job."
            )

    def test_deeply_negative_position_holds_under_correction_tier(self):
        """Sanity check via the real evaluation path: a position at R=-5.0 (deep loser) under
        the 'correction' tier (which used to force_exit_negative_r=True) must now return
        'hold', not 'force_exit' - the position's own stop-loss, not exposure, decides its
        fate."""
        correction_tier = next(t for t in EXPOSURE_TIERS if t["name"] == "correction")
        row = (
            "TRD-1",  # trade_id
            "AAPL",  # symbol
            100.0,  # entry_price
            90.0,  # init_stop
            None,  # t1_price
            None,  # t2_price
            None,  # t3_price
            date(2026, 1, 1),  # trade_date
            1,  # position_id
            10,  # qty
            0,  # target_hits
            90.0,  # cur_stop
            50.0,  # cur_price - deep loser, R = (50-100)/(100-90) = -5.0
            -50.0,  # pnl_pct
        )
        result = ExposurePolicy._evaluate_position(MagicMock(), row, tier=correction_tier)
        assert result["action"] == "hold", (
            f"A deeply negative position must hold under exposure policy - only the "
            f"position's own stop-loss should exit it. Got: {result}"
        )

    def test_review_existing_positions_returns_no_actions_across_all_tiers(self):
        """review_existing_positions() must return [] (no tighten/partial/force actions)
        regardless of which tier is active, given a mix of winning/losing open positions."""
        policy = ExposurePolicy()
        columns_row = (
            "TRD-1",
            "AAPL",
            100.0,  # entry_price
            90.0,  # init_stop
            150.0,
            170.0,
            190.0,  # t1/t2/t3
            date(2026, 1, 1),
            1,
            10,
            0,  # target_hits
            90.0,  # cur_stop
            40.0,  # cur_price - deep loser
            -60.0,
        )
        for tier in EXPOSURE_TIERS:
            with (
                patch.object(
                    policy,
                    "get_active_tier",
                    return_value={
                        "as_of_date": "2026-08-24",
                        "exposure_pct": (tier["min_pct"] + tier["max_pct"]) / 2,
                        "regime": tier["name"],
                        "halt_reasons": [],
                        "tier": tier,
                    },
                ),
                patch("algo.risk.exposure_policy.DatabaseContext") as MockDB,
            ):
                MockDB.return_value.__enter__.return_value.fetchall.return_value = [columns_row]
                actions = policy.review_existing_positions(date(2026, 8, 24))
            assert actions == [], f"Tier {tier['name']} produced exposure-driven actions: {actions}"
