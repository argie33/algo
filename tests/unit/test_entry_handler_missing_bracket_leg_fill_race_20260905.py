"""Regression test: a bracket order with a missing stop-loss/take-profit leg must still
recover a real fill that races past the cleanup cancel, instead of discarding it.

BUG FOUND 2026-09-05 (real-money-readiness audit): executor_entry_handler.py's bracket-leg
validation (`len(legs) < 2` and `not has_stop_loss or not has_take_profit`) called
`self.context._cancel_bracket_orders(alpaca_order_id)` and discarded the return value entirely,
unlike the sibling fill-wait-timeout branch a few lines below which already checked
`filled_qty`/`filled_avg_price` for a real fill that raced past the cancel (see
test_entry_handler_fill_vs_cancel_race_recovered_20260901.py). If the entry leg filled the
instant the cancel request landed - because Alpaca rejected the stop-loss/take-profit child leg
- the caller (execute_entry) would see order_ok=False and, in execution_mode="auto", take the
"hard stop, do NOT create a trade record" path: real shares held at the broker, zero DB record,
zero stop-loss, invisible to every downstream risk/exit check.

Fixed by extracting the race-recovery logic into `_recover_bracket_cancel_race()` and calling it
from all three cancel-then-check-for-a-race sites, not just the timeout one.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.executor_entry_handler import EntryHandler


def _make_handler(order_result: dict) -> tuple[EntryHandler, MagicMock]:
    handler_context = MagicMock()
    handler_context._submit_and_validate_order.return_value = (
        True,  # order_ok
        "alpaca-order-legrace",  # alpaca_order_id
        "new",  # order_status
        "",  # order_error
        None,  # executed_price
        None,  # rejection_reason
        order_result,
    )
    return EntryHandler(handler_context), handler_context


class TestMissingLegFillRaceRecovered:
    def test_missing_stop_loss_leg_but_entry_raced_a_full_fill_is_recorded(self):
        """Bracket came back with only 1 leg (missing stop-loss) - but the entry itself
        filled fully during the cleanup cancel. Must be recorded as a real fill, not dropped."""
        handler, handler_context = _make_handler({"legs": [{"order_type": "limit"}], "order_class": "bracket"})
        handler_context._cancel_bracket_orders.return_value = {
            "success": False,
            "message": "already terminal",
            "filled_qty": 10.0,
            "filled_avg_price": 50.10,
        }

        with patch("algo.trading.executor_entry_handler.notify") as mock_notify:
            result = handler._submit_entry_phase(
                cur=MagicMock(),
                symbol="LEGRACE",
                trade_id="trade-legrace-1",
                shares=Decimal("10"),
                entry_price=Decimal("50.00"),
                stop_loss_price=Decimal("47.50"),
                target_1_price=Decimal("55.00"),
                execution_mode="auto",
                idempotency_key="e" * 64,
            )

        order_ok, error_msg, order_status, alpaca_order_id, executed_price, _, _ = result
        assert order_ok is True, "a real broker fill must not be discarded just because a leg was missing"
        assert error_msg == ""
        assert order_status == "filled"
        assert alpaca_order_id == "alpaca-order-legrace"
        assert executed_price == Decimal("50.10")
        mock_notify.assert_called_once()

    def test_missing_take_profit_leg_but_entry_raced_a_partial_fill_is_recorded(self):
        """Bracket has both order_type legs but is missing take_profit specifically (only a
        stop leg present) - and the entry partially filled during the cleanup cancel."""
        handler, handler_context = _make_handler({"legs": [{"order_type": "stop"}], "order_class": "bracket"})
        handler_context._cancel_bracket_orders.return_value = {
            "success": True,
            "message": "Cancelled bracket order alpaca-order-legrace",
            "filled_qty": 3.0,
            "filled_avg_price": 49.90,
        }

        with patch("algo.trading.executor_entry_handler.notify"):
            result = handler._submit_entry_phase(
                cur=MagicMock(),
                symbol="LEGRACE2",
                trade_id="trade-legrace-2",
                shares=Decimal("10"),
                entry_price=Decimal("50.00"),
                stop_loss_price=Decimal("47.50"),
                target_1_price=Decimal("55.00"),
                execution_mode="auto",
                idempotency_key="f" * 64,
            )

        order_ok, _, order_status, _, executed_price, _, _ = result
        assert order_ok is True
        assert order_status == "partially_filled"
        assert executed_price == Decimal("49.90")

    def test_missing_leg_genuine_zero_fill_still_reports_failure_and_no_trade_record(self):
        """Sanity check: when the cancel confirms zero fill (the common case for a truly
        rejected bracket), the original "missing leg" failure must still be reported."""
        handler2, handler_context2 = _make_handler({"legs": [{"order_type": "stop"}], "order_class": "bracket"})
        handler_context2._cancel_bracket_orders.return_value = {
            "success": True,
            "message": "Cancelled bracket order",
            "filled_qty": None,
            "filled_avg_price": None,
        }

        with patch("algo.trading.executor_entry_handler.notify"):
            result = handler2._submit_entry_phase(
                cur=MagicMock(),
                symbol="LEGRACE3",
                trade_id="trade-legrace-3",
                shares=Decimal("10"),
                entry_price=Decimal("50.00"),
                stop_loss_price=Decimal("47.50"),
                target_1_price=Decimal("55.00"),
                execution_mode="auto",
                idempotency_key="0" * 64,
            )

        order_ok, error_msg, _, _, executed_price, _, _ = result
        assert order_ok is False
        assert "missing stop loss leg" in error_msg
        assert executed_price is None
