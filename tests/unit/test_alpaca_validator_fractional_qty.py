"""Regression: AlpacaResponseValidator.validate_order_status_response() invalidated the
entire result whenever filled_qty/qty was fractional, even when the field its only real
caller actually needs (filled_avg_price) was perfectly valid.

Alpaca returns qty fields as strings to preserve decimal precision (e.g. "4.87" for a
fractional-share fill) - this system actively trades fractional shares. int("4.87") always
raised inside the try/except here, appending an error and forcing valid=False.
order_manager.py's get_order_fill_price() is the only caller and only reads
status/filled_avg_price from the result - so any fractionally-filled order made fetching
its own fill price fail entirely via RuntimeError("Invalid response from Alpaca"), for a
reason unrelated to the price itself.
"""

from utils.validation.alpaca import AlpacaResponseValidator


def test_fractional_filled_qty_does_not_invalidate_result():
    result = AlpacaResponseValidator.validate_order_status_response(
        {"status": "filled", "filled_qty": "4.87", "filled_avg_price": "150.25", "qty": "4.87"}
    )
    assert result["valid"] is True, result["errors"]
    assert result["filled_qty"] == 4.87
    assert result["qty"] == 4.87
    assert result["filled_avg_price"] == 150.25


def test_whole_share_filled_qty_still_works():
    result = AlpacaResponseValidator.validate_order_status_response(
        {"status": "filled", "filled_qty": "10", "filled_avg_price": "150.25", "qty": "10"}
    )
    assert result["valid"] is True, result["errors"]
    assert result["filled_qty"] == 10.0


def test_genuinely_invalid_qty_is_still_rejected():
    result = AlpacaResponseValidator.validate_order_status_response(
        {"status": "filled", "filled_qty": "not_a_number", "filled_avg_price": "150.25"}
    )
    assert result["valid"] is False
    assert result["filled_qty"] is None
