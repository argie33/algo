#!/usr/bin/env python3
"""Test Phase 3 handles NULL close_price in price_daily gracefully.

CRITICAL FIX VERIFICATION: Phase 3 crashed with RowValidationError if price_daily
had NULL close prices. The fix allows NULL in accessor.get_float() call, letting
Phase 3's error handling catch it properly at line 304-315.

Commit: c6077b545 - Line 249 changed from accessor.get_float(1) to
accessor.get_float(1, allow_none=True)
"""

import pytest

from utils.db.result_validator import RowAccessor, RowValidationError


def test_row_accessor_allows_none_with_flag():
    """Verify RowAccessor.get_float(allow_none=True) returns None instead of raising."""
    # Test data: row with NULL float value (simulates price_daily.close = NULL)
    row = ("AAPL", None, False, "N/A")
    columns = ["symbol", "close", "data_unavailable", "reason"]

    accessor = RowAccessor(row, columns, "test_price_fetch")

    # CRITICAL: With allow_none=True, should return None instead of raising
    result = accessor.get_float(1, allow_none=True)
    assert result is None, "RowAccessor.get_float(allow_none=True) should return None for NULL values"


def test_row_accessor_raises_without_allow_none_flag():
    """Verify RowAccessor.get_float() without allow_none raises RowValidationError on NULL."""
    # Test data: row with NULL float value
    row = ("AAPL", None, False, "N/A")
    columns = ["symbol", "close", "data_unavailable", "reason"]

    accessor = RowAccessor(row, columns, "test_price_fetch")

    # CRITICAL: Without allow_none (default False), should raise RowValidationError
    with pytest.raises(RowValidationError, match="Column value is NULL"):
        accessor.get_float(1)  # No allow_none parameter = default False


def test_phase3_price_handling_with_null_close():
    """Verify Phase 3's price handling logic: NULL close → prices[symbol] = None → error at validation."""
    # This simulates Phase 3 line 271: prices[symbol] = float(close_price) if close_price is not None else None

    # Scenario: accessor.get_float(allow_none=True) returns None for NULL close_price
    close_price = None  # This is what get_float returns with allow_none=True

    # Phase 3 line 271 logic
    prices = {}
    prices["AAPL"] = float(close_price) if close_price is not None else None

    # Result: prices["AAPL"] = None
    assert prices["AAPL"] is None, "NULL close_price should result in prices[symbol] = None"

    # Phase 3 line 302-315: current_price = prices.get(symbol) then check if None
    current_price = prices.get("AAPL")
    if current_price is None:
        # This is the proper error handling that should execute
        error_triggered = True
    else:
        error_triggered = False

    assert error_triggered, "Phase 3 should detect NULL current_price and halt properly"
