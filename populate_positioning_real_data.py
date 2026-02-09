#!/usr/bin/env python3
"""
Populate positioning_metrics with real data from available sources
"""

import psycopg2
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "user": os.environ.get("DB_USER", "stocks"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "stocks"),
}

def populate_positioning():
    """Populate positioning_metrics with real data"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        logger.info("Checking available positioning data sources...")
        
        # Check institutional_positioning
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM institutional_positioning")
        inst_count = cur.fetchone()[0]
        logger.info(f"  Institutional positioning table: {inst_count} stocks")
        
        # Update from institutional_positioning
        if inst_count > 0:
            logger.info("Updating institutional ownership from institutional_positioning...")
            cur.execute("""
                WITH latest_inst AS (
                    SELECT symbol, SUM(market_share) as total_share
                    FROM institutional_positioning
                    WHERE filing_date = (SELECT MAX(filing_date) FROM institutional_positioning WHERE symbol = institutional_positioning.symbol)
                    GROUP BY symbol
                )
                UPDATE positioning_metrics pm SET
                    institutional_ownership_pct = li.total_share,
                    updated_at = NOW()
                FROM latest_inst li
                WHERE pm.symbol = li.symbol
            """)
            conn.commit()
            logger.info("✅ Institutional ownership updated")
        
        # Check for real short data in key_metrics  
        cur.execute("""SELECT COUNT(*) FILTER (WHERE short_ratio > 0) FROM key_metrics""")
        short_count = cur.fetchone()[0]
        logger.info(f"  Key metrics with short_ratio data: {short_count} stocks")
        
        # Update short data from key_metrics if available
        if short_count > 0:
            logger.info("Updating short data from key_metrics...")
            cur.execute("""
                UPDATE positioning_metrics pm SET
                    short_ratio = km.short_ratio,
                    short_percent_of_float = km.short_percent_of_float,
                    updated_at = NOW()
                FROM key_metrics km
                WHERE pm.symbol = km.ticker
                AND (km.short_ratio > 0 OR km.short_percent_of_float > 0)
            """)
            conn.commit()
            logger.info("✅ Short data updated")
        
        # Verify final coverage
        cur.execute("""
            SELECT 
              COUNT(*) FILTER (WHERE institutional_ownership_pct > 0 AND institutional_ownership_pct <= 100) as inst,
              COUNT(*) FILTER (WHERE insider_ownership_pct > 0 AND insider_ownership_pct <= 100) as insider,
              COUNT(*) FILTER (WHERE short_ratio > 0) as short
            FROM positioning_metrics
        """)
        
        results = cur.fetchone()
        logger.info(f"Final positioning coverage: Institutional={results[0]}, Insider={results[1]}, Short={results[2]}")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    populate_positioning()
