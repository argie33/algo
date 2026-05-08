#!/usr/bin/env python3
"""
Setup test database - Create stocks_test with schema and seed data.

Run this once to prepare the test environment:
  python tests/setup_test_db.py

Or import and call setup_test_db() from pytest fixtures.
"""

import os
import sys
import psycopg2
from pathlib import Path
from datetime import date, timedelta, datetime
from decimal import Decimal
from dotenv import load_dotenv

# Load .env.local or .env.test
env_file = Path(__file__).parent.parent / '.env.local'
if not env_file.exists():
    env_file = Path(__file__).parent.parent / '.env.test'
if env_file.exists():
    load_dotenv(env_file)

# Test DB config (stocks_test, not stocks)
TEST_DB_CONFIG = {
    "host": os.getenv("TEST_DB_HOST") or os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("TEST_DB_PORT") or os.getenv("DB_PORT", 5432)),
    "user": os.getenv("TEST_DB_USER") or os.getenv("DB_USER", "stocks"),
    "password": os.getenv("TEST_DB_PASSWORD") or os.getenv("DB_PASSWORD", ""),
    "database": "stocks_test",
}

# Main DB config (for initial DB creation)
MAIN_DB_CONFIG = {
    "host": TEST_DB_CONFIG["host"],
    "port": TEST_DB_CONFIG["port"],
    "user": TEST_DB_CONFIG["user"],
    "password": TEST_DB_CONFIG["password"],
    "database": "postgres",  # Connect to postgres to create stocks_test
}


def create_test_database():
    """Create stocks_test database if it doesn't exist."""
    print("Creating stocks_test database...")
    try:
        conn = psycopg2.connect(**MAIN_DB_CONFIG)
        conn.autocommit = True
        cur = conn.cursor()

        # Check if DB exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = 'stocks_test'")
        if cur.fetchone():
            print("  ✓ stocks_test already exists")
        else:
            cur.execute("CREATE DATABASE stocks_test")
            print("  ✓ Created stocks_test")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"  ✗ Failed to create database: {e}")
        raise


def init_schema():
    """Initialize schema in stocks_test using init_database.py logic."""
    print("Initializing schema...")
    try:
        # Import and run the schema initialization
        sys.path.insert(0, str(Path(__file__).parent.parent))
        os.environ['DB_NAME'] = 'stocks_test'
        os.environ['DB_HOST'] = TEST_DB_CONFIG['host']
        os.environ['DB_PORT'] = str(TEST_DB_CONFIG['port'])
        os.environ['DB_USER'] = TEST_DB_CONFIG['user']
        os.environ['DB_PASSWORD'] = TEST_DB_CONFIG['password']

        from init_database import init_db
        init_db()
        print("  ✓ Schema initialized")
    except Exception as e:
        print(f"  ✗ Failed to initialize schema: {e}")
        raise


