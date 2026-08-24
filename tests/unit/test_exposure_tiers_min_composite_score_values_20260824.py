"""Regression test for EXPOSURE_TIERS['min_composite_score'] and the phase7 fallback
constant, locking in the 2026-08-24 selectivity raise (user-directed: "buy the best
stocks... floor of 60 minimum") - see exposure_policy.py's TUNING docstring above
EXPOSURE_TIERS for the full rationale (rs_percentile proxy backtest, live composite_score
distribution anchoring).

Built after this exact change was found SILENTLY REVERTED back to the original 50/60/70/80
values TWICE in one day by concurrent-session git churn on the shared working tree -
EXPOSURE_TIERS has no database backing (unlike phase7_min_composite_score, which survives a
code-level revert because migration 1224's DB row still overrides it at runtime), so nothing
caught the loss except a human/agent noticing during a later audit. This test is the fix for
"nothing catches it": a real assertion on the literal values, not just informal
verification, so CI fails loudly the next time this reverts instead of it going unnoticed.
"""

from algo.infrastructure.config.main import AlgoConfig
from algo.infrastructure.config_schema import VALIDATION_SCHEMA
from algo.risk.exposure_policy import EXPOSURE_TIERS


class TestExposureTiersMinCompositeScoreValues:
    def test_tier_thresholds_match_selectivity_raise(self):
        by_name = {tier["name"]: tier["min_composite_score"] for tier in EXPOSURE_TIERS}
        assert by_name["confirmed_uptrend"] == 60.0
        assert by_name["uptrend_under_pressure"] == 65.0
        assert by_name["caution"] == 70.0
        assert by_name["correction"] == 75.0

    def test_four_tiers_present(self):
        # Guards against a tier being silently dropped, not just a value drifting.
        assert len(EXPOSURE_TIERS) == 4
        assert {tier["name"] for tier in EXPOSURE_TIERS} == {
            "confirmed_uptrend",
            "uptrend_under_pressure",
            "caution",
            "correction",
        }


class TestPhase7MinCompositeScoreFallbackConstant:
    """phase7_min_composite_score is only used when the regime-tier lookup itself fails
    (phase7_signal_generation.py) - a secondary defense-in-depth path, but must still track
    the same selectivity raise so a fallback doesn't silently trade at the old, weaker bar."""

    def test_config_schema_default_is_60(self):
        # Format: (type, min_value, max_value, is_critical, fail_closed_value)
        assert VALIDATION_SCHEMA["phase7_min_composite_score"][3] is False  # not a safety-critical field
        assert VALIDATION_SCHEMA["phase7_min_composite_score"][4] == 60

    def test_defaults_dict_value_is_60(self):
        assert AlgoConfig.DEFAULTS["phase7_min_composite_score"][0] == "60"
