#!/usr/bin/env python3
"""Regression test: Phase 6's portfolio-rotation-safety-check force-close must write an
algo_audit_log entry, like every other exit path in this codebase does.

BUG FOUND (goal session, "before real money" audit, compliance/audit-log completeness
pass): the Session 43 "portfolio rotation safety check" (fires when the portfolio is full
and the exit engine only raised stops, never actually exited anything - force-closes the
oldest position to prevent deadlock) does raw UPDATE algo_positions/algo_trades SQL
directly, completely bypassing algo_audit_log - unlike executor_exit_handler.py's
_execute_exit(), which writes the audit log entry as part of the SAME atomic transaction as
the position/trade UPDATE ("TRANSACTION GUARD 6: Audit log is part of atomic transaction").

Live-confirmed: TRD-313426C1FA (AII, closed 2026-08-20 via this exact path) had 15 routine
position_review audit entries but zero record of the actual closure event - invisible to any
compliance query scoped to real exit events (action_type LIKE 'exit_%', the same pattern
_compute_cumulative_pnl uses to sum multi-leg exit P&L), and never reaches TCA/slippage
tracking either.

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
        r"# FIX SESSION 43: Portfolio rotation safety check.*?except Exception as e:\s*\n\s*logger\.error",
        SOURCE,
        re.DOTALL,
    )
    assert match, (
        "expected to find the Session 43 portfolio rotation safety check block - source may have been restructured"
    )
    return match.group(0)


def test_portfolio_rotation_force_close_writes_audit_log():
    block = _portfolio_rotation_block()
    assert "INSERT INTO algo_audit_log" in block, (
        "the portfolio rotation safety check force-closes a real position but never wrote "
        "an algo_audit_log entry - every other exit path in this codebase (see "
        "executor_exit_handler.py's TRANSACTION GUARD 6) logs the exit as part of the same "
        "atomic transaction as the position/trade UPDATE; this force-close path must too"
    )


def test_audit_log_action_type_matches_exit_prefix_convention():
    """Must start with 'exit_' so it's visible to any query scoped to real exit events -
    e.g. _compute_cumulative_pnl's `action_type LIKE 'exit_%'` aggregation, and the same
    completeness check that found this bug: `algo_trades t WHERE t.status='closed' AND NOT
    EXISTS (SELECT 1 FROM algo_audit_log a WHERE a.action_type LIKE 'exit_%' AND ...)`."""
    block = _portfolio_rotation_block()
    match = re.search(r'"(exit_[a-z_]+)"', block)
    assert match, f"expected an 'exit_*' action_type literal in the audit log INSERT, block:\n{block}"


def test_audit_log_write_happens_in_the_same_transaction_as_the_position_close():
    """The INSERT must appear inside the same `with DatabaseContext("write") as cur_w:`
    block as the UPDATE statements, using the same cur_w cursor - not a separate
    connection/transaction, or a failure here wouldn't correctly roll back the whole
    force-close as one atomic unit."""
    block = _portfolio_rotation_block()
    insert_idx = block.index("INSERT INTO algo_audit_log")
    update_positions_idx = block.index("UPDATE algo_positions")
    update_trades_idx = block.index("UPDATE algo_trades")
    assert update_positions_idx < update_trades_idx < insert_idx, (
        "expected UPDATE algo_positions, then UPDATE algo_trades, then the audit log INSERT, "
        "all in that order within the same transaction block"
    )
    # Every DB call between the position UPDATE and the audit INSERT must use the same
    # cursor variable (cur_w), confirming they share one transaction.
    between = block[update_positions_idx:insert_idx]
    assert "cur_w.execute" in between
    assert not re.search(r"\bcur\.execute\(", between), (
        "found a call using a different cursor variable ('cur') between the position update "
        "and the audit log insert - this would not share the same transaction as cur_w"
    )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
