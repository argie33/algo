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

            # Get all stocks (limit for speed)
            cur.execute("""
                SELECT symbol, security_name, exchange, market_category
                FROM stock_symbols
                WHERE symbol IS NOT NULL
                ORDER BY symbol
                LIMIT 500
            """)

            rows = cur.fetchall()
            if not rows:
                logger.warning("No stock fundamentals data available")
                return {"success": False, "rows": 0}

            # Upsert company profiles
            inserted = 0
            for (symbol, name, exchange, market_cat) in rows:
                cur.execute("""
                    INSERT INTO company_profile
                    (ticker, symbol, short_name, display_name, exchange, created_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (ticker) DO UPDATE SET
                    exchange = EXCLUDED.exchange,
                    updated_at = CURRENT_TIMESTAMP
                """, (symbol, symbol, name, name, exchange))
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
