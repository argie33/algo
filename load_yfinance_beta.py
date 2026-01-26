#!/usr/bin/env python3
"""
Load Beta from yfinance - Simple direct beta loading from ticker.info
This is a quick loader to populate missing beta data (30-40% of stocks missing)
"""

import sys
import logging
import yfinance as yf
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_NAME = "load_yfinance_beta.py"

def main():
    logger.info(f"🚀 Starting {SCRIPT_NAME} - Loading beta from yfinance")
    
    conn = get_db_connection(SCRIPT_NAME)
    if not conn:
        logger.error("❌ Failed to connect to database")
        sys.exit(1)
    
    try:
        cur = conn.cursor()
        
        # Create beta_yfinance table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS beta_yfinance (
                symbol VARCHAR(50) PRIMARY KEY,
                beta DECIMAL(10, 4),
                source VARCHAR(50) DEFAULT 'yfinance',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("✅ beta_yfinance table ready")
        
        # Get all symbols that DON'T already have beta
        cur.execute("""
            SELECT s.symbol FROM stock_symbols s
            LEFT JOIN beta_yfinance b ON s.symbol = b.symbol
            WHERE b.symbol IS NULL
            LIMIT 5312
        """)
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"📥 Loading beta for {len(symbols)} symbols (skipping already loaded)...")

        # Use batch yfinance API for speed
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def fetch_beta(symbol):
            # Retry logic: try up to 5 times with exponential backoff for rate limiting
            for attempt in range(5):
                try:
                    yf_symbol = symbol.replace('.', '-').upper()
                    ticker = yf.Ticker(yf_symbol)
                    beta = ticker.info.get('beta')
                    if beta is not None:
                        logger.debug(f"{symbol}: Got beta={beta}")
                    return (symbol, beta)
                except Exception as e:
                    error_str = str(e).lower()
                    if 'too many' in error_str or '429' in error_str or 'rate' in error_str:
                        # Rate limited - exponential backoff: 0.2-0.5s, 0.5-1s, 1-2s, 2-4s, 4-8s
                        wait_time = (0.1 * (2 ** attempt)) + random.uniform(0, 0.1 * (2 ** attempt))
                        logger.debug(f"{symbol}: Rate limited, retry {attempt+1}/5 in {wait_time:.2f}s")
                        time.sleep(wait_time)
                    elif attempt == 4:
                        # Last attempt failed
                        logger.warning(f"Error loading {symbol} (final): {str(e)[:80]}")
                        return (symbol, None)
                    else:
                        # Other error, retry
                        logger.debug(f"{symbol}: Error (attempt {attempt+1}/5): {str(e)[:50]}")
                        time.sleep(0.1)
            return (symbol, None)

        loaded = 0
        skipped = 0
        errors = 0
        betas = []

        # Parallel fetching (max_workers=5) with intelligent retry logic for rate limiting
        # Exponential backoff on rate limit errors handles API throttling automatically
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_beta, symbol) for symbol in symbols]

            for i, future in enumerate(as_completed(futures)):
                try:
                    symbol, beta = future.result()
                    if beta:
                        betas.append((symbol, float(beta)))
                        loaded += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.warning(f"Error processing future: {e}")
                    errors += 1

                if (i + 1) % 50 == 0:
                    logger.info(f"  Processed {i + 1}/{len(symbols)} - Found: {loaded}, Skipped: {skipped}")

        # Batch insert all betas at once
        if betas:
            from psycopg2.extras import execute_values
            execute_values(cur, """
                INSERT INTO beta_yfinance (symbol, beta)
                VALUES %s
                ON CONFLICT (symbol) DO UPDATE SET beta = EXCLUDED.beta
            """, betas)
            conn.commit()
            logger.info(f"  Batch inserted {len(betas)} beta values")
        
        conn.commit()
        logger.info(f"✅ Beta loading complete:")
        logger.info(f"   Loaded: {loaded}/{len(symbols)} ({loaded*100/len(symbols):.1f}%)")
        logger.info(f"   Skipped (not available): {skipped}")
        logger.info(f"   Errors: {errors}")
        
        cur.close()
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
