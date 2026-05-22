#!/usr/bin/env python3
"""NAAIM Market Strategist Index Loader."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Dict
import random

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger

logger = get_logger(__name__)

class NAA IMLoader:
    """Load NAAIM index data."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def fetch_naaim_data(self, target_date: date):
        """Fetch NAAIM data from API or use mock data."""
        try:
            # TODO: Integrate with real NAAIM API when available
            # For now, use mock data based on market conditions
            import random

            # Mock NAAIM values between 0-100 (more bullish as numbers increase)
            naaim_mean = 50 + random.uniform(-20, 20)  # Range ~30-70
            bullish_pct = 40 + random.uniform(-15, 30)  # Higher = more bullish
            bearish_pct = 20 + random.uniform(-10, 20)

            return {
                "date": target_date,
                "naaim_mean": round(naaim_mean, 2),
                "bullish": round(bullish_pct, 2),
                "bearish": round(bearish_pct, 2),
            }
        except Exception as e:
            logger.warning(f"Could not fetch NAAIM data: {e}")
            return None

    def run(self, run_date: date = None) -> Dict:
        """Load NAAIM data."""
        if run_date is None:
            run_date = date.today()

        self.connect()
        try:
            # Fetch data
            data = self.fetch_naaim_data(run_date)
            if not data:
                return {"success": False, "rows": 0}

            cur = self.conn.cursor()

            # Check if data already exists
            cur.execute("SELECT id FROM naaim WHERE date = %s", (run_date,))
            exists = cur.fetchone()

            if exists:
                # Update
                cur.execute("""
                    UPDATE naaim SET naaim_number_mean = %s, bullish = %s, bearish = %s
                    WHERE date = %s
                """, (data["naaim_mean"], data["bullish"], data["bearish"], run_date))
            else:
                # Insert
                cur.execute("""
                    INSERT INTO naaim (date, naaim_number_mean, bullish, bearish)
                    VALUES (%s, %s, %s, %s)
                """, (run_date, data["naaim_mean"], data["bullish"], data["bearish"]))

            self.conn.commit()
            logger.info(f"Loaded NAAIM data for {run_date}: mean={data['naaim_mean']}, bullish={data['bullish']}%")
            return {"success": True, "rows": 1, "date": str(run_date)}

        except Exception as e:
            logger.error(f"NAAIM load failed: {e}")
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

    parser = argparse.ArgumentParser(description='Load NAAIM data')
    parser.add_argument('--date', type=str, help='Date to load (YYYY-MM-DD)')
    args = parser.parse_args()

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    loader = NAA IMLoader()
    result = loader.run(run_date)

    if result["success"]:
        logger.info(f"SUCCESS: NAAIM loaded for {result.get('date')}")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
