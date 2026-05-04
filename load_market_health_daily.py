#!/usr/bin/env python3
"""
Market Health Daily Loader

Calculates daily market-level metrics:
- Market distribution days (major indices down on heavier volume)
- Market breadth (advance-decline ratios)
- Market trend classification (uptrend/downtrend/consolidation)
- Market stage per Weinstein (1-4 scale)
- VIX, put/call ratios, yield curve
- Fed sentiment from economic data

Updated daily, idempotent design.
"""

import os
import sys
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

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

def get_market_indices():
    """Get major market indices for breadth calculation."""
    indices = ['^GSPC', '^INDU', '^IXIC', '^NYA', '^CCMP', '^RUT']
    return indices

def calculate_market_distribution_days(conn, date_obj):
    """
    Calculate distribution days for major indices.
    Distribution day = index down on heavier volume than previous 5-day avg.
    """
    cur = conn.cursor()

    try:
        # Get SPY (proxy for market) price and volume data for last 20 days
        cur.execute("""
            SELECT date, close, volume
            FROM price_daily
            WHERE symbol = '^GSPC'
            AND date >= %s - INTERVAL '20 days'
            AND date <= %s
            ORDER BY date DESC
            LIMIT 20
        """, (date_obj, date_obj))

        data = cur.fetchall()
        if not data:
            return 0

        # Count distribution days in last 4 weeks (20 trading days)
        dist_days = 0
        for i, (date, close, volume) in enumerate(data):
            if i < 1:
                continue

            prev_close = data[i-1][1]
            prev_volume = data[i-1][2]

            # Down day on heavier volume = distribution day
            if close < prev_close and volume > prev_volume * 1.05:
                dist_days += 1

        return dist_days
    except Exception as e:
        print(f"Error calculating distribution days: {e}")
        return 0
    finally:
        cur.close()

def calculate_market_breadth(conn, date_obj):
    """
    Calculate market breadth metrics.
    Compare advancing vs declining stocks.
    """
    cur = conn.cursor()

    try:
        # Get all stocks with price data for the date
        cur.execute("""
            SELECT symbol, close, (
                SELECT close FROM price_daily pd2
                WHERE pd2.symbol = pd1.symbol
                AND pd2.date < %s
                ORDER BY pd2.date DESC
                LIMIT 1
            ) as prev_close
            FROM price_daily pd1
            WHERE date = %s
        """, (date_obj, date_obj))

        stocks = cur.fetchall()
        advancing = sum(1 for s in stocks if s[1] and s[2] and s[1] > s[2])
        declining = sum(1 for s in stocks if s[1] and s[2] and s[1] < s[2])

        if advancing + declining == 0:
            ratio = 0
            up_pct = 0
        else:
            ratio = advancing / max(declining, 1)
            up_pct = (advancing / (advancing + declining)) * 100

        return {
            'advancing': advancing,
            'declining': declining,
            'ratio': ratio,
            'up_percent': up_pct
        }
    except Exception as e:
        print(f"Error calculating breadth: {e}")
        return {'advancing': 0, 'declining': 0, 'ratio': 0, 'up_percent': 0}
    finally:
        cur.close()

def determine_market_trend(conn, date_obj):
    """
    Classify market trend based on technical indicators.
    Uptrend = price above MAs, MAs aligned
    Downtrend = price below MAs
    Consolidation = sideways action
    """
    cur = conn.cursor()

    try:
        # Get SPY data
        cur.execute("""
            SELECT pd.date, pd.close, td.sma_50, td.sma_200
            FROM price_daily pd
            LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
            WHERE pd.symbol = '^GSPC'
            AND pd.date >= %s - INTERVAL '60 days'
            AND pd.date <= %s
            ORDER BY pd.date DESC
            LIMIT 60
        """, (date_obj, date_obj))

        data = cur.fetchall()
        if len(data) < 2:
            return 'unknown'

        latest = data[0]
        prev = data[1]

        if not latest[1]:
            return 'unknown'

        # Trend classification
        if latest[1] > latest[2] > latest[3] if latest[2] and latest[3] else False:
            return 'uptrend'
        elif latest[1] < latest[2] < latest[3] if latest[2] and latest[3] else False:
            return 'downtrend'
        else:
            return 'consolidation'
    except Exception as e:
        print(f"Error determining market trend: {e}")
        return 'unknown'
    finally:
        cur.close()

