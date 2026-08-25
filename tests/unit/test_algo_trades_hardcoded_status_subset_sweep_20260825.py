"""Regression tests for the 2026-08-25 sweep (real-money-readiness goal session) for the
same bug class as phase1_data_freshness.py's orphaned-position fix: a hand-rolled subset of
algo_trades status literals instead of TradeStatus.all_open(), silently excluding real,
reachable live statuses (most commonly 'partially_filled', routine for the illiquid/
small-cap names this system explicitly targets per liquidity_checks.py).

Runs against a real local Postgres inside a transaction that is always rolled back, so no
test data persists - these are SQL query-logic bugs, not something a mocked cursor can
meaningfully exercise.
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


class TestReconciliationPositionValueIncludesAllOpenStatuses:
    """algo/infrastructure/reconciliation.py's position-value/unrealized-P&L query."""

    def test_partially_filled_trade_included_in_position_value(self, conn):
        cur = conn.cursor()
        cur.execute(
            "CREATE TEMP TABLE algo_trades_pv_test (symbol text, entry_quantity numeric, "
            "entry_price numeric, status text, exit_date date) ON COMMIT DROP"
        )
        cur.execute("INSERT INTO algo_trades_pv_test VALUES ('NVDA', 10, 100.0, 'paper_pending', NULL)")
        cur.execute(
            """
            SELECT symbol FROM algo_trades_pv_test
            WHERE status = ANY(%s) AND exit_date IS NULL AND entry_price IS NOT NULL AND entry_price > 0
            """,
            (list(TradeStatus.all_open()),),
        )
        assert cur.fetchall() == [("NVDA",)], "a real paper_pending trade must count toward position value"


class TestPositionSyncValidateCountIncludesAllOpenStatuses:
    """algo/orchestration/position_sync.py's validate_position_count() cross-check."""

    def test_partially_filled_trade_not_flagged_as_missing(self, conn):
        cur = conn.cursor()
        cur.execute(
            "CREATE TEMP TABLE algo_trades_vpc_test (symbol text, quantity numeric, status text) ON COMMIT DROP"
        )
        cur.execute("INSERT INTO algo_trades_vpc_test VALUES ('IWM', 5, 'partially_filled')")
        cur.execute(
            """
            SELECT symbol, SUM(quantity) as total_qty FROM algo_trades_vpc_test
            WHERE status = ANY(%s) GROUP BY symbol HAVING SUM(quantity) > 0
            """,
            (list(TradeStatus.all_open()),),
        )
        assert cur.fetchall() == [("IWM", 5)], (
            "a real partially_filled trade must be counted, or validate_position_count() would "
            "falsely flag its position as orphaned"
        )


class TestPhase9RepairMissingExitPricesIncludesAllOpenStatuses:
    """algo/orchestrator/phase9_reconciliation.py's _repair_missing_exit_prices() detector."""

    def test_paper_pending_corrupted_trade_detected(self, conn):
        cur = conn.cursor()
        cur.execute(
            "CREATE TEMP TABLE algo_trades_repair_test (trade_id int, status text, exit_date date, "
            "exit_price numeric, exit_reason text) ON COMMIT DROP"
        )
        cur.execute(
            "INSERT INTO algo_trades_repair_test VALUES "
            "(1, 'paper_pending', CURRENT_DATE, NULL, 'Closed position recorded during reconciliation')"
        )
        cur.execute(
            """
            SELECT trade_id FROM algo_trades_repair_test
            WHERE exit_date IS NOT NULL AND exit_price IS NULL
              AND exit_reason ILIKE '%%Closed position recorded during reconciliation%%'
              AND status = ANY(%s)
            """,
            (list(TradeStatus.all_open()),),
        )
        assert cur.fetchall() == [(1,)], "a corrupted paper_pending trade must be detected for repair"
