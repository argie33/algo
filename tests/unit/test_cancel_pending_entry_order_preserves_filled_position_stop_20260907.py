"""Verifies OrderManager.cancel_pending_entry_order cancels only the specific still-open
entry order matching a client_order_id, and never a different order resting for the same
symbol - the pyramiding gap found in the 2026-09-07 real-money-readiness audit of
halt_flag_manager.py's original cancel_all_open_orders_for_symbol-based fix.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _manager() -> OrderManager:
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


def test_cancels_only_the_order_matching_client_order_id_not_a_filled_positions_stop():
    """Two open orders rest for the same symbol: the still-unfilled pyramid entry (matches
    client_order_id) and an unrelated filled position's resting protective stop (does not).
    Only the matching order may be cancelled."""
    mgr = _manager()
    open_orders = [
        {"id": "entry-order-1", "client_order_id": "pyramid-entry-key"},
        {"id": "old-stop-order-2", "client_order_id": "server-generated-leg-id"},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = open_orders
    mock_resp.raise_for_status.return_value = None

    with (
        patch("algo.trading.order_manager_stop_repair.requests.get", return_value=mock_resp),
        patch.object(mgr, "cancel_bracket_orders", return_value={"success": True}) as mock_cancel,
    ):
        result = mgr.cancel_pending_entry_order("AAPL", "pyramid-entry-key")

    assert result["success"] is True
    assert result["cancelled_order_ids"] == ["entry-order-1"]
    mock_cancel.assert_called_once_with("entry-order-1")


def test_no_matching_order_is_treated_as_success_not_failure():
    """The entry may have already filled or been cancelled by another path by the time this
    runs - nothing to cancel is not an error."""
    mgr = _manager()
    open_orders = [{"id": "old-stop-order-2", "client_order_id": "server-generated-leg-id"}]
    mock_resp = MagicMock()
    mock_resp.json.return_value = open_orders
    mock_resp.raise_for_status.return_value = None

    with patch("algo.trading.order_manager_stop_repair.requests.get", return_value=mock_resp):
        result = mgr.cancel_pending_entry_order("AAPL", "pyramid-entry-key")

    assert result["success"] is True
    assert result["cancelled_order_ids"] == []


def test_missing_client_order_id_fails_closed():
    mgr = _manager()
    result = mgr.cancel_pending_entry_order("AAPL", "")
    assert result["success"] is False
