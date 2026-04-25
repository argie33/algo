#!/usr/bin/env python3
"""
Populate stock_symbols table from company_profile.
This is a one-time migration to get the data flowing without waiting for external NASDAQ downloads.
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

env_file = Path('.env.local')
if env_file.exists():
    load_dotenv(env_file)

def main():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'stocks'),
    )

    try:
        cur = conn.cursor()

        # Check if stock_symbols already has data
        cur.execute("SELECT COUNT(*) FROM stock_symbols")
        existing_count = cur.fetchone()[0]

        if existing_count > 0:
            print(f"✓ stock_symbols already has {existing_count} rows, skipping population")
            return

        # Insert from company_profile
        print("Populating stock_symbols from company_profile...")
        cur.execute("""
            INSERT INTO stock_symbols
            (symbol, security_name, exchange, market_category)
            SELECT DISTINCT
                ticker,
                COALESCE(long_name, short_name, display_name, ticker),
                COALESCE(exchange, 'NASDAQ'),
                'Q'
            FROM company_profile
            WHERE ticker IS NOT NULL
            AND quote_type IN ('EQUITY', 'ETF')
            ON CONFLICT (symbol) DO NOTHING
        """)

        rows_inserted = cur.rowcount
        conn.commit()

        # Verify
        cur.execute("SELECT COUNT(*) FROM stock_symbols")
        final_count = cur.fetchone()[0]

        print(f"✓ Inserted {rows_inserted} rows")
        print(f"✓ stock_symbols now has {final_count} total rows")

    finally:
        conn.close()

if __name__ == '__main__':
    main()
