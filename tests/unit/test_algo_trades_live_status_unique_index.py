"""Verifies the partial unique index on algo_trades(symbol)/algo_positions(symbol) covers
every non-terminal status a real order can be inserted with, not just the literal 'open'.

Migration 007 added a UNIQUE INDEX on algo_trades(symbol) WHERE status = 'open' to stop
duplicate open positions for the same symbol, and algo/orchestrator/phase8_entry_execution.py's
duplicate-entry guard cites it as the DB-level backstop for its own known-non-atomic
check-then-insert race. That claim was false for real (execution_mode="auto") trades: a live
order that actually fills is inserted with status='filled' or 'partially_filled' (the
broker-verified status), never 'open' - 'open' is only used by the paper/dry execution_mode
branch. So the old index never fired for a live trade. Migration 1158 widened it; these tests
prove the new index actually rejects a second live-status row where the old one wouldn't have.
"""

import psycopg2
import pytest

BASE_TRADE = {
    "trade_id": "TEST-LIVE-STATUS-IDX-1",
    "symbol": "TESTLIVEIDX",
    "signal_date": "2026-01-01",
    "trade_date": "2026-01-01",
    "entry_price": 100.0,
    "entry_quantity": 10,
    "status": "filled",
}

BASE_POSITION = {
    "position_id": "TEST-LIVE-STATUS-IDX-POS-1",
    "symbol": "TESTLIVEIDX",
    "quantity": 10,
    "avg_entry_price": 100.0,
    "status": "open",
    "entry_date": "2026-01-01",
    "entry_price": 100.0,
    "stop_loss_price": 95.0,
    "current_stop_price": 95.0,
}


@pytest.fixture
def conn():
    try:
        connection = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")
    yield connection
    connection.rollback()
    connection.close()


def _insert_trade(conn, trade_id: str, status: str, entry_price: float = 100.0) -> None:
    row = dict(BASE_TRADE, trade_id=trade_id, status=status, entry_price=entry_price)
    columns = list(row.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO algo_trades ({', '.join(columns)}) VALUES ({placeholders})",
        [row[c] for c in columns],
    )


def _insert_position(conn, position_id: str, status: str) -> None:
    row = dict(BASE_POSITION, position_id=position_id, status=status)
    columns = list(row.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO algo_positions ({', '.join(columns)}) VALUES ({placeholders})",
        [row[c] for c in columns],
    )


def test_second_filled_trade_for_same_symbol_is_rejected(conn):
    """A live (auto-mode) order that fills writes status='filled', not 'open' - the exact
    gap the pre-1158 index (status='open' only) missed. Uses a distinct entry_price on the
    second insert so the pre-existing (symbol, signal_date, entry_price) constraint - a
    separate, unrelated legacy check - can't be the one raising instead of our new index."""
    _insert_trade(conn, "TEST-LIVE-STATUS-IDX-1", "filled", entry_price=100.0)
    with pytest.raises(psycopg2.errors.UniqueViolation, match="algo_trades_symbol_live_status_idx"):
        _insert_trade(conn, "TEST-LIVE-STATUS-IDX-2", "filled", entry_price=101.0)


def test_partially_filled_conflicts_with_filled_for_same_symbol(conn):
    _insert_trade(conn, "TEST-LIVE-STATUS-IDX-1", "filled", entry_price=100.0)
    with pytest.raises(psycopg2.errors.UniqueViolation, match="algo_trades_symbol_live_status_idx"):
        _insert_trade(conn, "TEST-LIVE-STATUS-IDX-2", "partially_filled", entry_price=101.0)


def test_closed_trade_does_not_block_a_new_live_trade(conn):
    """Terminal statuses must never block re-entry after a position is closed."""
    _insert_trade(conn, "TEST-LIVE-STATUS-IDX-1", "closed", entry_price=100.0)
    _insert_trade(conn, "TEST-LIVE-STATUS-IDX-2", "filled", entry_price=101.0)  # must not raise


def test_second_open_position_for_same_symbol_is_rejected(conn):
    """algo_positions previously had no uniqueness enforcement on symbol at all."""
    _insert_position(conn, "TEST-LIVE-STATUS-IDX-POS-1", "open")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _insert_position(conn, "TEST-LIVE-STATUS-IDX-POS-2", "open")


def test_paper_open_conflicts_with_open_position_for_same_symbol(conn):
    _insert_position(conn, "TEST-LIVE-STATUS-IDX-POS-1", "open")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _insert_position(conn, "TEST-LIVE-STATUS-IDX-POS-2", "paper_open")


def test_closed_position_does_not_block_a_new_open_position(conn):
    _insert_position(conn, "TEST-LIVE-STATUS-IDX-POS-1", "closed")
    _insert_position(conn, "TEST-LIVE-STATUS-IDX-POS-2", "open")  # must not raise
