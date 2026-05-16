#!/usr/bin/env python3
"""
Efficient SQL-based backfill of trend_template_data for all historical dates.

Uses window functions to calculate trend metrics in bulk rather than per-symbol per-date.
Much faster than looping approach.
"""

import psycopg2
import sys
from pathlib import Path
from dotenv import load_dotenv
import os

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "stocks"),
    }

def backfill_sql():
    """Use SQL to efficiently backfill trend_template_data."""
    conn = psycopg2.connect(**get_db_config())
    cur = conn.cursor()

    try:
        print("Starting SQL-based backfill of trend_template_data...\n")

        # Single efficient SQL statement to calculate and insert all trend data
        query = """
        WITH price_stats AS (
            SELECT
                symbol,
                date,
                close,
                high,
                low,
                MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) as high_52w,
                MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) as low_52w,
                AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma50,
                AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) as sma200
            FROM price_daily
            WHERE date <= (SELECT MAX(date) FROM price_daily)
        ),
        trend_calcs AS (
            SELECT
                symbol,
                date,
                high_52w,
                low_52w,
                close,
                sma50,
                sma200,
                CASE
                    WHEN high_52w != low_52w THEN ((close - low_52w) / (high_52w - low_52w) * 100)
                    ELSE 50
                END as pct_from_low,
                CASE
                    WHEN high_52w != low_52w THEN ((high_52w - close) / (high_52w - low_52w) * 100)
                    ELSE 50
                END as pct_from_high,
                CASE
                    WHEN (close > sma50) THEN 1 ELSE 0
                END +
                CASE
                    WHEN (close > sma200) THEN 1 ELSE 0
                END +
                CASE
                    WHEN (sma50 > sma200) THEN 1 ELSE 0
                END as base_score
            FROM price_stats
            WHERE high_52w IS NOT NULL AND low_52w IS NOT NULL
        ),
        final_scores AS (
            SELECT
                symbol,
                date,
                high_52w,
                low_52w,
                pct_from_low,
                pct_from_high,
                (close > sma50) as price_above_sma50,
                (close > sma200) as price_above_sma200,
                (sma50 > sma200) as sma50_above_sma200,
                LEAST(10, base_score + CASE WHEN pct_from_low > 75 THEN 1 ELSE 0 END) as trend_score
            FROM trend_calcs
        )
        INSERT INTO trend_template_data (
            symbol, date, price_52w_high, price_52w_low,
            percent_from_52w_low, percent_from_52w_high,
            price_above_sma50, price_above_sma200,
            sma50_above_sma200,
            minervini_trend_score, weinstein_stage,
            trend_direction, consolidation_flag
        )
        SELECT
            symbol,
            date,
            high_52w,
            low_52w,
            pct_from_low,
            pct_from_high,
            price_above_sma50,
            price_above_sma200,
            sma50_above_sma200,
            trend_score,
            CASE
                WHEN trend_score >= 8 THEN 2
                WHEN trend_score <= 2 THEN 4
                ELSE 1
            END as stage,
            CASE
                WHEN trend_score >= 8 THEN 'uptrend'
                WHEN trend_score <= 2 THEN 'downtrend'
                ELSE 'consolidation'
            END as direction,
            CASE
                WHEN trend_score NOT IN (8,9,10,0,1,2) THEN TRUE
                ELSE FALSE
            END as consolidation
        FROM final_scores
        ON CONFLICT (symbol, date) DO NOTHING
        """

        print("Executing bulk trend calculation SQL...")
        cur.execute(query)
        conn.commit()

        # Verify results
        cur.execute('SELECT COUNT(*), COUNT(DISTINCT date), COUNT(DISTINCT symbol) FROM trend_template_data')
        total, dates, symbols = cur.fetchone()

        print(f"\n✓ Backfill completed!")
        print(f"  Total rows: {total:,}")
        print(f"  Unique dates: {dates}")
        print(f"  Unique symbols: {symbols}")

        if dates >= 1000:
            print(f"\n✓ BACKFILL SUCCESSFUL - Ready for SQS regeneration")
            return True
        else:
            print(f"\n⚠ Backfill incomplete ({dates} dates)")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    success = backfill_sql()
    sys.exit(0 if success else 1)
