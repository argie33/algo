#!/usr/bin/env python3
"""Regression test: resolve_local_pending_exits() must fold in prior partial-exit legs'
P&L, the same way reconcile_exit_fills() and executor_exit_handler.py's
_compute_cumulative_pnl already do (see tests/unit/test_reconcile_exit_fills_multi_leg.py
and tests/unit/test_multi_leg_exit_pnl.py for those fixes).

Bug: resolve_local_pending_exits() is documented as running unconditionally in every
environment (including live trading) as a fallback for whatever reconcile_exit_fills()
couldn't resolve (no broker configured, or a live Alpaca call failed). It computed pnl
as (fill_price - entry_price) * entry_quantity - the ORIGINAL full position size - even
though fill_price only reflects the FINAL leg's price for a position closed via multiple
partial exits (T1/T2 profit-taking before a final stop/target exit). This silently
discarded every dollar realized on the earlier legs, reintroducing the exact bug class
already fixed on the two sibling code paths.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from algo.infrastructure.reconciliation import DailyReconciliation


def _make_recon() -> DailyReconciliation:
    return object.__new__(DailyReconciliation)


class TestResolveLocalPendingExitsMultiLeg:
    def test_no_prior_partial_legs_uses_entry_qty(self):
        """Simple single-leg case: no partial legs recorded, so this must produce the
        same result as before the fix."""
        recon = _make_recon()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (1, "AAPL", 50.0, 45.0, 100, date(2026, 7, 25), 55.0),
        ]
        cur.fetchone.side_effect = [
            (55.0,),  # price_daily close for exit_date
            (Decimal("0"), Decimal("0")),  # no prior partial legs
        ]

        result = recon.resolve_local_pending_exits(cur)

        assert result["resolved"] == 1
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]][0]
        params = update_call.args[1]
        pnl_dollars, pnl_pct, exit_r_multiple = params[1], params[2], params[3]
        assert pnl_dollars == 500.0  # (55-50) * 100
        assert pnl_pct == 10.0
        assert exit_r_multiple == 1.0

    def test_multi_leg_final_close_sums_with_prior_partial_pnl(self):
        """The core bug: 100-share position, T1 already took 40sh profit (+$200,
        recorded in algo_audit_log), final 60sh leg resolves via EOD close at
        breakeven ($50, same as entry). Total realized must be +$200, not $0."""
        recon = _make_recon()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (42, "AAPL", 50.0, 45.0, 100, date(2026, 7, 25), 50.0),
        ]
        cur.fetchone.side_effect = [
            (50.0,),  # price_daily close == entry price (breakeven final leg)
            (Decimal("200.0"), Decimal("40")),  # prior partial leg: +$200 on 40sh
        ]

        result = recon.resolve_local_pending_exits(cur)

        assert result["resolved"] == 1
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]][0]
        params = update_call.args[1]
        pnl_dollars, pnl_pct, exit_r_multiple = params[1], params[2], params[3]
        assert pnl_dollars == 200.0  # not $0 - the pre-fix bug
        assert pnl_pct == 4.0  # 200 / (50*100) * 100
        assert exit_r_multiple == 0.4  # 200 / ((50-45)*100)

    def test_multi_leg_final_leg_loss_still_sums_correctly(self):
        """T1 took +$300 profit, final 60sh leg resolves at a loss via EOD close -
        net must be the correct sum, not just the final leg's own loss."""
        recon = _make_recon()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (7, "AAPL", 50.0, 45.0, 100, date(2026, 7, 25), 48.0),
        ]
        cur.fetchone.side_effect = [
            (48.0,),
            (Decimal("300.0"), Decimal("40")),
        ]

        result = recon.resolve_local_pending_exits(cur)

        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]][0]
        params = update_call.args[1]
        pnl_dollars = params[1]
        # final leg: (48-50)*60 = -120; cumulative = 300 - 120 = 180
        assert pnl_dollars == 180.0
