"""Regression test for the 2026-08-11 fix: tier_for_exposure()'s NaN guard only checked
isinstance(exposure_pct, float), so a Decimal("NaN") skipped it entirely and blew up with a
raw, undiagnosed decimal.InvalidOperation deep in the tier-matching comparisons instead of
this function's own clean, diagnostic RuntimeError - Decimal NaN comparisons raise, unlike
float NaN which just evaluates False (same distinction already documented in
position_sizer.py's calculate_position_size). Not currently reachable via either live call
site (market_exposure_daily.exposure_pct is a `double precision` column, and the other call
site explicitly float()-casts first), but a latent trap for any future caller that doesn't.
"""

from decimal import Decimal

import pytest

from algo.risk.exposure_policy import tier_for_exposure


class TestTierForExposureNaNGuard:
    def test_decimal_nan_raises_clean_runtime_error(self):
        with pytest.raises(RuntimeError, match="Market exposure percentage is missing or invalid"):
            tier_for_exposure(Decimal("NaN"))

    def test_float_nan_still_raises_clean_runtime_error(self):
        with pytest.raises(RuntimeError, match="Market exposure percentage is missing or invalid"):
            tier_for_exposure(float("nan"))

    def test_none_still_raises_clean_runtime_error(self):
        with pytest.raises(RuntimeError, match="Market exposure percentage is missing or invalid"):
            tier_for_exposure(None)

    def test_decimal_valid_value_still_resolves_a_tier(self):
        assert tier_for_exposure(Decimal("70.5"))["name"] == "confirmed_uptrend"

    def test_decimal_infinity_still_raises_no_matching_tier_error(self):
        with pytest.raises(RuntimeError, match="does not match any tier"):
            tier_for_exposure(Decimal("Infinity"))

    def test_float_boundary_values_unaffected_by_the_fix(self):
        assert tier_for_exposure(70.0)["name"] == "confirmed_uptrend"
        assert tier_for_exposure(69.999999)["name"] == "uptrend_under_pressure"
        assert tier_for_exposure(0.0)["name"] == "correction"
        assert tier_for_exposure(100.0)["name"] == "confirmed_uptrend"
