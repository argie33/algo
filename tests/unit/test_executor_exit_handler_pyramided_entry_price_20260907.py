#!/usr/bin/env python3
"""Regression test: _fetch_and_lock_trade_data() must resolve entry_price from the
POSITION's blended avg_entry_price, not the individual trade leg's own entry_price.

Bug (2026-09-07 real-money-readiness audit): every exit call site resolves
trade_id = trade_ids_arr[0] - always the first/original leg of a position, never the
blended position. The exit query then joined t.entry_price (that first leg's own fill
price) with p.quantity (the position's TOTAL remaining quantity across ALL legs,
including later pyramid adds at different prices). A full exit therefore priced every
share - pyramid adds included - at the first leg's entry price.

Concrete example this test pins: leg1 buys 100sh@$10, leg2 (pyramid add) buys 50sh@$15.
algo_positions.avg_entry_price correctly blends to $11.67 on the add
(executor_entry_handler.py), but the exit path previously used entry_price=$10 (from
algo_trades, leg1 only) for the full 150sh exit - overstating realized P&L by $250 (20%)
on a true gain of $1250 at a $20 exit. The fix selects
COALESCE(p.avg_entry_price, t.entry_price) so the position's blended cost basis - not a
single leg's - feeds the P&L/R-multiple math that follows in _execute_exit().
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_handler import ExitHandler


class TestPyramidedEntryPriceUsesBlendedAverage:
    def test_query_selects_coalesced_position_avg_entry_price(self):
        """The SQL itself must prefer the position's blended avg_entry_price over the
        single leg's own entry_price - the coalescing has to happen in Postgres since a
        pyramided position's true blended price only lives on algo_positions."""
        handler = ExitHandler(MagicMock())
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("GEN", 11.67, 100.0, 9.0, None, "pos-uuid", 150.0, 0, "open"),
        ]

        handler._fetch_and_lock_trade_data(cur, "TRD-LEG1")

        executed_sql = cur.execute.call_args[0][0]
        assert "COALESCE(p.avg_entry_price, t.entry_price)" in executed_sql

    def test_blended_price_and_full_quantity_flow_through_together(self):
        """Once the DB has done the coalescing, the row returned to the caller must pair
        the blended price with the position's full (all-legs) quantity - both halves of
        the pnl_dollars = (exit - entry) * shares_to_exit calculation downstream."""
        handler = ExitHandler(MagicMock())
        cur = MagicMock()
        # Simulates what Postgres would return with the fixed query: entry_price is
        # already the blended $11.67 (not leg1's raw $10), quantity is all 150 shares.
        cur.fetchall.return_value = [
            ("GEN", 11.67, 100.0, 9.0, None, "pos-uuid", 150.0, 0, "open"),
        ]

        result = handler._fetch_and_lock_trade_data(cur, "TRD-LEG1")

        entry_price, quantity = result[1], result[6]
        assert entry_price == 11.67
        assert quantity == 150.0
        # The old bug's math: (20 - 10) * 150 = 1500 (wrong, overstated by $250).
        # The fixed math: (20 - 11.67) * 150 = 1249.5 (~= true blended-cost result of $1250).
        pnl_dollars = (20.0 - entry_price) * quantity
        assert pnl_dollars < 1500.0
        assert abs(pnl_dollars - 1250.0) < 1.0
