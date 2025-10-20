#!/usr/bin/env python3
"""
Analyze NULL value patterns across all database tables to identify data gaps
"""
import psycopg2
from psycopg2 import sql
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database connection
try:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "password"),
        dbname=os.environ.get("DB_NAME", "stocks"),
    )
    cur = conn.cursor()

    # Get all tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]

    logger.info(f"Found {len(tables)} tables")
    print("\n" + "="*80)
    print("DATABASE NULL VALUE ANALYSIS")
    print("="*80)

    for table_name in tables:
        print(f"\n📊 TABLE: {table_name}")
        print("-" * 80)

        # Get all columns for this table
        cur.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()

        # Count total rows
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cur.fetchone()[0]
        print(f"Total rows: {total_rows}")

        # Check NULL counts for each column
        null_info = []
        for col_name, col_type in columns:
            cur.execute(f"""
                SELECT COUNT(*) FROM {table_name} WHERE {col_name} IS NULL
            """)
            null_count = cur.fetchone()[0]

            if total_rows > 0:
                null_percent = (null_count / total_rows) * 100
            else:
                null_percent = 0

            null_info.append({
                'column': col_name,
                'type': col_type,
                'null_count': null_count,
                'null_percent': null_percent,
                'filled_count': total_rows - null_count
            })

        # Sort by NULL percentage (highest first)
        null_info.sort(key=lambda x: x['null_percent'], reverse=True)

        # Display results
        for info in null_info:
            null_bar = "█" * int(info['null_percent'] / 5) + "░" * (20 - int(info['null_percent'] / 5))
            status = "❌" if info['null_percent'] > 50 else "⚠️ " if info['null_percent'] > 20 else "✅"

            print(f"  {status} {info['column']:30s} {info['type']:15s} | {null_bar} | {info['null_percent']:6.1f}% NULL ({info['null_count']:,}/{total_rows:,})")

    print("\n" + "="*80)
    print("SUMMARY OF HIGH-NULL FIELDS (>20% NULL)")
    print("="*80)

    for table_name in tables:
        cur.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
        """)
        columns = cur.fetchall()

        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cur.fetchone()[0]

        if total_rows == 0:
            continue

        high_null_cols = []
        for col_name, col_type in columns:
            cur.execute(f"""
                SELECT COUNT(*) FROM {table_name} WHERE {col_name} IS NULL
            """)
            null_count = cur.fetchone()[0]
            null_percent = (null_count / total_rows) * 100

            if null_percent > 20:
                high_null_cols.append({
                    'table': table_name,
                    'column': col_name,
                    'null_percent': null_percent,
                    'null_count': null_count,
                    'total': total_rows
                })

        for col in sorted(high_null_cols, key=lambda x: x['null_percent'], reverse=True):
            print(f"  {col['table']:25s}.{col['column']:30s} → {col['null_percent']:6.1f}% ({col['null_count']:,}/{col['total']:,})")

    cur.close()
    conn.close()

except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    traceback.print_exc()
