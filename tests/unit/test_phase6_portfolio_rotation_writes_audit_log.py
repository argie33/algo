#!/usr/bin/env python3
"""Regression test: Phase 6's portfolio-rotation-safety-check force-close must go through a
real broker-side exit (with its own atomic algo_audit_log write), not a raw DB-only close.

BUG FOUND (goal session, "before real money" audit, compliance/audit-log completeness
pass): the Session 43 "portfolio rotation safety check" (fires when the portfolio is full
and the exit engine only raised stops, never actually exited anything - force-closes the
oldest position to prevent deadlock) originally did raw UPDATE algo_positions/algo_trades
SQL directly, completely bypassing algo_audit_log - unlike executor_exit_handler.py's
_execute_exit(), which writes the audit log entry as part of the SAME atomic transaction as
the position/trade UPDATE ("TRANSACTION GUARD 6: Audit log is part of atomic transaction").
A first fix added a manual algo_audit_log INSERT to the same raw-SQL block.

SECOND, MORE SERIOUS BUG FOUND on top of that fix: the raw-SQL close never cancelled the
broker-side bracket order or submitted a real sell in auto mode - the DB recorded the
position as closed while the real position (and its real capital at risk) stayed fully open
at the broker, invisible to every downstream system keying off algo_positions.status. Fixed
by routing through trade_executor.exit_trade() instead - the same real-exit path every other
exit in this system uses - which handles bracket cancellation, real order submission, AND
the atomic algo_audit_log write (via ExitHandler.execute_exit()'s "TRANSACTION GUARD 6")
automatically. The manual audit_log INSERT this test originally checked for is gone because
it's now redundant, not because the audit trail regressed.

Static source check rather than a full mocked call to run(): the function has a very large
dependency graph (trade_executor, ExitEngine, multiple DB cursors) impractical to mock
end-to-end here - matches the existing precedent in
test_exit_handler_clears_pending_client_order_id.py for the same reason.
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text()


def _portfolio_rotation_block() -> str:
    match = re.search(
        r"# BUG FOUND \(goal session.*?except Exception as e:\s*\n\s*logger\.error",
        SOURCE,
        re.DOTALL,
    )
    assert match, "expected to find the portfolio rotation safety check block - source may have been restructured"
    return match.group(0)


def test_portfolio_rotation_force_close_routes_through_trade_executor():
    """Must go through trade_executor.exit_trade() (real broker-side exit + atomic audit log
    write), not a raw UPDATE algo_positions/algo_trades SQL block - a raw DB-only close never
    cancels the broker bracket order or submits a real sell, leaving real capital at risk at
    the broker while the DB says 'closed'."""
    block = _portfolio_rotation_block()
    assert "trade_executor.exit_trade(" in block, (
        "the portfolio rotation safety check must force-close via trade_executor.exit_trade() "
        "so the broker-side bracket order is cancelled and a real exit order is submitted in "
        "auto mode - a raw UPDATE algo_positions/algo_trades SQL block only fakes the close in "
        "the DB while the real position stays open at the broker"
    )
    assert not re.search(r"UPDATE\s+algo_positions\s+SET\s+status\s*=\s*'closed'", block), (
        "found a raw UPDATE algo_positions...status='closed' - this bypasses the broker "
        "entirely; force-close must go through trade_executor.exit_trade() instead"
    )


def test_audit_log_action_type_matches_exit_prefix_convention():
    """The exit_trade() call must pass exit_stage="portfolio_rotation_safety_check" (or an
    exit_reason that resolves to an 'exit_*' action_type) so the resulting algo_audit_log
    entry is visible to any query scoped to real exit events - e.g.
    _compute_cumulative_pnl's `action_type LIKE 'exit_%'` aggregation - and specifically
    identifiable as a portfolio-rotation forced close, not generic 'exit_manual'. Without
    exit_stage, ExitHandler.execute_exit() falls back to f"exit_{exit_stage or 'manual'}",
    silently losing the specific reason from the action_type (though it still survives in the
    audit log's `details` JSON via exit_reason)."""
    block = _portfolio_rotation_block()
    match = re.search(r'exit_stage\s*=\s*"(portfolio_rotation_safety_check)"', block)
    assert match, (
        "expected trade_executor.exit_trade(...) to be called with "
        'exit_stage="portfolio_rotation_safety_check" so the audit log action_type reads '
        "exit_portfolio_rotation_safety_check instead of falling back to generic exit_manual, "
        f"block:\n{block}"
    )


def test_audit_log_write_happens_in_the_same_transaction_as_the_position_close():
    """exit_trade() must be called with cur=cur_w (the same cursor used for the rest of the
    portfolio-rotation block's writes), not a separate connection/transaction - otherwise a
    failure wouldn't correctly roll back the whole force-close as one atomic unit."""
    block = _portfolio_rotation_block()
    assert "trade_executor.exit_trade(" in block
    call_start = block.index("trade_executor.exit_trade(")
    call_end = block.index(")", block.index("cur=cur_w", call_start)) if "cur=cur_w" in block[call_start:] else -1
    assert call_end != -1, (
        "expected trade_executor.exit_trade(...) to pass cur=cur_w - without it, the force-close "
        "exit (and its audit log write) would run in a separate transaction from the rest of "
        "this block, breaking atomicity"
    )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
