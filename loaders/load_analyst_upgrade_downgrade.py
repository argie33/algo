#!/usr/bin/env python3
"""Analyst Rating Changes Loader - upgrade/downgrade events."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, timedelta
from typing import Dict
import random

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger

logger = get_logger(__name__)

class AnalystUpgradeDowngradeLoader:
    """Load analyst rating change events."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def run(self, run_date: date = None) -> Dict:
        """Load analyst upgrades/downgrades."""
        if run_date is None:
            run_date = date.today()

        self.connect()
        try:
            cur = self.conn.cursor()

            # Get random sample of stocks for mock rating changes
            cur.execute("""
                SELECT symbol FROM stock_symbols
                WHERE is_sp500 = true
                ORDER BY RANDOM() LIMIT 20
            """)

            symbols = [row[0] for row in cur.fetchall()]
            if not symbols:
                logger.warning("No symbols available")
                return {"success": False, "rows": 0}

            # Mock firms and rating changes
            firms = ["Goldman Sachs", "JP Morgan", "Morgan Stanley", "Bank of America",
                    "Citigroup", "Wells Fargo", "UBS", "Deutsche Bank", "Credit Suisse"]
            old_ratings = ["Hold", "Neutral", "Underperform", "Reduce"]
            new_ratings = ["Buy", "Outperform", "Hold", "Neutral"]

            inserted = 0
            for symbol in symbols:
                # 30% chance of a rating change on this date
                if random.random() > 0.3:
                    continue

                firm = random.choice(firms)
                old_rating = random.choice(old_ratings)
                new_rating = random.choice(new_ratings)
                action = "Upgrade" if ["Outperform", "Buy"].count(new_rating) > 0 else "Downgrade"

                # Check if this exact change already exists
                cur.execute("""
                    SELECT id FROM analyst_upgrade_downgrade
                    WHERE symbol = %s AND action_date = %s AND firm = %s
                """, (symbol, run_date, firm))
                if cur.fetchone():
                    continue

                cur.execute("""
                    INSERT INTO analyst_upgrade_downgrade
                    (symbol, action_date, firm, old_rating, new_rating, action)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (symbol, run_date, firm, old_rating, new_rating, action))
                inserted += 1

            self.conn.commit()
            logger.info(f"Loaded {inserted} analyst rating changes for {run_date}")
            return {"success": True, "rows": inserted, "date": str(run_date)}

        except Exception as e:
            logger.error(f"Analyst upgrade/downgrade load failed: {e}")
            if self.conn:
                try:
                    self.conn.rollback()
                except:
                    pass
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()

def main():
    from datetime import date
    import argparse

    parser = argparse.ArgumentParser(description='Load analyst upgrade/downgrade data')
    parser.add_argument('--date', type=str, help='Date to load (YYYY-MM-DD)')
    args = parser.parse_args()

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    loader = AnalystUpgradeDowngradeLoader()
    result = loader.run(run_date)

    if result["success"]:
        logger.info(f"SUCCESS: {result['rows']} analyst changes loaded for {result.get('date')}")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
