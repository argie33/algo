"""Regression test: EntryHandler._upsert_position_record()'s "adding to OPEN position" branch
must blend the existing position's quantity/cost basis with the new fill, not discard it.

BUG FOUND 2026-08-24 (real-money-readiness goal, phase8/position-sizer audit): this branch
used to set quantity=actual_shares and avg_entry_price/entry_price=executed_price directly -
i.e. only this trade's own fill, silently overwriting whatever the position already held.
Live-confirmed this branch should currently be UNREACHABLE in the real call graph
(trade_validator.py's check_duplicate_position() blocks any new entry into a symbol that
already has an open position for that entry_date, and Phase 8 always passes a real
entry_date) - but hardened as defense-in-depth per this codebase's own convention: dead code
that would corrupt data if a future change ever made it reachable should still be correct,
not just "currently safe because nothing calls it wrong yet."
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


class TestAddToOpenPositionBlendsCostBasis:
    def test_quantity_is_summed_not_overwritten(self):
        handler = _make_handler()
        cur = MagicMock()
        # First fetchone(): existence check finds the position.
        # Second fetchone(): trade_ids_arr, status, quantity, avg_entry_price for an OPEN
        # position already holding 100 shares at a $50.00 average cost.
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
            entry_date=date(2026, 8, 24),
            stop_loss_price=Decimal("45.00"),
            target_1_price=None,
            target_2_price=None,
            target_3_price=None,
            r_multiple=None,
            risk_pct=None,
        )

        update_call = cur.execute.call_args_list[-1]
        params = update_call.args[1]
        total_quantity, avg_entry_price, entry_price = params[0], params[1], params[2]

        assert total_quantity == Decimal("150"), (
            f"expected old 100 + new 50 = 150 shares, got {total_quantity} - the add "
            f"silently discarded the position's existing shares"
        )
        expected_avg = (Decimal("100") * Decimal("50.00") + Decimal("50") * Decimal("60.00")) / Decimal("150")
        assert avg_entry_price == expected_avg, (
            f"expected quantity-weighted average cost {expected_avg}, got {avg_entry_price} - "
            f"the add overwrote cost basis with just the new fill's price instead of blending"
        )
        assert entry_price == avg_entry_price, "entry_price must match the blended avg_entry_price"

    def test_first_add_with_no_prior_quantity_falls_back_to_new_price(self):
        """Defensive fallback: if existing_quantity/avg_entry_price somehow came back
        None/0 (e.g. a legacy row), don't divide by zero or produce a nonsensical blend -
        just use the new fill's own price, same as before this fix for that edge case."""
        handler = _make_handler()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("POS-1",),
            (["TRD-OLD"], "open", 0, None),
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
            entry_date=date(2026, 8, 24),
            stop_loss_price=Decimal("45.00"),
            target_1_price=None,
            target_2_price=None,
            target_3_price=None,
            r_multiple=None,
            risk_pct=None,
        )

        update_call = cur.execute.call_args_list[-1]
        params = update_call.args[1]
        assert params[0] == Decimal("50")
        assert params[1] == Decimal("60.00")
