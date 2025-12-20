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

def create_earnings_history_table():
    """Create the earnings_history table if it doesn't exist."""
    try:
        print(f"Connecting to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Creating earnings_history table...")
        
        # earnings_history table already exists with different structure
        
        # Create indexes for better performance
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_earnings_history_symbol 
        ON earnings_history(symbol);
        """)
        
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_earnings_history_date 
        ON earnings_history(date);
        """)
        
        # Insert some sample data for testing using the existing schema
        sample_data = [
            ('AAPL', '2024-03-31', 1, 2024, 81800000000, 23600000000, 1.53, 1.50, 2.0),
            ('AAPL', '2023-12-31', 4, 2023, 119600000000, 33900000000, 2.18, 2.10, 3.8),
            ('AAPL', '2023-09-30', 3, 2023, 89500000000, 23000000000, 1.46, 1.39, 5.0),
            ('MSFT', '2024-03-31', 1, 2024, 61900000000, 21900000000, 2.94, 2.84, 3.5),
            ('MSFT', '2023-12-31', 4, 2023, 62000000000, 21900000000, 2.93, 2.78, 5.4),
            ('GOOGL', '2024-03-31', 1, 2024, 80500000000, 23700000000, 1.89, 1.51, 25.2),
            ('GOOGL', '2023-12-31', 4, 2023, 86300000000, 20687000000, 1.64, 1.33, 23.3)
        ]
        
        print("Inserting sample earnings data...")
        for data in sample_data:
            cur.execute("""
            INSERT INTO earnings_history 
            (symbol, date, quarter, year, revenue, net_income, eps_reported, eps_estimate, surprise_percent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, data)
        
        conn.commit()
        print("✅ Successfully created earnings_history table and inserted sample data")
        
        # Verify the data
        cur.execute("SELECT COUNT(*) FROM earnings_history")
        count = cur.fetchone()['count']
        print(f"📊 Total earnings records: {count}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error setting up earnings_history table: {e}")
        raise

if __name__ == "__main__":
    create_earnings_history_table()