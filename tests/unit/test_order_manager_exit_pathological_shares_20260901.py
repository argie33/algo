"""Regression test for OrderManager.send_market_exit()'s `shares` validation.

BUG FOUND 2026-09-01 (/goal session, real-money-readiness sweep): unlike send_bracket_order()
(the entry path, hardened via a 28,561-combination fuzz pass that found 745 uncaught crashes at
magnitude >= 1e300 - see test_order_manager_bracket_order_pathological_inputs.py), this exit
path had zero validation on `shares` itself before it goes straight into order_data["qty"] and
gets POSTed to Alpaca as a real sell order. `limit_price` was already guarded (falls back to a
market order on invalid input) but `shares` was not.

shares_to_exit is computed upstream in executor_exit_handler.py's _calculate_exit_shares() via
Decimal(str(current_qty)) * Decimal(str(exit_fraction)) - if either input were ever corrupted
(NaN/Infinity), that Decimal arithmetic's exact failure mode isn't the kind of thing to reason
about by hand, and "probably fine" was exactly the wrong assumption on the entry side until it
was actually fuzzed. This adds the same-shape guard at the literal broker-submission boundary,
mirroring send_bracket_order's proven pattern, regardless of what upstream corruption might
look like.

The critical assertion in every test below is that the network call is NEVER attempted for
invalid input - garbage data must be rejected before it reaches the broker, not after.
"""

from unittest.mock import patch

import pytest

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


@pytest.mark.parametrize(
    "shares",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        0,
        0.0,
        -10,
        -0.01,
        1e300,
        -1e300,
    ],
)
def test_pathological_shares_rejected_before_any_network_call(shares):
    manager = _make_manager()

    with patch("algo.trading.order_manager.requests.post") as mock_post:
        result = manager.send_market_exit("CHAOSFUZZ", shares, execution_mode="auto")

    assert result["success"] is False
    assert result["order_id"] is None
    assert not mock_post.called, "invalid shares must be rejected before any broker call, not sent as garbage"


def test_paper_mode_bypasses_the_guard_entirely():
    """Paper mode never calls the broker at all - the validation added for the real
    broker-submission path must not accidentally start rejecting paper-mode exits, which
    have always accepted whatever shares value the caller passes through."""
    manager = _make_manager()
    with patch("algo.trading.order_manager.requests.post") as mock_post:
        result = manager.send_market_exit("CHAOSFUZZ", float("nan"), execution_mode="paper")

    assert result["success"] is True
    assert not mock_post.called


def test_valid_shares_still_makes_the_network_call():
    """Sanity check that the new validation doesn't over-reject legitimate exits, including
    fractional shares (this system actively trades fractional positions)."""
    manager = _make_manager()
    with patch("algo.trading.order_manager.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "id": "real-order-1",
            "status": "filled",
            "filled_avg_price": "100.00",
        }
        result = manager.send_market_exit("AAPL", 10.5, execution_mode="auto")

    assert mock_post.called
    assert result["success"] is True
