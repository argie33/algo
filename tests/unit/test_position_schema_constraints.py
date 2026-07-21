"""Verifies algo_positions enforces its required fields at the DB level.

Replaces four always-skipped stubs in tests/test_session_282_integration.py
(TestPositionCreationFieldValidation) that never actually connected to a
database or asserted anything. These run against a real local Postgres
inside a transaction that is always rolled back, so no test data persists.
"""

import psycopg2
import pytest

BASE_ROW = {
    "position_id": "TEST-POSITION-SCHEMA-CONSTRAINTS",
    "symbol": "TEST",
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


def _insert(conn, overrides: dict | None = None, omit: set[str] | None = None) -> None:
    row = dict(BASE_ROW)
    if overrides:
        row.update(overrides)
    if omit:
        for key in omit:
            row.pop(key, None)
    columns = list(row.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO algo_positions ({', '.join(columns)}) VALUES ({placeholders})",
        [row[c] for c in columns],
    )


def test_position_requires_stop_loss_price(conn):
    with pytest.raises(psycopg2.errors.NotNullViolation):
        _insert(conn, omit={"stop_loss_price"})


def test_position_requires_entry_price(conn):
    with pytest.raises(psycopg2.errors.NotNullViolation):
        _insert(conn, omit={"entry_price"})


def test_position_requires_entry_date(conn):
    with pytest.raises(psycopg2.errors.NotNullViolation):
        _insert(conn, omit={"entry_date"})


def test_position_requires_status(conn):
    with pytest.raises(psycopg2.errors.NotNullViolation):
        _insert(conn, omit={"status"})


def test_position_requires_avg_entry_price(conn):
    with pytest.raises(psycopg2.errors.NotNullViolation):
        _insert(conn, omit={"avg_entry_price"})


def test_position_target_levels_hit_defaults_to_zero(conn):
    _insert(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT target_levels_hit FROM algo_positions WHERE position_id = %s",
        (BASE_ROW["position_id"],),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 0
