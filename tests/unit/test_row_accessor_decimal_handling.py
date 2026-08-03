#!/usr/bin/env python3
"""Regression test: RowAccessor.get_float() must accept psycopg2 Decimal values.

Found live 2026-08-03: phase3_position_monitor.py's price_daily.close read via
RowAccessor.get_float() raised RowValidationError("Column has type Decimal, expected
int or float") for a real position - get_float()'s accepted-type tuple was (int, float),
never Decimal, despite NUMERIC/DECIMAL postgres columns always coming back as
decimal.Decimal from psycopg2. This was invisible all session because there were zero
real open positions to exercise the path until an end-to-end synthetic verification test
inserted one.
"""

from decimal import Decimal

import pytest

from utils.db.result_validator import RowAccessor, RowValidationError


class TestGetFloatAcceptsDecimal:
    def test_decimal_value_returns_native_float(self):
        row = ("AAPL", Decimal("308.91"))
        accessor = RowAccessor(row, ["symbol", "close"], "test")
        result = accessor.get_float(1)
        assert result == pytest.approx(308.91)
        assert isinstance(result, float)
        assert not isinstance(result, Decimal)

    def test_int_value_still_accepted(self):
        row = ("AAPL", 100)
        accessor = RowAccessor(row, ["symbol", "close"], "test")
        assert accessor.get_float(1) == 100.0

    def test_float_value_still_accepted(self):
        row = ("AAPL", 308.91)
        accessor = RowAccessor(row, ["symbol", "close"], "test")
        assert accessor.get_float(1) == pytest.approx(308.91)

    def test_none_with_allow_none_returns_none(self):
        row = ("AAPL", None)
        accessor = RowAccessor(row, ["symbol", "close"], "test")
        assert accessor.get_float(1, allow_none=True) is None

    def test_none_without_allow_none_raises(self):
        row = ("AAPL", None)
        accessor = RowAccessor(row, ["symbol", "close"], "test")
        with pytest.raises(RowValidationError):
            accessor.get_float(1)

    def test_string_value_still_rejected(self):
        # A string masquerading as a price must still fail - only int/float/Decimal are floats.
        row = ("AAPL", "not_a_number")
        accessor = RowAccessor(row, ["symbol", "close"], "test")
        with pytest.raises(RowValidationError):
            accessor.get_float(1)

    def test_decimal_with_high_precision_converts_correctly(self):
        row = ("AAPL", Decimal("768010.1234"))
        accessor = RowAccessor(row, ["symbol", "close"], "test")
        result = accessor.get_float(1)
        assert result == pytest.approx(768010.1234)
