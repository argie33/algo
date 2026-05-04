#!/usr/bin/env python3
"""
Trend Template Data Loader

Calculates Minervini trend template fields per symbol:
- 52-week highs and lows
- Price relative to 52-week ranges
- Moving average slopes (50-day and 200-day)
- MA alignment (above/below tests)
- MA spread percentage
- Minervini trend score (0-10)
- Weinstein stage classification (1-4)
- Trend direction (uptrend/downtrend/consolidation)

Updated daily, idempotent design.
"""

import os
import sys
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import math

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)

def calculate_trend_metrics(conn, symbol, date_obj):
    """
    Calculate all trend template metrics for a symbol on a given date.
    """
    cur = conn.cursor()

    try:
        # Get 52-week high/low
        cur.execute("""
            SELECT MAX(high), MIN(low)
            FROM price_daily
            WHERE symbol = %s
            AND date >= %s - INTERVAL '365 days'
            AND date <= %s
        """, (symbol, date_obj, date_obj))

        result = cur.fetchone()
        high_52w = float(result[0]) if result and result[0] else None
        low_52w = float(result[1]) if result and result[1] else None

        if not high_52w or not low_52w:
            return None

        # Get current price and moving averages
        cur.execute("""
            SELECT pd.close, td.sma_50, td.sma_200, td.atr
            FROM price_daily pd
            LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
            WHERE pd.symbol = %s AND pd.date = %s
        """, (symbol, date_obj))

        result = cur.fetchone()
        if not result or not result[0]:
            return None

        current_price = float(result[0])
        sma_50 = float(result[1]) if result[1] else None
        sma_200 = float(result[2]) if result[2] else None
        atr = float(result[3]) if result[3] else None

        # Calculate distance from 52-week levels
        range_52w = high_52w - low_52w
        pct_from_low = ((current_price - low_52w) / range_52w * 100) if range_52w > 0 else 0
        pct_from_high = ((high_52w - current_price) / range_52w * 100) if range_52w > 0 else 0

        # Get last 2 MA values to calculate slope
        cur.execute("""
            SELECT date, sma_50, sma_200
            FROM technical_data_daily
            WHERE symbol = %s
            AND date >= %s - INTERVAL '5 days'
            AND date <= %s
            ORDER BY date DESC
            LIMIT 2
        """, (symbol, date_obj, date_obj))

        ma_data = cur.fetchall()

        sma_50_slope = 0
        sma_200_slope = 0

        if len(ma_data) >= 2:
            if ma_data[0][1] and ma_data[1][1]:
                sma_50_slope = (float(ma_data[0][1]) - float(ma_data[1][1]))
            if ma_data[0][2] and ma_data[1][2]:
                sma_200_slope = (float(ma_data[0][2]) - float(ma_data[1][2]))

        # MA alignment checks
        price_above_sma50 = current_price > sma_50 if sma_50 else False
        price_above_sma200 = current_price > sma_200 if sma_200 else False
        sma50_above_sma200 = sma_50 > sma_200 if sma_50 and sma_200 else False

        # MA spread percentage
        ma_spread = 0
        if sma_200 and sma_200 > 0:
            ma_spread = abs((sma_50 - sma_200) / sma_200 * 100) if sma_50 else 0

        # Minervini trend score (0-10)
        trend_score = 0
        if price_above_sma50:
            trend_score += 2
        if price_above_sma200:
            trend_score += 2
        if sma50_above_sma200:
            trend_score += 2
        if sma_50_slope > 0:
            trend_score += 2
        if sma_200_slope > 0:
            trend_score += 2

        # Determine trend direction
        if trend_score >= 8:
            trend_direction = 'uptrend'
        elif trend_score <= 2:
            trend_direction = 'downtrend'
        else:
            trend_direction = 'consolidation'

        # Weinstein stage
        if trend_direction == 'uptrend' and pct_from_low > 70:
            stage = 2  # Strong uptrend, good for trading
        elif trend_direction == 'uptrend' and pct_from_low <= 70:
            stage = 2  # Emerging uptrend
        elif trend_direction == 'consolidation':
            stage = 1  # Accumulation/basing
        elif trend_direction == 'downtrend':
            stage = 4  # Downtrend
        else:
            stage = 1

        # Consolidation flag
        consolidation = trend_direction == 'consolidation'

        return {
            'price_52w_high': high_52w,
            'price_52w_low': low_52w,
            'percent_from_52w_low': pct_from_low,
            'percent_from_52w_high': pct_from_high,
            'sma_50_slope': sma_50_slope,
            'sma_200_slope': sma_200_slope,
            'price_above_sma50': price_above_sma50,
            'price_above_sma200': price_above_sma200,
            'sma50_above_sma200': sma50_above_sma200,
            'ma_spread_percent': ma_spread,
            'minervini_trend_score': trend_score,
            'weinstein_stage': stage,
            'trend_direction': trend_direction,
            'consolidation_flag': consolidation
        }

    except Exception as e:
        print(f"Error calculating trends for {symbol}: {e}")
        return None
    finally:
        cur.close()

