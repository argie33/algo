#!/usr/bin/env python3
"""Regression test: reconcile_exit_fills() must fold in prior partial-exit legs' P&L,
the same way executor_exit_handler.py's _compute_cumulative_pnl already does for the
synchronous exit path (see tests/unit/test_multi_leg_exit_pnl.py for that fix).

Bug: when a multi-leg exit's final leg fill price isn't known synchronously (order
returns filled_avg_price=None), executor_exit_handler.py correctly leaves
profit_loss_dollars=NULL for later reconciliation. But reconcile_exit_fills() - the
function that later resolves that NULL into a real value from the broker's fill data -
computed pnl using entry_qty (the ORIGINAL full position size) instead of this order's
actual filled_qty, and never queried algo_audit_log for prior partial legs' P&L at all.
For a position that took partial profit before its final leg reconciled this way, this
silently discarded every dollar realized on the earlier legs - reintroducing the exact
bug class the 2026-07-21 financial-integrity audit already fixed for the synchronous path.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from algo.infrastructure.reconciliation import DailyReconciliation


def _make_recon(orders) -> DailyReconciliation:
    recon = object.__new__(DailyReconciliation)
    recon.broker = MagicMock()
    recon.broker.fetch_closed_orders.return_value = orders
    return recon


def _sell_order(symbol="AAPL", filled_qty="60", filled_avg_price="55.00", order_id="order-1"):
    return {
        "id": order_id,
        "symbol": symbol,
        "side": "sell",
        "status": "filled",
        "filled_qty": filled_qty,
        "filled_avg_price": filled_avg_price,
    }


class TestReconcileExitFillsMultiLeg:
    def test_no_prior_partial_legs_uses_filled_qty_not_entry_qty(self):
        """Simple single-leg case: entry_qty and filled_qty are the same for a true
        one-shot full exit, so this must produce the same result as before."""
        recon = _make_recon([_sell_order(filled_qty="100", filled_avg_price="55.00")])
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (1, 50.0, 45.0, 100),  # trade_id, entry_price, stop_loss_price, entry_quantity
            (Decimal("0"),),  # prior partial pnl sum - no prior legs
            None,  # estimated_exit_price lookup - none set
        ]

        result = recon.reconcile_exit_fills(cur, reconcile_date=None)

        assert result["updated"] == 1
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]][0]
        params = update_call.args[1]
        filled_price, pnl_pct, pnl_dollars, exit_r_multiple = params[0], params[1], params[2], params[3]
        assert filled_price == 55.0
        assert pnl_dollars == 500.0  # (55-50) * 100
        assert pnl_pct == 10.0  # (55-50)/50 * 100
        assert exit_r_multiple == 1.0  # (55-50) / (50-45)

    def test_multi_leg_final_fill_sums_with_prior_partial_pnl(self):
        """The core bug: 100-share position, T1 already took 40sh profit (+$200,
        recorded in algo_audit_log), final leg's order actually only sold the
        remaining 60sh at breakeven ($0 this leg, since fill price == entry price).
        Total realized must be +$200, not $0, and must NOT use entry_qty=100 for the
        final leg's own dollar contribution (that would fabricate $0 * ... = wrong
        numbers even before adding prior legs)."""
        recon = _make_recon([_sell_order(filled_qty="60", filled_avg_price="50.00")])
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (42, 50.0, 45.0, 100),  # entry_price=50, entry_qty=100 (ORIGINAL, not 60)
            (Decimal("200.0"),),  # prior partial leg already realized +$200
            None,  # estimated_exit_price lookup
        ]

        result = recon.reconcile_exit_fills(cur, reconcile_date=None)

        assert result["updated"] == 1
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]][0]
        params = update_call.args[1]
        _filled_price, pnl_pct, pnl_dollars, exit_r_multiple = params[0], params[1], params[2], params[3]
        assert pnl_dollars == 200.0  # not $0 - the pre-fix bug
        # pct/r_multiple against the ORIGINAL 100-share cost basis/risk
        assert pnl_pct == 4.0  # 200 / (50*100) * 100
        assert exit_r_multiple == 0.4  # 200 / ((50-45)*100)

    def test_multi_leg_final_leg_loss_still_sums_correctly(self):
        """T1 took +$300 profit, final 60sh leg exits at a loss - net must be the
        correct sum, not just the final leg's own loss."""
        recon = _make_recon([_sell_order(filled_qty="60", filled_avg_price="48.00")])
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (7, 50.0, 45.0, 100),
            (Decimal("300.0"),),
            None,  # estimated_exit_price lookup
        ]

        result = recon.reconcile_exit_fills(cur, reconcile_date=None)

        assert result["updated"] == 1
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]][0]
        params = update_call.args[1]
        pnl_dollars = params[2]
        # final leg: (48-50)*60 = -120; cumulative = 300 - 120 = 180
        assert pnl_dollars == 180.0
