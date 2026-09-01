"""Regression test: OrderManager.cancel_bracket_orders must surface a real fill that raced
past the cancel request, not silently discard it.

BUG FOUND 2026-09-01 (real-money-readiness sweep, order-retry fringe-case review): a 200/204
DELETE response only means the cancel REQUEST was accepted - it does not guarantee zero shares
filled. Alpaca cancels only the still-open remainder of a partially-filled order and still
returns 200/204; the already-filled portion is real and stays filled. Likewise, a 422 response
means the order was ALREADY in a terminal state (e.g. fully filled) by the time the cancel
reached the broker - the exact signature of a fill winning the race. The previous version
returned a bare {"success": bool, "message": str} with no fill information in either case, so
every caller silently lost real fills. Fixed: check the order's real final state via the
existing get_order() after any cancel outcome and report filled_qty/filled_avg_price.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


class TestCancelBracketFillRace:
    def test_204_cancel_with_partial_fill_reports_filled_qty(self):
        """DELETE returns 204 (cancel accepted) but the order had already partially filled -
        must report the real filled_qty/filled_avg_price, not a bare success."""
        manager = _make_manager()
        cancelled = MagicMock(status_code=204)
        order_after_cancel = MagicMock(status_code=200)
        order_after_cancel.json.return_value = {
            "status": "canceled",
            "filled_qty": "4",
            "filled_avg_price": "99.80",
        }

        with (
            patch("algo.trading.order_manager.requests.delete", return_value=cancelled),
            patch("algo.trading.order_manager.requests.get", return_value=order_after_cancel),
        ):
            result = manager.cancel_bracket_orders("order-race-204")

        assert result["success"] is True
        assert result["filled_qty"] == 4.0
        assert result["filled_avg_price"] == 99.80

    def test_204_cancel_with_zero_fill_reports_none(self):
        """The common case: cancel succeeds, nothing had filled - filled_qty must be None,
        not 0.0 (None means 'no fill', distinct from a genuine zero that would still be
        falsy but semantically different)."""
        manager = _make_manager()
        cancelled = MagicMock(status_code=204)
        order_after_cancel = MagicMock(status_code=200)
        order_after_cancel.json.return_value = {
            "status": "canceled",
            "filled_qty": "0",
            "filled_avg_price": None,
        }

        with (
            patch("algo.trading.order_manager.requests.delete", return_value=cancelled),
            patch("algo.trading.order_manager.requests.get", return_value=order_after_cancel),
        ):
            result = manager.cancel_bracket_orders("order-race-zero")

        assert result["success"] is True
        assert result["filled_qty"] is None
        assert result["filled_avg_price"] is None

    def test_422_already_terminal_with_full_fill_reports_filled_not_bare_failure(self):
        """DELETE returns 422 (order already terminal, i.e. fully filled before the cancel
        reached the broker) - must report the fill, not just 'cancel failed'."""
        manager = _make_manager()
        already_terminal = MagicMock(status_code=422, text="order already filled")
        order_after_cancel = MagicMock(status_code=200)
        order_after_cancel.json.return_value = {
            "status": "filled",
            "filled_qty": "10",
            "filled_avg_price": "101.25",
        }

        with (
            patch("algo.trading.order_manager.requests.delete", return_value=already_terminal),
            patch("algo.trading.order_manager.requests.get", return_value=order_after_cancel),
        ):
            result = manager.cancel_bracket_orders("order-race-422")

        assert result["success"] is False
        assert result["filled_qty"] == 10.0
        assert result["filled_avg_price"] == 101.25
        assert "filled" in result["message"].lower()

    def test_422_already_terminal_with_zero_fill_stays_a_bare_failure(self):
        """422 for a genuinely non-fill terminal reason (e.g. rejected) must NOT be
        misreported as a fill - filled_qty stays None."""
        manager = _make_manager()
        already_terminal = MagicMock(status_code=422, text="order rejected")
        order_after_cancel = MagicMock(status_code=200)
        order_after_cancel.json.return_value = {
            "status": "rejected",
            "filled_qty": "0",
            "filled_avg_price": None,
        }

        with (
            patch("algo.trading.order_manager.requests.delete", return_value=already_terminal),
            patch("algo.trading.order_manager.requests.get", return_value=order_after_cancel),
        ):
            try:
                manager.cancel_bracket_orders("order-race-422-nofill")
                raise AssertionError("expected RuntimeError - 422 with zero fill is a bare cancel failure")
            except RuntimeError as e:
                assert "422" in str(e) or "Failed to cancel" in str(e)

    def test_post_cancel_fill_check_failure_does_not_mask_cancel_success(self):
        """If the post-cancel get_order() check itself fails (network blip), the cancel's
        own success must still be reported - this is a best-effort enrichment, not a
        blocking requirement. Phase 9's AlpacaSyncManager remains the backstop."""
        manager = _make_manager()
        cancelled = MagicMock(status_code=204)

        with (
            patch("algo.trading.order_manager.requests.delete", return_value=cancelled),
            patch("algo.trading.order_manager.requests.get", side_effect=RuntimeError("network blip")),
        ):
            result = manager.cancel_bracket_orders("order-race-checkfail")

        assert result["success"] is True
        assert result["filled_qty"] is None
