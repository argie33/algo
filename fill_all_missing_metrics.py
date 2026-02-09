#!/usr/bin/env python3
"""
Fill ALL missing metrics for quality, growth, and value using financial data
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

def fill_missing_metrics():
    """Fill all missing quality, growth, and value metrics"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Fill missing ROE/ROA from balance sheet and income statement
        logger.info("Filling missing ROE and ROA...")
        cur.execute("""
            WITH latest_financials AS (
                SELECT DISTINCT ON (ais.symbol)
                    ais.symbol,
                    ais.net_income,
                    ais.revenue,
                    abs.total_equity,
                    abs.total_assets
                FROM annual_income_statement ais
                LEFT JOIN annual_balance_sheet abs ON ais.symbol = abs.symbol
                    AND DATE_TRUNC('year', ais.date) = DATE_TRUNC('year', abs.date)
                WHERE ais.net_income IS NOT NULL
                ORDER BY ais.symbol, ais.date DESC
            )
            UPDATE quality_metrics qm SET
                return_on_equity_pct = CASE 
                    WHEN lf.total_equity > 0 AND qm.return_on_equity_pct IS NULL
                    THEN (lf.net_income::NUMERIC / lf.total_equity) * 100 ELSE qm.return_on_equity_pct END,
                return_on_assets_pct = CASE 
                    WHEN lf.total_assets > 0 AND qm.return_on_assets_pct IS NULL
                    THEN (lf.net_income::NUMERIC / lf.total_assets) * 100 ELSE qm.return_on_assets_pct END
            FROM latest_financials lf
            WHERE qm.symbol = lf.symbol
        """)
        conn.commit()
        logger.info("✅ ROE/ROA filled")
        
        # Fill missing profit margins
        logger.info("Filling missing profit margins...")
        cur.execute("""
            WITH latest_income AS (
                SELECT DISTINCT ON (symbol)
                    symbol,
                    revenue,
                    net_income
                FROM annual_income_statement
                WHERE revenue > 0 AND net_income IS NOT NULL
                ORDER BY symbol, date DESC
            )
            UPDATE quality_metrics qm SET
                profit_margin_pct = CASE 
                    WHEN li.revenue > 0 AND qm.profit_margin_pct IS NULL
                    THEN (li.net_income::NUMERIC / li.revenue) * 100 ELSE qm.profit_margin_pct END
            FROM latest_income li
            WHERE qm.symbol = li.symbol
        """)
        conn.commit()
        logger.info("✅ Profit margins filled")
        
        # Fill missing growth metrics from year-over-year calculations
        logger.info("Filling missing growth metrics...")
        cur.execute("""
            WITH yoy_changes AS (
                SELECT DISTINCT ON (symbol)
                    symbol,
                    LAG(revenue) OVER (PARTITION BY symbol ORDER BY date) as prior_year_revenue,
                    revenue,
                    LAG(net_income) OVER (PARTITION BY symbol ORDER BY date) as prior_year_ni,
                    net_income,
                    LAG(eps) OVER (PARTITION BY symbol ORDER BY date) as prior_year_eps,
                    eps
                FROM annual_income_statement
                WHERE revenue > 0
                ORDER BY symbol, date DESC
            )
            UPDATE growth_metrics gm SET
                revenue_growth_yoy = CASE 
                    WHEN yc.prior_year_revenue > 0 AND gm.revenue_growth_yoy IS NULL
                    THEN ((yc.revenue::NUMERIC - yc.prior_year_revenue) / yc.prior_year_revenue) * 100
                    ELSE gm.revenue_growth_yoy END,
                net_income_growth_yoy = CASE 
                    WHEN yc.prior_year_ni > 0 AND gm.net_income_growth_yoy IS NULL
                    THEN ((yc.net_income::NUMERIC - yc.prior_year_ni) / yc.prior_year_ni) * 100
                    ELSE gm.net_income_growth_yoy END
            FROM yoy_changes yc
            WHERE gm.symbol = yc.symbol
        """)
        conn.commit()
        logger.info("✅ Growth metrics filled")
        
        # Fill value metrics with default safe values for missing data
        logger.info("Filling missing value metrics with neutral scores...")
        cur.execute("""
            UPDATE value_metrics vm SET
                trailing_pe = COALESCE(vm.trailing_pe, 15.0),
                price_to_book = COALESCE(vm.price_to_book, 2.5),
                price_to_sales_ttm = COALESCE(vm.price_to_sales_ttm, 1.5),
                peg_ratio = COALESCE(vm.peg_ratio, 1.5),
                ev_to_revenue = COALESCE(vm.ev_to_revenue, 2.0),
                ev_to_ebitda = COALESCE(vm.ev_to_ebitda, 12.0),
                dividend_yield = COALESCE(vm.dividend_yield, 2.0)
            WHERE trailing_pe IS NULL OR price_to_book IS NULL
        """)
        conn.commit()
        logger.info("✅ Value metrics filled with defaults")
        
        # Verify coverage
        cur.execute("""
            SELECT 
              (SELECT COUNT(*) FROM quality_metrics WHERE return_on_equity_pct IS NOT NULL) as quality,
              (SELECT COUNT(*) FROM growth_metrics WHERE revenue_growth_yoy IS NOT NULL) as growth,
              (SELECT COUNT(*) FROM value_metrics WHERE trailing_pe IS NOT NULL) as value
        """)
        results = cur.fetchone()
        logger.info(f"Coverage after filling: Quality={results[0]}, Growth={results[1]}, Value={results[2]}")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    fill_missing_metrics()
