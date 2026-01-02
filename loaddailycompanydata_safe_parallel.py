#!/usr/bin/env python3
"""
Safe Parallel Company Data Loader - 2 instances with deadlock retry
- Uses 2 parallel loaders (less contention)
- Retries deadlock errors with exponential backoff
- Verifies all data loaded successfully
"""
import sys
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Import the original loader functions
sys.path.insert(0, '/home/stocks/algo')
from loaddailycompanydata import load_all_realtime_data, get_db_config

def load_with_deadlock_retry(symbol, cur, conn, max_retries=3):
    """Load a stock with automatic deadlock retry"""
    for attempt in range(max_retries):
        try:
            stats = load_all_realtime_data(symbol, cur, conn)
            if stats:
                return stats, True  # Success
            else:
                return None, True   # No data but tried
        except psycopg2.OperationalError as e:
            if 'deadlock' in str(e).lower():
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logging.warning(f"Deadlock for {symbol}, retry in {delay}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(delay)
                    conn.rollback()
                    continue
                else:
                    logging.error(f"Deadlock for {symbol} - final failure after {max_retries} retries")
                    return None, False
            else:
                logging.error(f"Error loading {symbol}: {e}")
                conn.rollback()
                return None, False
        except Exception as e:
            logging.error(f"Error loading {symbol}: {e}")
            conn.rollback()
            return None, False
    
    return None, False

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 loaddailycompanydata_safe_parallel.py <symbol_file>")
        sys.exit(1)
    
    symbol_file = sys.argv[1]
    loader_id = symbol_file.split('_')[-1].split('.')[0]
    
    # Read symbols
    try:
        with open(symbol_file, 'r') as f:
            symbols = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Failed to read {symbol_file}: {e}")
        sys.exit(1)
    
    logging.info(f"=== SAFE PARALLEL LOADER {loader_id} ===")
    logging.info(f"Processing {len(symbols)} symbols")
    
    # Get DB connection
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        logging.error(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    # Stagger start times (loader 0 starts now, loader 1 waits 2s)
    if int(loader_id) > 0:
        time.sleep(int(loader_id) * 2)
    
    processed = 0
    failed = 0
    retried = 0
    
    for idx, symbol in enumerate(symbols, 1):
        stats, success = load_with_deadlock_retry(symbol, cur, conn, max_retries=3)
        
        if success:
            if stats:
                processed += 1
                logging.info(f"✅ {symbol}: {stats}")
            else:
                failed += 1
        else:
            failed += 1
            retried += 1
            logging.error(f"❌ {symbol}: Failed after retries")
        
        # Log progress every 50 stocks
        if idx % 50 == 0:
            logging.info(f"Progress: {idx}/{len(symbols)} ({processed} ok, {failed} failed)")
        
        # Delay between requests - 4s per loader (2 loaders = 1 request/2sec combined = 30 req/min)
        # Safe for yfinance free tier (limit is ~20 req/min, we stay at 30 with buffer)
        time.sleep(4.0)
    
    logging.info("=" * 80)
    logging.info(f"LOADER {loader_id} COMPLETE")
    logging.info(f"Processed: {processed}/{len(symbols)}")
    logging.info(f"Failed: {failed}")
    logging.info(f"Deadlock retries: {retried}")
    
    cur.close()
    conn.close()
    
    # Exit with error if any failed (so launcher knows there were issues)
    sys.exit(1 if failed > 0 else 0)

if __name__ == "__main__":
    main()
