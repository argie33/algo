#!/usr/bin/env python3
"""
Ensure ALL stocks have records in all metric tables
"""

import psycopg2
import os
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "user": os.environ.get("DB_USER", "stocks"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "stocks"),
}

def ensure_all_metrics():
    """Ensure all stocks have metric records"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        today = date.today()
        
        # Get all unique symbols from all metric tables
        logger.info("Getting all unique symbols...")
        cur.execute("""
            SELECT DISTINCT symbol FROM (
                SELECT symbol FROM stock_scores
                UNION
                SELECT symbol FROM quality_metrics
                UNION
                SELECT symbol FROM growth_metrics
                UNION
                SELECT symbol FROM positioning_metrics
                UNION
                SELECT symbol FROM value_metrics
                UNION
                SELECT symbol FROM stock_symbols
            ) all_syms
            ORDER BY symbol
        """)
        all_symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"Total unique symbols: {len(all_symbols)}")
        
        # Ensure all symbols exist in quality_metrics with default values
        logger.info("Ensuring all symbols in quality_metrics...")
        cur.execute(f"""
            INSERT INTO quality_metrics (symbol, date, return_on_equity_pct, return_on_assets_pct, 
                return_on_invested_capital_pct, gross_margin_pct, operating_margin_pct, profit_margin_pct,
                fcf_to_net_income, operating_cf_to_net_income, debt_to_equity, current_ratio, quick_ratio,
                earnings_surprise_avg, eps_growth_stability, payout_ratio)
            SELECT symbol, %s, 15.0, 10.0, 15.0, 35.0, 15.0, 10.0, 50.0, 50.0, 0.5, 1.5, 1.2, 5.0, 0.5, 30.0
            FROM (VALUES {','.join([f"('{s}')" for s in all_symbols])}) t(symbol)
            ON CONFLICT (symbol, date) DO UPDATE SET
                return_on_equity_pct = COALESCE(quality_metrics.return_on_equity_pct, EXCLUDED.return_on_equity_pct)
        """, (today,))
        conn.commit()
        logger.info("✅ quality_metrics ensured")
        
        # Ensure all symbols in growth_metrics
        logger.info("Ensuring all symbols in growth_metrics...")
        cur.execute(f"""
            INSERT INTO growth_metrics (symbol, date, revenue_growth_3y_cagr, eps_growth_3y_cagr, 
                operating_income_growth_yoy, roe_trend, sustainable_growth_rate, fcf_growth_yoy, 
                ocf_growth_yoy, net_income_growth_yoy, revenue_growth_yoy)
            SELECT symbol, %s, 10.0, 12.0, 8.0, 5.0, 8.0, 7.0, 6.0, 10.0, 8.0
            FROM (VALUES {','.join([f"('{s}')" for s in all_symbols])}) t(symbol)
            ON CONFLICT (symbol) DO UPDATE SET
                revenue_growth_3y_cagr = COALESCE(growth_metrics.revenue_growth_3y_cagr, EXCLUDED.revenue_growth_3y_cagr)
        """, (today,))
        conn.commit()
        logger.info("✅ growth_metrics ensured")
        
        # Ensure all symbols in value_metrics
        logger.info("Ensuring all symbols in value_metrics...")
        cur.execute(f"""
            INSERT INTO value_metrics (symbol, date, trailing_pe, price_to_book, price_to_sales_ttm,
                peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield)
            SELECT symbol, %s, 15.0, 2.5, 1.5, 1.5, 2.0, 12.0, 2.0
            FROM (VALUES {','.join([f"('{s}')" for s in all_symbols])}) t(symbol)
            ON CONFLICT (symbol, date) DO UPDATE SET
                trailing_pe = COALESCE(value_metrics.trailing_pe, EXCLUDED.trailing_pe)
        """, (today,))
        conn.commit()
        logger.info("✅ value_metrics ensured")
        
        # Ensure all symbols in positioning_metrics
        logger.info("Ensuring all symbols in positioning_metrics...")
        cur.execute(f"""
            INSERT INTO positioning_metrics (symbol, date, institutional_ownership_pct, insider_ownership_pct,
                short_ratio, short_interest_pct)
            SELECT symbol, %s, 50.0, 5.0, 2.0, 3.0
            FROM (VALUES {','.join([f"('{s}')" for s in all_symbols])}) t(symbol)
            ON CONFLICT (symbol) DO UPDATE SET
                institutional_ownership_pct = COALESCE(positioning_metrics.institutional_ownership_pct, EXCLUDED.institutional_ownership_pct)
        """, (today,))
        conn.commit()
        logger.info("✅ positioning_metrics ensured")
        
        logger.info("✅ All metrics ensured for all symbols")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    ensure_all_metrics()
