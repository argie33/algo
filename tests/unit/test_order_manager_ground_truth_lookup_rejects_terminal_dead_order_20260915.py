"""Regression test: the ground-truth client_order_id lookup must never report a
terminal-dead order (rejected/canceled/expired) as a successful entry/exit.

BUG FOUND 2026-09-15 (real-money-readiness audit, closing the gap flagged in
realmoney_readiness_20260910_adversarial_second_pass: "a genuinely-rejected order
permanently blocks any same-day retry of that exact signal - the ground-truth
duplicate-recovery lookup reports the old rejected order as success rather than
minting a fresh id"). executor_entry_handler.py's idempotency_key (and
send_market_exit's client_order_id) is deterministic per symbol/price/date - once
Alpaca genuinely rejects an order under that id, _lookup_order_by_client_order_id
finds that SAME dead order on every same-day retry. _entry_result_from_order_data
used to return success=True for any schema-valid order object regardless of status,
disguising the dead order as a live one until a later fill-timeout finally surfaced
the failure - misleadingly, as a timeout rather than the real cause. Fixed:
_entry_result_from_order_data now reports failure immediately when the found order's
status is terminal-dead, with a clear message naming the real cause.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


class TestTerminalDeadOrderNeverReportedAsSuccess:
    def test_rejected_order_found_via_ground_truth_reports_failure(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="client order id must be unique")
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {
            "id": "dead-order-1",
            "status": "rejected",
            "order_class": "bracket",
            "legs": [
                {"id": "leg-stop", "type": "stop", "status": "canceled"},
                {"id": "leg-tp", "type": "limit", "status": "canceled"},
            ],
        }

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0, client_order_id="idem-key-dead")

        assert result["success"] is False
        assert result.get("terminal_dead_order") is True

    def test_canceled_order_found_via_ground_truth_reports_failure(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="client order id must be unique")
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {
            "id": "dead-order-2",
            "status": "canceled",
            "filled_avg_price": None,
        }

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_market_exit("AAPL", 5, "auto", client_order_id="exit-dead")

        assert result["success"] is False

    def test_expired_order_found_via_ground_truth_reports_failure(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="client order id must be unique")
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {
            "id": "dead-order-3",
            "status": "expired",
            "order_class": "bracket",
            "legs": [
                {"id": "leg-stop", "type": "stop", "status": "canceled"},
                {"id": "leg-tp", "type": "limit", "status": "canceled"},
            ],
        }

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_bracket_order(
                "MSFT", 10, 50.0, stop_loss_price=48.0, client_order_id="idem-key-expired"
            )

        assert result["success"] is False

    def test_live_filled_order_via_ground_truth_still_reports_success(self):
        """Non-regression: the original recovery behavior for a genuinely-live order
        (the whole point of the ground-truth check) must keep working."""
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="client order id must be unique")
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {
            "id": "live-order-1",
            "status": "filled",
            "order_class": "bracket",
            "filled_avg_price": "50.25",
            "legs": [
                {"id": "leg-stop", "type": "stop", "status": "held"},
                {"id": "leg-tp", "type": "limit", "status": "held"},
            ],
        }

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0, client_order_id="idem-key-live")

        assert result["success"] is True
        assert result["order_id"] == "live-order-1"

    def test_pending_new_order_via_ground_truth_still_reports_success(self):
        """Non-regression: an order still in-flight (not yet filled, not dead) must
        still be treated as a live success - only the terminal-dead statuses flip."""
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="client order id must be unique")
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {
            "id": "pending-order-1",
            "status": "pending_new",
            "order_class": "bracket",
            "legs": [
                {"id": "leg-stop", "type": "stop", "status": "held"},
                {"id": "leg-tp", "type": "limit", "status": "held"},
            ],
        }

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_bracket_order(
                "MSFT", 10, 50.0, stop_loss_price=48.0, client_order_id="idem-key-pending"
            )

        assert result["success"] is True
