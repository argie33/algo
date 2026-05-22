#!/usr/bin/env python3
"""Company Profile Loader - populate from existing stock fundamentals data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Dict

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger

logger = get_logger(__name__)

class CompanyProfileLoader:
    """Load company profiles from stock fundamentals."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def run(self) -> Dict:
        """Populate company_profile from stock_fundamentals."""
        self.connect()
        try:
            cur = self.conn.cursor()

            # Get all stocks with fundamentals data
            cur.execute("""
                SELECT DISTINCT s.symbol, s.security_name, s.sector, s.industry,
                       f.market_cap, f.pe_ratio, f.dividend_yield, f.roe,
                       f.debt_to_equity, f.current_ratio, f.quick_ratio
                FROM stock_symbols s
                LEFT JOIN stock_fundamentals f ON s.symbol = f.symbol
                WHERE s.is_sp500 = true
                ORDER BY s.symbol
            """)

            rows = cur.fetchall()
            if not rows:
                logger.warning("No stock fundamentals data available")
                return {"success": False, "rows": 0}

            # Upsert company profiles
            inserted = 0
            for (symbol, name, sector, industry, market_cap, pe, div_yield,
                 roe, debt_eq, current_ratio, quick_ratio) in rows:

                cur.execute("""
                    INSERT INTO company_profile
                    (symbol, company_name, sector, industry, market_cap, pe_ratio,
                     dividend_yield, roe, debt_to_equity, current_ratio, quick_ratio, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    market_cap = EXCLUDED.market_cap,
                    pe_ratio = EXCLUDED.pe_ratio,
                    dividend_yield = EXCLUDED.dividend_yield,
                    roe = EXCLUDED.roe,
                    debt_to_equity = EXCLUDED.debt_to_equity,
                    current_ratio = EXCLUDED.current_ratio,
                    quick_ratio = EXCLUDED.quick_ratio,
                    updated_at = CURRENT_TIMESTAMP
                """, (symbol, name, sector, industry, market_cap, pe, div_yield,
                      roe, debt_eq, current_ratio, quick_ratio))
                inserted += 1

            self.conn.commit()
            logger.info(f"Loaded {inserted} company profiles")
            return {"success": True, "rows": inserted}

        except Exception as e:
            logger.error(f"Company profile load failed: {e}")
            if self.conn:
                try:
                    self.conn.rollback()
                except:
                    pass
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()

def main():
    loader = CompanyProfileLoader()
    result = loader.run()

    if result["success"]:
        logger.info(f"SUCCESS: {result['rows']} company profiles loaded")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
