#!/usr/bin/env python3
"""Regression test: a partial exit must resize the resting broker bracket stop-loss
leg to the remaining share count, not just record the new quantity in our own DB.

[[order_types_and_stop_loss_architecture_audit_20260824]]: full exits already cancel
the bracket order outright (`_cancel_bracket_orders`), but a PARTIAL exit (T1/T2/T3
profit-taking, or any other fraction<1 exit) sells shares via a SEPARATE order and
left the bracket's resting legs completely untouched - still sized for the ORIGINAL
full entry quantity. A stale, oversized stop-loss leg firing later could try to sell
more shares than the account actually holds.

Static source check, matching the established precedent for this exact function
(test_executor_exit_handler_partial_exit_updates_quantity.py): _execute_exit has a
large dependency graph (guards, lock/fetch, bracket cancellation, order submission,
position update) impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()

_RESIZE_MARKER = "if not (full_exit or new_qty <= 0) and alpaca_order_id and not standalone_stop_order_id:"


def _partial_exit_resize_block(source: str) -> str:
    assert _RESIZE_MARKER in source, (
        "expected to find the partial-exit bracket-resize block - source may have been restructured"
    )
    start = source.index(_RESIZE_MARKER)
    # Window covers the resize guard through the logger.critical call - enough to check
    # ordering/content without depending on exact wording.
    return source[start : start + 1100]


def test_resize_only_attempted_on_a_true_partial_not_a_full_exit():
    block = _partial_exit_resize_block(SOURCE)
    assert "not (full_exit or new_qty <= 0)" in block, (
        "must skip the resize on a full exit (already handled by _cancel_bracket_orders "
        "above) or when the partial rounds down to a full exit (new_qty <= 0)"
    )


def test_resize_passes_current_quantity_and_effective_stop():
    block = _partial_exit_resize_block(SOURCE)
    assert "_sync_bracket_stop_loss(alpaca_order_id, effective_stop, new_qty)" in block, (
        "the resize call must pass the just-computed remaining share count (new_qty) "
        "and the effective stop price, not stale values"
    )


def test_resize_failure_does_not_raise():
    """The share sale has ALREADY happened for real by this point in the flow - unlike
    _raise_stop_only's fail-closed contract (nothing irreversible has happened yet
    there), abandoning the DB update here because a broker-side resize failed would
    leave a real, already-executed sale completely unrecorded. Must fail open: log,
    don't raise."""
    block = _partial_exit_resize_block(SOURCE)
    # Checks for an actual `raise` statement (line starting with "raise " after
    # stripping indentation), not just the substring "raise" - which also appears
    # inside this block's own "stop-raise" wording in the warning message.
    raise_statements = [line for line in block.splitlines() if line.strip().startswith("raise ")]
    assert not raise_statements, (
        "a failed bracket-leg resize after a partial exit must not raise - the sale is "
        f"already real and must still be recorded; log the failure and continue instead. "
        f"Found: {raise_statements}"
    )
    # Upgraded from logger.error to logger.critical by the 2026-09-07 pre-live audit fix
    # (see this block's own in-source comment) - a stale broker-side stop needs the same
    # "needs a human to notice" severity this file uses elsewhere, not a routine error log.
    assert "logger.critical" in block


def test_resize_precedes_the_position_update_call():
    resize_idx = SOURCE.index(_RESIZE_MARKER)
    update_call_idx = SOURCE.index("update_success, update_error = self.context._update_position_with_retry(")
    assert resize_idx < update_call_idx, (
        "the broker-side resize should be attempted before (or at least alongside) the "
        "DB position update, not after - keeps the ordering consistent with the "
        "_raise_stop_only sync-before-write pattern even though this path fails open"
    )
