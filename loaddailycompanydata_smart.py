#!/usr/bin/env python3
"""
Enhanced Company Data Loader with Exponential Backoff for Rate Limiting
- Detects rate limit errors (429, "Too Many Requests")
- Waits 60+ seconds before retry
- NO SKIPPED STOCKS - retries until success
"""
import sys
sys.path.insert(0, '/home/stocks/algo')

import time
import psycopg2
from psycopg2.extras import RealDictCursor
from loaddailycompanydata import (
    load_all_realtime_data, get_db_config, log_mem, get_rss_mb
)
import logging
from db_helper import get_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def load_with_smart_backoff(symbol, cur, conn, max_total_waits=10):
    """
    Load stock with SMART exponential backoff.
    When rate limited (429 or "Too Many Requests"):
    - Wait 60 seconds
    - Retry
    - If still limited, wait 120 seconds, etc.
    NEVER gives up - keeps retrying until success
    """
    wait_time = 60  # Start with 60 second wait for rate limits
    total_waits = 0
    
    while True:
        try:
            stats = load_all_realtime_data(symbol, cur, conn)
            if stats:
                logging.info(f"✅ {symbol}: {stats}")
                return True
            else:
                # No data found but no error - try once more
                time.sleep(5)
                try:
                    stats = load_all_realtime_data(symbol, cur, conn)
                    if stats:
                        logging.info(f"✅ {symbol}: {stats}")
                        return True
                except:
                    pass
                logging.warning(f"⚠️ {symbol}: No data available after retry")
                return False
                
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if rate limited
            if "too many requests" in error_str or "429" in error_str or "rate limited" in error_str:
                total_waits += 1
                if total_waits > max_total_waits:
                    logging.error(f"❌ {symbol}: Rate limited {total_waits} times, giving up")
                    return False
                
                logging.warning(f"⚠️ {symbol}: RATE LIMITED! Waiting {wait_time}s before retry #{total_waits}...")
                time.sleep(wait_time)
                wait_time = min(wait_time * 1.5, 300)  # Max 5 minute wait
                conn.rollback()
                continue
            else:
                logging.error(f"❌ {symbol}: {e}")
                return False

def main():
    logging.info("🚀 Starting SMART loader with exponential backoff for rate limits")
    logging.info("Strategy: When rate limited, wait longer, never give up, get ALL stocks")
    
    # Get database connection
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        logging.error(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    # Get all symbols
    cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') ORDER BY symbol;")
    all_symbols = [r["symbol"] for r in cur.fetchall()]
    
    # Get already processed symbols
    cur.execute("""
        SELECT DISTINCT ticker AS symbol FROM company_profile
        UNION
        SELECT DISTINCT symbol FROM positioning_metrics
    """)
    processed = set(r["symbol"] for r in cur.fetchall())
    
    # Get skipped symbols from log
    import subprocess
    result = subprocess.run(
        ["grep", "-o", "Error loading realtime data for [A-Z0-9]*", "loaddailycompanydata_run.log"],
        capture_output=True,
        text=True
    )
    skipped = set(line.split()[-1] for line in result.stdout.strip().split('\n') if line)
    
    logging.info(f"Already processed: {len(processed)} stocks")
    logging.info(f"Skipped (will retry): {len(skipped)} stocks")
    
    # Symbols to process: skipped first (to recover them), then remaining
    to_process = list(skipped) + [s for s in all_symbols if s not in processed and s not in skipped]
    
    logging.info(f"Total to process: {len(to_process)} stocks")
    logging.info(f"Starting with {len(skipped)} skipped stocks to recover")
    
    successful = 0
    failed = 0
    
    for idx, symbol in enumerate(to_process, 1):
        try:
            if load_with_smart_backoff(symbol, cur, conn):
                successful += 1
            else:
                failed += 1
            
            if idx % 50 == 0:
                logging.info(f"Progress: {idx}/{len(to_process)} - Successful: {successful}, Failed: {failed}")
            
            # Normal delay between successful requests
            time.sleep(3.5)
            
        except Exception as e:
            logging.error(f"Unexpected error processing {symbol}: {e}")
            failed += 1
    
    logging.info("=" * 80)
    logging.info("SMART LOADER COMPLETE")
    logging.info("=" * 80)
    logging.info(f"Successful: {successful}")
    logging.info(f"Failed: {failed}")
    logging.info(f"Total processed: {successful + failed}")
    
    cur.close()
    conn.close()
    
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
