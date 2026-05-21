#!/usr/bin/env python3
"""Add missing MACD columns to buy_sell_daily table."""

import os
import psycopg2
from psycopg2 import sql

def main():
    """Execute schema alterations."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'stocks'),
            user=os.getenv('DB_USER', 'stocks'),
            password=os.getenv('DB_PASSWORD', '')
        )

        cursor = conn.cursor()

        # Add MACD columns if they don't exist
        print("Adding MACD columns to buy_sell_daily...")
        cursor.execute("""
            ALTER TABLE buy_sell_daily
            ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2);
        """)

        print("Adding MACD columns to buy_sell_weekly...")
        cursor.execute("""
            ALTER TABLE buy_sell_weekly
            ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2);
        """)

        print("Adding MACD columns to buy_sell_monthly...")
        cursor.execute("""
            ALTER TABLE buy_sell_monthly
            ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2);
        """)

        conn.commit()
        print("Schema updates completed successfully!")

        conn.close()
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())
