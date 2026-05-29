#!/usr/bin/env python3
"""Company Profile Loader - populate from yfinance with sector/industry enrichment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Dict
import yfinance as yf

from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger

logger = get_logger(__name__)

class CompanyProfileLoader:
    """Load company profiles with sector and industry from yfinance."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def fetch_company_info(self, symbol: str) -> Dict:
        """Fetch company info from yfinance."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'long_name': info.get('longName'),
                'website': info.get('website'),
                'employees': info.get('fullTimeEmployees'),
            }
        except Exception as e:
            logger.debug(f"Could not fetch yfinance data for {symbol}: {e}")
            return {}

    def run(self) -> Dict:
        """Populate company_profile from stock_symbols and yfinance."""
        self.connect()
        try:
            cur = self.conn.cursor()

            # Get all stocks (limit for speed)
            cur.execute("""
                SELECT symbol, security_name, exchange
                FROM stock_symbols
                WHERE symbol IS NOT NULL
                ORDER BY symbol
                LIMIT 500
            """)

            rows = cur.fetchall()
            if not rows:
                logger.warning("No stock symbols found")
                return {"success": False, "rows": 0}

            # Upsert company profiles with sector/industry enrichment
            inserted = 0
            for (symbol, name, exchange) in rows:
                company_info = self.fetch_company_info(symbol)
                cur.execute("""
                    INSERT INTO company_profile
                    (ticker, symbol, short_name, long_name, display_name, sector, industry, exchange, website, employees, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (ticker) DO UPDATE SET
                    sector = COALESCE(EXCLUDED.sector, company_profile.sector),
                    industry = COALESCE(EXCLUDED.industry, company_profile.industry),
                    long_name = COALESCE(EXCLUDED.long_name, company_profile.long_name),
                    website = COALESCE(EXCLUDED.website, company_profile.website),
                    employees = COALESCE(EXCLUDED.employees, company_profile.employees),
                    exchange = EXCLUDED.exchange,
                    updated_at = CURRENT_TIMESTAMP
                """, (
                    symbol, symbol, name,
                    company_info.get('long_name', name),
                    name,
                    company_info.get('sector'),
                    company_info.get('industry'),
                    exchange,
                    company_info.get('website'),
                    company_info.get('employees')
                ))
                inserted += 1

            self.conn.commit()
            logger.info(f"Loaded {inserted} company profiles with sector/industry")
            return {"success": True, "rows": inserted}

        except Exception as e:
            logger.error(f"Company profile load failed: {e}")
            if self.conn:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()

def main():
    import argparse
    from utils.loader_history_tracker import LoaderHistoryTracker

    parser = argparse.ArgumentParser(description='Company Profile Loader')
    parser.add_argument('--symbols', type=str, help='(Unused - for compatibility)')
    parser.add_argument('--parallelism', type=int, help='(Unused - for compatibility)')
    args = parser.parse_args()

    tracker = LoaderHistoryTracker('company_profile')
    tracker.start()

    loader = CompanyProfileLoader()
    result = loader.run()

    if result["success"]:
        logger.info(f"SUCCESS: {result['rows']} company profiles loaded")
        tracker.complete(symbols_processed=result['rows'], errors=0)
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        tracker.failed(error_message=result.get('error', 'unknown error'))
        return 1

if __name__ == '__main__':
    sys.exit(main())
