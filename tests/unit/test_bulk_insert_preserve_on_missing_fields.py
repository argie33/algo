"""Regression test for the 2026-08-17 PRI net_income bug: BulkInsertManager.bulk_insert()
builds its ON CONFLICT DO UPDATE SET column list from the UNION of keys across every row in
a batch. For a per-symbol multi-fiscal-year batch (financial statements: one bulk_insert()
call = one symbol's own fiscal years), a column present on SOME fiscal years but absent from
one specific row's fetch gets forced to SQL NULL on that row (empty CSV field + COPY
FORCE_NULL), and `ON CONFLICT DO UPDATE SET col = EXCLUDED.col` then overwrites a
PREVIOUSLY-CORRECT value with that NULL - live-confirmed for PRI (Primerica) FY2025
net_income after a run whose fetch for that specific year didn't include the field.

`preserve_on_missing_fields` opts specific columns into `COALESCE(EXCLUDED.col, table.col)`
instead, so a row missing the field keeps its existing value rather than being nulled.

Runs against a real local Postgres. bulk_insert()'s schema lookup filters
`table_schema = 'public'`, which excludes session-scoped TEMP tables (they live under
`pg_temp_N`) - each test creates a real table and drops it in a finally block instead of
relying on rollback.
"""

import psycopg2
import pytest

from utils.bulk_insert_manager import BulkInsertManager
from utils.db.pooled_context_var import set_pooled_connection


@pytest.fixture
def conn():
    try:
        connection = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")
    # bulk_insert() opens its own DatabaseContext("write"), which by default acquires a
    # DIFFERENT connection from the pool - a table created on this fixture's connection would
    # need to be committed (not just a same-session TEMP table) to be visible to it.
    # Registering this connection as the thread's pooled connection makes DatabaseContext
    # reuse this exact connection instead of pulling an unrelated one from the pool.
    set_pooled_connection(connection)
    yield connection
    set_pooled_connection(None)
    connection.rollback()
    connection.close()


@pytest.fixture
def table(conn, request):
    name = f"test_bulk_insert_{request.node.name}"[:63]
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {name}")
    cur.execute(
        f"CREATE TABLE {name} ("
        "symbol text, fiscal_year int, net_income numeric, revenue numeric, "
        "PRIMARY KEY (symbol, fiscal_year))"
    )
    conn.commit()
    yield name
    cur.execute(f"DROP TABLE IF EXISTS {name}")
    conn.commit()


def test_missing_field_nulls_existing_value_without_preserve_opt_in(conn, table):
    """Baseline: default behavior (no preserve_on_missing_fields) reproduces the bug - a
    batch-mate row pulling `net_income` into the column union causes a row missing that key
    to NULL out its own previously-good value."""
    cur = conn.cursor()
    mgr = BulkInsertManager(table, ("symbol", "fiscal_year"))

    # First run: both fiscal years have net_income.
    mgr.bulk_insert(
        [
            {"symbol": "PRI", "fiscal_year": 2024, "net_income": 470518000, "revenue": 3089143000},
            {"symbol": "PRI", "fiscal_year": 2025, "net_income": 751234000, "revenue": 3291713000},
        ]
    )
    cur.execute(f"SELECT net_income FROM {table} WHERE symbol = 'PRI' AND fiscal_year = 2025")
    assert cur.fetchone()[0] == 751234000

    # Second run (simulates a re-fetch where FY2025's net_income concept wasn't found this
    # time, e.g. stale code): FY2025's row is missing the "net_income" key entirely, but
    # FY2024's row still has it, so it's still in the batch-wide column union.
    mgr.bulk_insert(
        [
            {"symbol": "PRI", "fiscal_year": 2024, "net_income": 470518000, "revenue": 3089143000},
            {"symbol": "PRI", "fiscal_year": 2025, "revenue": 3291713000},  # net_income key absent
        ]
    )
    cur.execute(f"SELECT net_income FROM {table} WHERE symbol = 'PRI' AND fiscal_year = 2025")
    # BUG (pre-fix default behavior): the previously-correct value is erased.
    assert cur.fetchone()[0] is None


def test_preserve_on_missing_fields_keeps_existing_value(conn, table):
    """With net_income opted into preserve_on_missing_fields, the same scenario above must
    keep the previously-correct value instead of nulling it."""
    cur = conn.cursor()
    mgr = BulkInsertManager(table, ("symbol", "fiscal_year"), preserve_on_missing_fields=frozenset({"net_income"}))

    mgr.bulk_insert(
        [
            {"symbol": "PRI", "fiscal_year": 2024, "net_income": 470518000, "revenue": 3089143000},
            {"symbol": "PRI", "fiscal_year": 2025, "net_income": 751234000, "revenue": 3291713000},
        ]
    )
    cur.execute(f"SELECT net_income FROM {table} WHERE symbol = 'PRI' AND fiscal_year = 2025")
    assert cur.fetchone()[0] == 751234000

    mgr.bulk_insert(
        [
            {"symbol": "PRI", "fiscal_year": 2024, "net_income": 470518000, "revenue": 3089143000},
            {"symbol": "PRI", "fiscal_year": 2025, "revenue": 3291713000},  # net_income key absent
        ]
    )
    cur.execute(f"SELECT net_income, revenue FROM {table} WHERE symbol = 'PRI' AND fiscal_year = 2025")
    row = cur.fetchone()
    assert row[0] == 751234000, "preserved field must keep its existing value, not be NULLed"
    assert row[1] == 3291713000, "non-preserved field present in this row's own data must still update normally"


def test_preserve_on_missing_fields_still_writes_real_new_values(conn, table):
    """A genuinely new/updated value for a preserved field must still overwrite the old one -
    COALESCE(EXCLUDED.col, table.col) only falls back to the existing value when EXCLUDED.col
    is itself NULL, never when it's a real (possibly different) value."""
    cur = conn.cursor()
    mgr = BulkInsertManager(table, ("symbol", "fiscal_year"), preserve_on_missing_fields=frozenset({"net_income"}))

    mgr.bulk_insert([{"symbol": "PRI", "fiscal_year": 2025, "net_income": 751234000}])
    mgr.bulk_insert([{"symbol": "PRI", "fiscal_year": 2025, "net_income": 999999999}])  # a real restated value

    cur.execute(f"SELECT net_income FROM {table} WHERE symbol = 'PRI' AND fiscal_year = 2025")
    assert cur.fetchone()[0] == 999999999
