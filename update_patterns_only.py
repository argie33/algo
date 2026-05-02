#!/usr/bin/env python3
"""
Update base_type patterns in database using proven Tier 1 algorithm
Bypasses technical indicator issues - PATTERNS ONLY
"""
import psycopg2
from psycopg2.extras import execute_batch
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

env_path = Path('.env.local')
load_dotenv(env_path)

# Import detection functions
import importlib.util
spec = importlib.util.spec_from_file_location("loadbuyselldaily", "loadbuyselldaily.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD', ''),
        dbname=os.getenv('DB_NAME', 'stocks')
    )

def update_patterns():
    """Update patterns for all buy_sell_daily signals"""

    logger.info("Starting pattern detection on existing price data...")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get all unique symbols
        cur.execute("SELECT DISTINCT symbol FROM buy_sell_daily ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"Found {len(symbols)} unique symbols to process")

        total_updated = 0
        total_patterns = 0
        pattern_counts = {}

        for idx, symbol in enumerate(symbols):
            if (idx + 1) % 100 == 0:
                logger.info(f"Processing symbol {idx+1}/{len(symbols)}: {symbol}")

            try:
                # Get price data for this symbol
                cur.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM price_daily
                    WHERE symbol = %s
                    AND date >= CURRENT_DATE - INTERVAL '400 days'
                    ORDER BY date ASC
                """, (symbol,))

                rows = cur.fetchall()
                if len(rows) < 65:
                    continue

                # Create dataframe
                df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')

                # Detect patterns for this symbol
                updates = []
                for i in range(65, len(df)):
                    date = df.index[i].date()
                    base_type, confidence = module.identify_base_pattern(df, i, lookback_days=65)

                    if base_type:
                        # Get all signals on this date for this symbol
                        cur.execute("""
                            SELECT id FROM buy_sell_daily
                            WHERE symbol = %s AND DATE(date) = %s
                        """, (symbol, date))

                        signal_ids = [row[0] for row in cur.fetchall()]
                        for signal_id in signal_ids:
                            updates.append((base_type, int(20 + (confidence / 100) * 45), signal_id))
                            pattern_counts[base_type] = pattern_counts.get(base_type, 0) + 1
                            total_patterns += 1

                # Batch update
                if updates:
                    execute_batch(cur, """
                        UPDATE buy_sell_daily
                        SET base_type = %s, base_length_days = %s
                        WHERE id = %s
                    """, updates, page_size=1000)
                    conn.commit()
                    total_updated += len(updates)

            except Exception as e:
                logger.warning(f"Symbol {symbol}: {str(e)[:100]}")
                conn.rollback()
                continue

        logger.info(f"\nPattern Update Complete:")
        logger.info(f"  Total signals updated: {total_updated}")
        logger.info(f"  Total patterns found: {total_patterns}")
        logger.info(f"  Detection rate: {total_patterns/741686*100:.1f}%")

        if pattern_counts:
            logger.info(f"  Pattern distribution:")
            for ptype, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
                pct = count / max(total_patterns, 1) * 100
                logger.info(f"    - {ptype}: {count:,} ({pct:.1f}%)")

    finally:
        conn.close()

if __name__ == "__main__":
    update_patterns()
