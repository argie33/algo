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
            print("  [OK] stocks_test already exists")
        else:
            cur.execute("CREATE DATABASE stocks_test")
            print("  [OK] Created stocks_test")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [FAIL] Failed to create database: {e}")
        raise


def init_schema():
    """Initialize schema in stocks_test using init_database.py logic."""
    print("Initializing schema...")
    try:
        # Import the SCHEMA from init_database directly
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from init_database import SCHEMA

        # Clean up Unicode characters from SCHEMA (for Windows console compatibility)
        # Replace fancy unicode box-drawing characters with ASCII
        schema_clean = SCHEMA.replace("═", "=").replace("║", "|").replace("╔", "+").replace("╗", "+")
        schema_clean = schema_clean.replace("╚", "+").replace("╝", "+").replace("╠", "+").replace("╣", "+")
        schema_clean = schema_clean.replace("╦", "+").replace("╩", "+").replace("├", "+").replace("┤", "+")

        # Connect to test database and execute schema
        conn = psycopg2.connect(**TEST_DB_CONFIG)
        conn.set_session(autocommit=False)
        cur = conn.cursor()

        # Execute schema in chunks to avoid unicode issues
        cur.execute(schema_clean)
        conn.commit()
        cur.close()
        conn.close()
        print("  [OK] Schema initialized")
    except Exception as e:
        print(f"  [FAIL] Failed to initialize schema: {e}")
        raise


def seed_test_data():
    """Seed minimal test data - just enough for tests to run without errors."""
    print("Seeding test data...")
    try:
        conn = psycopg2.connect(**TEST_DB_CONFIG)
        cur = conn.cursor()

        today = date.today()

        # Seed minimal price_daily: a few SPY records
        print("    * Seeding price_daily (SPY)...")
        for i in range(5, 0, -1):
            d = today - timedelta(days=i)
            spy_close = 500 + (i % 3)

            cur.execute(
                """
                INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                ('SPY', d, spy_close*0.98, spy_close*1.01, spy_close*0.97, spy_close, 1000000)
            )

        # Seed market_health_daily: a few records
        print("    * Seeding market_health_daily...")
        for i in range(3, 0, -1):
            d = today - timedelta(days=i)
            cur.execute(
                """
                INSERT INTO market_health_daily (date, market_stage, market_trend, vix_level)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (d, 2, 'uptrend', Decimal('18.0'))
            )

        conn.commit()
        print("  [OK] Test data seeded")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [FAIL] Failed to seed data: {e}")
        try:
            conn.rollback()
                except Exception:
            pass
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
    print("[OK] stocks_test setup complete")
    print("="*70 + "\n")


if __name__ == '__main__':
    setup_test_db()
