#!/usr/bin/env python3

import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration for local development
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'stocks'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password')
}

def check_earnings_table():
    """Check the structure of the earnings_history table."""
    try:
        print(f"Connecting to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if table exists
        cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'earnings_history'
        );
        """)
        table_exists = cur.fetchone()['exists']
        print(f"Table earnings_history exists: {table_exists}")
        
        if table_exists:
            # Get column information
            cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'earnings_history'
            ORDER BY ordinal_position;
            """)
            columns = cur.fetchall()
            print("\nCurrent table structure:")
            print("-" * 60)
            for col in columns:
                print(f"Column: {col['column_name']:<20} Type: {col['data_type']:<15} Nullable: {col['is_nullable']}")
            
            # Get row count
            cur.execute("SELECT COUNT(*) FROM earnings_history")
            count = cur.fetchone()['count']
            print(f"\nTotal rows: {count}")
            
            if count > 0:
                # Show sample data
                cur.execute("SELECT * FROM earnings_history LIMIT 5")
                sample_data = cur.fetchall()
                print("\nSample data:")
                print("-" * 60)
                for row in sample_data:
                    print(dict(row))
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking earnings_history table: {e}")
        raise

if __name__ == "__main__":
    check_earnings_table()