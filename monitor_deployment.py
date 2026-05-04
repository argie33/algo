#!/usr/bin/env python3
"""
Deployment Monitor - Watch AWS loader execution in real-time.
Checks database tables every 10 minutes for new rows (indicates active loading).
"""

import os
import sys
import time
import psycopg2
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env.local
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

# Tables to monitor
TABLES = [
    ("stock_symbols", None),
    ("price_daily", "date"),
    ("buy_sell_daily", "date"),
    ("technical_data_daily", "date"),
    ("swing_trader_scores", None),
    ("annual_income_statement", None),
    ("quarterly_balance_sheet", None),
    ("annual_balance_sheet", None),
    ("market_overview", "date"),
]

def connect_db():
    """Connect to database."""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        return None

def check_tables():
    """Check table row counts and latest date."""
    conn = connect_db()
    if not conn:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Cannot connect to database")
        print(f"  Config: {DB_CONFIG['host']}:{DB_CONFIG['port']} / {DB_CONFIG['database']}")
        return None

    try:
        cur = conn.cursor()
        results = {}

        for table, date_col in TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]

                latest = "N/A"
                if date_col:
                    cur.execute(f"SELECT MAX({date_col}) FROM {table}")
                    latest_val = cur.fetchone()[0]
                    if latest_val:
                        latest = str(latest_val).split()[0]  # Just the date part

                results[table] = (count, latest)
            except Exception as e:
                results[table] = (0, f"ERROR: {str(e)[:30]}")

        conn.close()
        return results
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def print_status(results, prev_results=None):
    """Print table status."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] DATABASE TABLE STATUS")
    print("=" * 90)

    for table, (count, latest) in sorted(results.items()):
        # Check if count changed since last run
        indicator = "  "
        if prev_results and table in prev_results:
            prev_count, _ = prev_results[table]
            if count > prev_count:
                indicator = "↑ " if isinstance(count, int) else "  "

        status_str = f"{table:35s} | {count:>15,} rows | latest: {latest:12s}"
        print(f"{indicator} {status_str}")

    print("=" * 90)

def main():
    """Monitor deployment continuously."""
    print("\n" + "=" * 90)
    print("DEPLOYMENT MONITOR — Real-time Loader Execution Tracking")
    print("=" * 90)
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"Check interval: Every 10 minutes")
    print(f"Start time: {datetime.now()}")
    print("=" * 90)

    prev_results = None
    check_count = 0

    while True:
        results = check_tables()
        if results:
            check_count += 1
            print_status(results, prev_results)
            prev_results = results

            # Show guidance every 3 checks (30 min)
            if check_count % 3 == 0:
                print("\nGuidance:")
                print("  ✓ If row counts are stable: loaders may be waiting for trigger or between runs")
                print("  ✓ If row counts increasing: loaders are EXECUTING in AWS (good!)")
                print("  ✓ If latest date near today: fresh data is flowing")
                print("  ✓ If latest date is old: loaders may not have run yet")
                print("\nMonitor GitHub Actions at: https://github.com/argeropolos/algo/actions")
                print("Stop this monitor with Ctrl+C\n")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Cannot reach database, will retry in 10 min...")

        # Wait 10 minutes before next check
        try:
            time.sleep(600)
        except KeyboardInterrupt:
            print("\n\nMonitor stopped by user.")
            sys.exit(0)

if __name__ == "__main__":
    main()
