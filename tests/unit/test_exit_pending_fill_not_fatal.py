#!/usr/bin/env python3
"""Regression test for the pending-fill-treated-as-fatal-error bug in executor_exit_handler.py.

order_manager.py's _exit_result_from_order_data() legitimately returns
{"success": True, "filled_price": None, ...} when Alpaca accepts a market exit order but
hasn't confirmed the fill price yet - a routine, documented response, not an error. By the
time execute_exit() sees this, the protective bracket may already be cancelled and the real
sell may already be in flight at the broker.

The bug: execute_exit() used to unconditionally set is_estimated_price=False then raise
DataUnavailableError the moment filled_price was None, unwinding the whole DB transaction
with zero bookkeeping - leaving the DB showing the position untouched/still protected while
the broker had already acted on it. This also made the PENDING_FILL_RECONCILIATION code path
(estimated_exit_price + status='closed', finalized later by
algo/infrastructure/reconciliation.py's resolve_local_pending_exits/audit_stale_estimated_prices)
permanently unreachable dead code.

Static source check rather than a full mocked call: execute_exit() has a large dependency
graph (guards, lock/fetch, bracket cancellation, order submission, position update) - see
test_exit_handler_clears_pending_client_order_id.py for the established precedent of testing
this function's structure this way.
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()


def _auto_mode_exit_block(source: str) -> str:
    """Extract the `if execution_mode == "auto": ... if exit_order_result["success"]:` block."""
    start = source.index('if exit_order_result["success"]:')
    # Bounded by the next top-level `else:` that handles the failed-order branch
    end = source.index("# Determine final exit price", start)
    return source[start:end]


def test_pending_fill_does_not_raise():
    block = _auto_mode_exit_block(SOURCE)
    assert "raise DataUnavailableError" not in block, (
        "A pending fill (success=True, filled_price=None) is a routine broker response, not "
        "an error - it must not raise. By this point the protective bracket may already be "
        "cancelled and the sell may already be in flight; raising abandons all DB bookkeeping "
        "and leaves the broker and DB silently diverged."
    )


def test_pending_fill_falls_back_to_estimated_price():
    block = _auto_mode_exit_block(SOURCE)
    assert "actual_fill_price = exit_price" in block, (
        "On a pending fill, actual_fill_price must fall back to the exit engine's "
        "evaluation-time quote so downstream code (final_exit_price fail-fast check) has a "
        "placeholder value and the trade can be recorded via PENDING_FILL_RECONCILIATION."
    )


def test_confirmed_fill_still_clears_is_estimated_price():
    block = _auto_mode_exit_block(SOURCE)
    assert "is_estimated_price = False" in block, (
        "A genuinely confirmed fill (filled_price is not None) must still clear "
        "is_estimated_price so real P&L gets recorded immediately, not deferred."
    )


def test_partial_fill_verification_only_runs_on_confirmed_fill():
    block = _auto_mode_exit_block(SOURCE)
    # The filled-quantity verification call must be scoped under the confirmed-fill branch,
    # not run unconditionally for a pending order that has no real filled quantity yet.
    confirmed_branch = block.split("is_estimated_price = False", 1)[1]
    assert "_get_order_filled_quantity" in confirmed_branch
