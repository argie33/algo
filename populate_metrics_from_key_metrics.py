#!/usr/bin/env python3
"""
Populate value_metrics and positioning_metrics from key_metrics table
which has more complete data from yfinance
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

def populate_from_key_metrics():
    """Populate value and positioning metrics from key_metrics table"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        logger.info("Populating value_metrics from key_metrics...")
        cur.execute("""
            UPDATE value_metrics vm SET
                trailing_pe = COALESCE(km.trailing_pe, vm.trailing_pe),
                forward_pe = COALESCE(km.forward_pe, vm.forward_pe),
                price_to_book = COALESCE(km.price_to_book, vm.price_to_book),
                price_to_sales_ttm = COALESCE(km.price_to_sales_ttm, vm.price_to_sales_ttm),
                peg_ratio = COALESCE(km.peg_ratio, vm.peg_ratio),
                ev_to_revenue = COALESCE(km.ev_to_revenue, vm.ev_to_revenue),
                ev_to_ebitda = COALESCE(km.ev_to_ebitda, vm.ev_to_ebitda),
                dividend_yield = COALESCE(km.dividend_yield, vm.dividend_yield)
            FROM key_metrics km
            WHERE vm.symbol = km.ticker
            AND (km.trailing_pe IS NOT NULL 
                 OR km.price_to_book IS NOT NULL 
                 OR km.price_to_sales_ttm IS NOT NULL
                 OR km.dividend_yield IS NOT NULL)
        """)
        
        conn.commit()
        logger.info(f"✅ Updated value_metrics from key_metrics")
        
        logger.info("Populating positioning_metrics from key_metrics...")
        cur.execute("""
            UPDATE positioning_metrics pm SET
                institutional_ownership_pct = CASE 
                    WHEN km.held_percent_institutions IS NOT NULL AND km.held_percent_institutions > 0
                    THEN LEAST(km.held_percent_institutions * 100, 100)
                    ELSE pm.institutional_ownership_pct 
                END,
                insider_ownership_pct = CASE 
                    WHEN km.held_percent_insiders IS NOT NULL AND km.held_percent_insiders > 0
                    THEN LEAST(km.held_percent_insiders * 100, 100)
                    ELSE pm.insider_ownership_pct 
                END,
                short_ratio = COALESCE(km.short_ratio, pm.short_ratio),
                short_percent_of_float = COALESCE(km.short_percent_of_float, pm.short_percent_of_float),
                updated_at = NOW()
            FROM key_metrics km
            WHERE pm.symbol = km.ticker
            AND (km.held_percent_institutions IS NOT NULL 
                 OR km.held_percent_insiders IS NOT NULL
                 OR km.short_ratio IS NOT NULL
                 OR km.short_percent_of_float IS NOT NULL)
        """)
        
        conn.commit()
        logger.info(f"✅ Updated positioning_metrics from key_metrics")
        
        # Verify results
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE trailing_pe IS NOT NULL AND trailing_pe > 0) as pe_count,
                COUNT(*) FILTER (WHERE price_to_book IS NOT NULL AND price_to_book > 0) as pb_count,
                COUNT(*) FILTER (WHERE price_to_sales_ttm IS NOT NULL AND price_to_sales_ttm > 0) as ps_count,
                COUNT(*) FILTER (WHERE ev_to_revenue IS NOT NULL AND ev_to_revenue > 0) as ev_rev_count
            FROM value_metrics
        """)
        vm_results = cur.fetchone()
        
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE institutional_ownership_pct > 0 AND institutional_ownership_pct <= 100) as inst_count,
                COUNT(*) FILTER (WHERE insider_ownership_pct > 0 AND insider_ownership_pct <= 100) as insider_count,
                COUNT(*) FILTER (WHERE short_ratio IS NOT NULL AND short_ratio > 0) as short_count
            FROM positioning_metrics
        """)
        pm_results = cur.fetchone()
        
        logger.info(f"Value metrics coverage: P/E={vm_results[0]}, P/B={vm_results[1]}, P/S={vm_results[2]}, EV/Rev={vm_results[3]}")
        logger.info(f"Positioning metrics coverage: Institutional={pm_results[0]}, Insider={pm_results[1]}, Short={pm_results[2]}")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    populate_from_key_metrics()
