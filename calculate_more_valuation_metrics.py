#!/usr/bin/env python3
"""
Calculate additional valuation metrics (P/B, P/S, EV/Revenue, Dividend Yield)
from balance sheet, income statement, and price data
"""

import psycopg2
import os
import logging
import math

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "user": os.environ.get("DB_USER", "stocks"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "stocks"),
}

def calculate_valuation_metrics():
    """Calculate valuation metrics from available financial data"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Calculate P/B (Price-to-Book) = Market Cap / Book Value (Total Assets - Total Liabilities)
        logger.info("Calculating P/B ratios...")
        cur.execute("""
            WITH latest_price AS (
                SELECT DISTINCT ON (symbol) symbol, close as price, date
                FROM price_daily
                ORDER BY symbol, date DESC
            ),
            latest_balance_sheet AS (
                SELECT DISTINCT ON (symbol) symbol, total_assets, total_liabilities, shares_outstanding, date
                FROM annual_balance_sheet
                ORDER BY symbol, date DESC
            ),
            with_pb AS (
                SELECT
                    lp.symbol,
                    CASE
                        WHEN abs.total_assets > 0 AND abs.total_liabilities >= 0 AND abs.shares_outstanding > 0
                        THEN (lp.price * abs.shares_outstanding) / (abs.total_assets - abs.total_liabilities)
                        ELSE NULL
                    END as pb_ratio
                FROM latest_price lp
                JOIN latest_balance_sheet abs ON lp.symbol = abs.symbol
            )
            UPDATE value_metrics vm SET price_to_book = pb.pb_ratio
            FROM (SELECT symbol, pb_ratio FROM with_pb) pb
            WHERE vm.symbol = pb.symbol AND pb.pb_ratio IS NOT NULL AND pb.pb_ratio > 0
        """)
        conn.commit()
        logger.info("✅ P/B ratios calculated")
        
        # Calculate P/S (Price-to-Sales) = Market Cap / Annual Revenue
        logger.info("Calculating P/S ratios...")
        cur.execute("""
            WITH latest_price AS (
                SELECT DISTINCT ON (symbol) symbol, close as price, date
                FROM price_daily
                ORDER BY symbol, date DESC
            ),
            latest_income AS (
                SELECT DISTINCT ON (symbol) symbol, revenue, shares_outstanding, date
                FROM annual_income_statement
                WHERE revenue > 0
                ORDER BY symbol, date DESC
            ),
            with_ps AS (
                SELECT
                    lp.symbol,
                    CASE
                        WHEN li.revenue > 0 AND li.shares_outstanding > 0
                        THEN (lp.price * li.shares_outstanding) / li.revenue
                        ELSE NULL
                    END as ps_ratio
                FROM latest_price lp
                JOIN latest_income li ON lp.symbol = li.symbol
            )
            UPDATE value_metrics vm SET price_to_sales_ttm = ps.ps_ratio
            FROM (SELECT symbol, ps_ratio FROM with_ps) ps
            WHERE vm.symbol = ps.symbol AND ps.ps_ratio IS NOT NULL AND ps.ps_ratio > 0
        """)
        conn.commit()
        logger.info("✅ P/S ratios calculated")
        
        # Calculate EV/Revenue = Enterprise Value / Revenue
        logger.info("Calculating EV/Revenue ratios...")
        cur.execute("""
            WITH latest_price AS (
                SELECT DISTINCT ON (symbol) symbol, close as price, date
                FROM price_daily
                ORDER BY symbol, date DESC
            ),
            latest_financials AS (
                SELECT DISTINCT ON (symbol) 
                    symbol, revenue, shares_outstanding, total_debt, cash_and_equivalents, date
                FROM annual_income_statement ais
                JOIN annual_balance_sheet abs ON ais.symbol = abs.symbol 
                    AND DATE_TRUNC('year', ais.date) = DATE_TRUNC('year', abs.date)
                WHERE revenue > 0
                ORDER BY symbol, date DESC
            ),
            with_ev_rev AS (
                SELECT
                    lp.symbol,
                    CASE
                        WHEN lf.revenue > 0
                        THEN ((lp.price * lf.shares_outstanding + COALESCE(lf.total_debt, 0) - COALESCE(lf.cash_and_equivalents, 0)) / lf.revenue)
                        ELSE NULL
                    END as ev_rev_ratio
                FROM latest_price lp
                JOIN latest_financials lf ON lp.symbol = lf.symbol
            )
            UPDATE value_metrics vm SET ev_to_revenue = ev_rev.ev_rev_ratio
            FROM (SELECT symbol, ev_rev_ratio FROM with_ev_rev) ev_rev
            WHERE vm.symbol = ev_rev.symbol AND ev_rev.ev_rev_ratio IS NOT NULL AND ev_rev.ev_rev_ratio > 0
        """)
        conn.commit()
        logger.info("✅ EV/Revenue ratios calculated")
        
        # Verify results
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE price_to_book IS NOT NULL) as pb_count,
                COUNT(*) FILTER (WHERE price_to_sales_ttm IS NOT NULL) as ps_count,
                COUNT(*) FILTER (WHERE ev_to_revenue IS NOT NULL) as ev_rev_count,
                COUNT(*) FILTER (WHERE trailing_pe IS NOT NULL) as pe_count
            FROM value_metrics
        """)
        results = cur.fetchone()
        logger.info(f"Value metrics coverage: P/B={results[0]}, P/S={results[1]}, EV/Rev={results[2]}, P/E={results[3]}")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    calculate_valuation_metrics()
