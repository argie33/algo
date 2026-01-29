#!/usr/bin/env python3
"""
Positioning Metrics Loader
Loads institutional positioning, insider ownership, and smart money flow data
"""

import sys
import logging
import os
from lib.db import get_connection, get_db_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_NAME = "loadpositioningmetrics.py"

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
        logger.info("📊 Loading positioning metrics from major_holders data...")

        cur = conn.cursor()

        # Get all symbols with major_holders data
        cur.execute("""
            SELECT DISTINCT symbol FROM major_holders
            WHERE major_holders IS NOT NULL
        """)
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"Processing positioning data for {len(symbols)} symbols...")

        # Load positioning metrics from major_holders data
        count = 0
        for symbol in symbols:
            try:
                cur.execute("""
                    INSERT INTO positioning_metrics (symbol, institutional_ownership_pct, insider_ownership_pct)
                    SELECT
                        %s,
                        SUM(CASE WHEN holder_type = 'Institutional' THEN percentage ELSE 0 END),
                        SUM(CASE WHEN holder_type = 'Insiders' THEN percentage ELSE 0 END)
                    FROM major_holders WHERE symbol = %s
                    ON CONFLICT (symbol) DO UPDATE SET
                        institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
                        insider_ownership_pct = EXCLUDED.insider_ownership_pct
                """, (symbol, symbol))
                count += 1
                if count % 500 == 0:
                    logger.info(f"  Processed {count}/{len(symbols)} symbols")
                    conn.commit()
            except Exception as e:
                logger.warning(f"  Error processing {symbol}: {e}")

        conn.commit()
        logger.info(f"✅ Positioning metrics loaded for {count} symbols")
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
