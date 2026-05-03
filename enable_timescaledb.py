#!/usr/bin/env python3
"""
Enable TimescaleDB extension and convert price tables to hypertables.
This gives 10-100x query speedup on time-series data (free).

Execution:
  python3 enable_timescaledb.py
"""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

def connect_db():
    """Connect to PostgreSQL using environment variables."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER", "stocks"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "stocks")
    )

def enable_timescaledb(conn):
    """Enable TimescaleDB extension on the database."""
    cur = conn.cursor()
    try:
        print("📦 Enabling TimescaleDB extension...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
        conn.commit()
        print("✅ TimescaleDB extension enabled")
        return True
    except Exception as e:
        print(f"❌ Failed to enable TimescaleDB: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()

def check_table_exists(conn, table_name):
    """Check if table exists."""
    cur = conn.cursor()
    cur.execute(f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (table_name,))
    exists = cur.fetchone()[0]
    cur.close()
    return exists

def convert_to_hypertable(conn, table_name, time_column, chunk_interval):
    """Convert a table to a hypertable if it's not already."""
    cur = conn.cursor()
    try:
        # Check if already a hypertable
        cur.execute(f"""
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables
                WHERE hypertable_name = %s
            )
        """, (table_name,))
        is_hypertable = cur.fetchone()[0]

        if is_hypertable:
            print(f"  ⏭️  {table_name} already a hypertable")
            return True

        if not check_table_exists(conn, table_name):
            print(f"  ⏭️  {table_name} does not exist, skipping")
            return False

        print(f"  🔄 Converting {table_name} to hypertable...")
        cur.execute(f"""
            SELECT create_hypertable(
                '{table_name}',
                '{time_column}',
                if_not_exists => TRUE,
                chunk_time_interval => interval '{chunk_interval}'
            )
        """)
        conn.commit()
        print(f"  ✅ {table_name} converted to hypertable")
        return True
    except Exception as e:
        print(f"  ⚠️  {table_name}: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()

def create_indices(conn):
    """Create optimal indices for time-series queries."""
    cur = conn.cursor()

    indices = [
        ("price_daily", "symbol", "date_trunc('day', date)"),
        ("price_weekly", "symbol", "date_trunc('week', date)"),
        ("price_monthly", "symbol", "date_trunc('month', date)"),
        ("technical_data_daily", "symbol", "date_trunc('day', date)"),
    ]

    for table, col1, col2 in indices:
        if not check_table_exists(conn, table):
            continue
        try:
            idx_name = f"idx_{table}_{col1}_date"
            print(f"  🔍 Creating index {idx_name}...")
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {idx_name}
                ON {table} ({col1}, date DESC)
            """)
            conn.commit()
            print(f"  ✅ Index {idx_name} created")
        except Exception as e:
            print(f"  ⚠️  Index creation failed: {e}")
            conn.rollback()

    cur.close()

def enable_compression(conn):
    """Enable TimescaleDB compression on historical data."""
    cur = conn.cursor()

    tables = [
        ("price_daily", "date"),
        ("price_weekly", "date"),
        ("price_monthly", "date"),
    ]

    for table, time_col in tables:
        if not check_table_exists(conn, table):
            continue
        try:
            print(f"  🗜️  Enabling compression on {table}...")
            cur.execute(f"""
                ALTER TABLE {table} SET (
                    timescaledb.compress,
                    timescaledb.compress_orderby = '{time_col} DESC',
                    timescaledb.compress_segmentby = 'symbol'
                )
            """)

            # Add compression job
            cur.execute(f"""
                SELECT add_compression_policy(
                    '{table}',
                    INTERVAL '7 days',
                    if_not_exists => true
                )
            """)
            conn.commit()
            print(f"  ✅ Compression enabled on {table}")
        except Exception as e:
            print(f"  ⚠️  Compression setup failed: {e}")
            conn.rollback()

    cur.close()

def show_stats(conn):
    """Show hypertable statistics."""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                hypertable_name,
                num_chunks,
                to_char(total_size, '999,999,999 bytes') as size
            FROM timescaledb_information.hypertables h
            JOIN (
                SELECT hypertable_name, count(*) as num_chunks
                FROM timescaledb_information.chunks
                GROUP BY hypertable_name
            ) c ON h.hypertable_name = c.hypertable_name
            JOIN timescaledb_information.hypertable_approximate_byte_size s
            ON h.hypertable_name = s.hypertable_name
            ORDER BY h.hypertable_name
        """)

        rows = cur.fetchall()
        if rows:
            print("\n📊 Hypertable Statistics:")
            print("─" * 60)
            for name, chunks, size in rows:
                print(f"  {name:25s} {chunks:3d} chunks  {size:>15s}")
        else:
            print("\n⚠️  No hypertables found yet")
    except Exception as e:
        print(f"⚠️  Could not fetch stats: {e}")
    finally:
        cur.close()

def main():
    print("\n🚀 TimescaleDB Optimization - 10-100x Query Speedup\n")

    try:
        conn = connect_db()
        print("✅ Connected to PostgreSQL\n")

        # Enable extension
        if not enable_timescaledb(conn):
            return 1

        print("\n🔄 Converting price tables to hypertables...")
        convert_to_hypertable(conn, "price_daily", "date", "1 month")
        convert_to_hypertable(conn, "price_weekly", "date", "3 months")
        convert_to_hypertable(conn, "price_monthly", "date", "1 year")
        convert_to_hypertable(conn, "technical_data_daily", "date", "1 month")

        print("\n🔍 Creating time-series indices...")
        create_indices(conn)

        print("\n🗜️  Enabling compression...")
        enable_compression(conn)

        print("\n✨ TimescaleDB optimization complete!")
        show_stats(conn)

        conn.close()
        print("\n✅ Done! Expected speedup: 10-100x on time-series queries")
        return 0

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