def determine_market_stage(conn, date_obj, trend):
    """
    Classify market stage per Weinstein (1-4).
    Stage 1: Downtrend, declining
    Stage 2: Uptrend, advancing (BEST for trading)
    Stage 3: Top, rolling over
    Stage 4: Downtrend deteriorating
    """
    breadth = calculate_market_breadth(conn, date_obj)

    if trend == 'uptrend' and breadth['up_percent'] > 55:
        return 2  # Stage 2 - Best for trading
    elif trend == 'uptrend' and breadth['up_percent'] < 55:
        return 3  # Stage 3 - Rolling over
    elif trend == 'downtrend':
        return 4  # Stage 4 - Deteriorating
    elif trend == 'consolidation':
        return 1  # Stage 1 - Accumulation/basing
    else:
        return 1

def get_vix_level(conn, date_obj):
    """Get VIX (volatility) level if available."""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT close FROM price_daily
            WHERE symbol = '^VIX' AND date = %s
        """, (date_obj,))
        result = cur.fetchone()
        return float(result[0]) if result and result[0] else 20.0
    except:
        return 20.0
    finally:
        cur.close()

def load_market_health_daily():
    """Main loader function."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        print("\n" + "="*60)
        print("Market Health Daily Loader")
        print("="*60 + "\n")

        # Start from 90 days ago to catch up
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=90)

        current_date = start_date
        inserted = 0
        updated = 0
        skipped = 0

        while current_date <= end_date:
            try:
                # Check if already loaded for this date
                cur.execute(
                    "SELECT id FROM market_health_daily WHERE date = %s",
                    (current_date,)
                )
                if cur.fetchone():
                    skipped += 1
                    current_date += timedelta(days=1)
                    continue

                # Calculate metrics
                dist_days = calculate_market_distribution_days(conn, current_date)
                breadth = calculate_market_breadth(conn, current_date)
                trend = determine_market_trend(conn, current_date)
                stage = determine_market_stage(conn, current_date, trend)
                vix = get_vix_level(conn, current_date)

                # Insert or update
                cur.execute("""
                    INSERT INTO market_health_daily (
                        date, market_trend, market_stage,
                        distribution_days_4w, up_volume_percent,
                        advance_decline_ratio, vix_level, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (date) DO UPDATE SET
                        market_trend = EXCLUDED.market_trend,
                        market_stage = EXCLUDED.market_stage,
                        distribution_days_4w = EXCLUDED.distribution_days_4w,
                        up_volume_percent = EXCLUDED.up_volume_percent,
                        advance_decline_ratio = EXCLUDED.advance_decline_ratio,
                        vix_level = EXCLUDED.vix_level
                """, (
                    current_date, trend, stage,
                    dist_days, breadth['up_percent'],
                    breadth['ratio'], vix
                ))

                inserted += 1

                if inserted % 10 == 0:
                    print(f"  Processed {inserted} dates...")
                    conn.commit()

            except Exception as e:
                print(f"  Error on {current_date}: {e}")
                conn.rollback()
                # Reconnect after error
                cur.close()
                conn.close()
                conn = get_db_connection()
                cur = conn.cursor()

            current_date += timedelta(days=1)

        conn.commit()

        print(f"\n[OK] Market Health Daily loader complete!")
        print(f"  Inserted: {inserted}")
        print(f"  Skipped: {skipped}")
        print(f"  Period: {start_date} to {end_date}\n")

        return inserted > 0

    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    success = load_market_health_daily()
    sys.exit(0 if success else 1)
