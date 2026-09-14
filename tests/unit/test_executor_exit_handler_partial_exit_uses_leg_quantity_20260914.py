#!/usr/bin/env python3
"""Regression test: a partial exit's algo_trades.quantity write and bracket/standalone-stop
resize must use THIS leg's own quantity (t.quantity), not the position-wide total
(p.quantity), for a pyramided (2+ leg) position.

BUG FOUND (real-money-readiness audit): _execute_exit's partial-exit branch computed
`new_qty_partial = current_qty - shares_to_exit`, where `current_qty` is p.quantity - the
SUM across every leg. Since position_sync.py's sync_positions_from_trades() re-derives
algo_positions.quantity as SUM(algo_trades.quantity) across every leg on the very next
run, writing a position-wide value into ONE leg's own algo_trades.quantity row corrupts
that invariant for any 2+ leg position: e.g. leg0=100/leg2=50 (total 150), a 30sh partial
exit wrote 150-30=120 into leg0's own row (which only ever held 100) while leg2's row
stayed untouched at 50 - the next SUM read 170, not the true 120, a phantom 50-share
overstatement. The bracket/standalone-stop resize reused the same wrong value, risking an
oversized resting sell order at the broker (this leg's own bracket resized to MORE shares
than this leg ever held).

Fixed by fetching t.quantity (leg_quantity) alongside p.quantity, and using
leg_new_qty = leg_quantity - shares_to_exit for the algo_trades.quantity write and both
resize calls - a no-op for the overwhelming majority of single-leg positions, where
leg_quantity == current_qty by construction.

Static source check, matching the established precedent for this function (see
test_executor_exit_handler_partial_exit_updates_quantity.py's docstring): _execute_exit has
a large dependency graph impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()


def test_query_selects_this_legs_own_quantity():
    assert "p.status, t.quantity" in SOURCE, (
        "the trade/position fetch query must select t.quantity (this leg's own share "
        "count) alongside p.quantity (the position-wide total) - source may have moved"
    )


def test_leg_quantity_falls_back_to_current_qty_when_no_position_row():
    assert "leg_quantity_f = float(leg_quantity) if leg_quantity is not None else current_qty_f" in SOURCE, (
        "leg_quantity must fall back to the position-wide current_qty only in the "
        "no-position-row edge case, matching entry_price's own COALESCE fallback"
    )


def test_partial_exit_write_uses_leg_new_qty_not_position_wide_new_qty():
    assert "leg_new_qty = float(Decimal(str(leg_quantity)) - Decimal(str(shares_to_exit)))" in SOURCE
    assert "new_qty_partial = leg_new_qty" in SOURCE
    # The old, buggy expression must be gone entirely, not just superseded.
    assert "new_qty_partial = float(Decimal(str(current_qty)) - Decimal(str(shares_to_exit)))" not in SOURCE


def test_bracket_and_standalone_resize_both_use_leg_new_qty():
    assert "_sync_bracket_stop_loss(alpaca_order_id, effective_stop, leg_new_qty)" in SOURCE, (
        "the bracket resize must use leg_new_qty (this leg's own remaining shares), not "
        "new_qty (the position-wide total)"
    )
    resize_call_idx = SOURCE.index("resize_standalone_stop_after_partial_exit(")
    standalone_call_block = SOURCE[resize_call_idx : resize_call_idx + 300]
    assert "leg_new_qty," in standalone_call_block, (
        "the standalone-stop resize must also use leg_new_qty, not the position-wide new_qty"
    )


def test_leg_new_qty_clamped_at_zero_with_a_critical_alert_when_exit_exceeds_this_legs_shares():
    """A partial-exit fraction of the WHOLE position can exceed what this specific leg
    alone holds (e.g. leg0=30/leg2=120, a 50%-of-position exit sells 75sh > leg0's own 30).
    There's no established convention for which leg's shares a partial exit draws from
    across multiple legs - must clamp at 0 and alert loudly rather than write (or resize
    a broker order to) a nonsensical negative quantity."""
    assert "if leg_new_qty < 0:" in SOURCE
    clamp_idx = SOURCE.index("if leg_new_qty < 0:")
    clamp_block = SOURCE[clamp_idx : clamp_idx + 2000]
    assert "logger.critical(" in clamp_block
    assert 'notify(\n                        "critical"' in clamp_block or '"critical",' in clamp_block
    assert "leg_new_qty = 0.0" in clamp_block


def test_new_qty_position_wide_still_used_for_algo_positions_update():
    """The position-wide new_qty must still be what gets written to algo_positions.quantity
    (correctly the aggregate across every leg) - only the PER-LEG bookkeeping/resize should
    have changed, not the position-level total."""
    update_call_idx = SOURCE.index("update_success, update_error = self.context._update_position_with_retry(")
    update_call_block = SOURCE[update_call_idx : update_call_idx + 300]
    assert "new_qty=new_qty," in update_call_block
