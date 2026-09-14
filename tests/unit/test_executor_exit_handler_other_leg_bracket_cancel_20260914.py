#!/usr/bin/env python3
"""Regression test: a full exit on a pyramided (2+ leg) position must cancel EVERY other
leg's bracket order too, not just trade_ids_arr[0]'s own bracket - and must apply the same
fill-vs-cancel race handling and unconfirmed-cancel-failure abort logic already proven out
for the primary bracket and the standalone-stop paths.

BUG FOUND (real-money-readiness audit): algo_positions.trade_ids_arr holds one algo_trades
row per pyramid add (executor_entry_handler.py appends on each add,
max_reentries_per_name=2 by default - a live, reachable config). Every exit call site
resolves trade_id = trade_ids_arr[0] only. `_execute_exit`'s full-exit path submits ONE new
sell order sized for the position's ENTIRE remaining quantity across every leg
(algo_positions.quantity) but, before this fix, cancelled only trade_ids_arr[0]'s own
bracket order - every other leg's own stop-loss/take-profit bracket stayed resting live at
the broker after the position was fully sold to zero, a naked-short risk if either later
fired.

Static source check, matching the established precedent for this function (see
test_executor_exit_handler_bracket_cancel_race_20260905.py's docstring): _execute_exit has
a large dependency graph impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()

_MARKER = "# See executor_exit_other_leg_brackets.py (real-money-readiness fix)"


def _other_leg_block(source: str, length: int = 9000) -> str:
    assert _MARKER in source, "expected to find the other-leg bracket-cancel block - source may have moved"
    start = source.index(_MARKER)
    return source[start : start + length]


def test_other_legs_are_fetched_and_cancelled_on_full_exit():
    block = _other_leg_block(SOURCE)
    assert "fetch_other_leg_order_ids(cur, position_id, trade_id)" in block
    assert "cancel_other_leg_brackets_on_full_exit(" in block


def test_other_leg_block_runs_before_the_new_exit_order_is_submitted():
    idx_other_leg = SOURCE.index(_MARKER)
    idx_submit = SOURCE.index("# Execute exit order (if not review/paper mode)")
    assert idx_other_leg < idx_submit


def test_unconfirmed_other_leg_cancel_failure_aborts_in_auto_mode_without_submitting_a_new_order():
    block = _other_leg_block(SOURCE)
    marker = 'not other_leg_cancel_result["success"] and not other_leg_cancel_result.get("filled_qty")'
    assert marker in block, (
        "a genuine (non-race) cancel failure on another leg's bracket must be distinguished "
        "from a raced fill before deciding whether to abort"
    )
    abort_idx = block.index('if execution_mode == "auto":', block.index(marker))
    return_idx = block.index("return {", abort_idx)
    assert return_idx > abort_idx
    between = block[abort_idx:return_idx]
    assert "notify(" in between, "must alert before aborting, matching the primary-bracket abort path"


def test_other_leg_raced_full_fill_sets_the_closed_position_flag_without_reducing_shares():
    block = _other_leg_block(SOURCE)
    assert "raced_fill_closed_position = True" in block
    idx_flag = block.index("raced_fill_closed_position = True")
    idx_reduce = block.index("shares_to_exit = shares_to_exit - other_leg_raced_qty")
    assert idx_flag < idx_reduce, (
        "the fully-closed branch must be checked before the partial-reduction branch, and "
        "must not fall through into reducing shares_to_exit"
    )


def test_other_leg_partial_raced_fill_reduces_the_new_order_quantity_and_accumulates():
    block = _other_leg_block(SOURCE)
    assert "shares_to_exit = shares_to_exit - other_leg_raced_qty" in block
    assert "raced_filled_qty = (raced_filled_qty or 0) + other_leg_raced_qty" in block, (
        "must accumulate onto the same raced_filled_qty the primary-bracket/standalone-stop "
        "paths already thread through to the order-submission decision, not overwrite it"
    )


def test_other_leg_fill_price_none_raises_rather_than_silently_proceeding():
    block = _other_leg_block(SOURCE)
    assert "if other_leg_raced_fill_price is None:" in block
    idx = block.index("if other_leg_raced_fill_price is None:")
    raise_idx = block.index("raise RuntimeError(", idx)
    assert 0 < raise_idx - idx < 300
