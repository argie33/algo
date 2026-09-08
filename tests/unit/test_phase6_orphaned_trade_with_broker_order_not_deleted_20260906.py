"""Regression test: phase6_exit_execution.py's orphaned-trade cleanup must NOT delete
an algo_trades row that has a real alpaca_order_id attached.

Bug (found 2026-09-06, real-money-readiness audit): the orphaned-trade cleanup DELETE
matched ANY row with position_id IS NULL, regardless of alpaca_order_id.
executor_entry_handler.py persists alpaca_order_id on the algo_trades row at INSERT
time - before the position row is created - so a row with position_id IS NULL but
alpaca_order_id IS NOT NULL means a REAL broker order was actually submitted/filled and
the crash happened between that fill and the position-row insert, not before order
submission at all. Deleting that row permanently erased the only DB trace of a real,
live, broker-side position (including the alpaca_order_id needed to find and manage it)
after just 5 minutes in auto mode.

Fixed: the DELETE is scoped to alpaca_order_id IS NULL only (the genuinely harmless
case). A row with alpaca_order_id IS NOT NULL is selected separately and alerted for
manual review instead of being auto-deleted.

Source inspection rather than a full mocked run: the surrounding function has a large
dependency graph (see test_phase6_concentration_uses_account_equity.py's precedent for
this exact file/class of change).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text(encoding="utf-8")


def _orphan_cleanup_block() -> str:
    start = SOURCE.index("# CLEANUP: Remove orphaned trades")
    end = SOURCE.index("# CRITICAL FIX 2026-07-30: ALWAYS validate Phase 3 data")
    return SOURCE[start:end]


class TestOrphanedTradeWithBrokerOrderNotDeleted:
    def test_delete_statement_excludes_rows_with_a_real_broker_order(self):
        block = _orphan_cleanup_block()
        delete_stmt = block[block.index("DELETE FROM algo_trades") : block.index("orphaned_count = cur.rowcount")]
        assert "alpaca_order_id IS NULL" in delete_stmt, (
            "the auto-DELETE must be scoped to alpaca_order_id IS NULL - a row with a real "
            "broker order attached must never be silently deleted."
        )

    def test_rows_with_broker_order_are_selected_and_not_deleted(self):
        block = _orphan_cleanup_block()
        select_marker = "SELECT trade_id, symbol, alpaca_order_id, updated_at FROM algo_trades"
        assert select_marker in block, (
            "orphaned rows WITH a real alpaca_order_id must be queried separately (not "
            "deleted) so they can be alerted for manual reconciliation."
        )
        # The query immediately following this SELECT must filter on
        # alpaca_order_id IS NOT NULL, not another DELETE.
        after_select = block[block.index(select_marker) :]
        assert "alpaca_order_id IS NOT NULL" in after_select[:400]

    def test_broker_order_case_sends_a_critical_alert(self):
        block = _orphan_cleanup_block()
        assert 'notify(\n                            "critical"' in block or '"critical"' in block
        assert "manual reconciliation" in block.lower()

    def test_notify_failure_is_not_swallowed(self):
        block = _orphan_cleanup_block()
        notify_idx = block.index("notify(")
        guard_region = block[notify_idx : notify_idx + 1200]
        assert "except NotificationError" in guard_region
        assert "raise RuntimeError" in guard_region, (
            "a failed alert for an orphaned real-broker-order trade must not be silently "
            "swallowed - operators must be aware of potentially unmanaged positions."
        )
