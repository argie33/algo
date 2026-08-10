"""Regression test for OrderManager.send_bracket_order, found via fuzzing with
pathological inputs on 2026-08-10.

This is the ACTUAL real-order-to-the-broker submission path, and had zero validation on
entry_price/shares, plus a stop_loss_price guard that didn't catch NaN (NaN comparisons
are always False in Python, so `stop_loss_price <= 0` silently passes for NaN). A
NaN/Infinite price then flowed into `_q2()`, which formats via Decimal.quantize() -
Decimal NaN doesn't raise, it silently produces the literal string "NaN" - which would
have been sent to Alpaca as order_data["stop_loss"]["stop_price"]/["limit_price"], a real
order submission with a garbage price field.

Same bug class already found and fixed this session in position_sizer.py, financial.py,
phase8_entry_execution.py, and exit_engine.py - this is the most consequential instance
since it's the actual broker submission call, not an internal calculation upstream of it.

The critical assertion in every test below is that the network call is NEVER attempted
for invalid input - garbage data must be rejected before it reaches the broker, not after.
"""

from unittest.mock import patch

import pytest

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"entry_price": float("nan")},
        {"entry_price": float("inf")},
        {"entry_price": -100.0},
        {"entry_price": 0.0},
        {"stop_loss_price": float("nan")},
        {"stop_loss_price": float("inf")},
        {"shares": float("nan")},
        {"shares": 0},
        {"shares": -10},
    ],
)
def test_pathological_input_rejected_before_any_network_call(kwargs):
    manager = _make_manager()
    defaults = {"symbol": "CHAOSFUZZ", "shares": 10, "entry_price": 100.0, "stop_loss_price": 95.0}
    defaults.update(kwargs)

    with patch("algo.trading.order_manager.requests.post") as mock_post:
        result = manager.send_bracket_order(**defaults)

    assert result["success"] is False
    assert not mock_post.called, "invalid input must be rejected before any broker call, not sent as garbage"


def test_valid_input_still_makes_the_network_call():
    """Sanity check that the new validation doesn't over-reject legitimate orders."""
    manager = _make_manager()
    with patch("algo.trading.order_manager.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "id": "real-order-1",
            "status": "filled",
            "order_class": "bracket",
            "filled_avg_price": "100.00",
            "legs": [
                {"id": "leg-stop", "type": "stop", "status": "held"},
                {"id": "leg-tp", "type": "limit", "status": "held"},
            ],
        }
        result = manager.send_bracket_order(symbol="AAPL", shares=10, entry_price=100.0, stop_loss_price=95.0)

    assert mock_post.called
    assert result["success"] is True
