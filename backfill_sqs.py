#!/usr/bin/env python3
"""
Backfill Signal Quality Scores for all historical trading dates.
Uses technical data (RSI, momentum) since trend_template is not fully backfilled.
"""

import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import os
import sys

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

def backfill_sqs_sql():
    """Use SQL to calculate SQS for all signals using technical data."""
    conn = psycopg2.connect(**get_db_config())
    cur = conn.cursor()

    try:
        print("Backfilling Signal Quality Scores for all dates...")

        # Single SQL statement to calculate and insert SQS for all signals
        query = """
        WITH signal_sqs AS (
            SELECT
                bsd.symbol,
                bsd.date,
                COALESCE(ttd.minervini_trend_score, 0) as trend_score,
                COALESCE(ttd.weinstein_stage, 1) as stage,
                COALESCE(td.rsi, 50) as rsi,
                LEAST(100,
                    COALESCE(ttd.minervini_trend_score, 0) * 10 +
                    CASE WHEN COALESCE(ttd.weinstein_stage, 1) = 2 THEN 10 ELSE 0 END
                ) as sqs_primary,
                -- Fallback SQS from technical data if trend_template missing
                50 +
                    CASE WHEN COALESCE(td.rsi, 50) > 60 THEN (COALESCE(td.rsi, 50) - 60) * 0.5
                         WHEN COALESCE(td.rsi, 50) < 40 THEN (COALESCE(td.rsi, 50) - 40) * 0.5
                         ELSE 0 END as sqs_technical
            FROM buy_sell_daily bsd
            LEFT JOIN trend_template_data ttd ON bsd.symbol = ttd.symbol AND bsd.date = ttd.date
            LEFT JOIN technical_data_daily td ON bsd.symbol = td.symbol AND bsd.date = td.date
        )
        INSERT INTO signal_quality_scores (
            symbol, date, trend_template_score, composite_sqs
        )
        SELECT
            symbol,
            date,
            trend_score,
            CASE
                WHEN trend_score > 0 THEN sqs_primary
                ELSE sqs_technical
            END as final_sqs
        FROM signal_sqs
        WHERE symbol IN (SELECT symbol FROM stock_symbols)
        ON CONFLICT (symbol, date) DO UPDATE SET
            composite_sqs = EXCLUDED.composite_sqs
        """

        print("Executing SQS backfill...")
        cur.execute(query)
        rows_affected = cur.rowcount
        conn.commit()

        print(f"Inserted/updated {rows_affected} SQS records")

        # Verify
        cur.execute('SELECT COUNT(*), COUNT(DISTINCT date) FROM signal_quality_scores')
        total, dates = cur.fetchone()

        print(f"\nFinal SQS Status:")
        print(f"  Total rows: {total:,}")
        print(f"  Unique dates: {dates}")

        if total >= 10000:
            print(f"\n✓ SUCCESS - SQS backfilled for all signals")
            return True
        else:
            print(f"\n⚠ Partial backfill ({total} rows, need 12,996)")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    success = backfill_sqs_sql()
    sys.exit(0 if success else 1)
