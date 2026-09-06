"""Regression test: EntryHandler._upsert_position_record()'s "reopening a CLOSED position"
branch must RESET trade_ids_arr to just the new trade, not append onto the closed position's
prior trade lineage.

BUG FOUND 2026-09-05 (real-money-readiness audit, order execution review): a same-day
stop-out followed by a fresh signal on the same symbol is a legitimately reachable path
(trade_validator.check_duplicate_position only blocks re-entry when is_open=true). When that
happens, this branch used to APPEND the new trade_id onto the existing (closed) position's
trade_ids_arr instead of resetting it, leaving trade_ids_arr = [stale_closed_trade,
live_trade]. trade_ids_arr[0] is the established "the trade for this position" convention
read throughout the codebase (phase6_exit_execution.py, phase9_stop_loss_repair.py,
position_monitor.py all resolve "the" trade this way) - with the stale trade first, stop
management/exit logic would resolve the already-closed bracket's alpaca_order_id/entry_price
instead of the live one actually protecting the current shares, and an exit's P&L could get
recorded against the wrong trade row. The existing multi-position data-integrity guard in
executor_exit_handler.py doesn't catch this case because both trade_ids map to the SAME
single position, not to >1 distinct positions.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.executor_entry_handler import EntryHandler


def _make_handler():
    handler_context = MagicMock()
    handler_context.execution_mode = "paper"
    handler_context.t1_target_r_multiple = 1.5
    handler_context.t2_target_r_multiple = 2.5
    handler_context.t3_target_r_multiple = 3.5
    return EntryHandler(handler_context)


class TestReopenResetsTradeIdsArr:
    def test_reopen_replaces_stale_trade_id_not_appends(self):
        handler = _make_handler()
        cur = MagicMock()
        # First fetchone(): existence check finds the position.
        # Second fetchone(): trade_ids_arr, status, quantity, avg_entry_price for a CLOSED
        # position whose last trade was TRD-OLD.
        cur.fetchone.side_effect = [
            ("POS-1",),
            (["TRD-OLD"], "closed", 0, Decimal("50.00")),
        ]

        handler._upsert_position_record(
            cur=cur,
            position_id="POS-1",
            symbol="TEST",
            trade_id="TRD-NEW",
            actual_shares=Decimal("50"),
            executed_price=Decimal("60.00"),
            position_value=Decimal("3000.00"),
            position_status="open",
            entry_date=date(2026, 9, 5),
            stop_loss_price=Decimal("55.00"),
            target_1_price=None,
            target_2_price=None,
            target_3_price=None,
            r_multiple=None,
            risk_pct=None,
        )

        update_call = cur.execute.call_args_list[-1]
        params = update_call.args[1]
        trade_ids_text, trade_ids_arr = params[9], params[10]

        assert trade_ids_arr == ["TRD-NEW"], (
            f"expected trade_ids_arr reset to just the new live trade ['TRD-NEW'], got "
            f"{trade_ids_arr} - reopening a closed position must not carry the prior "
            f"(closed) trade lineage forward, since trade_ids_arr[0] is read elsewhere as "
            f"'the' trade for this position's stop management and exit P&L attribution"
        )
        assert trade_ids_text == "TRD-NEW"

    def test_adding_to_open_position_still_appends(self):
        """Contrast case: adding to a genuinely OPEN (not closed) position must still append,
        preserving the existing multi-trade pyramided lineage - this branch is unchanged."""
        handler = _make_handler()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("POS-1",),
            (["TRD-OLD"], "open", 100, Decimal("50.00")),
        ]

        handler._upsert_position_record(
            cur=cur,
            position_id="POS-1",
            symbol="TEST",
            trade_id="TRD-NEW",
            actual_shares=Decimal("50"),
            executed_price=Decimal("60.00"),
            position_value=Decimal("3000.00"),
            position_status="open",
            entry_date=date(2026, 9, 5),
            stop_loss_price=Decimal("45.00"),
            target_1_price=None,
            target_2_price=None,
            target_3_price=None,
            r_multiple=None,
            risk_pct=None,
        )

        update_call = cur.execute.call_args_list[-1]
        params = update_call.args[1]
        # The "add to open position" branch's UPDATE has a different column order/count than
        # the reopen branch's - trade_ids_arr param position is validated by the existing
        # blended-cost-basis test file; here we only need the array's own value.
        trade_ids_arr = next(p for p in params if isinstance(p, list))
        assert trade_ids_arr == ["TRD-OLD", "TRD-NEW"]
