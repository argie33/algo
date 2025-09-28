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

def check_all_earnings_tables():
    """Check all earnings-related tables."""
    try:
        print(f"Connecting to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Find all earnings-related tables
        cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE '%earning%'
        ORDER BY table_name;
        """)
        earnings_tables = cur.fetchall()

        print("All earnings-related tables:")
        print("=" * 60)

        for table in earnings_tables:
            table_name = table['table_name']
            print(f"\n📊 Table: {table_name}")

            # Get column information
            cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
            """, (table_name,))
            columns = cur.fetchall()

            print("Columns:")
            for col in columns:
                print(f"  {col['column_name']:<20} {col['data_type']:<15} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'}")

            # Get row count
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()['count']
            print(f"Rows: {count}")

            # Show sample data if any exists
            if count > 0:
                cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
                sample_data = cur.fetchall()
                print("Sample data:")
                for i, row in enumerate(sample_data, 1):
                    print(f"  Row {i}: {dict(row)}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error checking earnings tables: {e}")
        raise

if __name__ == "__main__":
    check_all_earnings_tables()