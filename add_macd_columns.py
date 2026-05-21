#!/usr/bin/env python3
"""Add MACD columns to buy_sell tables in RDS."""

import os
import sys
import psycopg2

def main():
    """Add MACD columns to buy_sell_daily, buy_sell_weekly, buy_sell_monthly."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com'),
            port=int(os.environ.get('DB_PORT', 5432)),
            database=os.environ.get('DB_NAME', 'stocks'),
            user=os.environ.get('DB_USER', 'stocks'),
            password=os.environ.get('DB_PASSWORD', 'stocks'),
        )

        cursor = conn.cursor()

        tables = ['buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly']
        for table in tables:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2)")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2)")
            print(f"✓ Added MACD columns to {table}")

        conn.commit()
        cursor.close()
        conn.close()
        print("\n✓ MACD columns added successfully")
        return 0

    except Exception as e:
        print(f"✗ Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
