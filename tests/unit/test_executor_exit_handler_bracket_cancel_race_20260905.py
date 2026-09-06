#!/usr/bin/env python3
"""Regression test: a full-exit bracket cancel that races against the bracket's own
stop-loss/take-profit leg filling (or that genuinely fails to confirm) must not lead to
a duplicate sell order - an oversell/short risk with real money.

BUG FOUND 2026-09-05 (real-money-readiness audit): `_execute_exit`'s full-exit path called
`self.context._cancel_bracket_orders(alpaca_order_id)` and only checked `cancel_result["success"]`,
completely ignoring `filled_qty`/`filled_avg_price` - both of which order_manager.py's
`cancel_bracket_orders()` already populates whenever a post-cancel check finds the bracket's
own stop/take-profit leg filled (fully or partially) before the cancel landed (a 200/204 on a
partial fill, or a 422 "already terminal" after a full fill). The code then unconditionally
proceeded to submit a brand-new sell order for the full `shares_to_exit` regardless:
  - if the raced leg fully filled, this is a plain oversell/possible unintended short
  - if a genuine (non-race) cancel failure occurred (credentials, network, retries exhausted),
    the original bracket legs are still live at the broker - submitting a second sell creates
    two independent live sell-side order structures for the same position.

Fixed by checking `filled_qty` after every cancel outcome (mirroring the symmetric fix already
made to executor_entry_handler.py's `_recover_bracket_cancel_race`), reducing/skipping the new
sell order on a raced fill, and aborting entirely (no new order, alert instead) on a genuine
unconfirmed cancel failure in execution_mode="auto".

Static source check, matching the established precedent for this function (see
test_executor_exit_handler_partial_exit_resizes_bracket_leg_20260824.py's docstring):
_execute_exit has a large dependency graph impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()

_CANCEL_MARKER = "# Cancel bracket orders on full exit"


def _cancel_block(source: str, length: int = 7500) -> str:
    assert _CANCEL_MARKER in source, "expected to find the full-exit bracket-cancel block - source may have moved"
    start = source.index(_CANCEL_MARKER)
    return source[start : start + length]


def test_filled_qty_is_read_from_the_cancel_result():
    block = _cancel_block(SOURCE)
    assert 'cancel_result.get("filled_qty")' in block, (
        "must read filled_qty off the cancel result to detect a raced bracket-leg fill, not just check success/failure"
    )


def test_full_raced_fill_sets_the_closed_position_flag_without_reducing_shares():
    block = _cancel_block(SOURCE)
    assert "raced_fill_closed_position = True" in block
    idx_flag = block.index("raced_fill_closed_position = True")
    idx_reduce = block.index("shares_to_exit = shares_to_exit - raced_filled_qty")
    assert idx_flag < idx_reduce, (
        "the fully-closed branch (raced_filled_qty >= shares_to_exit) must be checked before "
        "the partial-reduction branch, and must not fall through into reducing shares_to_exit"
    )


def test_partial_raced_fill_reduces_the_new_order_quantity():
    block = _cancel_block(SOURCE)
    assert "shares_to_exit = shares_to_exit - raced_filled_qty" in block, (
        "a partial raced fill must shrink the new sell order by the amount already filled, "
        "not submit the original full quantity on top of it"
    )


def test_genuine_unconfirmed_cancel_failure_aborts_in_auto_mode_without_submitting_a_new_order():
    block = _cancel_block(SOURCE)
    assert 'execution_mode == "auto" and not cancel_result.get("filled_qty")' in block, (
        "a real (non-race) cancel failure in auto mode must be distinguished from the "
        "expected paper-mode 'no Alpaca order to cancel' response before deciding to abort"
    )
    abort_idx = block.index('execution_mode == "auto" and not cancel_result.get("filled_qty")')
    return_idx = block.index('"message": f"Bracket cancellation unconfirmed', abort_idx)
    assert abort_idx < return_idx
    # Must return (abort) rather than fall through to submitting a new order.
    between = block[abort_idx:return_idx]
    assert "return {" in between


def test_raced_position_closure_skips_resubmitting_a_new_sell_order():
    source = SOURCE
    marker = 'if execution_mode == "auto" and raced_fill_closed_position:'
    assert marker in source, "must special-case the fully-closed-by-race branch before the normal auto-mode submit path"
    idx = source.index(marker)
    elif_idx = source.index("elif execution_mode ==", idx)
    window = source[idx:elif_idx]
    assert "_send_alpaca_exit" not in window, (
        "when the bracket leg already fully closed the position during the cancel race, "
        "the handler must NOT submit a second sell order (oversell/short risk)"
    )
    assert "actual_fill_price = raced_fill_price" in window
