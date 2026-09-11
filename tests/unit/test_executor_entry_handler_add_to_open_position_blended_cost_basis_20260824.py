"""Regression test: EntryHandler._upsert_position_record()'s "adding to OPEN position" branch
must blend the existing position's quantity/cost basis with the new fill, not discard it.

BUG FOUND 2026-08-24 (real-money-readiness goal, phase8/position-sizer audit): this branch
used to set quantity=actual_shares and avg_entry_price/entry_price=executed_price directly -
i.e. only this trade's own fill, silently overwriting whatever the position already held.

CORRECTION 2026-09-10 (real-money-readiness risk audit): this branch is NOT dead code. The
prior docstring here claimed trade_validator.py's check_duplicate_position() makes it
unreachable - false. That guard only blocks a duplicate for the SAME entry_date; a pyramid
add on a later trading day into a position opened earlier reaches this branch for real, every
time a winning position gets scaled into.
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
            (["TRD-OLD"], "open", 100, Decimal("50.00"), Decimal("45.00")),
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
            (["TRD-OLD"], "open", 0, None, None),
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


class TestAddToOpenPositionPreservesFrozenStopLossPrice:
    """Regression test for the 2026-09-10 risk audit finding: a pyramid add must NOT overwrite
    the position's frozen stop_loss_price (the entry-time risk basis R-multiple/exit-gating math
    is computed against) with the new lot's own stop - that would retroactively shrink the
    recorded risk-per-share and corrupt R-multiple math for the whole blended position."""

    def test_existing_stop_loss_price_is_preserved_not_overwritten(self):
        handler = _make_handler()
        cur = MagicMock()
        # Existing position: 100 shares @ $50.00 avg cost, frozen stop at $40.00 (risk/share=$10).
        cur.fetchone.side_effect = [
            ("POS-1",),
            (["TRD-OLD"], "open", 100, Decimal("50.00"), Decimal("40.00")),
        ]

        handler._upsert_position_record(
            cur=cur,
            position_id="POS-1",
            symbol="TEST",
            trade_id="TRD-NEW",
            actual_shares=Decimal("50"),
            executed_price=Decimal("65.00"),
            position_value=Decimal("3250.00"),
            position_status="open",
            entry_date=date(2026, 9, 10),
            # New lot's own (tighter) stop - must NOT clobber the existing $40.00 basis.
            stop_loss_price=Decimal("60.00"),
            target_1_price=None,
            target_2_price=None,
            target_3_price=None,
            r_multiple=None,
            risk_pct=None,
        )

        update_call = cur.execute.call_args_list[-1]
        params = update_call.args[1]
        stored_stop_loss_price = params[11]
        assert stored_stop_loss_price == Decimal("40.00"), (
            f"expected the position's existing frozen stop_loss_price $40.00 to be preserved, "
            f"got {stored_stop_loss_price} - the pyramid add overwrote the risk basis with the "
            f"new lot's own stop, corrupting R-multiple math for the blended position"
        )

    def test_risk_pct_recomputed_against_preserved_stop_and_blended_price(self):
        handler = _make_handler()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("POS-1",),
            (["TRD-OLD"], "open", 100, Decimal("50.00"), Decimal("40.00")),
        ]

        handler._upsert_position_record(
            cur=cur,
            position_id="POS-1",
            symbol="TEST",
            trade_id="TRD-NEW",
            actual_shares=Decimal("50"),
            executed_price=Decimal("65.00"),
            position_value=Decimal("3250.00"),
            position_status="open",
            entry_date=date(2026, 9, 10),
            stop_loss_price=Decimal("60.00"),
            target_1_price=None,
            target_2_price=None,
            target_3_price=None,
            r_multiple=None,
            risk_pct=None,
        )

        update_call = cur.execute.call_args_list[-1]
        params = update_call.args[1]
        blended_avg_price = params[1]
        risk_pct = params[19]
        expected_risk_pct = ((float(blended_avg_price) - 40.00) / float(blended_avg_price)) * 100.0
        assert risk_pct == expected_risk_pct
