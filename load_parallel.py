#!/usr/bin/env python3
"""
Parallel data loader - loads multiple stocks simultaneously
Faster than sequential loading
"""

import os
import sys
import logging
import psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "user": os.environ.get("DB_USER", "stocks"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "stocks"),
}

def get_symbols():
    """Get all symbols to load, prioritizing S&P 500"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Get S&P 500 first, then others
    cur.execute("""
        SELECT symbol FROM stock_symbols
        WHERE is_sp500 = true
        ORDER BY symbol
        UNION ALL
        SELECT symbol FROM stock_symbols
        WHERE is_sp500 = false
        ORDER BY symbol
    """)
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return symbols

def load_stock(symbol):
    """Load single stock data"""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", f"""
import os
os.environ['DB_HOST'] = '{DB_CONFIG['host']}'
os.environ['DB_USER'] = '{DB_CONFIG['user']}'
os.environ['DB_PASSWORD'] = '{DB_CONFIG['password']}'
os.environ['DB_NAME'] = '{DB_CONFIG['dbname']}'

from loaddailycompanydata import load_all_realtime_data
import psycopg2
conn = psycopg2.connect(**{DB_CONFIG})
cur = conn.cursor()
load_all_realtime_data('{symbol}', cur, conn)
conn.commit()
conn.close()
"""],
            timeout=30,
            capture_output=True
        )

        if result.returncode == 0:
            logger.info(f"✅ {symbol}")
            return (symbol, True)
        else:
            logger.error(f"❌ {symbol}: {result.stderr.decode()[:100]}")
            return (symbol, False)
    except Exception as e:
        logger.error(f"❌ {symbol}: {str(e)[:100]}")
        return (symbol, False)

def main():
    symbols = get_symbols()
    logger.info(f"Loading {len(symbols)} stocks with parallel processing")

    loaded = 0
    failed = 0

    # Use 4 parallel workers
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(load_stock, symbol): symbol for symbol in symbols}

        for i, future in enumerate(as_completed(futures)):
            symbol, success = future.result()
            if success:
                loaded += 1
            else:
                failed += 1

            if (i + 1) % 50 == 0:
                logger.info(f"Progress: {i + 1}/{len(symbols)} ({loaded} loaded, {failed} failed)")

    logger.info(f"\n✅ COMPLETE: {loaded} loaded, {failed} failed out of {len(symbols)}")

if __name__ == "__main__":
    main()
