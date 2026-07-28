"""Regression test: DailyReconciliation's realized-P&L-today query in
algo/infrastructure/reconciliation.py must not treat "every closed trade today is still
pending broker-fill confirmation" as data corruption.

phase9_reconciliation.py deliberately leaves profit_loss_dollars/estimated_exit_price set
this way for exits whose broker fill hasn't been confirmed yet (see its own comment: "leave
profit_loss_dollars/pct NULL (unknown, not zero)... so reconcile_exit_fills()... can replace
this guess with the broker's actual fill price"). SUM(profit_loss_dollars) correctly excludes
those NULL rows when only SOME of the day's closed trades are pending - but when ALL of them
are pending, Postgres SUM() over an all-NULL group returns NULL for the whole aggregate, and
the old code could not tell that apart from genuine corruption (a NULL profit_loss_dollars
with no estimated_exit_price marker at all) - live-reproduced 2026-07-27: 9 closed trades, all
pending, wrongly raised "[RECONCILIATION CRITICAL] ... data corruption" and errored Phase 9.

Fixed by counting pending (estimated_exit_price IS NOT NULL) vs genuinely-corrupt
(profit_loss_dollars AND estimated_exit_price both NULL) separately: only the latter raises.
"""

import psycopg2
import pytest

BASE_TRADE = {
    "symbol": "TESTRECONPNL",
    "signal_date": "2026-01-01",
    "trade_date": "2026-01-01",
    "entry_price": 100.0,
    "entry_quantity": 10,
    "status": "closed",
    "exit_date": "2026-01-02",
}

QUERY = """
    SELECT COUNT(*) as closed_count,
           SUM(profit_loss_dollars) as realized_pnl_today,
           COUNT(*) FILTER (
               WHERE profit_loss_dollars IS NULL AND estimated_exit_price IS NOT NULL
           ) as pending_count,
           COUNT(*) FILTER (
               WHERE profit_loss_dollars IS NULL AND estimated_exit_price IS NULL
           ) as corrupt_count
    FROM algo_trades
    WHERE status = 'closed' AND exit_date = %s
"""


@pytest.fixture
def conn():
    try:
        connection = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")
    yield connection
    connection.rollback()
    connection.close()


def _insert_trade(conn, trade_id, profit_loss_dollars, estimated_exit_price, entry_price=100.0):
    row = dict(
        BASE_TRADE,
        trade_id=trade_id,
        profit_loss_dollars=profit_loss_dollars,
        estimated_exit_price=estimated_exit_price,
        entry_price=entry_price,
    )
    columns = list(row.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO algo_trades ({', '.join(columns)}) VALUES ({placeholders})",
        [row[c] for c in columns],
    )


def test_all_pending_gives_null_sum_but_zero_corrupt(conn):
    """All-NULL group: SUM() returns NULL, but corrupt_count must be 0 (all have the
    pending marker) so the caller knows to treat this as pending, not corruption."""
    _insert_trade(conn, "TEST-RECON-PNL-1", None, 101.0, entry_price=100.0)
    _insert_trade(conn, "TEST-RECON-PNL-2", None, 102.0, entry_price=100.01)
    cur = conn.cursor()
    cur.execute(QUERY, ("2026-01-02",))
    closed_count, realized_pnl_today, pending_count, corrupt_count = cur.fetchone()
    assert closed_count == 2
    assert realized_pnl_today is None
    assert pending_count == 2
    assert corrupt_count == 0


def test_mixed_pending_and_resolved_excludes_pending_from_sum(conn):
    _insert_trade(conn, "TEST-RECON-PNL-3", 50.0, None, entry_price=100.0)
    _insert_trade(conn, "TEST-RECON-PNL-4", None, 103.0, entry_price=100.01)
    cur = conn.cursor()
    cur.execute(QUERY, ("2026-01-02",))
    closed_count, realized_pnl_today, pending_count, corrupt_count = cur.fetchone()
    assert closed_count == 2
    assert float(realized_pnl_today) == 50.0
    assert pending_count == 1
    assert corrupt_count == 0


def test_null_pnl_with_no_pending_marker_is_flagged_corrupt(conn):
    """No estimated_exit_price at all alongside a NULL profit_loss_dollars is genuinely
    unexplained - must still be flagged so the caller raises."""
    _insert_trade(conn, "TEST-RECON-PNL-5", None, None)
    cur = conn.cursor()
    cur.execute(QUERY, ("2026-01-02",))
    closed_count, realized_pnl_today, pending_count, corrupt_count = cur.fetchone()
    assert closed_count == 1
    assert pending_count == 0
    assert corrupt_count == 1


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
