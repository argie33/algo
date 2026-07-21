#!/usr/bin/env python3
"""Regression tests for utils/type_conversion.py's NaN/Infinity rejection.

Covers the 2026-07-21 financial-integrity audit fix: safe_float() previously let
float('nan')/float('inf')/Decimal("NaN") pass through silently (isinstance(value, float):
return value had no finiteness check), which would poison every downstream comparison
(NaN comparisons are always False) without ever raising. safe_float() is used across ~40
files specifically for fail-fast numeric conversion, so this must never regress.
"""

import math
from decimal import Decimal

import pytest

from utils.type_conversion import safe_float, safe_int


class TestSafeFloatRejectsNonFinite:
    def test_rejects_nan_float(self):
        with pytest.raises(ValueError, match="not a finite number"):
            safe_float(float("nan"), "test.field")

    def test_rejects_positive_infinity_float(self):
        with pytest.raises(ValueError, match="not a finite number"):
            safe_float(float("inf"), "test.field")

    def test_rejects_negative_infinity_float(self):
        with pytest.raises(ValueError, match="not a finite number"):
            safe_float(float("-inf"), "test.field")

    def test_rejects_nan_decimal(self):
        with pytest.raises(ValueError, match="not a finite number"):
            safe_float(Decimal("NaN"), "test.field")

    def test_rejects_infinity_decimal(self):
        with pytest.raises(ValueError, match="not a finite number"):
            safe_float(Decimal("Infinity"), "test.field")

    def test_rejects_nan_string(self):
        with pytest.raises(ValueError):
            safe_float("nan", "test.field")

    def test_rejects_infinity_string(self):
        with pytest.raises(ValueError):
            safe_float("inf", "test.field")

    def test_accepts_normal_float(self):
        assert safe_float(3.14, "test.field") == 3.14

    def test_accepts_normal_int(self):
        assert safe_float(42, "test.field") == 42.0

    def test_accepts_normal_decimal(self):
        assert safe_float(Decimal("19.99"), "test.field") == 19.99

    def test_accepts_none_when_allowed(self):
        assert safe_float(None, "test.field", allow_none=True) is None

    def test_raises_on_none_when_disallowed(self):
        with pytest.raises(ValueError):
            safe_float(None, "test.field", allow_none=False)

    def test_zero_is_finite_and_accepted(self):
        assert safe_float(0.0, "test.field") == 0.0

    def test_negative_value_is_finite_and_accepted(self):
        assert safe_float(-5.5, "test.field") == -5.5


class TestSafeFloatResultNeverNaN:
    """Any value that survives safe_float() must be usable in a normal comparison
    (i.e. must not be NaN, since NaN breaks every threshold/gating check that assumes
    x > y or x < y is meaningful)."""

    @pytest.mark.parametrize("value", [1.5, -1.5, 0, 100, Decimal("2.5"), "3.5"])
    def test_result_compares_equal_to_itself(self, value):
        result = safe_float(value, "test.field")
        assert result == result  # NaN != NaN; this fails only for NaN


class TestSafeIntUnaffected:
    """safe_int operates on int/Decimal/str only - Python int has no NaN/Infinity
    concept, so no equivalent check is needed there. Confirms it still works normally."""

    def test_accepts_normal_int(self):
        assert safe_int(5, "test.field") == 5

    def test_accepts_none_when_allowed(self):
        assert safe_int(None, "test.field", allow_none=True) is None
