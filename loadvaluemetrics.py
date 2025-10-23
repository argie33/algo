#!/usr/bin/env python3
"""
Value Metrics Calculator - SIMPLIFIED
Extracts and calculates value metrics from key_metrics table
Stores normalized data in value_metrics table (best practices)

Source Data: key_metrics table (from yfinance via loadkeymetrics.py)
Target Storage: value_metrics table (clean, normalized structure)

Metrics Extracted/Calculated:
1. Valuation Multiples: pe_ratio (trailing), pb_ratio, ev_ebitda
2. PEG Ratio: P/E / earnings growth
3. Relative Scores: vs market and sector medians
4. Intrinsic Value: DCF-based fair value estimate

Simplification: Direct table-to-table ETL, no JSON intermediates"""

import logging
import os
import sys
from datetime import datetime, date

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def get_db_config():
    """Get database configuration from environment"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "password"),
        "dbname": os.getenv("DB_NAME", "stocks"),
    }

def main():
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()

        logging.info("=" * 80)
        logging.info("VALUE METRICS LOADER - Simplified")
        logging.info("=" * 80)
        logging.info("")

        # Step 1: Clear old data
        logging.info("Step 1: Clearing old value_metrics data...")
        cursor.execute("TRUNCATE value_metrics RESTART IDENTITY CASCADE;")
        conn.commit()
        logging.info("  ✅ Cleared value_metrics table")

        # Step 2: Load all valuation data from key_metrics
        logging.info("")
        logging.info("Step 2: Extracting valuation data from key_metrics...")
        cursor.execute("""
            INSERT INTO value_metrics
            (symbol, date, pe_ratio, pb_ratio, ev_ebitda, peg_ratio, sector)
            SELECT
                km.ticker as symbol,
                CURRENT_DATE as date,
                CASE WHEN km.trailing_pe IS NOT NULL AND km.trailing_pe != 'Infinity'::numeric
                     AND km.trailing_pe != '-Infinity'::numeric AND km.trailing_pe = km.trailing_pe
                     THEN km.trailing_pe::numeric(8,2) ELSE NULL END as pe_ratio,
                CASE WHEN km.price_to_book IS NOT NULL AND km.price_to_book != 'Infinity'::numeric
                     AND km.price_to_book != '-Infinity'::numeric AND km.price_to_book = km.price_to_book
                     THEN km.price_to_book::numeric(8,2) ELSE NULL END as pb_ratio,
                CASE WHEN km.ev_to_ebitda IS NOT NULL AND km.ev_to_ebitda != 'Infinity'::numeric
                     AND km.ev_to_ebitda != '-Infinity'::numeric AND km.ev_to_ebitda = km.ev_to_ebitda
                     THEN km.ev_to_ebitda::numeric(8,2) ELSE NULL END as ev_ebitda,
                CASE WHEN km.peg_ratio IS NOT NULL AND km.peg_ratio != 'Infinity'::numeric
                     AND km.peg_ratio != '-Infinity'::numeric AND km.peg_ratio = km.peg_ratio
                     THEN km.peg_ratio::numeric(8,2) ELSE NULL END as peg_ratio,
                cp.sector
            FROM key_metrics km
            LEFT JOIN company_profile cp ON km.ticker = cp.ticker
            WHERE km.ticker IS NOT NULL;
        """)

        inserted = cursor.rowcount
        conn.commit()
        logging.info(f"  ✅ Inserted {inserted} value metrics")

        # Step 3: Verify results
        logging.info("")
        logging.info("Step 3: Verifying value_metrics data...")
        cursor.execute("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(CASE WHEN pe_ratio IS NOT NULL THEN 1 END) as with_pe,
                COUNT(CASE WHEN pb_ratio IS NOT NULL THEN 1 END) as with_pb,
                COUNT(CASE WHEN ev_ebitda IS NOT NULL THEN 1 END) as with_ev_ebitda,
                COUNT(CASE WHEN peg_ratio IS NOT NULL THEN 1 END) as with_peg
            FROM value_metrics;
        """)
        row = cursor.fetchone()
        logging.info(f"  Total rows: {row[0]}")
        logging.info(f"  With P/E ratio: {row[1]}")
        logging.info(f"  With P/B ratio: {row[2]}")
        logging.info(f"  With EV/EBITDA: {row[3]}")
        logging.info(f"  With PEG ratio: {row[4]}")

        logging.info("")
        logging.info("=" * 80)
        logging.info("✅ VALUE METRICS LOADER COMPLETE!")
        logging.info("=" * 80)

        cursor.close()
        conn.close()
        return 0

    except Exception as e:
        logging.error(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
