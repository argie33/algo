"""Regression test for a real TOCTOU race found in the order-execution audit (2026-09-05):
check_and_repair_one_position's `quantity`/`current_stop_price` parameters come from a batch
SELECT the caller (phase9_reconciliation.py) ran at the START of the whole reconciliation
cycle. By the time a given position reaches the repair branch, several live Alpaca round-trips
(is_order_still_live, check_stop_loss_leg_live - each with its own retry/backoff) have already
happened. If a concurrent execute_exit fully closes the position in that window, submitting a
standalone GTC sell-stop off the stale batch-read quantity would leave a naked resting sell
order on a symbol the account no longer holds - able to fire later against a completely
unrelated future position in the same symbol.

Fixed by re-reading algo_positions.status/quantity/current_stop_price immediately before
submitting the repair, and skipping (not submitting) if the position is no longer open.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_stop_loss_repair import check_and_repair_one_position


def _order_mgr():
    mgr = MagicMock()
    mgr.is_order_still_live.return_value = None
    mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "No live stop-loss leg",
    }
    return mgr


def _patch_db(fresh_row):
    contexts = [MagicMock(), MagicMock()]
    contexts[0].__enter__.return_value.fetchone.return_value = ("order-abc",)
    contexts[0].__exit__.return_value = False
    contexts[1].__enter__.return_value.fetchone.return_value = fresh_row
    contexts[1].__exit__.return_value = False
    return patch(
        "algo.orchestrator.phase9_stop_loss_repair.DatabaseContext",
        side_effect=list(contexts),
    )


def test_position_closed_since_batch_read_is_skipped_not_repaired():
    """The position was fully exited by a concurrent process between this cycle's batch
    SELECT and this repair attempt - must not submit a naked sell-stop for a symbol the
    account no longer holds."""
    order_mgr = _order_mgr()

    with _patch_db(("closed", 25.0, 210.50)):
        outcome = check_and_repair_one_position(
            order_mgr,
            pos_id=1,
            symbol="TSLA",
            trade_ids_arr=["trade-1"],
            quantity=25.0,  # stale batch-read value - position has since closed
            current_stop_price=210.50,
            standalone_stop_order_id=None,
        )

    assert outcome == "skipped"
    order_mgr.submit_standalone_protective_stop.assert_not_called()


def test_position_emptied_since_batch_read_is_skipped_not_repaired():
    """Quantity dropped to zero (fully exited) but status hasn't flipped yet - same
    naked-order risk, must still refuse to submit."""
    order_mgr = _order_mgr()

    with _patch_db(("open", 0, 210.50)):
        outcome = check_and_repair_one_position(
            order_mgr,
            pos_id=1,
            symbol="TSLA",
            trade_ids_arr=["trade-1"],
            quantity=25.0,
            current_stop_price=210.50,
            standalone_stop_order_id=None,
        )

    assert outcome == "skipped"
    order_mgr.submit_standalone_protective_stop.assert_not_called()


def test_quantity_changed_since_batch_read_uses_fresh_value_for_repair():
    """A partial exit shrank the position between the batch read and this repair attempt -
    the repair stop must be sized off the FRESH quantity, not the stale batch-read one."""
    order_mgr = _order_mgr()
    order_mgr.submit_standalone_protective_stop.return_value = {
        "success": True,
        "order_id": "new-stop-1",
        "message": "ok",
    }
    order_mgr.cancel_bracket_orders.return_value = {"success": True}

    contexts = [MagicMock(), MagicMock(), MagicMock()]
    contexts[0].__enter__.return_value.fetchone.return_value = ("order-abc",)
    contexts[0].__exit__.return_value = False
    contexts[1].__enter__.return_value.fetchone.return_value = ("open", 10.0, 210.50)
    contexts[1].__exit__.return_value = False
    contexts[2].__enter__.return_value = MagicMock()
    contexts[2].__exit__.return_value = False

    with patch(
        "algo.orchestrator.phase9_stop_loss_repair.DatabaseContext",
        side_effect=list(contexts),
    ):
        outcome = check_and_repair_one_position(
            order_mgr,
            pos_id=1,
            symbol="TSLA",
            trade_ids_arr=["trade-1"],
            quantity=25.0,  # stale batch-read value
            current_stop_price=210.50,
            standalone_stop_order_id=None,
        )

    assert outcome == "repaired"
    order_mgr.submit_standalone_protective_stop.assert_called_once_with(
        "TSLA",
        10.0,
        210.50,
        client_order_id=order_mgr.submit_standalone_protective_stop.call_args.kwargs["client_order_id"],
        pos_id=1,
    )