def seed_test_data():
    """Seed minimal realistic test data."""
    print("Seeding test data...")
    try:
        conn = psycopg2.connect(**TEST_DB_CONFIG)
        cur = conn.cursor()

        today = date.today()

        # 1. Seed price_daily: 90 days of SPY and AAPL
        print("  - Seeding price_daily (90 days SPY + AAPL)...")
        for i in range(90, 0, -1):
            d = today - timedelta(days=i)
            # SPY: base 500, noise
            spy_close = 500 + (i % 10) - 5
            aapl_close = 150 + (i % 8) - 4

            cur.execute(
                """
                INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                ('SPY', d, spy_close*0.98, spy_close*1.01, spy_close*0.97, spy_close, 1000000)
            )
            cur.execute(
                """
                INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                ('AAPL', d, aapl_close*0.98, aapl_close*1.01, aapl_close*0.97, aapl_close, 500000)
            )

        # 2. Seed market_health_daily: 30 days with mixed stage 2/4
        print("  - Seeding market_health_daily (30 days mixed stages)...")
        for i in range(30, 0, -1):
            d = today - timedelta(days=i)
            stage = 2 if i % 3 == 0 else 4
            trend = 'uptrend' if stage == 2 else 'downtrend'

            cur.execute(
                """
                INSERT INTO market_health_daily (date, market_stage, market_trend, vix_level,
                    dist_days_down, distribution_day_flag, rsi_spy, high_low_ratio)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (d, stage, trend, 18.0 if stage == 2 else 28.0, 2 if stage == 4 else 0,
                 stage == 4, 55 if stage == 2 else 35, 0.5)
            )

        # 3. Seed buy_sell_daily: 5 BUY signals, 3 SELL signals
        print("  - Seeding buy_sell_daily (5 BUY + 3 SELL)...")
        test_signals = [
            ('AAPL', today - timedelta(days=5), 'BUY'),
            ('SPY', today - timedelta(days=4), 'BUY'),
            ('AAPL', today - timedelta(days=3), 'SELL'),
            ('MSFT', today - timedelta(days=2), 'BUY'),
            ('GOOGL', today - timedelta(days=1), 'BUY'),
            ('SPY', today - timedelta(days=1), 'SELL'),
        ]
        for symbol, sig_date, signal in test_signals:
            cur.execute(
                """
                INSERT INTO buy_sell_daily (symbol, date, signal, rsi_value, macd_value,
                    completeness_pct, price_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (symbol, sig_date, signal, 35 if signal == 'BUY' else 75, 0.5, 85, 150.0)
            )

        # 4. Seed trend_template_data
        print("  - Seeding trend_template_data...")
        cur.execute(
            """
            INSERT INTO trend_template_data (symbol, date, minervini_score, trend_stage,
                distance_from_52w_hi, distance_from_52w_lo)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            ('AAPL', today - timedelta(days=5), 8.5, 2, 5, 45)
        )
        cur.execute(
            """
            INSERT INTO trend_template_data (symbol, date, minervini_score, trend_stage,
                distance_from_52w_hi, distance_from_52w_lo)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            ('MSFT', today - timedelta(days=2), 7.2, 2, 8, 40)
        )

        # 5. Seed data_completeness_scores
        print("  - Seeding data_completeness_scores...")
        for symbol in ['SPY', 'AAPL', 'MSFT', 'GOOGL']:
            cur.execute(
                """
                INSERT INTO data_completeness_scores (symbol, composite_completeness_pct,
                    is_tradeable, last_updated)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (symbol, 90.0, True, today)
            )

        # 6. Seed signal_quality_scores
        print("  - Seeding signal_quality_scores...")
        for symbol in ['AAPL', 'MSFT']:
            cur.execute(
                """
                INSERT INTO signal_quality_scores (symbol, date, composite_sqs,
                    confidence_level, trend_alignment)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (symbol, today - timedelta(days=5), 70.0, 0.85, 0.9)
            )

        # 7. Seed algo_portfolio_snapshots
        print("  - Seeding algo_portfolio_snapshots...")
        for i in range(10, 0, -1):
            d = today - timedelta(days=i)
            cur.execute(
                """
                INSERT INTO algo_portfolio_snapshots (snapshot_date, total_portfolio_value,
                    cash, positions_value, daily_return_pct, cumulative_return_pct, sharpe_ratio)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (d, Decimal('100000.00'), Decimal('50000.00'), Decimal('50000.00'),
                 Decimal('0.5'), Decimal('5.25'), Decimal('1.45'))
            )

        # 8. Seed algo_trades (2 closed trades)
        print("  - Seeding algo_trades...")
        cur.execute(
            """
            INSERT INTO algo_trades (trade_id, symbol, signal_date, entry_date, entry_price,
                entry_quantity, stop_loss_price, target_1_price, target_2_price, target_3_price,
                status, execution_mode, profit_loss_pct, exit_date, exit_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            ('TRD-TEST-001', 'AAPL', today-timedelta(days=10), today-timedelta(days=10),
             150.0, 100, 142.5, 157.5, 165.0, 172.5, 'closed', 'paper',
             1.5, today-timedelta(days=5), 152.25)
        )
        cur.execute(
            """
            INSERT INTO algo_trades (trade_id, symbol, signal_date, entry_date, entry_price,
                entry_quantity, stop_loss_price, target_1_price, target_2_price, target_3_price,
                status, execution_mode, profit_loss_pct, exit_date, exit_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            ('TRD-TEST-002', 'SPY', today-timedelta(days=8), today-timedelta(days=8),
             500.0, 50, 492.5, 507.5, 515.0, 522.5, 'closed', 'paper',
             -0.75, today-timedelta(days=2), 496.25)
        )

        # 9. Seed algo_positions (1 open position)
        print("  - Seeding algo_positions...")
        cur.execute(
            """
            INSERT INTO algo_positions (position_id, symbol, quantity, avg_entry_price,
                current_price, position_value, status, trade_ids_arr, current_stop_price,
                target_levels_hit, opened_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            ('POS-TEST-001', 'MSFT', 100, 300.0, 305.0, 30500.0, 'open',
             ['TRD-TEST-003'], 285.0, '[]', today-timedelta(days=3))
        )

        conn.commit()
        print("  ✓ Test data seeded")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  ✗ Failed to seed data: {e}")
        conn.rollback()
        raise


def setup_test_db():
    """Main setup function - create DB, schema, seed data."""
    print("\n" + "="*70)
    print("Setting up stocks_test database")
    print("="*70 + "\n")

    create_test_database()
    init_schema()
    seed_test_data()

    print("\n" + "="*70)
    print("✓ stocks_test setup complete")
    print("="*70 + "\n")


if __name__ == '__main__':
    setup_test_db()
