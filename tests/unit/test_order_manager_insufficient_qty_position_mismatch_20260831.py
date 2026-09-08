"""Regression test: OrderManager._handle_insufficient_qty() / send_market_exit()'s handling of
Alpaca's 403 "insufficient qty available" response - the exact scenario PRODUCTION_READINESS_
AUDIT_20260831.md's Observation 3 ("Position Quantity Mismatch Guard") calls out as needing
verification before going live, but had zero direct test coverage (confirmed via repo-wide grep
for `_handle_insufficient_qty`/`held_for_orders` before this file was added).

Traced end to end for this audit (2026-08-31), read-only - no code changes were needed:
  1. DB qty != Alpaca available qty (e.g. a fractional fill not yet reconciled): send_market_exit
     retries with the broker's actual available qty (Case 1 below) rather than failing outright.
  2. All shares locked by an existing open order (e.g. a resting bracket leg): falls back to the
     close-position endpoint, which bypasses the hold (Case 2 below).
  3. Neither case applies: an ambiguous response (available==0 with no 'held_for_orders' field)
     raises RuntimeError immediately (fail-loud); an exhausted retry loop (e.g. persistent 5xx)
     falls through to the normal last_error/failure return. Both fail safe either way - no DB
     mutation happens anywhere downstream on a failed exit.
  4. Downstream, executor_exit_handler.py never trusts the originally-requested `shares_to_exit`
     for the DB write - it independently re-verifies via order_manager.get_order_filled_quantity()
     and corrects `shares_to_exit`/`full_exit` before writing algo_trades/algo_positions/
     algo_audit_log. So even if this retry undersells relative to what was requested, the position
     is recorded as a PARTIAL exit (remainder stays open in the DB) rather than being marked fully
     closed while shares are still held at the broker - the "orphaned position" failure mode
     Observation 3 worries about does not occur. That downstream verification already has coverage
     in test_order_manager_fractional_filled_qty.py; this file covers the upstream retry/fallback
     decision that test doesn't reach.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.trading.order_manager import OrderManager


def _resp(status_code, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def _filled_order(order_id="order-123", filled_avg_price="10.00"):
    return {"id": order_id, "status": "filled", "filled_avg_price": filled_avg_price}


class TestHandleInsufficientQtyPartialAvailability:
    """Case 1: Alpaca reports fewer shares available than the DB thinks we hold."""

    def test_retries_with_actual_available_qty_and_succeeds(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        first_403 = _resp(403, json_data={"available": "60", "held_for_orders": "0"})
        second_200 = _resp(200, json_data=_filled_order())

        with patch(
            "algo.trading.order_manager.requests.post",
            side_effect=[first_403, second_200],
        ) as mock_post:
            result = manager.send_market_exit("AAPL", shares=100, execution_mode="auto")

        assert result["success"] is True
        assert result["order_id"] == "order-123"
        # The retried request must carry the corrected (smaller) qty, not the original 100 -
        # otherwise it would just 403 again identically.
        assert mock_post.call_count == 2
        retried_payload = mock_post.call_args_list[1].kwargs["json"]
        assert retried_payload["qty"] == "60.0"

    def test_does_not_retry_with_corrected_qty_past_attempt_zero(self):
        """The 'available' partial-qty correction is only trusted on attempt 0 (a stale
        second 403 with a different 'available' figure mid-retry-loop should not silently
        keep shrinking the order qty indefinitely)."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        # attempt 0: corrects 100 -> 60 and retries. attempt 1: another 403, but attempt != 0
        # so the partial-availability branch is skipped; held_for_orders present so it falls
        # to the "fallthrough" path (last_error) rather than looping the qty down further.
        responses = [
            _resp(403, json_data={"available": "60", "held_for_orders": "0"}),
            _resp(403, json_data={"available": "10", "held_for_orders": "50"}, text="still short"),
            _resp(200, json_data=_filled_order()),
        ]
        with patch("algo.trading.order_manager.requests.post", side_effect=responses) as mock_post:
            result = manager.send_market_exit("AAPL", shares=100, execution_mode="auto")

        assert result["success"] is True
        assert mock_post.call_count == 3
        assert mock_post.call_args_list[1].kwargs["json"]["qty"] == "60.0"
        assert mock_post.call_args_list[2].kwargs["json"]["qty"] == "60.0"


class TestHandleInsufficientQtyLockedByOrders:
    """Case 2: zero shares available because all of them are held by an existing open order
    (e.g. a resting bracket leg) - falls back to the close-position endpoint."""

    def test_falls_back_to_close_position_endpoint(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        first_403 = _resp(403, json_data={"available": "0", "held_for_orders": "100"})
        close_position_resp = _resp(
            200,
            json_data={"id": "close-order-456", "filled_avg_price": "9.95"},
        )

        with (
            patch("algo.trading.order_manager.requests.post", return_value=first_403) as mock_post,
            patch("algo.trading.order_manager.requests.delete", return_value=close_position_resp) as mock_delete,
        ):
            result = manager.send_market_exit("AAPL", shares=100, execution_mode="auto")

        assert result["success"] is True
        assert result["order_id"] == "close-order-456"
        assert result["filled_price"] == 9.95
        mock_delete.assert_called_once()
        # Only the initial failed POST - no further POST retries once the DELETE fallback succeeds.
        assert mock_post.call_count == 1


class TestHandleInsufficientQtyFailsSafe:
    """Neither case applies, or the retry itself never succeeds: must fail without ever
    reporting success - a false 'success' here is exactly what would let the caller mark a
    position closed in the DB while shares remain open at the broker."""

    def test_missing_held_for_orders_field_raises_rather_than_silently_succeeding(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        # available == 0 but no held_for_orders field at all - ambiguous broker response.
        # Verified: this raises RuntimeError rather than falling through to a false success
        # or a quietly-swallowed failure - the ambiguity itself is treated as fail-fast/
        # fail-loud, matching this system's "no silent fallback" governance rule.
        malformed_403 = _resp(403, json_data={"available": "0"}, text="no held_for_orders")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=malformed_403),
            pytest.raises(RuntimeError, match="held_for_orders"),
        ):
            manager.send_market_exit("AAPL", shares=100, execution_mode="auto")

    def test_exhausted_retries_returns_failure_not_false_success(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        persistent_500 = _resp(500, text="broker error")

        with patch("algo.trading.order_manager.requests.post", return_value=persistent_500):
            result = manager.send_market_exit("AAPL", shares=100, execution_mode="auto")

        assert result["success"] is False
