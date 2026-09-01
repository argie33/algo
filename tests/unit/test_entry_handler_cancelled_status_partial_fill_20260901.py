#!/usr/bin/env python3
"""Regression test for EntryHandler._record_entry_phase, found 2026-09-01 during a
real-money-readiness partial-fill lifecycle audit.

A terminal cancel/expire order status can still carry a nonzero filled_qty at the broker -
Alpaca moves a partially-filled day order straight to "canceled"/"expired" (not
"partially_filled", which is a still-open state) once no further fill is possible, e.g. a TIF
expiry or a manual cancel-remaining after a partial fill. In execution_mode="auto",
_record_entry_phase re-verifies order_status via context._verify_order_status() and would get
this same terminal status back - without normalizing it, the "partially_filled" check right
below (which sets actual_shares from the broker's real filled_qty) never fired: actual_shares
stayed at the originally-REQUESTED shares, and the position-creation gate further down (which
only recognizes "filled"/"partially_filled"/"paper_pending"/"open") skipped creating a position
entirely - real shares bought at the broker would become an invisible live position, invisible
to circuit_breaker.py's risk checks and position_monitor's stop-loss/exit engine alike.

order_manager.wait_for_order_fill() has a matching fix (see
tests/unit/test_order_manager_wait_for_fill.py's TestWaitForOrderFillTerminalStatusWithPartialFill)
so this scenario reaches _record_entry_phase at all instead of hard-stopping earlier in
_submit_entry_phase's "not fill_ok" branch.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.executor_entry_handler import EntryHandler


def _make_trade_context():
    ctx = MagicMock()
    ctx.signal_date = date(2026, 7, 24)
    ctx.entry_date = date(2026, 7, 24)
    ctx.sqs = 75
    ctx.signals.trend_score = 80
    ctx.signals.base_type = "flat_base"
    ctx.signals.base_quality = "A"
    ctx.signals.stage_phase = "mid"
    ctx.signals.rs_percentile = 90
    ctx.signals.advanced_components = None
    ctx.market.sector = "Technology"
    ctx.market.industry = "Software"
    ctx.market.market_exposure_at_entry = 50.0
    ctx.market.exposure_tier_at_entry = "full"
    ctx.execution.stop_method = "atr"
    ctx.execution.stop_reasoning = "atr_based"
    return ctx


def _make_handler(verified_status, filled_qty):
    handler_context = MagicMock()
    handler_context.execution_mode = "auto"
    handler_context._get_portfolio_value.return_value = Decimal("100000")
    handler_context._verify_order_status.return_value = verified_status
    handler_context._get_order_filled_quantity.return_value = filled_qty
    return EntryHandler(handler_context)


def test_cancelled_status_with_broker_filled_qty_creates_position_with_actual_shares():
    """100 shares requested, broker filled 40 before cancelling the remainder - the position
    must be created (not skipped) with quantity=40, not the requested 100."""
    handler = _make_handler(verified_status="cancelled", filled_qty=40.0)
    cur = MagicMock()
    cur.fetchone.return_value = None  # no existing position row

    final_status = handler._record_entry_phase(
        cur=cur,
        trade_id="TRD-PARTIALCANCEL",
        symbol="PARTIALCANCEL",
        shares=Decimal("100"),
        entry_price=Decimal("50.00"),
        executed_price=Decimal("50.00"),
        stop_loss_price=Decimal("45.00"),
        target_1_price=Decimal("55.00"),
        target_2_price=None,
        target_3_price=None,
        order_status="cancelled",
        alpaca_order_id="alpaca-order-partial-cancel",
        context=_make_trade_context(),
        rejection_reason=None,
        idempotency_key="idem-partial-cancel",
        order_send_time=None,
    )

    assert final_status == "partially_filled", (
        "a cancelled status with real broker fill must be normalized to partially_filled, "
        "not treated as a total failure"
    )

    position_insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_positions" in str(c.args[0])]
    assert len(position_insert_calls) == 1, "the 40 shares that DID fill must create a position, not be discarded"
    inserted_qty = position_insert_calls[0].args[1][2]  # (position_id, symbol, quantity, ...)
    assert inserted_qty == Decimal("40"), f"position quantity must be the broker's actual fill (40), got {inserted_qty}"

    trade_insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_trades" in str(c.args[0])]
    assert len(trade_insert_calls) == 1
    trade_qty_param = trade_insert_calls[0].args[1][6]  # entry_quantity column position
    assert trade_qty_param == Decimal("40"), (
        f"algo_trades.entry_quantity must match the actual fill (40), not the requested 100 - got {trade_qty_param}"
    )


def test_cancelled_status_with_zero_broker_filled_qty_does_not_create_position():
    """A genuine full cancellation (filled_qty=0) must still skip position creation - the
    normalization must not paper over a real total failure."""
    handler = _make_handler(verified_status="cancelled", filled_qty=0.0)
    cur = MagicMock()
    cur.fetchone.return_value = None

    final_status = handler._record_entry_phase(
        cur=cur,
        trade_id="TRD-FULLCANCEL",
        symbol="FULLCANCEL",
        shares=Decimal("100"),
        entry_price=Decimal("50.00"),
        executed_price=Decimal("50.00"),
        stop_loss_price=Decimal("45.00"),
        target_1_price=Decimal("55.00"),
        target_2_price=None,
        target_3_price=None,
        order_status="cancelled",
        alpaca_order_id="alpaca-order-full-cancel",
        context=_make_trade_context(),
        rejection_reason="user requested",
        idempotency_key="idem-full-cancel",
        order_send_time=None,
    )

    assert final_status == "cancelled"
    position_insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_positions" in str(c.args[0])]
    assert not position_insert_calls, "a genuine zero-fill cancellation must not create a position"
