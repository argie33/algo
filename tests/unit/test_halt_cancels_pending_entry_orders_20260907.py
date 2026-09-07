"""Verifies set_halt_flag() cancels resting, not-yet-filled ENTRY orders at the broker as
soon as a halt is set, and never touches filled positions' bracket legs.

REAL-MONEY-READINESS FIX (2026-09-07 audit): before this fix, a halt only ever blocked
FUTURE order submission - an entry already sent to Alpaca before the halt fired stayed
resting at the broker and could still fill, silently adding the exposure the halt was
meant to prevent. A repo-wide grep for cancel_order/cancel_all_orders found no automatic
caller at all, only scripts/flatten_all_positions.py's manual operator path. This locks in
that set_halt_flag() now drives the same OrderManager.cancel_all_open_orders_for_symbol
primitive automatically, for PENDING/OPEN (unfilled) trades only.
"""

from unittest.mock import MagicMock, patch

from algo.orchestration.halt_flag_manager import HaltFlagManager


def _manager() -> HaltFlagManager:
    return HaltFlagManager(alerts=MagicMock(), log_phase_result=MagicMock())


def test_set_halt_flag_cancels_pending_entry_orders_via_dynamodb_path():
    manager = _manager()
    with (
        patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": "test"}, clear=False),
        patch("boto3.resource") as mock_boto,
        patch.object(manager, "_cancel_pending_entry_orders_on_halt") as mock_cancel,
    ):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"halt_count": 1, "triggered_at": None}}
        mock_boto.return_value.Table.return_value = mock_table

        result = manager.set_halt_flag("data stale", triggered_by="phase1_data_freshness")

        assert result is True
        mock_cancel.assert_called_once_with("data stale", "phase1_data_freshness")


def test_set_halt_flag_cancels_pending_entry_orders_via_rds_fallback_path():
    manager = _manager()
    with (
        patch.dict("os.environ", {}, clear=True),  # no AWS creds -> forces RDS fallback
        patch.object(manager, "_set_halt_flag_rds", return_value=True) as mock_rds,
        patch.object(manager, "_cancel_pending_entry_orders_on_halt") as mock_cancel,
    ):
        result = manager.set_halt_flag("manual halt", triggered_by="manual_operator", force=True)

        assert result is True
        assert mock_rds.called
        mock_cancel.assert_called_once_with("manual halt", "manual_operator")


def test_cancel_pending_entry_orders_only_touches_unfilled_trades_not_filled_positions():
    """The helper must query only PENDING/OPEN trades - never cancel a filled position's
    resting stop-loss/take-profit bracket legs, which are the position's own protection."""
    manager = _manager()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [("AAPL",), ("MSFT",)]
    mock_db_context = MagicMock()
    mock_db_context.__enter__.return_value = mock_cursor

    mock_order_mgr = MagicMock()
    mock_order_mgr.cancel_all_open_orders_for_symbol.return_value = {
        "success": True,
        "cancelled_order_ids": ["o1"],
        "message": "ok",
    }

    with (
        patch("algo.config.credential_manager.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
        patch("algo.config.api_endpoints.get_alpaca_base_url", return_value="https://paper-api.alpaca.markets"),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("utils.db.DatabaseContext", return_value=mock_db_context),
    ):
        manager._cancel_pending_entry_orders_on_halt("reason", "phase2_circuit_breaker")

    assert mock_order_mgr.cancel_all_open_orders_for_symbol.call_count == 2
    called_symbols = {c.args[0] for c in mock_order_mgr.cancel_all_open_orders_for_symbol.call_args_list}
    assert called_symbols == {"AAPL", "MSFT"}

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "algo_trades" in executed_sql
    assert "status IN" in executed_sql


def test_cancel_pending_entry_orders_is_best_effort_never_raises():
    """A failure inside the cancel helper must never propagate - the halt flag write
    already succeeded by the time this runs and must not be undone by this side effect."""
    manager = _manager()
    with patch("algo.config.credential_manager.get_alpaca_credentials", side_effect=RuntimeError("boom")):
        manager._cancel_pending_entry_orders_on_halt("reason", "phase2_circuit_breaker")  # must not raise
