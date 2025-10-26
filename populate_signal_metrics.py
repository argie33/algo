#!/usr/bin/env python3
"""
Populate missing calculated fields in buy_sell_daily table.

Calculates:
- avg_volume_50d: 50-day average volume from price_daily
- volume_surge_pct: (current_volume / avg_volume_50d - 1) * 100
- risk_reward_ratio: (target_price - entry_price) / (entry_price - stop_loss)
- breakout_quality: Based on price range and volume surge

This is a post-processing step to fill in metrics that the loader didn't calculate.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# DB Configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "stocks")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=60000'
    )
    return conn

def calculate_avg_volume_50d(conn, symbol, date):
    """
    Calculate 50-day average volume for a given symbol and date.

    Args:
        conn: Database connection
        symbol: Stock symbol
        date: Target date (DATE)

    Returns:
        Average volume (int) or 0 if not enough data
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Get 50-day average volume ending at or before the given date
        sql = """
            SELECT AVG(volume)::BIGINT as avg_volume
            FROM price_daily
            WHERE symbol = %s
              AND date <= %s
              AND date > %s - INTERVAL '50 days'
        """
        cur.execute(sql, (symbol, date, date))
        result = cur.fetchone()
        avg_vol = result['avg_volume'] if result and result['avg_volume'] else 0
        return avg_vol if avg_vol > 0 else 0
    except Exception as e:
        logging.warning(f"Error calculating avg_volume_50d for {symbol} {date}: {e}")
        return 0
    finally:
        cur.close()

def calculate_volume_surge_pct(current_volume, avg_volume_50d):
    """
    Calculate volume surge percentage.

    Formula: (current_volume / avg_volume_50d - 1) * 100
    """
    if avg_volume_50d <= 0:
        return 0.0
    surge = ((current_volume / avg_volume_50d) - 1.0) * 100
    return round(max(-100, surge), 2)  # Clamp to -100% minimum

def calculate_risk_reward_ratio(close_price, buy_level, stop_level):
    """
    Calculate risk/reward ratio.

    Formula: (target_price - entry_price) / (entry_price - stop_loss)
    Where:
    - entry_price = buy_level
    - stop_loss = stop_level
    - target_price = close_price * 1.25 (25% profit target)
    """
    if stop_level <= 0 or buy_level <= 0 or (buy_level - stop_level) == 0:
        return 0.0

    target_price = close_price * 1.25 if close_price > 0 else buy_level * 1.25
    profit = target_price - buy_level
    risk = buy_level - stop_level

    if risk == 0:
        return 0.0

    ratio = profit / risk
    return round(max(0, ratio), 2)  # Clamp to >= 0

def determine_breakout_quality(high, low, volume_surge_pct):
    """
    Determine breakout quality based on price range and volume surge.

    Returns: 'STRONG', 'MODERATE', or 'WEAK'
    """
    if low <= 0:
        return 'WEAK'

    daily_range_pct = ((high - low) / low) * 100

    # STRONG: > 3% range AND > 50% volume surge
    if daily_range_pct > 3.0 and volume_surge_pct > 50:
        return 'STRONG'
    # MODERATE: > 1.5% range AND > 25% volume surge
    elif daily_range_pct > 1.5 and volume_surge_pct > 25:
        return 'MODERATE'
    # WEAK: anything else
    else:
        return 'WEAK'

def populate_metrics():
    """Main function to populate missing metrics."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get records with missing or zero values
        logging.info("📊 Fetching records with missing calculated fields...")
        sql = """
            SELECT id, symbol, date, open, high, low, close, volume, buylevel, stoplevel,
                   avg_volume_50d, volume_surge_pct, risk_reward_ratio, breakout_quality
            FROM buy_sell_daily
            WHERE (avg_volume_50d = 0 OR avg_volume_50d IS NULL
                OR volume_surge_pct = 0 OR volume_surge_pct IS NULL
                OR risk_reward_ratio = 0 OR risk_reward_ratio IS NULL
                OR breakout_quality IS NULL)
              AND date >= CURRENT_DATE - INTERVAL '60 days'
            ORDER BY date DESC
            LIMIT 5000
        """
        cur.execute(sql)
        records = cur.fetchall()
        logging.info(f"Found {len(records)} records to update")

        if not records:
            logging.info("✅ No records need updating")
            return

        # Process each record
        updated = 0
        skipped = 0

        for idx, record in enumerate(records):
            try:
                record_id = record['id']
                symbol = record['symbol']
                date = record['date']
                volume = record['volume']
                close = record['close']
                buy_level = record['buylevel']
                stop_level = record['stoplevel']

                # Calculate avg_volume_50d
                avg_vol_50d = calculate_avg_volume_50d(conn, symbol, date)

                # Calculate volume_surge_pct
                vol_surge = calculate_volume_surge_pct(volume, avg_vol_50d)

                # Calculate risk_reward_ratio
                rr_ratio = calculate_risk_reward_ratio(close, buy_level, stop_level)

                # Determine breakout_quality
                breakout_qual = determine_breakout_quality(record['high'], record['low'], vol_surge)

                # Update the record
                update_sql = """
                    UPDATE buy_sell_daily
                    SET avg_volume_50d = %s,
                        volume_surge_pct = %s,
                        risk_reward_ratio = %s,
                        breakout_quality = %s
                    WHERE id = %s
                """
                cur.execute(update_sql, (avg_vol_50d, vol_surge, rr_ratio, breakout_qual, record_id))
                updated += 1

                # Log progress every 100 records
                if (idx + 1) % 100 == 0:
                    logging.info(f"  Processed {idx + 1}/{len(records)} records...")

            except Exception as e:
                logging.warning(f"Error processing record {record['id']}: {e}")
                skipped += 1
                continue

        # Commit all changes
        conn.commit()
        logging.info(f"✅ Updated {updated} records, skipped {skipped}")

        # Show sample of updated records
        logging.info("\n📋 Sample of updated records:")
        sample_sql = """
            SELECT symbol, date, avg_volume_50d, volume_surge_pct,
                   risk_reward_ratio, breakout_quality
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '5 days'
            ORDER BY date DESC
            LIMIT 10
        """
        cur.execute(sample_sql)
        samples = cur.fetchall()
        for row in samples:
            logging.info(f"  {row['symbol']:6} {row['date']} | AvgVol50d: {row['avg_volume_50d']:>12} | "
                         f"VolSurge: {row['volume_surge_pct']:>7.2f}% | RR: {row['risk_reward_ratio']:>5.2f} | "
                         f"Quality: {row['breakout_quality']}")

    except Exception as e:
        logging.error(f"Fatal error in populate_metrics: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    logging.info("=" * 80)
    logging.info("Starting Signal Metrics Population Script")
    logging.info("=" * 80)

    try:
        populate_metrics()
        logging.info("\n" + "=" * 80)
        logging.info("✅ Metrics population complete!")
        logging.info("=" * 80)
    except Exception as e:
        logging.error(f"\n❌ Script failed: {e}")
        sys.exit(1)
