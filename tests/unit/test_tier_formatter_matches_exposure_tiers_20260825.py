"""Regression test: dashboard/formatter_strategies.py's TierFormatter must derive its
percentage->tier boundaries from algo/risk/exposure_policy.py's EXPOSURE_TIERS, not an
independent hand-maintained copy.

BUG FOUND 2026-08-25 (goal session, "exposure dashboard summary/extended panels not
reflecting current state" audit): TierFormatter.TIER_MAP hardcoded boundaries at
80/60/40/0 - the pre-2026-08-24-redesign values - while EXPOSURE_TIERS moved to 70/45/25/0
along with the rest of the exposure-tier work that day. Same double-source-of-truth bug
class already fixed once for lambda/api/routes/algo_handlers/signals.py's _TIER_CONFIG (see
test_tier_config_derived_from_exposure_tiers_20260824.py) - fixed here the same way: derive
from the one real source instead of a second hand-maintained copy that can silently drift
again.

This formatter backs 5 render call sites: dashboard/panels/exposure.py's compact and
expanded panel header tier badges (tier name + color), and dashboard/panels/market.py's
exp_bar() exposure-% bar color in 3 places. With the drifted boundaries, exposure_pct in
[70,80), [45,60), and [25,40) rendered the WRONG tier/color there - directly contradicting
the correct tier name shown by the same panel's "Policy Tier:" row (sourced from the real
active_tier API field).
"""

from algo.risk.exposure_policy import EXPOSURE_TIERS, tier_for_exposure
from dashboard.formatter_strategies import TierFormatter


class TestTierFormatterMatchesExposureTiers:
    def test_boundaries_match_exposure_tiers_across_full_range(self):
        tf = TierFormatter()
        # Sample every integer percent plus fractional boundary-adjacent values, and check
        # against the real tier_for_exposure() policy lookup - not just the raw thresholds -
        # so this catches drift in either the formatter or a future EXPOSURE_TIERS reorder.
        samples = [p / 10.0 for p in range(1001)]
        for p in samples:
            expected = tier_for_exposure(p)["name"]
            actual = tf.format(p)
            assert actual == expected, f"at {p}%: TierFormatter said {actual!r}, real tier is {expected!r}"

    def test_min_pct_boundaries_exactly(self):
        tf = TierFormatter()
        for tier in EXPOSURE_TIERS:
            min_pct = tier["min_pct"]
            assert tf.format(min_pct) == tier["name"], f"lower bound {min_pct}% should be {tier['name']}"

    def test_none_and_invalid_input_returns_unknown(self):
        tf = TierFormatter()
        assert tf.format(None) == "unknown"
        assert tf.format("not-a-number") == "unknown"
