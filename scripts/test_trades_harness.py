#!/usr/bin/env python3
"""
Test trades harness - Create, verify, and clean up test trades for dashboard testing.

Usage:
  python scripts/test_trades_harness.py create   # Insert test trades
  python scripts/test_trades_harness.py verify   # Check they appear on dashboard
  python scripts/test_trades_harness.py cleanup  # Delete all test trades
"""

import logging
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

TEST_TRADES = [
    {
        "symbol": "AAPL",
        "signal_date": datetime.now() - timedelta(days=5),
        "trade_date": datetime.now() - timedelta(days=5),
        "entry_date": datetime.now() - timedelta(days=5),
        "exit_date": datetime.now() - timedelta(days=2),
        "entry_price": 150.00,
        "entry_quantity": 100,
        "exit_price": 155.00,
        "profit_loss_dollars": 500.00,
        "profit_loss_pct": 3.33,
        "exit_r_multiple": 1.5,
        "trade_duration_days": 3,
        "status": "closed",
        "exit_reason": "t1_target",
        "description": "TEST: Winner - hit T1 target",
    },
    {
        "symbol": "MSFT",
        "signal_date": datetime.now() - timedelta(days=3),
        "trade_date": datetime.now() - timedelta(days=3),
        "entry_date": datetime.now() - timedelta(days=3),
        "exit_date": datetime.now() - timedelta(days=1),
        "entry_price": 300.00,
        "entry_quantity": 50,
        "exit_price": 295.00,
        "profit_loss_dollars": -500.00,
        "profit_loss_pct": -1.67,
        "exit_r_multiple": -0.5,
        "trade_duration_days": 2,
        "status": "closed",
        "exit_reason": "stop_loss",
        "description": "TEST: Loser - stopped out",
    },
    {
        "symbol": "TSLA",
        "signal_date": datetime.now() - timedelta(days=7),
        "trade_date": datetime.now() - timedelta(days=7),
        "entry_date": datetime.now() - timedelta(days=7),
        "exit_date": datetime.now() - timedelta(days=4),
        "entry_price": 250.00,
        "entry_quantity": 80,
        "exit_price": 270.00,
        "profit_loss_dollars": 2000.00,
        "profit_loss_pct": 8.0,
        "exit_r_multiple": 2.0,
        "trade_duration_days": 3,
        "status": "closed",
        "exit_reason": "t2_target",
        "description": "TEST: Big winner - hit T2 target",
    },
]

TEST_MARKER = "test_harness_"


def get_db_connection() -> psycopg2.extensions.connection:
    """Get database connection."""
    try:
        conn = psycopg2.connect(
            dbname="stocks",
            user="stocks",
            host="localhost",
            password="stocks",
        )
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.error("   Make sure PostgreSQL is running: psql -d stocks -c 'SELECT 1'")
        sys.exit(1)


def create_test_trades() -> None:
    """Insert test trades into the database."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        inserted = []
        for trade in TEST_TRADES:
            trade_id = f"{TEST_MARKER}{trade['symbol']}_{uuid4().hex[:8]}"

            cur.execute(
                """
                INSERT INTO algo_trades (
                    trade_id, symbol, signal_date, trade_date, entry_date, exit_date,
                    entry_price, entry_quantity, exit_price,
                    profit_loss_dollars, profit_loss_pct, exit_r_multiple, trade_duration_days,
                    status, exit_reason, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING trade_id, symbol, status, profit_loss_pct
                """,
                (
                    trade_id,
                    trade["symbol"],
                    trade["signal_date"],
                    trade["trade_date"],
                    trade["entry_date"],
                    trade["exit_date"],
                    trade["entry_price"],
                    trade["entry_quantity"],
                    trade["exit_price"],
                    trade["profit_loss_dollars"],
                    trade["profit_loss_pct"],
                    trade["exit_r_multiple"],
                    trade["trade_duration_days"],
                    trade["status"],
                    trade["exit_reason"],
                    datetime.now(),
                ),
            )
            result = cur.fetchone()
            inserted.append(result)

        conn.commit()

        logger.info(f"Inserted {len(inserted)} test trades:")
        for row in inserted:
            pnl_indicator = "📈" if float(row["profit_loss_pct"]) > 0 else "📉"
            logger.info(
                f"   {pnl_indicator} {row['symbol']:6} | P&L: {row['profit_loss_pct']:+6.1f}% | "
                f"ID: {row['trade_id']}"
            )
        logger.info("\nTest trades ready. Run dashboard to verify RECENT TRADES panel displays them.")
        logger.info("   python dashboard.py\n")

    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def verify_test_trades() -> None:
    """Check that test trades are in the database and display stats."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get all test trades
        cur.execute(
            """
            SELECT trade_id, symbol, entry_price, exit_price, profit_loss_pct,
                   exit_r_multiple, status, exit_date
            FROM algo_trades
            WHERE trade_id LIKE %s
            ORDER BY exit_date DESC
            """,
            (f"{TEST_MARKER}%",),
        )
        rows = cur.fetchall()

        if not rows:
            logger.warning("No test trades found in database.")
            return

        logger.info(f"\nFound {len(rows)} test trades in database:\n")
        logger.info(
            f"{'Symbol':<8} {'Entry$':<10} {'Exit$':<10} {'P&L%':<8} {'R':<6} {'Exit Date':<12}"
        )
        logger.info("-" * 60)

        total_pnl = Decimal("0")
        wins = 0
        losses = 0

        for row in rows:
            pnl_pct = float(row["profit_loss_pct"]) if row["profit_loss_pct"] else 0
            total_pnl += Decimal(str(pnl_pct))
            if pnl_pct > 0:
                wins += 1
            else:
                losses += 1

            logger.info(
                f"{row['symbol']:<8} ${row['entry_price']:<9.2f} "
                f"${row['exit_price']:<9.2f} {pnl_pct:+6.1f}% "
                f"{float(row['exit_r_multiple']):<6.2f}R "
                f"{row['exit_date'].strftime('%b %d %Y'):<12}"
            )

        logger.info("-" * 60)
        logger.info(
            f"Summary: {wins}W / {losses}L | Avg P&L: {float(total_pnl)/len(rows):+.1f}%\n"
        )
        logger.info("Test trades verified. Open dashboard to see them in RECENT TRADES panel.")

    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def cleanup_test_trades() -> None:
    """Delete all test trades from the database."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get count before deletion
        cur.execute("SELECT COUNT(*) as count FROM algo_trades WHERE trade_id LIKE %s", (f"{TEST_MARKER}%",))
        result = cur.fetchone()
        if not result:
            raise RuntimeError("Failed to fetch count of test trades")
        count = result["count"]

        if count == 0:
            logger.info("No test trades to clean up.")
            return

        # Delete all test trades
        cur.execute("DELETE FROM algo_trades WHERE trade_id LIKE %s", (f"{TEST_MARKER}%",))
        conn.commit()

        logger.info(f"Deleted {count} test trades from database.")
        logger.info("   Database is clean. Ready for real trading pipeline.\n")

    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: python scripts/test_trades_harness.py [create|verify|cleanup]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "create":
        logger.info("Creating test trades for dashboard verification...\n")
        create_test_trades()
    elif command == "verify":
        logger.info("Verifying test trades in database...\n")
        verify_test_trades()
    elif command == "cleanup":
        logger.info("Cleaning up test trades...\n")
        cleanup_test_trades()
    else:
        logger.error(f"Unknown command: {command}")
        logger.error("Valid commands: create, verify, cleanup")
        sys.exit(1)


if __name__ == "__main__":
    main()
