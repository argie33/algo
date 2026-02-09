#!/usr/bin/env python3
"""
Fix missing metrics by calculating from available financial data
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

def fix_metrics():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # 1. Calculate ROE from net_income and total_equity
        logger.info("Calculating ROE from financial data...")
        cur.execute("""
            WITH latest AS (
                SELECT DISTINCT ON (ais.symbol)
                    ais.symbol, ais.net_income,
                    abs.total_equity, ais.date
                FROM annual_income_statement ais
                LEFT JOIN annual_balance_sheet abs ON ais.symbol = abs.symbol
                    AND DATE_TRUNC('year', ais.date) = DATE_TRUNC('year', abs.date)
                WHERE ais.net_income IS NOT NULL AND abs.total_equity > 0
                ORDER BY ais.symbol, ais.date DESC
            )
            UPDATE quality_metrics qm SET
                return_on_equity_pct = (l.net_income::NUMERIC / l.total_equity) * 100
            FROM latest l
            WHERE qm.symbol = l.symbol AND qm.return_on_equity_pct IS NULL
        """)
        conn.commit()
        logger.info("✅ ROE calculated")
        
        # 2. Calculate ROA from net_income and total_assets
        logger.info("Calculating ROA from financial data...")
        cur.execute("""
            WITH latest AS (
                SELECT DISTINCT ON (ais.symbol)
                    ais.symbol, ais.net_income,
                    abs.total_assets, ais.date
                FROM annual_income_statement ais
                LEFT JOIN annual_balance_sheet abs ON ais.symbol = abs.symbol
                    AND DATE_TRUNC('year', ais.date) = DATE_TRUNC('year', abs.date)
                WHERE ais.net_income IS NOT NULL AND abs.total_assets > 0
                ORDER BY ais.symbol, ais.date DESC
            )
            UPDATE quality_metrics qm SET
                return_on_assets_pct = (l.net_income::NUMERIC / l.total_assets) * 100
            FROM latest l
            WHERE qm.symbol = l.symbol AND qm.return_on_assets_pct IS NULL
        """)
        conn.commit()
        logger.info("✅ ROA calculated")
        
        # 3. Fill P/E where missing
        logger.info("Filling missing P/E ratios...")
        cur.execute("""
            WITH price_eps AS (
                SELECT DISTINCT ON (km.ticker)
                    km.ticker, km.eps_trailing,
                    (SELECT close FROM price_daily WHERE symbol = km.ticker ORDER BY date DESC LIMIT 1) as price
                FROM key_metrics km
                WHERE km.eps_trailing > 0
                ORDER BY km.ticker, km.eps_trailing DESC
            )
            UPDATE value_metrics vm SET
                trailing_pe = price_eps.price / price_eps.eps_trailing
            FROM price_eps
            WHERE vm.symbol = price_eps.ticker 
                AND vm.trailing_pe IS NULL
                AND price_eps.price > 0
        """)
        conn.commit()
        logger.info("✅ P/E filled")
        
        # Verify
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FILTER (WHERE return_on_equity_pct > 0 OR return_on_equity_pct < 0) FROM quality_metrics) as real_roe,
                (SELECT COUNT(*) FILTER (WHERE return_on_assets_pct > 0 OR return_on_assets_pct < 0) FROM quality_metrics) as real_roa,
                (SELECT COUNT(*) FILTER (WHERE trailing_pe IS NOT NULL AND trailing_pe > 0) FROM value_metrics) as real_pe
        """)
        results = cur.fetchone()
        logger.info(f"Fixed metrics: ROE={results[0]}, ROA={results[1]}, P/E={results[2]}")

    except Exception as e:
        logger.error(f"Error: {str(e)[:300]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    fix_metrics()
