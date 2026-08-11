"""Regression test for the 2026-08-11 fix: circuit_breaker.py's _float() ran its NaN/Inf
check inside the same try block as the float() conversion, so its own
`raise ValueError("Invalid float ... (NaN/Inf)")` was immediately caught by the enclosing
`except (ValueError, TypeError)` and silently rewritten into the generic "Failed to
convert ... to float" message - losing the distinction between "couldn't parse a number at
all" and "parsed fine but the value itself is NaN/Infinity", two different data-quality
failure modes worth telling apart when debugging a real circuit-breaker halt. Not a safety
gap (both paths still correctly raise/return default), just a diagnostics gap.
"""

from decimal import Decimal

import pytest

from algo.risk.circuit_breaker import _float


class TestFloatHelperErrorMessages:
    def test_nan_raises_the_specific_nan_inf_message_not_the_generic_conversion_message(self):
        with pytest.raises(ValueError, match=r"Invalid float .* \(NaN/Inf\)"):
            _float(float("nan"), default=None, context="test")

    def test_infinity_raises_the_specific_nan_inf_message(self):
        with pytest.raises(ValueError, match=r"Invalid float .* \(NaN/Inf\)"):
            _float(float("inf"), default=None, context="test")

    def test_decimal_nan_raises_the_specific_nan_inf_message(self):
        with pytest.raises(ValueError, match=r"Invalid float .* \(NaN/Inf\)"):
            _float(Decimal("NaN"), default=None, context="test")

    def test_unparseable_value_still_raises_the_generic_conversion_message(self):
        with pytest.raises(ValueError, match=r"Failed to convert .* to float"):
            _float("not_a_number", default=None, context="test")

    def test_nan_with_default_still_returns_default_not_the_generic_default(self):
        assert _float(float("nan"), default=0.0, context="test") == 0.0

    def test_valid_value_still_converts_normally(self):
        assert _float("42.5", default=None, context="test") == 42.5
