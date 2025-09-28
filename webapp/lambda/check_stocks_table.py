#!/usr/bin/env python3

import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'database': 'stocks',
    'user': 'postgres',
    'password': 'password'
}

def check_stocks_table():
    """Check what fields exist in the stocks table."""
    try:
        print(f"Connecting to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get column information for stocks table
        cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'stocks'
        ORDER BY ordinal_position;
        """)
        columns = cur.fetchall()

        print("\nStocks table structure:")
        print("-" * 60)
        for col in columns:
            print(f"Column: {col['column_name']:<20} Type: {col['data_type']:<15} Nullable: {col['is_nullable']}")

        # Get row count
        cur.execute("SELECT COUNT(*) FROM stocks")
        count = cur.fetchone()['count']
        print(f"\nTotal rows: {count}")

        if count > 0:
            # Show sample data
            cur.execute("SELECT * FROM stocks LIMIT 3")
            sample_data = cur.fetchall()
            print("\nSample data:")
            print("-" * 60)
            for row in sample_data:
                print(dict(row))

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error checking stocks table: {e}")
        raise

if __name__ == "__main__":
    check_stocks_table()