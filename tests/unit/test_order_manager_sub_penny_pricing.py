"""Regression test: OrderManager._build_bracket_order_payload() must quantize sub-$1
prices to 4 decimal places (SEC Rule 612 / the "sub-penny rule"), not silently truncate
them to 2 decimals like every other price.

BUG FOUND 2026-08-11: _q2() (now _quantize_price()) unconditionally quantized every price
to Decimal("0.01"), but securities priced under $1.00 must be quoted in $0.0001
increments - Alpaca enforces this and can reject (or mis-price) a sub-$1 order submitted
with only 2 decimals of precision. This codebase already treats sub-$1/low-priced symbols
as a real, expected case elsewhere (buy_signal_generator.py computes buy/stop/target
levels at 4-decimal precision throughout; executor_entry_handler.py normalizes
entry_price/stop_loss_price to 4 decimals; phase8_entry_execution.py explicitly lists
"penny stocks" as an anticipated case) - this was the one place in the actual
broker-submission path that silently threw that precision away.

Verified via: python -m pytest tests/unit/test_order_manager_sub_penny_pricing.py -v
"""

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


def test_sub_dollar_prices_use_4_decimal_places():
    manager = _make_manager()
    payload = manager._build_bracket_order_payload(
        symbol="PENNY",
        shares=1000,
        entry_price=0.8523,
        stop_loss_price=0.7891,
        take_profit_price=0.9999,
        client_order_id=None,
    )

    assert payload["limit_price"] == "0.8523"
    assert payload["stop_loss"]["stop_price"] == "0.7891"
    assert payload["take_profit"]["limit_price"] == "0.9999"


def test_sub_dollar_price_rounds_to_4_places_not_2():
    manager = _make_manager()
    payload = manager._build_bracket_order_payload(
        symbol="PENNY",
        shares=1000,
        entry_price=0.12345,
        stop_loss_price=0.1,
        take_profit_price=None,
        client_order_id=None,
    )

    assert payload["limit_price"] == "0.1235", "must round to 4 decimals (ROUND_HALF_UP), not 2"
    assert payload["stop_loss"]["stop_price"] == "0.1000"


def test_normal_priced_stock_still_uses_2_decimal_places():
    """The fix must not change behavior for the overwhelmingly common >=$1 case."""
    manager = _make_manager()
    payload = manager._build_bracket_order_payload(
        symbol="AAPL",
        shares=10,
        entry_price=150.678,
        stop_loss_price=145.321,
        take_profit_price=160.0,
        client_order_id=None,
    )

    assert payload["limit_price"] == "150.68"
    assert payload["stop_loss"]["stop_price"] == "145.32"
    assert payload["take_profit"]["limit_price"] == "160.00"


def test_computed_take_profit_fallback_also_respects_sub_penny_precision():
    """The 1.5R-computed take-profit fallback (when no explicit target is passed) must
    also use the same precision rule, not the old always-2-decimal quantize it had
    independently of _quantize_price()."""
    manager = _make_manager()
    payload = manager._build_bracket_order_payload(
        symbol="PENNY",
        shares=1000,
        entry_price=0.5,
        stop_loss_price=0.4,
        take_profit_price=None,
        client_order_id=None,
    )

    # risk = 0.1, 1.5R target = 0.5 + 0.15 = 0.65
    assert payload["take_profit"]["limit_price"] == "0.6500"
