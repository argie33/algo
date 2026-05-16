#!/usr/bin/env python3
"""
Comprehensive verification script for local setup
Run this after following SETUP_LOCAL.md to verify everything is working
"""
import psycopg2
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

print("\n" + "=" * 80)
print(" COMPREHENSIVE SETUP VERIFICATION")
print("=" * 80)

# Load env
load_dotenv('.env.local')

# 1. Connection test
print("\n[1/5] Testing PostgreSQL Connection...")
try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "stocks"),
    )
    cur = conn.cursor()
    print("      Connected to PostgreSQL")
except Exception as e:
    print(f"      FAILED: {e}")
    print("      Fix: Update DB_PASSWORD in .env.local")
    sys.exit(1)

# 2. Schema check
print("\n[2/5] Checking Database Schema...")
cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
table_count = cur.fetchone()[0]
print(f"      Tables found: {table_count}")

if table_count < 100:
    print("      WARNING: Schema incomplete")
    print("      Fix: Run 'set PYTHONIOENCODING=utf-8' then 'python3 init_database.py'")
else:
    print("      Schema OK")

# 3. Critical tables
print("\n[3/5] Checking Critical Tables...")
critical_tables = {
    'stock_symbols': 'Stock universe',
    'price_daily': 'Daily prices',
    'buy_sell_daily': 'Buy/sell signals',
    'stock_scores': 'Quality scores',
    'algo_positions': 'Open positions',
    'algo_trades': 'Trade history',
}

tables_ok = True
for table, description in critical_tables.items():
    cur.execute(f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='{table}')")
    exists = cur.fetchone()[0]
    status = "OK" if exists else "MISSING"
    print(f"      {table:25} {status:10} ({description})")
    if not exists:
        tables_ok = False

# 4. Data load status
print("\n[4/5] Checking Data Load Status...")
try:
    cur.execute("SELECT COUNT(*) FROM stock_symbols")
    symbols = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM price_daily")
    prices = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM buy_sell_daily")
    signals = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stock_scores")
    scores = cur.fetchone()[0]

    print(f"      Stock symbols:    {symbols:>10,}")
    print(f"      Price records:    {prices:>10,}")
    print(f"      Signal records:   {signals:>10,}")
    print(f"      Score records:    {scores:>10,}")

    if symbols > 0 and prices > 0:
        print("\n      Status: DATA LOADED")
        data_ok = True
    elif symbols == 0 and prices == 0:
        print("\n      Status: NO DATA YET")
        print("      Next: Run 'python3 run-all-loaders.py' to load data")
        data_ok = True  # Not an error yet
    else:
        print("\n      Status: PARTIAL DATA")
        print("      Some loaders may have failed or are still running")
        data_ok = True  # Loaders may still be running

except Exception as e:
    print(f"      Error checking data: {e}")
    data_ok = False

# 5. Summary
print("\n" + "=" * 80)
print(" VERIFICATION SUMMARY")
print("=" * 80)

all_ok = tables_ok and (table_count >= 100)

if all_ok:
    if symbols > 0 and prices > 0:
        print("\n[OK] SETUP COMPLETE - Ready to use!")
        print("\n  Next steps:")
        print("  1. Test orchestrator: python3 algo_orchestrator.py --mode paper --dry-run")
        print("  2. Check logs: Check output above for any errors")
        print("  3. Deploy to AWS: git push origin main")
    else:
        print("\n[OK] SETUP PARTIAL - Database ready, waiting for data loaders")
        print("\n  Next steps:")
        print("  1. If loaders are running, wait for them to complete")
        print("  2. Run this script again to verify data was loaded")
        print("  3. Once data loads, test orchestrator: python3 algo_orchestrator.py --mode paper --dry-run")
else:
    print("\n[ERROR] SETUP INCOMPLETE - Errors found above")
    print("\n  Fixes needed:")
    if table_count < 100:
        print("  1. Initialize schema: set PYTHONIOENCODING=utf-8")
        print("     Then: python3 init_database.py")
    if not tables_ok:
        print("  2. Check database connection and permissions")

conn.close()
print("\n" + "=" * 80 + "\n")
