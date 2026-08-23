#!/usr/bin/env python3
"""Regression test: a partial exit must reduce algo_trades.quantity, not leave it frozen
at entry_quantity.

CRITICAL (goal session, "before real money" finance-accuracy audit): algo_trades.quantity
was never updated on a partial exit - only algo_positions.quantity was.
algo/orchestration/position_sync.py's sync_positions_from_trades() (runs before every
Phase 1) recomputes algo_positions.quantity fresh from SUM(algo_trades.quantity) for
every symbol's still-open trades, so the correct post-partial-exit
algo_positions.quantity got silently overwritten back to the stale, too-high
entry_quantity on the very next orchestrator run - live-reproduced via TRD-29F350E6A9
(RPM): a real partial exit correctly set algo_positions.quantity=11, but two days later
algo_positions.quantity read back 22 (the original full size). In live/auto mode the
final exit would submit a sell order for shares that no longer existed.

Static source check rather than a full mocked call to _execute_exit, matching the
precedent in test_exit_handler_clears_pending_client_order_id.py: _execute_exit has a
large dependency graph (guards, lock/fetch, bracket cancellation, order submission,
position update) impractical to mock end-to-end here.
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()


def _partial_exit_update_statement(source: str) -> str:
    """Extract the partial-exit branch's `UPDATE algo_trades ... WHERE trade_id = %s` block -
    the one that sets partial_exits_log (unique to the partial-exit branch, unlike the two
    full-exit branches)."""
    match = re.search(
        r"UPDATE algo_trades\s+SET partial_exits_log = .*?WHERE trade_id = %s",
        source,
        re.DOTALL,
    )
    assert match, "expected to find the partial-exit UPDATE algo_trades statement - source may have been restructured"
    return match.group(0)


def test_partial_exit_update_sets_quantity():
    stmt = _partial_exit_update_statement(SOURCE)
    assert "quantity = %s" in stmt, (
        "the partial-exit UPDATE algo_trades statement must set quantity to the "
        "remaining share count (current_qty - shares_to_exit), or "
        "position_sync.py's SUM(algo_trades.quantity) will keep recomputing "
        "algo_positions.quantity from the stale, too-high entry_quantity on every "
        f"subsequent orchestrator run:\n{stmt}"
    )


def test_new_qty_partial_computed_before_the_update():
    """The new_qty_partial variable referenced in the UPDATE's params must actually be
    computed as current_qty - shares_to_exit (the remaining shares), not left as some
    other value (e.g. accidentally reusing shares_to_exit itself, which would zero out
    quantity instead of reducing it)."""
    match = re.search(
        r"new_qty_partial\s*=\s*float\(Decimal\(str\(current_qty\)\)\s*-\s*Decimal\(str\(shares_to_exit\)\)\)",
        SOURCE,
    )
    assert match, (
        "expected new_qty_partial = current_qty - shares_to_exit (as Decimals, for exact "
        "arithmetic) immediately before the partial-exit UPDATE - if this expression "
        "changed, verify the replacement still computes the correct remaining share count"
    )
