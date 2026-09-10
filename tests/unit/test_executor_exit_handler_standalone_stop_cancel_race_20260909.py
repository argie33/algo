#!/usr/bin/env python3
"""Regression test: a full-exit standalone-stop cancel that races against the standalone
stop's own fill must not lead to a duplicate sell order - the same oversell/short risk
already fixed for the bracket-order path (see
test_executor_exit_handler_bracket_cancel_race_20260905.py), just on the newer
Phase-9-repaired-position code path.

BUG FOUND 2026-09-09 (real-money-readiness audit): `_execute_exit`'s full-exit path called
`cancel_standalone_stop_on_full_exit(...)` and discarded its return value entirely, even
though the underlying `cancel_order_fn` (`OrderManager.cancel_bracket_orders`, reused
generically) already performs the identical post-cancel fill check and reports
filled_qty/filled_avg_price whenever the standalone stop fired at the broker before the
cancel landed. Left unchecked, a raced fill went completely unnoticed and the code proceeded
to submit a brand-new full-quantity sell order regardless - an oversell/short specifically
for positions Phase 9 had already auto-repaired onto a standalone stop.

Fixed by having cancel_standalone_stop_on_full_exit return the same {success, message,
filled_qty, filled_avg_price} shape as cancel_bracket_orders, and having _execute_exit apply
the identical race-handling it already applies to the bracket path (reduce/skip the new sell
order on a raced fill, reusing the same raced_filled_qty/raced_fill_price/
raced_fill_closed_position variables).

Static source check, matching the established precedent for this function (see
test_executor_exit_handler_bracket_cancel_race_20260905.py's docstring): _execute_exit has a
large dependency graph impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()

_CANCEL_MARKER = "if full_exit:\n            standalone_cancel_result = cancel_standalone_stop_on_full_exit("


def _cancel_block(source: str, length: int = 3500) -> str:
    assert _CANCEL_MARKER in source, (
        "expected to find the full-exit standalone-stop-cancel block - source may have moved"
    )
    start = source.index(_CANCEL_MARKER)
    return source[start : start + length]


def test_filled_qty_is_read_from_the_standalone_cancel_result():
    block = _cancel_block(SOURCE)
    assert 'standalone_cancel_result.get("filled_qty")' in block, (
        "must read filled_qty off the standalone-stop cancel result to detect a raced fill, "
        "not just cancel and discard the result"
    )


def test_full_raced_fill_sets_the_closed_position_flag_without_reducing_shares():
    block = _cancel_block(SOURCE)
    assert "raced_fill_closed_position = True" in block
    idx_flag = block.index("raced_fill_closed_position = True")
    idx_reduce = block.index("shares_to_exit = shares_to_exit - standalone_raced_qty")
    assert idx_flag < idx_reduce, (
        "the fully-closed branch (standalone_raced_qty >= shares_to_exit) must be checked "
        "before the partial-reduction branch, and must not fall through into reducing "
        "shares_to_exit"
    )


def test_partial_raced_fill_reduces_the_new_order_quantity():
    block = _cancel_block(SOURCE)
    assert "shares_to_exit = shares_to_exit - standalone_raced_qty" in block, (
        "a partial raced fill on the standalone stop must shrink the new sell order by the "
        "amount already filled, not submit the original full quantity on top of it"
    )


def test_raced_qty_and_price_feed_the_shared_variables_used_by_the_order_submission_decision():
    block = _cancel_block(SOURCE)
    assert "raced_filled_qty = (raced_filled_qty or 0) + standalone_raced_qty" in block
    assert "raced_fill_price = standalone_raced_fill_price" in block, (
        "the standalone race must feed the same raced_filled_qty/raced_fill_price variables "
        "the bracket path uses, so the downstream order-submission decision "
        "(raced_fill_closed_position) and P&L blending both see it"
    )


def test_missing_fill_price_on_a_reported_fill_raises_rather_than_guesses():
    block = _cancel_block(SOURCE)
    assert "standalone_raced_fill_price is None" in block
    idx = block.index("standalone_raced_fill_price is None")
    window = block[idx : idx + 300]
    assert "raise RuntimeError" in window, (
        "a reported raced fill with no price must fail loudly, not silently skip the race "
        "adjustment and let a duplicate sell order through"
    )
