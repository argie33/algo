#!/usr/bin/env python3
"""
Set up test database with schema and seed data.

Called by tests/conftest.py to initialize stocks_test database
with complete schema and realistic test data for integration tests.
"""

import os
import psycopg2
from pathlib import Path
from datetime import date, datetime, timedelta
import logging

from config.credential_helper import (
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_DB_NAME,
)

logger = logging.getLogger(__name__)

# Test database config — read from environment, fallback to defaults
TEST_DB_HOST = os.getenv('TEST_DB_HOST') or os.getenv('DB_HOST', DEFAULT_DB_HOST)
TEST_DB_PORT = int(os.getenv('TEST_DB_PORT') or os.getenv('DB_PORT', DEFAULT_DB_PORT))
TEST_DB_NAME = os.getenv('TEST_DB_NAME') or os.getenv('DB_NAME', 'stocks_test')
TEST_DB_USER = os.getenv('TEST_DB_USER') or os.getenv('DB_USER', DEFAULT_DB_USER)
TEST_DB_PASSWORD = os.getenv('TEST_DB_PASSWORD') or os.getenv('DB_PASSWORD', '')
MAIN_DB_NAME = DEFAULT_DB_NAME


def setup_test_db():
    """Set up test database with schema and seed data.

    This function:
    1. Connects to PostgreSQL
    2. Creates stocks_test database if it doesn't exist
    3. Initializes the schema (via init_database.py)
    4. Seeds minimal realistic test data
    """
    try:
        # Connect to default postgres database to create stocks_test
        conn = psycopg2.connect(
            host=TEST_DB_HOST,
            port=TEST_DB_PORT,
            database="postgres",
            user=TEST_DB_USER,
            password=TEST_DB_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Create test database if it doesn't exist
        cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
        if not cur.fetchone():
            logger.info(f"Creating {TEST_DB_NAME} database...")
            cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
            logger.info(f"Created {TEST_DB_NAME}")

        cur.close()
        conn.close()

        # Connect to test database and initialize schema
        conn = psycopg2.connect(
            host=TEST_DB_HOST,
            port=TEST_DB_PORT,
            database=TEST_DB_NAME,
            user=TEST_DB_USER,
            password=TEST_DB_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Check if schema already initialized (stock_symbols table exists)
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'stock_symbols'
        """)
        if not cur.fetchone():
            logger.info("Initializing schema...")
            # Use init_database.py to create schema
            from init_database import init_database
            init_database(override_db_name=TEST_DB_NAME)
            logger.info("Schema initialized")

        # Seed minimal test data
        logger.info("Seeding test data...")
        _seed_test_data(cur)
        logger.info("Test data seeded")

        cur.close()
        conn.close()

        logger.info("Test database setup complete")

    except psycopg2.OperationalError as e:
        raise RuntimeError(f"Database connection failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Test database setup failed: {e}")


def _seed_test_data(cur):
    """Insert minimal realistic test data into test database.

    Adds:
    - Test stock symbols (AAPL, GOOGL, MSFT)
    - Price data (last 30 days)
    - Market health data
    - Portfolio snapshot
    """
    # Clear any existing test data
    cur.execute("DELETE FROM stock_symbols WHERE symbol IN ('AAPL', 'GOOGL', 'MSFT')")

    # Insert test symbols
    test_symbols = [
        ('AAPL', 'Apple Inc.', 'NASDAQ', 'Technology'),
        ('GOOGL', 'Alphabet Inc.', 'NASDAQ', 'Technology'),
        ('MSFT', 'Microsoft Corporation', 'NASDAQ', 'Technology'),
    ]
    for symbol, name, exchange, sector in test_symbols:
        cur.execute("""
            INSERT INTO stock_symbols (symbol, security_name, exchange, sector)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol) DO NOTHING
        """, (symbol, name, exchange, sector))

    # Insert price data (last 30 days)
    today = date.today()
    for symbol in ['AAPL', 'GOOGL', 'MSFT']:
        for days_ago in range(30, -1, -1):
            price_date = today - timedelta(days=days_ago)
            base_price = {'AAPL': 150.0, 'GOOGL': 140.0, 'MSFT': 420.0}[symbol]
            open_price = base_price + (days_ago % 5) - 2
            close_price = base_price + (days_ago % 5)
            high_price = close_price + 1
            low_price = open_price - 0.5
            volume = 1000000 + days_ago * 10000

            cur.execute("""
                INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO NOTHING
            """, (symbol, price_date, open_price, high_price, low_price, close_price, volume))

    # Insert market health data for last 5 days
    for days_ago in range(5, -1, -1):
        health_date = today - timedelta(days=days_ago)
        cur.execute("""
            INSERT INTO market_health_daily (date, vix_level, market_stage, market_trend, distribution_days)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (date) DO NOTHING
        """, (health_date, 20.0 + days_ago, 2, 'uptrend', 0))

    # Insert portfolio snapshot
    cur.execute("""
        INSERT INTO algo_portfolio_snapshots (snapshot_date, total_portfolio_value, cash, positions_value)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (snapshot_date) DO NOTHING
    """, (today, 100000.0, 50000.0, 50000.0))

    cur.execute("COMMIT")


if __name__ == '__main__':
    setup_test_db()
    print("Test database ready")
