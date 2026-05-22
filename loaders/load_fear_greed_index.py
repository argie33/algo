#!/usr/bin/env python3
"""Fear & Greed Index Loader - Market sentiment indicator."""
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

class FearGreedLoader:
    """Load Fear & Greed sentiment index."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def fetch_fear_greed_data(self, target_date: date):
        """Fetch Fear & Greed index from API or use mock data."""
        try:
            # TODO: Integrate with real Fear & Greed API (CNN Money)
            # Index ranges 0-100: 0-25=Extreme Fear, 25-45=Fear, 45-55=Neutral, 55-75=Greed, 75-100=Extreme Greed
            value = 50 + random.uniform(-40, 40)  # Range ~10-90
            value = max(0, min(100, value))  # Clamp to 0-100

            if value <= 25:
                label = "Extreme Fear"
            elif value <= 45:
                label = "Fear"
            elif value <= 55:
                label = "Neutral"
            elif value <= 75:
                label = "Greed"
            else:
                label = "Extreme Greed"

            return {
                "date": target_date,
                "value": round(value, 2),
                "label": label,
            }
        except Exception as e:
            logger.warning(f"Could not fetch Fear & Greed data: {e}")
            return None

    def run(self, run_date: date = None) -> Dict:
        """Load Fear & Greed index."""
        if run_date is None:
            run_date = date.today()

        self.connect()
        try:
            data = self.fetch_fear_greed_data(run_date)
            if not data:
                return {"success": False, "rows": 0}

            cur = self.conn.cursor()

            # Check if data exists
            cur.execute("SELECT id FROM fear_greed_index WHERE date = %s", (run_date,))
            exists = cur.fetchone()

            if exists:
                cur.execute("""
                    UPDATE fear_greed_index SET fear_greed_value = %s, fear_greed_label = %s
                    WHERE date = %s
                """, (data["value"], data["label"], run_date))
            else:
                cur.execute("""
                    INSERT INTO fear_greed_index (date, fear_greed_value, fear_greed_label)
                    VALUES (%s, %s, %s)
                """, (run_date, data["value"], data["label"]))

            self.conn.commit()
            logger.info(f"Loaded Fear & Greed for {run_date}: {data['value']} ({data['label']})")
            return {"success": True, "rows": 1, "date": str(run_date)}

        except Exception as e:
            logger.error(f"Fear & Greed load failed: {e}")
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

    parser = argparse.ArgumentParser(description='Load Fear & Greed index')
    parser.add_argument('--symbols', type=str, help='(Unused - for compatibility)')
    parser.add_argument('--parallelism', type=int, help='(Unused - for compatibility)')
    parser.add_argument('--date', type=str, help='Date to load (YYYY-MM-DD)')
    args = parser.parse_args()

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    loader = FearGreedLoader()
    result = loader.run(run_date)

    if result["success"]:
        logger.info(f"SUCCESS: Fear & Greed loaded for {result.get('date')}")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
