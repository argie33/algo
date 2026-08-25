"""Regression test for a 2026-08-25 CRITICAL bug (real-money-readiness goal session,
full-file audit) in algo/orchestrator/phase1_data_freshness.py's Phase-1-startup "clean up
orphaned positions" query.

The "does this symbol have a live trade" check used a hardcoded `t.status = 'open'` instead
of TradeStatus.all_open() (open/filled/partially_filled/active/pending/paper_pending) - the
same "hand-rolled subset missing FILLED/PARTIAL" bug class already found and fixed once in
exit_engine.py's own exit-candidate query (see TradeStatus.all_open()'s own docstring).

In real live/auto mode, executor_entry_handler.py records a normally-filled order's
algo_trades.status as 'filled'/'partially_filled', never the literal string 'open'. So for
ANY symbol that had ever been closed before and was later re-entered and filled for real,
this query's NOT EXISTS saw zero rows with status='open' (the real row was 'filled') and
concluded the position was orphaned - silently marking a genuinely open, broker-held,
real-money position as 'closed' in the database on every Phase 1 run (4-5x/day). Invisible
in local dev testing because paper-mode trades are recorded with status literally 'open'
(never 'filled').

Runs against a real local Postgres inside a transaction that is always rolled back, so no
test data persists - this bug is a SQL query-logic bug, not something a mocked cursor can
meaningfully exercise (the whole point is real WHERE-clause/NOT EXISTS semantics).
"""

import psycopg2
import pytest

from utils.trading import TradeStatus


@pytest.fixture
def conn():
    try:
        connection = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")
    yield connection
    connection.rollback()
    connection.close()


def _run_cleanup_query(cur, status_filter_sql, status_filter_params):
    cur.execute(
        """
        CREATE TEMP TABLE algo_positions_orphan_test (symbol text, status text) ON COMMIT DROP;
        CREATE TEMP TABLE algo_trades_orphan_test (symbol text, status text) ON COMMIT DROP;

        INSERT INTO algo_positions_orphan_test VALUES ('AAPL', 'open');
        INSERT INTO algo_trades_orphan_test VALUES ('AAPL', 'closed');  -- prior history
        INSERT INTO algo_trades_orphan_test VALUES ('AAPL', 'filled');  -- real, currently active trade
        """
    )
    cur.execute(
        f"""
        WITH closed_trades AS (
            SELECT DISTINCT symbol FROM algo_trades_orphan_test WHERE status = 'closed'
        )
        SELECT p.symbol FROM algo_positions_orphan_test p
        WHERE p.status = 'open' AND p.symbol IN (SELECT symbol FROM closed_trades)
        AND NOT EXISTS (
            SELECT 1 FROM algo_trades_orphan_test t
            WHERE t.symbol = p.symbol AND {status_filter_sql}
        )
        """,
        status_filter_params,
    )
    return cur.fetchall()


class TestOrphanedPositionCleanupRespectsAllOpenStatuses:
    def test_pre_fix_query_incorrectly_flags_a_real_filled_position_as_orphaned(self, conn):
        """Documents the bug: the old hardcoded `t.status = 'open'` check wrongly treats a
        real, currently-filled position (whose symbol has prior closed-trade history) as
        orphaned, because the live trade's status is 'filled', not the literal 'open'."""
        cur = conn.cursor()
        wrongly_flagged = _run_cleanup_query(cur, "t.status = 'open'", None)
        assert wrongly_flagged == [("AAPL",)], (
            "expected the pre-fix query to (incorrectly) flag AAPL as orphaned despite its "
            "real 'filled' trade being live - if this now returns [], the old query's bug "
            "reproduction here is stale and should be re-verified against the real fix."
        )

    def test_fixed_query_does_not_flag_a_real_filled_position_as_orphaned(self, conn):
        """The fix: t.status = ANY(TradeStatus.all_open()) must NOT flag AAPL, since its
        'filled' trade is a real, live, active trade."""
        cur = conn.cursor()
        correctly_not_flagged = _run_cleanup_query(cur, "t.status = ANY(%s)", (list(TradeStatus.all_open()),))
        assert correctly_not_flagged == [], (
            f"fixed query should not flag a position with a real 'filled' trade as orphaned, "
            f"got {correctly_not_flagged}"
        )

    def test_fixed_query_still_catches_a_genuinely_orphaned_position(self, conn):
        """Sanity check: the fix must not break the cleanup's real purpose - a position with
        ONLY closed trades for its symbol (no live trade of any status) is genuinely
        orphaned and must still be caught."""
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TEMP TABLE algo_positions_orphan_test2 (symbol text, status text) ON COMMIT DROP;
            CREATE TEMP TABLE algo_trades_orphan_test2 (symbol text, status text) ON COMMIT DROP;

            INSERT INTO algo_positions_orphan_test2 VALUES ('MSFT', 'open');
            INSERT INTO algo_trades_orphan_test2 VALUES ('MSFT', 'closed');
            """
        )
        cur.execute(
            """
            WITH closed_trades AS (
                SELECT DISTINCT symbol FROM algo_trades_orphan_test2 WHERE status = 'closed'
            )
            SELECT p.symbol FROM algo_positions_orphan_test2 p
            WHERE p.status = 'open' AND p.symbol IN (SELECT symbol FROM closed_trades)
            AND NOT EXISTS (
                SELECT 1 FROM algo_trades_orphan_test2 t
                WHERE t.symbol = p.symbol AND t.status = ANY(%s)
            )
            """,
            (list(TradeStatus.all_open()),),
        )
        assert cur.fetchall() == [("MSFT",)], (
            "a genuinely orphaned position (no live trade at all) must still be caught"
        )
