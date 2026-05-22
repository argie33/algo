#!/usr/bin/env python3
"""Sector Performance Loader - compute daily returns and relative strength by sector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, timedelta
from typing import Dict, List
import psycopg2

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger

logger = get_logger(__name__)

class SectorPerformanceLoader:
    """Compute sector performance from daily price data."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def run(self, run_date: date = None) -> Dict:
        """Compute sector performance for a given date."""
        if run_date is None:
            run_date = date.today()

        self.connect()
        try:
            # Get max date in price_daily
            cur = self.conn.cursor()
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_price_date = cur.fetchone()[0]
            if not max_price_date:
                logger.warning("No price data available")
                return {"success": False, "rows": 0}

            # Use max_price_date as data_date
            data_date = max_price_date

            # Get SP500 stocks with sector info
            cur.execute("""
                SELECT f.symbol, f.sector, p.close
                FROM stock_fundamentals f
                JOIN stock_symbols s ON f.symbol = s.symbol
                JOIN price_daily p ON f.symbol = p.symbol
                WHERE s.is_sp500 = true AND f.sector IS NOT NULL
                  AND p.date = %s
                ORDER BY f.sector, f.symbol
            """, (data_date,))

            rows = cur.fetchall()
            if not rows:
                logger.warning(f"No price data for {data_date}")
                return {"success": False, "rows": 0}

            # Group by sector, compute returns
            sector_data = {}
            for symbol, sector, close in rows:
                if not sector:
                    continue

                # Get previous close
                cur.execute("""
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND date < %s
                    ORDER BY date DESC LIMIT 1
                """, (symbol, data_date))
                prev = cur.fetchone()
                prev_close = prev[0] if prev else close

                if prev_close <= 0:
                    pct_return = 0
                else:
                    pct_return = (close - prev_close) / prev_close * 100

                if sector not in sector_data:
                    sector_data[sector] = {"returns": [], "symbols": 0}
                sector_data[sector]["returns"].append(pct_return)
                sector_data[sector]["symbols"] += 1

            # Compute sector-level metrics
            sector_summary = {}
            for sector, data in sector_data.items():
                avg_return = sum(data["returns"]) / len(data["returns"])
                # Relative strength = how much better than market average
                market_avg = sum(sum(v["returns"]) for v in sector_data.values()) / sum(len(v["returns"]) for v in sector_data.values())
                rel_strength = avg_return - market_avg
                sector_summary[sector] = {
                    "return_pct": round(avg_return, 4),
                    "relative_strength": round(rel_strength, 4),
                    "symbol_count": data["symbols"]
                }

            # Delete existing data for this date (idempotent)
            cur.execute("DELETE FROM sector_performance WHERE date = %s", (data_date,))

            # Insert sector performance
            inserted = 0
            for sector, metrics in sector_summary.items():
                cur.execute("""
                    INSERT INTO sector_performance (sector, date, return_pct, relative_strength)
                    VALUES (%s, %s, %s, %s)
                """, (sector, data_date, metrics["return_pct"], metrics["relative_strength"]))
                inserted += 1

            self.conn.commit()
            logger.info(f"Inserted {inserted} sectors for {data_date}")
            return {"success": True, "rows": inserted, "date": str(data_date)}

        except Exception as e:
            logger.error(f"Sector performance load failed: {e}")
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

    parser = argparse.ArgumentParser(description='Load sector performance data')
    parser.add_argument('--date', type=str, help='Date to load (YYYY-MM-DD)')
    args = parser.parse_args()

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    loader = SectorPerformanceLoader()
    result = loader.run(run_date)

    if result["success"]:
        logger.info(f"SUCCESS: {result['rows']} sectors loaded for {result.get('date')}")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
