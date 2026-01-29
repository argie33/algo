#!/usr/bin/env python3
"""
Fundamental Metrics Loader
Loads fundamental company metrics and valuation ratios
"""

import sys
import logging
import os
from lib.db import get_connection, get_db_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_NAME = "loadfundamentalmetrics.py"

def get_db_connection(script_name):
    """Get database connection using lib.db utilities"""
    try:
        cfg = get_db_config()
        conn = get_connection(cfg)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None

def main():
    """Main execution"""
    logger.info(f"🚀 Starting {SCRIPT_NAME}")

    # Get database connection
    conn = get_db_connection(SCRIPT_NAME)
    if not conn:
        logger.error("❌ Failed to connect to database")
        sys.exit(1)

    try:
        logger.info("📊 Loading fundamental metrics from key_metrics table...")

        cur = conn.cursor()

        # Ensure value_metrics table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS value_metrics (
                symbol VARCHAR(50) PRIMARY KEY,
                pe_ratio DECIMAL(10, 2),
                forward_pe DECIMAL(10, 2),
                pb_ratio DECIMAL(10, 2),
                ps_ratio DECIMAL(10, 2),
                peg_ratio DECIMAL(10, 2),
                ev_revenue DECIMAL(10, 2),
                ev_ebitda DECIMAL(10, 2),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Load valuation multiples from key_metrics
        cur.execute("""
            INSERT INTO value_metrics (symbol, pe_ratio, forward_pe, pb_ratio, ps_ratio, peg_ratio, ev_revenue, ev_ebitda)
            SELECT
                ticker,
                trailing_pe,
                forward_pe,
                price_to_book,
                price_to_sales_ttm,
                peg_ratio,
                ev_to_revenue,
                ev_to_ebitda
            FROM key_metrics
            ON CONFLICT (symbol) DO UPDATE SET
                pe_ratio = EXCLUDED.pe_ratio,
                forward_pe = EXCLUDED.forward_pe,
                pb_ratio = EXCLUDED.pb_ratio,
                ps_ratio = EXCLUDED.ps_ratio,
                peg_ratio = EXCLUDED.peg_ratio,
                ev_revenue = EXCLUDED.ev_revenue,
                ev_ebitda = EXCLUDED.ev_ebitda
        """)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM value_metrics")
        count = cur.fetchone()[0]
        logger.info(f"✅ Fundamental metrics loaded for {count} symbols")
        cur.close()
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
