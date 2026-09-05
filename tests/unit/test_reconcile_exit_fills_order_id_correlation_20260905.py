#!/usr/bin/env python3
"""Regression test for a 2026-09-05 financial-integrity finding: reconcile_exit_fills()
matched a broker fill to "the most recently closed trade for this symbol within 2 days" -
wrong whenever the same symbol closes twice in that window (routine for this swing-trading
system), silently overwriting an unrelated, already-correct trade's exit_price/
profit_loss_dollars with a different trade's fill data.

Concrete failure scenario this replaces: symbol XYZ closes as Trade A (already correctly
reconciled) and is re-entered and closed again as Trade B within the same 2-day window. A
late broker fill notification for either trade used to match "most recent closed XYZ"
regardless of which trade the fill actually belonged to.

Fix: every exit this system submits carries a client_order_id persisted in
algo_trades.pending_exit_client_order_id BEFORE the order reaches Alpaca (executor.py's
_send_alpaca_exit), cleared only once that exact exit is confirmed. Matching on it is
exact, not a date-proximity guess. A fill with no client_order_id, or one that doesn't
match any trade still awaiting reconciliation, is skipped rather than guessed at.
"""

from unittest.mock import MagicMock

from algo.infrastructure.reconciliation import DailyReconciliation


def _make_recon(orders) -> DailyReconciliation:
    recon = object.__new__(DailyReconciliation)
    recon.broker = MagicMock()
    recon.broker.fetch_closed_orders.return_value = orders
    return recon


def _sell_order(symbol="AAPL", filled_qty="100", filled_avg_price="55.00", client_order_id="exit-1-abc"):
    order = {
        "id": "order-1",
        "symbol": symbol,
        "side": "sell",
        "status": "filled",
        "filled_qty": filled_qty,
        "filled_avg_price": filled_avg_price,
    }
    if client_order_id is not None:
        order["client_order_id"] = client_order_id
    return order


class TestOrderIdCorrelation:
    def test_matches_by_pending_exit_client_order_id_not_date_proximity(self):
        recon = _make_recon([_sell_order(client_order_id="exit-42-abc123")])
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (42, 50.0, 45.0, 100),
            (0,),
            None,
        ]

        result = recon.reconcile_exit_fills(cur, reconcile_date=None)

        assert result["updated"] == 1
        trade_lookup_call = [c for c in cur.execute.call_args_list if "pending_exit_client_order_id" in c.args[0]][0]
        query, params = trade_lookup_call.args
        assert "exit_date" not in query, "must no longer rely on date-proximity matching"
        assert params == ("exit-42-abc123", "AAPL")

    def test_order_with_no_client_order_id_is_skipped_not_guessed(self):
        """A fill with no client_order_id can't be safely correlated - must be skipped,
        never matched via a symbol/date fallback guess."""
        recon = _make_recon([_sell_order(client_order_id=None)])
        cur = MagicMock()

        result = recon.reconcile_exit_fills(cur, reconcile_date=None)

        assert result["updated"] == 0
        cur.execute.assert_not_called()

    def test_no_matching_trade_skips_gracefully_instead_of_raising(self):
        """Old behavior treated 'no match' as a CRITICAL error (raised, caught, logged) -
        under order-id matching this is the ordinary case for a fill that isn't one of our
        trades still awaiting reconciliation (already reconciled, or a foreign order), so
        it must skip cleanly rather than raising."""
        recon = _make_recon([_sell_order(client_order_id="exit-99-notfound")])
        cur = MagicMock()
        cur.fetchone.side_effect = [None]

        result = recon.reconcile_exit_fills(cur, reconcile_date=None)

        assert result["updated"] == 0

    def test_two_trades_same_symbol_in_window_each_matched_independently(self):
        """The core bug scenario: two different orders for the same symbol, each with its
        own client_order_id. Each must independently look up its own trade via its own id -
        this test asserts both queries carry their own distinct client_order_id, which is
        exactly what prevents the second fill from ever being able to match the first
        trade's row (or vice versa), regardless of exit_date ordering."""
        recon = _make_recon(
            [
                _sell_order(filled_avg_price="55.00", client_order_id="exit-1-aaa"),
                _sell_order(filled_avg_price="60.00", client_order_id="exit-2-bbb"),
            ]
        )
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (1, 50.0, 45.0, 100),
            (0,),
            None,
            (2, 55.0, 50.0, 100),
            (0,),
            None,
        ]

        result = recon.reconcile_exit_fills(cur, reconcile_date=None)

        assert result["updated"] == 2
        lookup_calls = [c for c in cur.execute.call_args_list if "pending_exit_client_order_id" in c.args[0]]
        assert len(lookup_calls) == 2
        assert lookup_calls[0].args[1] == ("exit-1-aaa", "AAPL")
        assert lookup_calls[1].args[1] == ("exit-2-bbb", "AAPL")
