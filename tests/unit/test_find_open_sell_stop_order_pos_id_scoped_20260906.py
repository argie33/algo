"""Regression test (2026-09-06, real-money-readiness audit): _find_open_sell_stop_order
used to match the FIRST open sell-stop order for a symbol, full stop - a broker-level
/v2/orders query has no concept of this codebase's own position_id, so a leftover resting
stop from a DIFFERENT, unrelated position in the same symbol (e.g. an earlier position that
closed without its stop being cancelled) could be misidentified as "this position is
already protected," reusing that unrelated order's id/qty/stop_price instead of actually
repairing the position that has none.

phase9_stop_loss_repair.py's own repair client_order_id is always
f"stoprepair-{pos_id}-{uuid}" - when pos_id is passed, only an order whose client_order_id
carries that exact prefix should count as "already resting for this position."
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _make_manager() -> OrderManager:
    return OrderManager(alpaca_key="key", alpaca_secret="secret", alpaca_base_url="https://api.example.com")


def _orders_response(orders):
    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = orders
    return resp


class TestFindOpenSellStopOrderPosIdScoping:
    def test_pos_id_given_matches_only_own_repair_order(self):
        manager = _make_manager()
        orders = [
            {"id": "unrelated-1", "side": "sell", "type": "stop", "client_order_id": "stoprepair-999-aaaa"},
            {"id": "mine-1", "side": "sell", "type": "stop", "client_order_id": "stoprepair-42-bbbb"},
        ]
        with patch("algo.trading.order_manager_stop_repair.requests.get", return_value=_orders_response(orders)):
            found = manager._find_open_sell_stop_order("AAPL", pos_id=42)
        assert found is not None
        assert found["id"] == "mine-1"

    def test_pos_id_given_no_matching_prefix_returns_none_not_unrelated_order(self):
        """The bug this closes: an unrelated position's leftover stop must NEVER be reused
        just because it's the only resting sell-stop for the symbol."""
        manager = _make_manager()
        orders = [
            {"id": "unrelated-1", "side": "sell", "type": "stop", "client_order_id": "stoprepair-999-aaaa"},
        ]
        with patch("algo.trading.order_manager_stop_repair.requests.get", return_value=_orders_response(orders)):
            found = manager._find_open_sell_stop_order("AAPL", pos_id=42)
        assert found is None

    def test_pos_id_given_order_with_no_client_order_id_is_not_matched(self):
        manager = _make_manager()
        orders = [{"id": "bracket-leg-1", "side": "sell", "type": "stop"}]  # no client_order_id at all
        with patch("algo.trading.order_manager_stop_repair.requests.get", return_value=_orders_response(orders)):
            found = manager._find_open_sell_stop_order("AAPL", pos_id=42)
        assert found is None

    def test_no_pos_id_falls_back_to_symbol_only_match(self):
        """Backward-compatible default for any caller that doesn't track pos_id."""
        manager = _make_manager()
        orders = [{"id": "any-order-1", "side": "sell", "type": "stop"}]
        with patch("algo.trading.order_manager_stop_repair.requests.get", return_value=_orders_response(orders)):
            found = manager._find_open_sell_stop_order("AAPL")
        assert found is not None
        assert found["id"] == "any-order-1"
