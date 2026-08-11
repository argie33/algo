"""Regression test: a live order that fails to fill (rejected/cancelled/expired/timed out
during the up-to-30s post-submission wait) must send a real operator alert via notify(),
not just a log line.

BUG FOUND 2026-08-11: executor_entry_handler.py::_submit_entry_phase() had a "Check for
order rejection/cancellation" block that called notify("critical", ..., strict=True) - but
it checked `order_status`, a variable set once from _submit_and_validate_order's IMMEDIATE
POST response and never reassigned. By construction that value can only be "new"/"accepted"/
"pending_new" at that point in the code (anything Alpaca rejects outright at POST time
already short-circuits earlier with order_ok=False), so
`order_status in ("rejected", "cancelled", "expired")` was structurally unreachable dead
code. The `if not fill_ok:` branch just above it - populated from wait_for_order_fill's own
live status polling - is the ONLY path that actually observes a mid-wait rejection/
cancellation/expiry/timeout, and it only called logger.critical(), never notify(). A real
live order failing to fill during that window reached the operator only as a log line, never
an actual alert - despite GOVERNANCE explicitly requiring operator awareness for events like
this (see notify()'s own docstring: "not silent best-effort delivery"). Fixed by moving the
notify() call into the reachable `if not fill_ok:` branch.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.executor_entry_handler import EntryHandler


def _make_handler():
    handler_context = MagicMock()
    handler_context._submit_and_validate_order.return_value = (
        True,  # order_ok
        "alpaca-order-123",  # alpaca_order_id
        "new",  # order_status (immediate POST response - never "rejected"/"cancelled")
        "",  # order_error
        None,  # executed_price (not yet filled)
        None,  # rejection_reason
        {"legs": [{"order_type": "stop"}, {"order_type": "limit"}], "order_class": "bracket"},
    )
    return EntryHandler(handler_context), handler_context


class TestFillFailureSendsAlert:
    def test_order_fails_to_fill_sends_notify_alert(self):
        handler, handler_context = _make_handler()
        handler_context._wait_for_order_fill.return_value = (
            False,
            None,
            "Order rejected: insufficient buying power",
        )

        with patch("algo.trading.executor_entry_handler.notify") as mock_notify:
            result = handler._submit_entry_phase(
                cur=MagicMock(),
                symbol="TESTSYM",
                trade_id="trade-1",
                shares=Decimal("10"),
                entry_price=Decimal("100.00"),
                stop_loss_price=Decimal("95.00"),
                target_1_price=Decimal("110.00"),
                execution_mode="auto",
                idempotency_key="a" * 64,
            )

        order_ok = result[0]
        assert order_ok is False
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        assert call_kwargs.args[0] == "critical" or call_kwargs.kwargs.get("severity") == "critical"
        assert call_kwargs.kwargs.get("strict") is True
        assert "TESTSYM" in call_kwargs.kwargs.get("title", "") or "TESTSYM" in str(call_kwargs)

    def test_order_fills_successfully_does_not_send_alert(self):
        """Sanity check: the alert must not fire on the healthy path."""
        handler, handler_context = _make_handler()
        handler_context._wait_for_order_fill.return_value = (True, 100.05, "")

        with patch("algo.trading.executor_entry_handler.notify") as mock_notify:
            result = handler._submit_entry_phase(
                cur=MagicMock(),
                symbol="TESTSYM",
                trade_id="trade-1",
                shares=Decimal("10"),
                entry_price=Decimal("100.00"),
                stop_loss_price=Decimal("95.00"),
                target_1_price=Decimal("110.00"),
                execution_mode="auto",
                idempotency_key="a" * 64,
            )

        order_ok = result[0]
        assert order_ok is True
        mock_notify.assert_not_called()
