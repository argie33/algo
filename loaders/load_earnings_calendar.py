#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Earnings Calendar Loader - Fetches upcoming earnings dates.

Run:
    python3 load_earnings_calendar.py [--symbols AAPL,MSFT] [--days-ahead 180]
"""
import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional, Dict, Any

from utils.structured_logger import get_logger
from utils.db_connection import get_db_connection
from config.env_loader import load_env

logger = get_logger(__name__)


class EarningsCalendarLoader:
    """Load upcoming earnings dates for all symbols."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = get_db_connection()
            self.cur = self.conn.cursor()
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def get_symbols(self) -> List[str]:
        """Get all active symbols from database."""
        try:
            self.cur.execute("SELECT symbol FROM stock_symbols WHERE symbol NOT LIKE '%.%'")
            return [row[0] for row in self.cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch symbols: {e}")
            return []

    def fetch_earnings_from_yfinance(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings dates from yfinance."""
        try:
            from utils.yfinance_wrapper import get_ticker
            import pandas as pd

            ticker = get_ticker(symbol)
            if not ticker:
                return []

            results = []

            # Try ticker.calendar
            try:
                cal = ticker.calendar
                if cal and isinstance(cal, dict) and 'Earnings Date' in cal:
                    earnings_date = cal['Earnings Date']
                    if earnings_date and earnings_date >= date.today():
                        results.append({
                            'symbol': symbol,
                            'earnings_date': earnings_date if isinstance(earnings_date, date) else pd.Timestamp(earnings_date).date(),
                            'announce_time': None,
                            'eps_estimate': float(cal.get('Earnings Average')) if cal.get('Earnings Average') else None,
                            'actual_eps': None,
                            'revenue_estimate': int(cal.get('Revenue Average')) if cal.get('Revenue Average') else None,
                            'actual_revenue': None,
                            'fiscal_period': None,
                        })
            except Exception as e:
                logger.debug(f"[{symbol}] ticker.calendar error: {e}")

            return results
        except Exception as e:
            logger.warning(f"yfinance fetch failed for {symbol}: {e}")
            return []

    def load_earnings(self, symbols: Optional[List[str]] = None) -> int:
        """Load earnings dates for symbols."""
        if symbols is None:
            symbols = self.get_symbols()

        if not symbols:
            logger.warning("No symbols to load")
            return 0

        total_loaded = 0

        for symbol in symbols:
            try:
                earnings = self.fetch_earnings_from_yfinance(symbol)
                for earning in earnings:
                    try:
                        self.cur.execute("""
                            INSERT INTO earnings_calendar
                            (symbol, earnings_date, announce_time, eps_estimate, actual_eps,
                             revenue_estimate, actual_revenue, fiscal_period)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (symbol, earnings_date) DO UPDATE SET
                                announce_time = EXCLUDED.announce_time,
                                eps_estimate = EXCLUDED.eps_estimate,
                                actual_eps = EXCLUDED.actual_eps,
                                revenue_estimate = EXCLUDED.revenue_estimate,
                                actual_revenue = EXCLUDED.actual_revenue,
                                fiscal_period = EXCLUDED.fiscal_period,
                                updated_at = CURRENT_TIMESTAMP
                        """, (
                            earning['symbol'],
                            earning['earnings_date'],
                            earning['announce_time'],
                            earning['eps_estimate'],
                            earning['actual_eps'],
                            earning['revenue_estimate'],
                            earning['actual_revenue'],
                            earning['fiscal_period'],
                        ))
                        total_loaded += 1
                    except Exception as e:
                        logger.error(f"Failed to insert earnings for {symbol}: {e}")

                if earnings:
                    logger.info(f"{symbol}: Loaded {len(earnings)} earnings dates")

            except Exception as e:
                logger.warning(f"Failed to load earnings for {symbol}: {e}")

        try:
            self.conn.commit()
            logger.info(f"Committed {total_loaded} earnings calendar records")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to commit: {e}")
            return 0

        return total_loaded

    def run(self, symbols: Optional[List[str]] = None) -> int:
        """Run the loader."""
        try:
            self.connect()
            return self.load_earnings(symbols)
        finally:
            self.close()


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Earnings Calendar Loader")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    loader = EarningsCalendarLoader()
    symbols = args.symbols.split(",") if args.symbols else None
    count = loader.run(symbols)

    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
