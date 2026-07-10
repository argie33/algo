#!/usr/bin/env python3
"""Manual database tests - requires local PostgreSQL."""
import os
os.environ["LOCAL_MODE"] = "true"

import pytest
import psycopg2


# Skip all tests in this file in CI - requires local PostgreSQL
pytestmark = pytest.mark.skip(reason="Manual database tests require local PostgreSQL")


def test_db_connection():
    """Test database connectivity and table row counts."""
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="stocks",
        user="stocks",
        password="stocks",
        sslmode="disable"
    )
    cur = conn.cursor()

    # Check tables
    tables = [
        ("market_exposure_daily", "SELECT COUNT(*) FROM market_exposure_daily"),
        ("sector_ranking", "SELECT COUNT(*) FROM sector_ranking"),
        ("market_health_daily", "SELECT COUNT(*) FROM market_health_daily"),
        ("price_daily (SPY)", "SELECT COUNT(*) FROM price_daily WHERE symbol='SPY'"),
    ]

    for table_name, query in tables:
        try:
            cur.execute(query)
            count = cur.fetchone()[0]
            print(f"[OK] {table_name}: {count} rows")
        except Exception as e:
            print(f"[ERR] {table_name}: {e}")

    # Check latest market_exposure_daily
    print("\nLatest market_exposure_daily row:")
    try:
        cur.execute("SELECT date, exposure_pct, regime FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            print(f"  date={row[0]}, exposure_pct={row[1]}, regime={row[2]}")
        else:
            print("  No data")
    except Exception as e:
        print(f"  Error: {e}")

    conn.close()
