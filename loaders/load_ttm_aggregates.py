#!/usr/bin/env python3
"""TTM (Trailing Twelve Months) aggregates loader.

Aggregates the 4 most recent quarters into TTM tables:
- ttm_income_statement: Sum of last 4 quarters revenue, net_income, etc.
- ttm_cash_flow: Sum of last 4 quarters operating_cash_flow, free_cash_flow, etc.

Run:
    python3 load_ttm_aggregates.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import os
from datetime import datetime
import psycopg2
from psycopg2 import sql

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_ttm_aggregates():
    """Populate TTM tables by summing last 4 quarters."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'stocks'),
            user=os.getenv('DB_USER', 'stocks'),
            password=os.getenv('DB_PASSWORD', 'stocks'),
            connect_timeout=10
        )
        conn.autocommit = True
        cur = conn.cursor()

        logger.info("Loading TTM aggregates from quarterly data...")

        # TTM Income Statement - sum last 4 quarters
        logger.info("Aggregating TTM income statement...")
        # Clear existing TTM data first
        cur.execute("DELETE FROM ttm_income_statement")
        logger.info("  Cleared existing TTM income statement records")

        cur.execute("""
            INSERT INTO ttm_income_statement (symbol, date, item_name, value, created_at)
            SELECT
                symbol,
                MAX(created_at)::DATE as date,
                'ttm_aggregate'::VARCHAR as item_name,
                SUM(value) as ttm_value,
                NOW()
            FROM (
                SELECT
                    symbol,
                    revenue as value,
                    created_at,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC, fiscal_quarter DESC) as rn
                FROM quarterly_income_statement
                WHERE revenue IS NOT NULL
            ) quarterly_data
            WHERE rn <= 4
            GROUP BY symbol
        """)
        ttm_income_count = cur.rowcount
        logger.info(f"  Inserted {ttm_income_count} TTM income statement records")

        # TTM Cash Flow - sum last 4 quarters
        logger.info("Aggregating TTM cash flow...")
        # Clear existing TTM data first
        cur.execute("DELETE FROM ttm_cash_flow")
        logger.info("  Cleared existing TTM cash flow records")

        cur.execute("""
            INSERT INTO ttm_cash_flow (symbol, date, item_name, value, created_at)
            SELECT
                symbol,
                MAX(created_at)::DATE as date,
                'ttm_aggregate'::VARCHAR as item_name,
                SUM(value) as ttm_value,
                NOW()
            FROM (
                SELECT
                    symbol,
                    COALESCE(operating_cash_flow, 0) + COALESCE(free_cash_flow, 0) as value,
                    created_at,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC, fiscal_quarter DESC) as rn
                FROM quarterly_cash_flow
            ) quarterly_data
            WHERE rn <= 4
            GROUP BY symbol
        """)
        ttm_cf_count = cur.rowcount
        logger.info(f"  Inserted {ttm_cf_count} TTM cash flow records")

        cur.close()
        conn.close()

        total_ttm = ttm_income_count + ttm_cf_count
        logger.info(f"[OK] TTM aggregates loaded successfully ({total_ttm} records)")
        logger.info(f"  - TTM Income Statement: {ttm_income_count} item records")
        logger.info(f"  - TTM Cash Flow: {ttm_cf_count} item records")
        return True

    except Exception as e:
        logger.error(f"[ERROR] Error: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    success = load_ttm_aggregates()
    sys.exit(0 if success else 1)
