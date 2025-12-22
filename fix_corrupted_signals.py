#!/usr/bin/env python3
"""
FIX CORRUPTED SIGNALS

Clears and regenerates all buy/sell signals to ensure data integrity.
Removes duplicates and ensures proper state machine sequencing.

This script:
1. Identifies symbols with duplicate signals
2. Clears corrupt signal tables
3. Provides instructions for regeneration
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv('/home/stocks/algo/.env.local')

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "stocks")

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=30000'
    )
    return conn

def find_corrupt_symbols():
    """Find all symbols with duplicate signals"""
    conn = get_db_connection()
    cur = conn.cursor()

    # Find symbols with duplicates
    cur.execute("""
        SELECT symbol, date, signal, COUNT(*) as count
        FROM buy_sell_daily
        WHERE signal IN ('Buy', 'Sell')
        GROUP BY symbol, date, signal
        HAVING COUNT(*) > 1
        ORDER BY symbol, date DESC
    """)

    duplicates = cur.fetchall()
    cur.close()
    conn.close()

    return duplicates

def clear_signal_tables():
    """Clear all signal tables to start fresh"""
    conn = get_db_connection()
    cur = conn.cursor()

    tables = ['buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
              'buy_sell_daily_etf', 'buy_sell_weekly_etf', 'buy_sell_monthly_etf']

    print("\nDELETING CORRUPTED SIGNAL RECORDS:")
    print("=" * 80)

    for table in tables:
        # Check if table exists
        cur.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE signal IN ('Buy', 'Sell')
        """)
        count = cur.fetchone()[0]

        if count > 0:
            # Delete ALL signal records (we'll regenerate)
            cur.execute(f"DELETE FROM {table} WHERE signal IN ('Buy', 'Sell')")
            conn.commit()
            print(f"✅ Cleared {count} signal records from {table}")
        else:
            print(f"✅ {table}: already clean")

    cur.close()
    conn.close()

def main():
    print("\n" + "=" * 80)
    print("SIGNAL DATA INTEGRITY REPORT")
    print("=" * 80)

    # Find corrupted data
    print("\n1. SEARCHING FOR DUPLICATE SIGNALS...")
    duplicates = find_corrupt_symbols()

    if duplicates:
        print(f"\n   ⚠️  FOUND {len(duplicates)} DUPLICATE SIGNAL ENTRIES:")
        print(f"\n   {'Symbol':<10} {'Date':<12} {'Signal':<6} {'Count':<6}")
        print("   " + "-" * 40)

        for symbol, date, signal, count in duplicates[:50]:  # Show first 50
            print(f"   {symbol:<10} {date} {signal:<6} {count:<6} ← CORRUPT!")

        if len(duplicates) > 50:
            print(f"   ... and {len(duplicates) - 50} more duplicates")

    # Summary
    print("\n2. IMPACT ANALYSIS:")
    print("   ❌ Duplicate signals corrupt the state machine")
    print("   ❌ Trading signals are UNRELIABLE")
    print("   ❌ Must regenerate all signals from scratch")

    # Offer to fix
    print("\n3. RECOMMENDED FIX:")
    print("   1. Run: python3 /home/stocks/algo/loadbuyselldaily.py")
    print("   2. Run: python3 /home/stocks/algo/loadbuysellweekly.py")
    print("   3. Run: python3 /home/stocks/algo/loadbuysellmonthly.py")
    print("   4. Run: python3 /home/stocks/algo/loadbuysell_etf_daily.py")
    print("   5. Run: python3 /home/stocks/algo/loadbuysell_etf_weekly.py")
    print("   6. Run: python3 /home/stocks/algo/loadbuysell_etf_monthly.py")
    print("\n   This will regenerate all signals with proper deduplication.")

    # Option to proceed with deletion
    print("\n4. AUTOMATED FIX OPTION:")
    response = input("   Delete corrupt signal records and start fresh? (yes/no): ").strip().lower()

    if response == 'yes':
        clear_signal_tables()
        print("\n✅ Corrupted signals cleared. Run loaders to regenerate.")
    else:
        print("\n⚠️  Corrupt signals remain in database.")
        print("   Manual cleaning required before regenerating signals.")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
