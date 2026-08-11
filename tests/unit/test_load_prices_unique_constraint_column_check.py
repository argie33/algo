"""Verifies PriceLoader._verify_unique_constraint_exists() checks the constraint's actual
columns, not just that *some* UNIQUE constraint exists on the table.

Regression for a real bug: the pre-fix query was
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_name = %s AND constraint_type = 'UNIQUE'
which matches ANY unique constraint on the table regardless of which columns it covers.
A table carrying an unrelated UNIQUE constraint (e.g. on a surrogate column) while its
real (symbol, date) pair has no such constraint would silently pass this "CRITICAL"
duplicate-prevention check - exactly the class of bug this check exists to catch (see
the docstring's own reference to the 20,150-duplicate-row incident).

Runs against a real local Postgres inside a transaction that is always rolled back, so
no test data persists.
"""

import psycopg2
import pytest

from loaders.load_prices import PriceLoader


@pytest.fixture
def conn():
    try:
        connection = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")
    yield connection
    connection.rollback()
    connection.close()


def _make_loader(table_name: str) -> PriceLoader:
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = table_name
    loader.primary_key = ("symbol", "date")
    return loader


def test_unrelated_unique_constraint_does_not_satisfy_check(conn):
    """A UNIQUE constraint on a column that isn't (symbol, date) must NOT count."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TEMP TABLE test_price_unrelated_unique (id serial, symbol text, date date, unrelated_col text UNIQUE)"
    )
    loader = _make_loader("test_price_unrelated_unique")
    with pytest.raises(RuntimeError, match="No UNIQUE constraint or index"):
        loader._verify_unique_constraint_exists(cur)


def test_real_symbol_date_unique_constraint_satisfies_check(conn):
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE test_price_real_unique (id serial, symbol text, date date, UNIQUE(symbol, date))")
    loader = _make_loader("test_price_real_unique")
    loader._verify_unique_constraint_exists(cur)  # must not raise


def test_real_symbol_date_unique_index_satisfies_check(conn):
    """A unique INDEX (not a named constraint) on the same columns must also count."""
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE test_price_unique_index (id serial, symbol text, date date)")
    cur.execute("CREATE UNIQUE INDEX test_price_unique_index_idx ON test_price_unique_index (symbol, date)")
    loader = _make_loader("test_price_unique_index")
    loader._verify_unique_constraint_exists(cur)  # must not raise


def test_no_unique_constraint_at_all_fails(conn):
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE test_price_no_unique (id serial, symbol text, date date)")
    loader = _make_loader("test_price_no_unique")
    with pytest.raises(RuntimeError, match="No UNIQUE constraint or index"):
        loader._verify_unique_constraint_exists(cur)
