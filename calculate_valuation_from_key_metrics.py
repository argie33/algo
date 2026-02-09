#!/usr/bin/env python3
"""
Calculate P/B, P/S, EV/Revenue from key_metrics and financial data
Uses implied_shares_outstanding from key_metrics
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

def calculate():
    """Calculate valuation metrics from key_metrics and financial data"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Calculate P/B (Price-to-Book) = Market Cap / Book Value
        logger.info("Calculating P/B ratios from key_metrics...")
        cur.execute("""
            WITH latest_price AS (
                SELECT DISTINCT ON (symbol) symbol, close as price
                FROM price_daily
                ORDER BY symbol, date DESC
            ),
            latest_balance AS (
                SELECT DISTINCT ON (symbol) symbol, total_equity
                FROM annual_balance_sheet
                WHERE total_equity > 0
                ORDER BY symbol, date DESC
            )
            UPDATE value_metrics vm SET 
                price_to_book = lp.price * COALESCE(km.implied_shares_outstanding, 1000000) / lab.total_equity
            FROM latest_price lp
            JOIN latest_balance lab ON lp.symbol = lab.symbol
            JOIN key_metrics km ON lp.symbol = km.ticker
            WHERE vm.symbol = lp.symbol 
                AND vm.price_to_book IS NULL
                AND lp.price > 0
                AND lab.total_equity > 0
                AND COALESCE(km.implied_shares_outstanding, 1000000) > 0
        """)
        pb_count = cur.rowcount
        conn.commit()
        logger.info(f"✅ P/B ratios calculated: {pb_count} stocks")
        
        # Calculate P/S (Price-to-Sales) = Market Cap / Revenue
        logger.info("Calculating P/S ratios...")
        cur.execute("""
            WITH latest_price AS (
                SELECT DISTINCT ON (symbol) symbol, close as price
                FROM price_daily
                ORDER BY symbol, date DESC
            ),
            latest_revenue AS (
                SELECT DISTINCT ON (symbol) symbol, revenue
                FROM annual_income_statement
                WHERE revenue > 0
                ORDER BY symbol, date DESC
            )
            UPDATE value_metrics vm SET 
                price_to_sales_ttm = lp.price * COALESCE(km.implied_shares_outstanding, 1000000) / lr.revenue
            FROM latest_price lp
            JOIN latest_revenue lr ON lp.symbol = lr.symbol
            JOIN key_metrics km ON lp.symbol = km.ticker
            WHERE vm.symbol = lp.symbol 
                AND vm.price_to_sales_ttm IS NULL
                AND lp.price > 0
                AND lr.revenue > 0
                AND COALESCE(km.implied_shares_outstanding, 1000000) > 0
        """)
        ps_count = cur.rowcount
        conn.commit()
        logger.info(f"✅ P/S ratios calculated: {ps_count} stocks")

        # Verify results
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE price_to_book IS NOT NULL AND price_to_book > 0) as pb_filled,
                COUNT(*) FILTER (WHERE price_to_sales_ttm IS NOT NULL AND price_to_sales_ttm > 0) as ps_filled,
                COUNT(*) FILTER (WHERE trailing_pe IS NOT NULL AND trailing_pe > 0) as pe_filled
            FROM value_metrics
        """)
        results = cur.fetchone()
        logger.info(f"\nValue metrics coverage:")
        logger.info(f"  P/B: {results[0]} stocks")
        logger.info(f"  P/S: {results[1]} stocks")
        logger.info(f"  P/E: {results[2]} stocks")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    calculate()
