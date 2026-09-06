"""Regression: a position closed entirely outside the algo (manual close via Alpaca's own
dashboard/API, or any other out-of-band exit) is detected by _sync_alpaca_positions_impl as
"in DB but not at Alpaca" and was previously only alerted on, never cleaned up - any resting
bracket sibling leg (stop-loss/take-profit) for that symbol stayed live at the broker
indefinitely. Fixed 2026-09-06: the sync now also cancels every open order for that symbol
(a pure risk-reduction action) while leaving the deliberate DB alert-only behavior untouched.
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager():
    manager = object.__new__(AlpacaSyncManager)
    manager.config = {"execution_mode": "auto", "api_request_timeout_seconds": 10}
    manager._alpaca_key = "key"
    manager._alpaca_secret = "secret"
    manager._alpaca_base_url = "https://paper-api.alpaca.markets"
    manager.fetch_alpaca_account = MagicMock()
    return manager


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_missing_position_triggers_stale_order_cancel_not_db_close():
    manager = _make_manager()
    # Alpaca reports zero live positions - "MANUALCLOSED" is missing entirely.
    manager._session = MagicMock()
    manager._session.get.return_value = _mock_response([])

    cur = MagicMock()
    # First fetchall(): distinct open DB positions not in Alpaca's symbol set.
    # Second fetchall(): distinct open DB symbols (used to compute orphan_symbols).
    cur.fetchall.side_effect = [
        [("MANUALCLOSED",)],  # missing_positions query
        [],  # db_symbols query (nothing else open)
    ]
    cur.rowcount = 0

    mock_order_mgr = MagicMock()
    mock_order_mgr.cancel_all_open_orders_for_symbol.return_value = {
        "success": True,
        "cancelled_order_ids": ["order-123"],
        "message": "Cancelled 1 stale order(s) for MANUALCLOSED",
    }

    with (
        patch("algo.reporting.notify"),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr) as mock_ctor,
    ):
        result = manager._sync_alpaca_positions_impl(cur)

    # The DB-side decision must remain untouched - still alert-only, never auto-close.
    assert result["closed_count"] == 0
    close_calls = [
        c
        for c in cur.execute.call_args_list
        if "UPDATE algo_positions" in c.args[0] and "status='closed'" in c.args[0].replace(" ", "")
    ]
    assert not close_calls, "missing-at-broker position must not be auto-closed in DB"

    # But the stale resting order for that symbol must have been cancelled at the broker.
    mock_ctor.assert_called_once_with("key", "secret", "https://paper-api.alpaca.markets")
    mock_order_mgr.cancel_all_open_orders_for_symbol.assert_called_once_with("MANUALCLOSED")


def test_no_missing_positions_never_calls_cancel():
    manager = _make_manager()
    manager._session = MagicMock()
    manager._session.get.return_value = _mock_response(
        [{"symbol": "AAPL", "qty": "10", "avg_entry_price": "150.00", "current_price": 155.0}]
    )

    cur = MagicMock()
    cur.fetchone.return_value = (10.0,)
    cur.rowcount = 1
    cur.fetchall.side_effect = [
        [],  # missing_positions query - nothing missing
        [("AAPL",)],  # db_symbols query
    ]

    with (
        patch("algo.reporting.notify"),
        patch("algo.trading.order_manager.OrderManager") as mock_ctor,
    ):
        manager._sync_alpaca_positions_impl(cur)

    mock_ctor.assert_not_called()
