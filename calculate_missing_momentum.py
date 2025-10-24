#!/usr/bin/env python3
"""
Calculate and populate missing momentum scores for ALL stocks.
Focuses on direct calculation and database update.
"""

import sys
import logging
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf

# Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
        dbname=os.getenv("DB_NAME", "stocks")
    )

def calculate_momentum_score(symbol: str) -> dict:
    """
    Calculate momentum score for a single symbol.
    Momentum = 12-1 month return (Jegadeesh-Titman methodology)
    Returns dict with symbol and momentum_score
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y")

        if hist.empty or len(hist) < 252:
            logging.warning(f"Insufficient data for {symbol}")
            return {"symbol": symbol, "momentum_score": 0.0}

        # Jegadeesh-Titman 12-1 month momentum
        current_price = hist['Close'].iloc[-1]
        price_12m_ago = hist['Close'].iloc[-252]
        price_1m_ago = hist['Close'].iloc[-21]

        # 12-1 month return (skip most recent month to avoid short-term reversal)
        jt_momentum = ((price_1m_ago - price_12m_ago) / price_12m_ago) * 100

        # Normalize to 0-100 scale
        momentum_score = max(0, min(100, 50 + (jt_momentum / 2)))  # Center around 50

        return {
            "symbol": symbol,
            "momentum_score": round(momentum_score, 2),
            "jt_momentum_raw": round(jt_momentum, 4)
        }

    except Exception as e:
        logging.error(f"Error calculating momentum for {symbol}: {e}")
        return {"symbol": symbol, "momentum_score": 0.0}

def main():
    conn = get_db_connection()
    cur = conn.cursor()

    logging.info("=" * 80)
    logging.info("MOMENTUM SCORE CALCULATION FOR ALL STOCKS")
    logging.info("=" * 80)

    # Get all symbols
    cur.execute("""
        SELECT symbol FROM stock_scores
        WHERE symbol IS NOT NULL
        ORDER BY symbol
    """)
    symbols = [row[0] for row in cur.fetchall()]
    logging.info(f"Total symbols to process: {len(symbols)}")

    # Split into groups to show progress
    batch_size = 100
    total_processed = 0
    total_updated = 0

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        logging.info(f"\n>>> Processing batch {batch_num}/{total_batches} ({len(batch)} symbols)...")

        momentum_data = []
        for j, symbol in enumerate(batch):
            result = calculate_momentum_score(symbol)
            momentum_data.append(result)
            total_processed += 1

            if (j + 1) % 10 == 0:
                logging.info(f"    [{symbol}] Processed {j + 1}/{len(batch)}")

            # Rate limiting
            time.sleep(0.1)

        # Update database
        logging.info(f"    Updating {len(momentum_data)} records in stock_scores...")
        try:
            for data in momentum_data:
                cur.execute("""
                    UPDATE stock_scores
                    SET momentum_score = %s, last_updated = CURRENT_TIMESTAMP
                    WHERE symbol = %s
                """, (data["momentum_score"], data["symbol"]))

            conn.commit()
            total_updated += len(momentum_data)
            logging.info(f"    ✅ Batch {batch_num} updated successfully")

        except Exception as e:
            conn.rollback()
            logging.error(f"    ❌ Batch {batch_num} failed: {e}")

        # Progress summary
        progress_pct = (total_processed / len(symbols)) * 100
        logging.info(f"    Progress: {total_processed}/{len(symbols)} ({progress_pct:.1f}%)")

    # Final verification
    logging.info("\n" + "=" * 80)
    logging.info("VERIFICATION")
    logging.info("=" * 80)

    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN momentum_score IS NOT NULL THEN 1 END) as with_score,
            COUNT(CASE WHEN momentum_score = 0 THEN 1 END) as zero_scores,
            ROUND(AVG(momentum_score)::NUMERIC, 2) as avg_score,
            MIN(momentum_score) as min_score,
            MAX(momentum_score) as max_score
        FROM stock_scores
    """)

    stats = cur.fetchone()
    logging.info(f"Total stocks: {stats[0]:,}")
    logging.info(f"Stocks with momentum score: {stats[1]:,}")
    logging.info(f"Stocks with zero score: {stats[2]:,}")
    logging.info(f"Average momentum score: {stats[3]}")
    logging.info(f"Score range: {stats[4]:.2f} - {stats[5]:.2f}")

    # Check Q-Z stocks specifically
    logging.info("\n" + "=" * 80)
    logging.info("Q-Z STOCKS CHECK")
    logging.info("=" * 80)

    for letter in ['Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
        cur.execute("""
            SELECT COUNT(*) FROM stock_scores
            WHERE LEFT(symbol, 1) = %s AND momentum_score IS NOT NULL AND momentum_score > 0
        """, (letter,))
        count = cur.fetchone()[0]
        logging.info(f"  {letter}: {count} stocks with momentum score > 0")

    cur.close()
    conn.close()

    logging.info("\n" + "=" * 80)
    logging.info("✅ MOMENTUM SCORE CALCULATION COMPLETE")
    logging.info("=" * 80)

if __name__ == "__main__":
    main()
