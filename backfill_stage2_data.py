#!/usr/bin/env python3
from credential_helper import get_db_password, get_db_config
"""
Backfill price data for Stage 2 stocks (BRK-B, LEN-B, WSO-B)

These large-cap stocks may not be in the loader's default watchlist
but are strategically important for Stage 2 opportunities.

Usage:
  python3 backfill_stage2_data.py

This script:
1. Adds BRK-B, LEN-B, WSO-B to stock_symbols if not present
2. Runs loadpricedaily.py with these symbols to backfill data
3. Verifies data was loaded successfully
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import sys
import subprocess
import psycopg2
from datetime import datetime

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "stocks"),
    "password": get_db_password(),
    "database": os.getenv("DB_NAME", "stocks"),
    }

STAGE2_SYMBOLS = ['BRK-B', 'LEN-B', 'WSO-B']


def ensure_symbols_exist():
    """Ensure Stage 2 symbols are in stock_symbols table."""
    conn = psycopg2.connect(**_get_db_config())
    try:
        with conn.cursor() as cur:
            for symbol in STAGE2_SYMBOLS:
                cur.execute("SELECT 1 FROM stock_symbols WHERE symbol = %s", (symbol,))
                if not cur.fetchone():
                    print(f"Adding {symbol} to stock_symbols...")
                    cur.execute(
                        "INSERT INTO stock_symbols (symbol, company_name, exchange, market_cap) VALUES (%s, %s, %s, %s)",
                        (symbol, f"{symbol} (Stage 2)", "NYSE", "LARGE_CAP")
                    )
            conn.commit()
            print(f"OK: All {len(STAGE2_SYMBOLS)} symbols present in stock_symbols table")
    finally:
        conn.close()


def verify_data_loaded():
    """Verify that price data was loaded for Stage 2 symbols."""
    conn = psycopg2.connect(**_get_db_config())
    try:
        with conn.cursor() as cur:
            for symbol in STAGE2_SYMBOLS:
                cur.execute(
                    "SELECT COUNT(*), MAX(date) FROM price_daily WHERE symbol = %s",
                    (symbol,)
                )
                count, latest = cur.fetchone()
                status = "OK" if count > 0 else "MISSING"
                latest_str = latest.isoformat() if latest else "N/A"
                print(f"  {status}: {symbol} - {count} rows, latest: {latest_str}")
    finally:
        conn.close()


def main():
    print("\n=== STAGE 2 DATA BACKFILL ===\n")

    print("Step 1: Ensure symbols exist in database...")
    ensure_symbols_exist()

    print("\nStep 2: Run price loader for Stage 2 symbols...")
    cmd = [
        "python3", "loadpricedaily.py",
        "--symbols", ",".join(STAGE2_SYMBOLS),
        "--parallelism", "2"
    ]
    print(f"  Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: Price loader failed")
        print(result.stderr)
        return False

    print(result.stdout)

    print("\nStep 3: Verify data was loaded...")
    verify_data_loaded()

    print("\n=== BACKFILL COMPLETE ===")
    print("Stage 2 symbols are now ready for signal generation and trading.")
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

