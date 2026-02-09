#!/usr/bin/env python3
"""
Calculate missing quality metrics from annual financial statements
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

def calculate_quality_metrics():
    """Calculate profitability metrics from financial statements"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        logger.info("Calculating ROE, ROA, and margins from financial data...")
        
        # Calculate profitability metrics
        cur.execute("""
            WITH latest_financials AS (
                SELECT DISTINCT ON (ais.symbol)
                    ais.symbol,
                    ais.revenue,
                    ais.operating_income,
                    ais.net_income,
                    abs.total_equity,
                    abs.total_assets
                FROM annual_income_statement ais
                LEFT JOIN annual_balance_sheet abs ON ais.symbol = abs.symbol
                WHERE ais.revenue > 0 AND ais.net_income IS NOT NULL
                ORDER BY ais.symbol, ais.date DESC
            )
            UPDATE quality_metrics qm SET
                return_on_equity_pct = CASE 
                    WHEN lf.total_equity > 0 THEN (lf.net_income::NUMERIC / lf.total_equity) * 100 
                    ELSE NULL END,
                return_on_assets_pct = CASE 
                    WHEN lf.total_assets > 0 THEN (lf.net_income::NUMERIC / lf.total_assets) * 100 
                    ELSE NULL END,
                operating_margin_pct = CASE 
                    WHEN lf.revenue > 0 AND lf.operating_income IS NOT NULL
                    THEN (lf.operating_income::NUMERIC / lf.revenue) * 100 
                    ELSE NULL END,
                profit_margin_pct = COALESCE(qm.profit_margin_pct, 
                    CASE WHEN lf.revenue > 0 THEN (lf.net_income::NUMERIC / lf.revenue) * 100 ELSE NULL END)
            FROM latest_financials lf
            WHERE qm.symbol = lf.symbol
        """)
        
        conn.commit()
        logger.info("✅ Profitability metrics calculated")
        
        # Count results
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE return_on_equity_pct IS NOT NULL AND return_on_equity_pct > -999) as roe,
                COUNT(*) FILTER (WHERE return_on_assets_pct IS NOT NULL AND return_on_assets_pct > -999) as roa,
                COUNT(*) FILTER (WHERE operating_margin_pct IS NOT NULL) as om,
                COUNT(*) FILTER (WHERE profit_margin_pct IS NOT NULL) as pm
            FROM quality_metrics
        """)
        
        results = cur.fetchone()
        logger.info(f"Quality metrics now: ROE={results[0]}, ROA={results[1]}, OM={results[2]}, PM={results[3]}")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    calculate_quality_metrics()
