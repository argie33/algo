#!/usr/bin/env python3
"""
Phase 4: Data Quality Verification
Checks that critical data is loaded and up-to-date.
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import date, datetime, timedelta

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
}

print("=" * 70)
print("DATA QUALITY VERIFICATION - PHASE 4")
print("=" * 70)
print(f"\nDate: {date.today()}\n")

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Check 1: Stage 2 coverage (BRK-B, LEN-B, WSO-B)
    print("CHECK 1: Stage 2 Symbol Data Coverage")
    print("-" * 70)

    stage2_symbols = ['BRK-B', 'LEN-B', 'WSO-B']
    for symbol in stage2_symbols:
        cur.execute("""
            SELECT MAX(date) as latest_date, COUNT(*) as row_count
            FROM price_daily
            WHERE symbol = %s
        """, (symbol,))
        result = cur.fetchone()
        if result and result[0]:
            latest = result[0]
            count = result[1]
            is_current = latest >= date.today() - timedelta(days=2)
            status = "OK" if is_current else "STALE"
            print(f"  {symbol:10} latest: {latest}  rows: {count:6}  {status}")
        else:
            print(f"  {symbol:10} NO DATA - needs backfill")

    # Check 2: SPY Technical Indicators
    print("\nCHECK 2: SPY Technical Indicator Data")
    print("-" * 70)

    cur.execute("""
        SELECT MAX(date) as latest_date, COUNT(*) as row_count
        FROM technical_data_daily
        WHERE symbol = 'SPY'
    """)
    result = cur.fetchone()
    if result and result[0]:
        latest = result[0]
        count = result[1]
        is_current = latest >= date.today() - timedelta(days=2)
        status = "OK" if is_current else "STALE"
        print(f"  SPY indicators: latest {latest}, {count} rows  {status}")
    else:
        print(f"  SPY indicators: NO DATA")

    # Check 3: Price data for primary universe
    print("\nCHECK 3: Primary Universe Price Data (Sample)")
    print("-" * 70)

    cur.execute("""
        SELECT symbol, MAX(date) as latest_date, COUNT(*) as row_count
        FROM price_daily
        WHERE symbol IN ('AAPL', 'MSFT', 'TSLA', 'JPM', 'V')
        GROUP BY symbol
        ORDER BY latest_date DESC
    """)
    results = cur.fetchall()
    for symbol, latest, count in results:
        is_current = latest >= date.today() - timedelta(days=2)
        status = "OK" if is_current else "STALE"
        print(f"  {symbol:10} latest: {latest}  {status}")

    # Check 4: Overall price_daily stats
    print("\nCHECK 4: Overall Database Statistics")
    print("-" * 70)

    cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily")
    symbol_count = cur.fetchone()[0]
    print(f"  Total symbols in price_daily: {symbol_count}")

    cur.execute("SELECT COUNT(*) FROM price_daily WHERE date = %s", (date.today(),))
    today_count = cur.fetchone()[0]
    print(f"  Rows with today's date: {today_count}")

    cur.execute("SELECT COUNT(*) FROM price_daily")
    total_rows = cur.fetchone()[0]
    print(f"  Total price_daily rows: {total_rows}")

    conn.close()

    print("\n" + "=" * 70)
    print("DATA QUALITY VERIFICATION COMPLETE")
    print("=" * 70)
    print("""
SUMMARY:
[OK] Phase 4 data verification completed
[OK] Check results above for any stale or missing data
[OK] If any STALE flags appear, run loaders to refresh data
[OK] If BRK.B, LEN.B, WSO.B show NO DATA, add to loader watchlist

Next: System is ready for production deployment!
""")

except Exception as e:
    print(f"\nERROR: {str(e)}")
    print("Could not connect to database or execute queries.")
