#!/usr/bin/env python3
"""Regression test for the crash-safe exit idempotency fix (migration 1166).

executor.py's _send_alpaca_exit() persists algo_trades.pending_exit_client_order_id
BEFORE calling Alpaca so a crash-recovery retry can reuse it (see
test_order_manager_exit_idempotency.py for that half). This file guards the other
half: every UPDATE algo_trades statement in executor_exit_handler.py's _execute_exit()
that records a *confirmed* exit (full real-fill, full estimated-fill, and partial)
must clear that column back to NULL - otherwise a genuinely new, later exit attempt
on the same trade would incorrectly reuse a stale id from an already-completed prior
exit instead of minting a fresh one.

Static source check rather than a full mocked call: _execute_exit has a large
dependency graph (guards, lock/fetch, bracket cancellation, order submission,
position update) that would need extensive mocking to exercise end-to-end here:
the executor-level behavior (persist-before-call, reuse-if-pending) is already
covered live in test_order_manager_exit_idempotency.py.
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()


def _update_algo_trades_statements(source: str) -> list[str]:
    """Extract each `UPDATE algo_trades ... WHERE trade_id = %s` SQL block."""
    return re.findall(r'UPDATE algo_trades\s+SET.*?WHERE trade_id = %s', source, re.DOTALL)


def test_found_all_three_confirmed_exit_update_statements():
    """Sanity check the extraction itself finds the expected statements - if this count
    changes, the assertion below needs to be re-examined, not silently pass fewer checks."""
    statements = _update_algo_trades_statements(SOURCE)
    assert len(statements) == 3, (
        f"expected 3 UPDATE algo_trades...WHERE trade_id statements (real-fill full exit, "
        f"estimated-fill full exit, partial exit), found {len(statements)} - update this "
        f"test if _execute_exit's UPDATE statements were intentionally restructured"
    )


def test_every_confirmed_exit_update_clears_pending_client_order_id():
    statements = _update_algo_trades_statements(SOURCE)
    for i, stmt in enumerate(statements):
        assert "pending_exit_client_order_id = NULL" in stmt, (
            f"UPDATE algo_trades statement #{i} (recording a confirmed exit) must clear "
            f"pending_exit_client_order_id, or a later genuine exit attempt on the same "
            f"trade will incorrectly reuse a stale id from this completed exit:\n{stmt}"
        )
