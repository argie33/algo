#!/usr/bin/env python3
"""
Populate earnings data for local testing
This script adds earnings data to match our stocks
"""

import psycopg2
from datetime import datetime, date, timedelta
import random

def get_local_db_config():
    """Get local database configuration"""
    return {
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "password",
        "dbname": "stocks"
    }

def populate_earnings_data(cur):
    """Populate earnings data"""
    print("Populating earnings data...")

    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA']

    # Clear existing earnings data
    cur.execute("DELETE FROM earnings WHERE symbol IN %s", (tuple(symbols),))

    for symbol in symbols:
        # Create earnings data for the last 4 quarters
        for i in range(4):
            quarter_date = date.today() - timedelta(days=90 * i)

            # Generate realistic earnings data based on symbol
            base_eps = {
                'AAPL': 1.65,
                'MSFT': 3.42,
                'GOOGL': 2.35,
                'AMZN': 1.63,
                'TSLA': 0.85,
                'META': 6.77,
                'NVDA': 0.88
            }

            eps_actual = round(base_eps[symbol] * random.uniform(0.8, 1.2), 2)
            eps_estimate = round(eps_actual * random.uniform(0.9, 1.1), 2)
            eps_surprise = round(eps_actual - eps_estimate, 2)
            eps_surprise_pct = round((eps_surprise / eps_estimate) * 100, 2) if eps_estimate != 0 else 0

            revenue_actual = random.randint(20000000000, 150000000000)  # $20B-$150B
            revenue_estimate = int(revenue_actual * random.uniform(0.95, 1.05))
            revenue_surprise_pct = round(((revenue_actual - revenue_estimate) / revenue_estimate) * 100, 2) if revenue_estimate != 0 else 0

            cur.execute("""
                INSERT INTO earnings
                (symbol, period_ending, report_date, eps_actual, eps_estimate, eps_surprise, eps_surprise_pct,
                 revenue_actual, revenue_estimate, revenue_surprise_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol, quarter_date, quarter_date,
                eps_actual, eps_estimate, eps_surprise, eps_surprise_pct,
                revenue_actual, revenue_estimate, revenue_surprise_pct
            ))

    print(f"Inserted earnings data for {len(symbols)} symbols over 4 quarters")

def create_earnings_table_if_not_exists(cur):
    """Create earnings table if it doesn't exist"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earnings (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            period_ending DATE NOT NULL,
            report_date DATE,
            eps_actual DECIMAL(10,4),
            eps_estimate DECIMAL(10,4),
            eps_surprise DECIMAL(10,4),
            eps_surprise_pct DECIMAL(6,2),
            revenue_actual BIGINT,
            revenue_estimate BIGINT,
            revenue_surprise_pct DECIMAL(6,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, period_ending)
        )
    """)

def main():
    print("Starting earnings data population...")

    try:
        # Connect to database
        conn = psycopg2.connect(**get_local_db_config())
        cur = conn.cursor()

        print("Connected to database successfully")

        # Create table if needed
        create_earnings_table_if_not_exists(cur)

        # Populate data
        populate_earnings_data(cur)

        # Commit changes
        conn.commit()
        print("✅ Successfully populated earnings data!")

        # Verify data
        cur.execute("SELECT COUNT(*) FROM earnings")
        earnings_count = cur.fetchone()[0]

        print(f"\nData verification:")
        print(f"  Earnings records: {earnings_count}")

        cur.close()
        conn.close()

    except Exception as error:
        print(f"❌ Error populating earnings data: {error}")
        return False

    return True

if __name__ == "__main__":
    main()