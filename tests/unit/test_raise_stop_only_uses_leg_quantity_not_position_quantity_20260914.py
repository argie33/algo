#!/usr/bin/env python3
"""Regression test: _raise_stop_only must sync the broker using the CHECKED LEG's own
quantity, not the position-wide total across every leg of a pyramided position.

BUG FOUND (real-money-readiness audit): the SELECT backing _raise_stop_only fetched
p.quantity (algo_positions.quantity, the SUM across every leg) and passed it as `new_qty`
to sync_bracket_stop_loss/sync_standalone_stop - both of which resize/replace the ONE
resting order belonging to `trade_id`'s own leg. For a pyramided (2+ leg) position
(max_reentries_per_name=2 by default, a live, reachable config), this resized leg[0]'s own
stop-loss/take-profit to cover the WHOLE position's shares while leg[2]'s own separate stop
order stays resting for its own shares - leaving MORE resting protective sell quantity at
the broker than the account actually holds. Same failure mode already fixed in
phase9_stop_loss_repair.py for the auto-repair path; this is the identical bug on the
trailing-stop-raise path, previously missed.

Fixed by selecting t.quantity (this leg's own share count) instead of p.quantity.
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_handler import ExitHandler


def _make_context(sync_result=None, standalone_sync_result=None):
    context = MagicMock()
    context._sync_bracket_stop_loss = MagicMock(
        return_value=sync_result or {"success": True, "synced": True, "message": "ok"}
    )
    context._sync_standalone_stop = MagicMock(
        return_value=standalone_sync_result or {"success": True, "synced": True, "message": "ok"}
    )
    return context


def _make_cursor(leg_quantity, alpaca_order_id="alpaca-abc-123", standalone_stop_order_id=None, rowcount=1):
    """leg_quantity is what the (fixed) query now returns for t.quantity - deliberately
    DIFFERENT from a hypothetical much-larger position-wide total, to prove the resize call
    uses the leg's own number, not the position's."""
    cur = MagicMock()
    cur.fetchone.return_value = (100.0, alpaca_order_id, leg_quantity, standalone_stop_order_id, "pos-1")
    cur.rowcount = rowcount
    return cur


class TestRaiseStopOnlyUsesLegQuantity:
    def test_bracket_sync_uses_the_smaller_leg_quantity_not_a_larger_position_total(self):
        """leg[0] holds 25 shares of its own even though (in a pyramided position) the
        position total could be much larger (e.g. 75 across 3 legs) - the resize call must
        use 25, never the bigger number."""
        context = _make_context()
        cur = _make_cursor(leg_quantity=25.0)
        handler = ExitHandler(context)

        result = handler.execute_exit(
            trade_id=42,
            exit_price=None,
            exit_reason="trailing stop tighten",
            exit_fraction=0,
            exit_stage="trail",
            new_stop_price=105.0,
            cur=cur,
        )

        context._sync_bracket_stop_loss.assert_called_once_with("alpaca-abc-123", 105.0, 25.0)
        assert result["success"] is True

    def test_standalone_sync_uses_the_leg_quantity_too(self):
        context = _make_context()
        cur = _make_cursor(leg_quantity=10.0, standalone_stop_order_id="standalone-order-1")
        handler = ExitHandler(context)

        handler.execute_exit(
            trade_id=42,
            exit_price=None,
            exit_reason="trailing stop tighten",
            exit_fraction=0,
            exit_stage="trail",
            new_stop_price=105.0,
            cur=cur,
        )

        context._sync_standalone_stop.assert_called_once_with("standalone-order-1", 105.0, 10.0)
        context._sync_bracket_stop_loss.assert_not_called()

    def test_query_selects_t_quantity_not_p_quantity(self):
        """Static guard against regressing back to the position-wide column: the SELECT
        must read the trade's own quantity, not algo_positions.quantity."""
        import inspect

        source = inspect.getsource(ExitHandler._raise_stop_only)
        assert "SELECT p.current_stop_price, t.alpaca_order_id, t.quantity," in source, (
            "must select the leg's own quantity from algo_trades, not the position-wide "
            "total - resizing one leg's resting order to the position total leaves every "
            "other leg's own order still resting for its own shares too"
        )
