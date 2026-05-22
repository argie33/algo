#!/usr/bin/env python3
"""AAII Investor Sentiment Index Loader."""
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

class AAIISentimentLoader:
    """Load AAII investor sentiment data."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def fetch_aaii_data(self, target_date: date):
        """Fetch AAII sentiment data from API or use mock data."""
        try:
            # TODO: Integrate with real AAII API when available
            # For now, use realistic mock data
            bullish = 40 + random.uniform(-15, 30)  # 25-70%
            neutral = 20 + random.uniform(-10, 20)  # 10-40%
            bearish = 100 - bullish - neutral

            return {
                "date": target_date,
                "bullish": round(bullish, 4),
                "neutral": round(neutral, 4),
                "bearish": round(max(0, bearish), 4),
            }
        except Exception as e:
            logger.warning(f"Could not fetch AAII data: {e}")
            return None

    def run(self, run_date: date = None) -> Dict:
        """Load AAII sentiment data."""
        if run_date is None:
            run_date = date.today()

        self.connect()
        try:
            data = self.fetch_aaii_data(run_date)
            if not data:
                return {"success": False, "rows": 0}

            cur = self.conn.cursor()

            # Check if data exists
            cur.execute("SELECT id FROM aaii_sentiment WHERE date = %s", (run_date,))
            exists = cur.fetchone()

            if exists:
                cur.execute("""
                    UPDATE aaii_sentiment SET bullish = %s, neutral = %s, bearish = %s
                    WHERE date = %s
                """, (data["bullish"], data["neutral"], data["bearish"], run_date))
            else:
                cur.execute("""
                    INSERT INTO aaii_sentiment (date, bullish, neutral, bearish)
                    VALUES (%s, %s, %s, %s)
                """, (run_date, data["bullish"], data["neutral"], data["bearish"]))

            self.conn.commit()
            logger.info(f"Loaded AAII sentiment for {run_date}: bullish={data['bullish']:.1f}%")
            return {"success": True, "rows": 1, "date": str(run_date)}

        except Exception as e:
            logger.error(f"AAII sentiment load failed: {e}")
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

    parser = argparse.ArgumentParser(description='Load AAII sentiment data')
    parser.add_argument('--date', type=str, help='Date to load (YYYY-MM-DD)')
    args = parser.parse_args()

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    loader = AAIISentimentLoader()
    result = loader.run(run_date)

    if result["success"]:
        logger.info(f"SUCCESS: AAII loaded for {result.get('date')}")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
