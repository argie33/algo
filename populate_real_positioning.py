#!/usr/bin/env python3
"""
Populate real positioning metrics from institutional_positioning and insider data
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

def populate_real_positioning():
    """Populate positioning_metrics with real data from institutional_positioning"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Get institutional ownership from institutional_positioning
        logger.info("Loading institutional ownership data...")
        cur.execute("""
            SELECT symbol, SUM(market_share) as total_inst_ownership
            FROM institutional_positioning
            WHERE filing_date = (SELECT MAX(filing_date) FROM institutional_positioning WHERE symbol = institutional_positioning.symbol)
            GROUP BY symbol
        """)
        
        inst_data = cur.fetchall()
        logger.info(f"Found institutional data for {len(inst_data)} stocks")
        
        # Get insider ownership count
        logger.info("Loading insider ownership data...")
        cur.execute("""
            SELECT symbol, COUNT(DISTINCT insider_name) as insider_count
            FROM insider_roster
            GROUP BY symbol
        """)
        
        insider_data = cur.fetchall()
        insider_dict = {row[0]: row[1] for row in insider_data}
        logger.info(f"Found insider data for {len(insider_dict)} stocks")
        
        # Update positioning_metrics with real institutional data
        updated = 0
        for symbol, inst_ownership in inst_data:
            try:
                # Calculate insider ownership as percentage (using count as proxy)
                insider_ownership = min(insider_dict.get(symbol, 0) / 100.0, 50.0)  # Cap at 50%
                
                cur.execute("""
                    UPDATE positioning_metrics 
                    SET institutional_ownership_pct = %s,
                        insider_ownership_pct = %s,
                        updated_at = NOW()
                    WHERE symbol = %s
                """, (inst_ownership, insider_ownership, symbol))
                updated += 1
                
                if updated % 100 == 0:
                    logger.info(f"  Updated {updated} stocks...")
                    conn.commit()
                    
            except Exception as e:
                logger.error(f"Error updating {symbol}: {str(e)[:100]}")
        
        conn.commit()
        logger.info(f"✅ Updated {updated} positioning_metrics with real institutional data")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    populate_real_positioning()
