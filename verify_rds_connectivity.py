#!/usr/bin/env python3
"""
Verify RDS Database Connectivity

Tests connection to the PostgreSQL RDS instance and verifies schema.
Run this after infrastructure deployment to confirm database is accessible.

Usage:
    export DB_HOST=<rds-endpoint>
    export DB_PORT=5432
    export DB_USER=postgres
    export DB_PASSWORD=<password>
    export DB_NAME=stocks
    python3 verify_rds_connectivity.py
"""

import sys
import os
import psycopg2
from datetime import datetime

def verify_rds():
    """Test RDS connectivity and schema."""

    # Get connection parameters
    host = os.getenv("DB_HOST")
    port = int(os.getenv("DB_PORT", 5432))
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "stocks")

    if not host or not password:
        print("❌ MISSING: DB_HOST and DB_PASSWORD environment variables required")
        return False

    print(f"🔍 Verifying RDS connectivity to {user}@{host}:{port}/{database}")

    try:
        # Connect to database
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5
        )
        print("✅ Connected to RDS PostgreSQL")

        # Check schema
        cur = conn.cursor()

        # Count tables
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        table_count = cur.fetchone()[0]
        print(f"✅ Schema has {table_count} tables")

        # Check critical tables
        critical_tables = [
            "stock_symbols",
            "daily_prices",
            "stock_scores",
            "algo_metrics"
        ]

        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        existing_tables = {row[0] for row in cur.fetchall()}

        missing = [t for t in critical_tables if t not in existing_tables]
        if missing:
            print(f"⚠️  Missing tables: {', '.join(missing)}")
        else:
            print(f"✅ All critical tables present")

        # Check row counts
        cur.execute("SELECT COUNT(*) FROM stock_symbols")
        symbol_count = cur.fetchone()[0]
        print(f"   - stock_symbols: {symbol_count} rows")

        cur.execute("SELECT COUNT(*) FROM daily_prices")
        price_count = cur.fetchone()[0]
        print(f"   - daily_prices: {price_count} rows")

        # Check database info
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        print(f"✅ Database: {version.split(',')[0]}")

        cur.close()
        conn.close()

        print("\n✅ RDS VERIFICATION PASSED")
        return True

    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = verify_rds()
    sys.exit(0 if success else 1)