def load_trend_template_data():
    """Main loader function."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        print("\n" + "="*60)
        print("Trend Template Data Loader")
        print("="*60 + "\n")

        # Get all symbols
        cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]

        print(f"Found {len(symbols)} symbols to process\n")

        # Load last 30 days
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        total_inserted = 0
        total_skipped = 0

        for sym_idx, symbol in enumerate(symbols):
            try:
                current_date = start_date
                while current_date <= end_date:
                    try:
                        # Check if already loaded
                        cur.execute(
                            "SELECT id FROM trend_template_data WHERE symbol = %s AND date = %s",
                            (symbol, current_date)
                        )
                        if cur.fetchone():
                            total_skipped += 1
                            current_date += timedelta(days=1)
                            continue

                        # Calculate metrics
                        metrics = calculate_trend_metrics(conn, symbol, current_date)
                        if not metrics:
                            current_date += timedelta(days=1)
                            continue

                        # Insert
                        cur.execute("""
                            INSERT INTO trend_template_data (
                                symbol, date, price_52w_high, price_52w_low,
                                percent_from_52w_low, percent_from_52w_high,
                                sma_50_slope, sma_200_slope,
                                price_above_sma50, price_above_sma200,
                                sma50_above_sma200, ma_spread_percent,
                                minervini_trend_score, weinstein_stage,
                                trend_direction, consolidation_flag,
                                created_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                            )
                            ON CONFLICT (symbol, date) DO UPDATE SET
                                price_52w_high = EXCLUDED.price_52w_high,
                                price_52w_low = EXCLUDED.price_52w_low,
                                percent_from_52w_low = EXCLUDED.percent_from_52w_low,
                                percent_from_52w_high = EXCLUDED.percent_from_52w_high,
                                sma_50_slope = EXCLUDED.sma_50_slope,
                                sma_200_slope = EXCLUDED.sma_200_slope,
                                price_above_sma50 = EXCLUDED.price_above_sma50,
                                price_above_sma200 = EXCLUDED.price_above_sma200,
                                sma50_above_sma200 = EXCLUDED.sma50_above_sma200,
                                ma_spread_percent = EXCLUDED.ma_spread_percent,
                                minervini_trend_score = EXCLUDED.minervini_trend_score,
                                weinstein_stage = EXCLUDED.weinstein_stage,
                                trend_direction = EXCLUDED.trend_direction,
                                consolidation_flag = EXCLUDED.consolidation_flag
                        """, (
                            symbol, current_date,
                            metrics['price_52w_high'],
                            metrics['price_52w_low'],
                            metrics['percent_from_52w_low'],
                            metrics['percent_from_52w_high'],
                            metrics['sma_50_slope'],
                            metrics['sma_200_slope'],
                            metrics['price_above_sma50'],
                            metrics['price_above_sma200'],
                            metrics['sma50_above_sma200'],
                            metrics['ma_spread_percent'],
                            metrics['minervini_trend_score'],
                            metrics['weinstein_stage'],
                            metrics['trend_direction'],
                            metrics['consolidation_flag']
                        ))

                        total_inserted += 1

                        current_date += timedelta(days=1)

                    except Exception as e:
                        print(f"  Error on {symbol}/{current_date}: {e}")
                        conn.rollback()
                        cur.close()
                        conn = get_db_connection()
                        cur = conn.cursor()
                        current_date += timedelta(days=1)

                if (sym_idx + 1) % 50 == 0:
                    print(f"  Processed {sym_idx + 1}/{len(symbols)} symbols...")
                    conn.commit()

            except Exception as e:
                print(f"  Error on symbol {symbol}: {e}")
                continue

        conn.commit()

        print(f"\n[OK] Trend Template Data loader complete!")
        print(f"  Inserted: {total_inserted}")
        print(f"  Skipped: {total_skipped}")
        print(f"  Symbols: {len(symbols)}\n")

        return total_inserted > 0

    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    success = load_trend_template_data()
    sys.exit(0 if success else 1)
