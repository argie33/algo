"""Regression test for a real-money-readiness audit finding: AlpacaSyncManager.
_sync_untracked_positions's "clear resolved untracked positions" step used to only bump
`updated_at` for symbols no longer in the current orphan_symbols list - it never actually
removed or flagged them as resolved.

No consumer of algo_untracked_positions filters by last_seen_at/staleness (grepped
repo-wide: lambda/api/routes/algo_handlers/dashboard/positions.py's untracked-position count
and list both do a plain unconditional SELECT/COUNT), so a row created once - a manual
broker position later closed at Alpaca, or one that became properly algo-tracked - stayed in
the dashboard's "Untracked Broker Position(s)" alert/count forever. For a real-money
dashboard, a permanently-stuck phantom alert trains an operator to stop trusting the one
alert meant to catch a genuinely orphaned, un-stopped position.

Fix: actually DELETE rows for symbols no longer orphaned this cycle, matching migration
1118's own column comment ("last_seen_at ... used to detect closed positions").
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager():
    return object.__new__(AlpacaSyncManager)


def test_resolved_untracked_position_is_deleted_not_just_touched():
    """A symbol that is no longer in the current orphan_symbols list must be DELETEd from
    algo_untracked_positions, not merely have its updated_at timestamp refreshed."""
    manager = _make_manager()
    cur = MagicMock()
    cur.fetchone.return_value = None
    cur.rowcount = 2

    with patch("algo.reporting.notifications.notify"):
        untracked_count, untracked_closed_count = manager._sync_untracked_positions(
            cur, orphan_symbols=[], alpaca_positions=[]
        )

    assert untracked_closed_count == 2

    delete_calls = [
        c for c in cur.execute.call_args_list if "algo_untracked_positions" in c.args[0] and "DELETE" in c.args[0]
    ]
    assert delete_calls, (
        "expected a DELETE against algo_untracked_positions for symbols no longer orphaned - "
        f"actual execute calls: {[c.args[0] for c in cur.execute.call_args_list]}"
    )
    update_calls = [
        c
        for c in cur.execute.call_args_list
        if "algo_untracked_positions" in c.args[0] and c.args[0].strip().upper().startswith("UPDATE")
    ]
    assert not update_calls, "must not silently bump updated_at instead of actually clearing resolved rows"


def test_still_orphaned_symbol_is_not_deleted():
    """A symbol still present in orphan_symbols this cycle must survive the cleanup DELETE
    (it's excluded via `symbol != ALL(orphan_symbols)`) - only verifying the DELETE targets
    the right parameter, since a MagicMock cursor doesn't execute real SQL."""
    manager = _make_manager()
    cur = MagicMock()
    cur.fetchone.return_value = (1,)
    cur.rowcount = 1

    with patch("algo.reporting.notifications.notify"):
        manager._sync_untracked_positions(
            cur,
            orphan_symbols=["AAPL"],
            alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
        )

    delete_calls = [
        c for c in cur.execute.call_args_list if "algo_untracked_positions" in c.args[0] and "DELETE" in c.args[0]
    ]
    assert len(delete_calls) == 1
    assert delete_calls[0].args[1] == (["AAPL"],)
