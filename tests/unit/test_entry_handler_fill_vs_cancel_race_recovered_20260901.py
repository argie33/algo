"""Regression test: a real fill that races past _wait_for_order_fill's 30s poll timeout must
be recorded, not discarded.

BUG FOUND 2026-09-01 (real-money-readiness sweep, order-retry fringe-case review): a 30s poll
timeout in order_manager.wait_for_order_fill() does not mean the order died - it's still LIVE
at the broker and can fill at any moment, including during the cleanup cancel request the
caller (executor_entry_handler.py::_submit_entry_phase) sends right after. The previous version
of order_manager.cancel_bracket_orders() returned a bare {"success": bool, "message": str} with
no fill information at all, so the caller always treated the timeout as a total failure and
never wrote a trade/position record - even when real shares had genuinely filled at the broker.
This is the exact same "invisible live position" bug class already fixed for
wait_for_order_fill's own partially_filled/cancelled-with-fill branches (see
test_order_manager_wait_for_fill.py), just reached via this different cancel-cleanup path.

Fixed: cancel_bracket_orders() now checks the order's real final state (via the existing
get_order()) after any cancel outcome (200/204 success, or 422 already-terminal) and reports
filled_qty/filled_avg_price if a real fill is found. _submit_entry_phase() checks this and
returns a genuine (possibly partial) fill instead of reporting failure and losing the trade.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.executor_entry_handler import EntryHandler


def _make_handler():
    handler_context = MagicMock()
    handler_context._submit_and_validate_order.return_value = (
        True,  # order_ok
        "alpaca-order-race",  # alpaca_order_id
        "new",  # order_status (immediate POST response)
        "",  # order_error
        None,  # executed_price (not yet filled)
        None,  # rejection_reason
        {"legs": [{"order_type": "stop"}, {"order_type": "limit"}], "order_class": "bracket"},
    )
    handler_context._wait_for_order_fill.return_value = (
        False,
        None,
        "Order fill timeout after 30.0s (60 polls). Order may still fill asynchronously.",
    )
    return EntryHandler(handler_context), handler_context


class TestFillVsCancelRaceRecovered:
    def test_full_fill_race_recorded_as_filled_not_discarded(self):
        """The cancel raced past a FULL fill - cancel_bracket_orders reports the whole
        requested quantity filled (the 422-already-terminal case). Must be recorded as a
        genuine fill, not a failure."""
        handler, handler_context = _make_handler()
        handler_context._cancel_bracket_orders.return_value = {
            "success": False,
            "message": "Order alpaca-order-race could not be cancelled (422 - already terminal) "
            "but filled 10.0 shares before the cancel raced past it",
            "filled_qty": 10.0,
            "filled_avg_price": 101.25,
        }

        with patch("algo.trading.executor_entry_handler.notify") as mock_notify:
            result = handler._submit_entry_phase(
                cur=MagicMock(),
                symbol="RACESYM",
                trade_id="trade-race-full",
                shares=Decimal("10"),
                entry_price=Decimal("100.00"),
                stop_loss_price=Decimal("95.00"),
                target_1_price=Decimal("110.00"),
                execution_mode="auto",
                idempotency_key="a" * 64,
            )

        order_ok, error_msg, order_status, alpaca_order_id, executed_price, rejection_reason, _ = result
        assert order_ok is True, "a real broker fill must not be reported as a failure"
        assert error_msg == ""
        assert order_status == "filled"
        assert alpaca_order_id == "alpaca-order-race"
        assert executed_price == Decimal("101.25")

        # A recovery notice must be sent, but NOT the "order fill failed" critical alert.
        mock_notify.assert_called_once()
        call = mock_notify.call_args
        severity = call.args[0] if call.args else call.kwargs.get("severity")
        assert severity == "warning", "a recovered fill is informational, not a critical failure alert"
        assert "RACESYM" in str(call)

    def test_partial_fill_race_recorded_as_partially_filled(self):
        """The cancel raced past a PARTIAL fill (4 of 10 requested shares) - must be recorded
        as partially_filled with the real filled quantity reflected in executed_price/status,
        not the full requested amount."""
        handler, handler_context = _make_handler()
        handler_context._cancel_bracket_orders.return_value = {
            "success": True,
            "message": "Cancelled bracket order alpaca-order-race",
            "filled_qty": 4.0,
            "filled_avg_price": 99.80,
        }

        with patch("algo.trading.executor_entry_handler.notify"):
            result = handler._submit_entry_phase(
                cur=MagicMock(),
                symbol="RACESYM",
                trade_id="trade-race-partial",
                shares=Decimal("10"),
                entry_price=Decimal("100.00"),
                stop_loss_price=Decimal("95.00"),
                target_1_price=Decimal("110.00"),
                execution_mode="auto",
                idempotency_key="b" * 64,
            )

        order_ok, _, order_status, _, executed_price, _, _ = result
        assert order_ok is True
        assert order_status == "partially_filled"
        assert executed_price == Decimal("99.80")

    def test_genuine_zero_fill_still_reports_failure(self):
        """Sanity check: when the cancel confirms zero fill (the common case), the existing
        critical-alert failure path must still fire unchanged."""
        handler, handler_context = _make_handler()
        handler_context._cancel_bracket_orders.return_value = {
            "success": True,
            "message": "Cancelled bracket order alpaca-order-race",
            "filled_qty": None,
            "filled_avg_price": None,
        }

        with patch("algo.trading.executor_entry_handler.notify") as mock_notify:
            result = handler._submit_entry_phase(
                cur=MagicMock(),
                symbol="RACESYM",
                trade_id="trade-race-zero",
                shares=Decimal("10"),
                entry_price=Decimal("100.00"),
                stop_loss_price=Decimal("95.00"),
                target_1_price=Decimal("110.00"),
                execution_mode="auto",
                idempotency_key="c" * 64,
            )

        order_ok = result[0]
        assert order_ok is False
        mock_notify.assert_called_once()
        call = mock_notify.call_args
        severity = call.args[0] if call.args else call.kwargs.get("severity")
        assert severity == "critical"
        assert call.kwargs.get("strict") is True

    def test_missing_fill_price_raises_rather_than_silently_dropping_shares(self):
        """A raced fill with no price available is a data-integrity emergency, not something
        to silently discard - the position is real at the broker but cannot be recorded
        without a price, so this must raise loudly (Phase 9 sync remains the backstop)."""
        handler, handler_context = _make_handler()
        handler_context._cancel_bracket_orders.return_value = {
            "success": False,
            "message": "already terminal",
            "filled_qty": 10.0,
            "filled_avg_price": None,
        }

        with patch("algo.trading.executor_entry_handler.notify"):
            try:
                handler._submit_entry_phase(
                    cur=MagicMock(),
                    symbol="RACESYM",
                    trade_id="trade-race-noprice",
                    shares=Decimal("10"),
                    entry_price=Decimal("100.00"),
                    stop_loss_price=Decimal("95.00"),
                    target_1_price=Decimal("110.00"),
                    execution_mode="auto",
                    idempotency_key="d" * 64,
                )
                raise AssertionError("expected RuntimeError for a raced fill with no price")
            except RuntimeError as e:
                assert "no fill price" in str(e) or "filled during the cancel race" in str(e)
