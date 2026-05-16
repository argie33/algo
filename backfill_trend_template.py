#!/usr/bin/env python3
"""
Backfill trend_template_data for all historical trading dates.

This script fills the gap where trend_template_data only had one day of data.
With this backfill, load_algo_metrics_daily can create SQS for all 12,996 signals.
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "stocks"),
    }

def backfill_trend_template():
    """Backfill trend_template_data for all trading dates."""
    conn = psycopg2.connect(**_get_db_config())
    cur = conn.cursor()

    try:
        # Get all unique trading dates from price_daily, ordered chronologically
        cur.execute('''
            SELECT DISTINCT date FROM price_daily
            ORDER BY date ASC
        ''')
        dates = [row[0] for row in cur.fetchall()]
        logger.info(f"Found {len(dates)} trading dates to backfill")

        # Get all symbols
        cur.execute('SELECT symbol FROM stock_symbols ORDER BY symbol')
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"Processing {len(symbols)} symbols")

        # For each date, calculate trend template data for all symbols
        inserted = 0
        for i, date_obj in enumerate(dates):
            if (i + 1) % 100 == 0:
                logger.info(f"  Progress: {i+1}/{len(dates)} dates")

            for symbol in symbols:
                # Get price data for this symbol up to this date
                cur.execute('''
                    SELECT date, close, high, low, volume
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC
                    LIMIT 252  -- 1 year of trading days
                ''', (symbol, date_obj))
                rows = cur.fetchall()

                if len(rows) < 50:  # Need at least 50 days for calculations
                    continue

                # Extract data
                dates_list = [row[0] for row in rows]
                closes = [float(row[1]) for row in rows]
                highs = [float(row[2]) for row in rows]
                lows = [float(row[3]) for row in rows]
                volumes = [float(row[4]) for row in rows]

                # Reverse to chronological order
                dates_list = list(reversed(dates_list))
                closes = list(reversed(closes))
                highs = list(reversed(highs))
                lows = list(reversed(lows))
                volumes = list(reversed(volumes))

                try:
                    # Calculate 52-week high/low
                    high_52w = max(highs)
                    low_52w = min(lows)

                    # Calculate SMA
                    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else closes[-1]
                    sma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else closes[-1]
                    current = closes[-1]

                    # Boolean flags
                    price_above_sma50 = current > sma50
                    price_above_sma200 = current > sma200
                    sma50_above_sma200 = sma50 > sma200

                    # Calculate percentages
                    pct_from_low = ((current - low_52w) / (high_52w - low_52w) * 100) if high_52w != low_52w else 50
                    pct_from_high = ((high_52w - current) / (high_52w - low_52w) * 100) if high_52w != low_52w else 50

                    # Simple Minervini trend score (0-10)
                    trend_score = 0
                    if price_above_sma50:
                        trend_score += 3
                    if price_above_sma200:
                        trend_score += 3
                    if sma50_above_sma200:
                        trend_score += 2
                    if pct_from_low > 75:
                        trend_score += 2

                    trend_score = min(10, trend_score)

                    # Determine stage
                    if trend_score >= 8:
                        stage = 2
                        trend_dir = 'uptrend'
                    elif trend_score <= 2:
                        stage = 4
                        trend_dir = 'downtrend'
                    else:
                        stage = 1
                        trend_dir = 'consolidation'

                    # Insert
                    query = '''
                        INSERT INTO trend_template_data (
                            symbol, date, price_52w_high, price_52w_low,
                            percent_from_52w_low, percent_from_52w_high,
                            price_above_sma50, price_above_sma200,
                            sma50_above_sma200,
                            minervini_trend_score, weinstein_stage,
                            trend_direction, consolidation_flag, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            price_52w_high = EXCLUDED.price_52w_high,
                            price_52w_low = EXCLUDED.price_52w_low
                    '''

                    cur.execute(query, (
                        symbol, date_obj, high_52w, low_52w,
                        pct_from_low, pct_from_high,
                        price_above_sma50, price_above_sma200, sma50_above_sma200,
                        trend_score, stage, trend_dir,
                        trend_dir == 'consolidation'
                    ))
                    inserted += 1

                except Exception as e:
                    logger.debug(f"Error calculating trend for {symbol} on {date_obj}: {e}")
                    continue

        conn.commit()
        logger.info(f"Successfully inserted {inserted} trend_template_data records")

        # Verify
        cur.execute('SELECT COUNT(*) FROM trend_template_data')
        final_count = cur.fetchone()[0]
        logger.info(f"Final trend_template_data count: {final_count}")

        return True

    except Exception as e:
        logger.error(f"Error in backfill: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    success = backfill_trend_template()
    sys.exit(0 if success else 1)
