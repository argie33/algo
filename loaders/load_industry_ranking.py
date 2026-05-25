#!/usr/bin/env python3
"""Industry Ranking Loader - compute daily industry momentum rankings."""
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

class IndustryRankingLoader:
    """Compute industry rankings from daily price data."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def run(self, run_date: date = None) -> Dict:
        """Compute industry rankings for a given date."""
        if run_date is None:
            run_date = date.today()

        self.connect()
        try:
            cur = self.conn.cursor()

            # Get max date in price_daily
            cur.execute("SELECT MAX(date) FROM price_daily")
            result = cur.fetchone()
            max_price_date = result[0] if result else None
            if not max_price_date:
                logger.warning("No price data available")
                return {"success": False, "rows": 0}

            data_date = max_price_date

            # Get stocks with industry info
            cur.execute("""
                SELECT f.symbol, f.industry, p.close
                FROM stock_fundamentals f
                JOIN stock_symbols s ON f.symbol = s.symbol
                JOIN price_daily p ON f.symbol = p.symbol
                WHERE f.industry IS NOT NULL
                  AND p.date = %s
                ORDER BY f.industry, f.symbol
            """, (data_date,))

            rows = cur.fetchall()
            if not rows:
                logger.warning(f"No industry data for {data_date}")
                return {"success": False, "rows": 0}

            # Compute momentum for each industry
            industry_momentum = {}
            for symbol, industry, close in rows:
                if not industry:
                    continue

                # Get 20-day return (momentum)
                cur.execute("""
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT 21
                """, (symbol, data_date))

                prices = [p[0] for p in cur.fetchall()]
                if len(prices) >= 2:
                    momentum = (prices[0] - prices[-1]) / prices[-1] * 100
                else:
                    momentum = 0

                if industry not in industry_momentum:
                    industry_momentum[industry] = {"momentum_scores": []}
                industry_momentum[industry]["momentum_scores"].append(momentum)

            # Rank industries by avg momentum
            ranked = []
            for industry, data in industry_momentum.items():
                avg_momentum = sum(data["momentum_scores"]) / len(data["momentum_scores"])
                ranked.append((industry, avg_momentum, len(data["momentum_scores"])))

            ranked.sort(key=lambda x: x[1], reverse=True)

            # Delete existing rankings for this date
            cur.execute("DELETE FROM industry_ranking WHERE date_recorded = %s", (data_date,))

            # Insert rankings
            inserted = 0
            for rank, (industry, momentum, count) in enumerate(ranked, 1):
                cur.execute("""
                    INSERT INTO industry_ranking (industry, date_recorded, current_rank, momentum_score)
                    VALUES (%s, %s, %s, %s)
                """, (industry, data_date, rank, round(momentum, 4)))
                inserted += 1

            self.conn.commit()
            logger.info(f"Inserted {inserted} industry rankings for {data_date}")
            return {"success": True, "rows": inserted, "date": str(data_date)}

        except Exception as e:
            logger.error(f"Industry ranking load failed: {e}")
            if self.conn:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()

def main():
    from datetime import date
    import argparse

    parser = argparse.ArgumentParser(description='Load industry ranking data')
    parser.add_argument('--symbols', type=str, help='(Unused - for compatibility)')
    parser.add_argument('--parallelism', type=int, help='(Unused - for compatibility)')
    parser.add_argument('--date', type=str, help='Date to load (YYYY-MM-DD)')
    args = parser.parse_args()

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    loader = IndustryRankingLoader()
    result = loader.run(run_date)

    if result["success"]:
        logger.info(f"SUCCESS: {result['rows']} industries ranked for {result.get('date')}")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
