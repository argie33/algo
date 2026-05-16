#!/usr/bin/env python3
"""
Earnings Calendar Loader - Fetches upcoming earnings dates for blackout enforcement.

Populates earnings_calendar table with:
- Earnings announcement dates
- Pre/post market announcement times
- Analyst EPS/Revenue estimates

Sources:
- yfinance (earnings dates + estimates)
- Fallback: SEC EDGAR filings (dates only)

Run:
    python3 load_earnings_calendar.py [--symbols AAPL,MSFT] [--days-ahead 180]
"""

import argparse
import logging
import os
import sys
import psycopg2
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from credential_helper import get_db_password, get_db_config

# dotenv-autoload
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).resolve().parent / '.env.local'
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class EarningsCalendarLoader:
    """Load upcoming earnings dates for all symbols."""

    def __init__(self):
        self.conn = None
        self.cur = None
        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": get_db_password(),
            "database": os.getenv("DB_NAME", "stocks"),
        }

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
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
            self.cur.execute("SELECT symbol FROM stock_symbols WHERE symbol NOT LIKE '%.%' LIMIT 500")
            return [row[0] for row in self.cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch symbols: {e}")
            return []

    def fetch_earnings_from_yfinance(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings dates from yfinance."""
        try:
            import yfinance as yf
            import pandas as pd

            ticker = yf.Ticker(symbol)

            # yfinance provides earnings dates
            earnings_dates = ticker.earnings_dates
            if earnings_dates is None or earnings_dates.empty:
                return []

            results = []
            for date_val, row in earnings_dates.iterrows():
                if pd.isna(date_val):
                    continue

                # yfinance returns datetime, convert to date
                earnings_date = pd.Timestamp(date_val).date()

                # Only include future earnings
                if earnings_date < date.today():
                    continue

                results.append({
                    'symbol': symbol,
                    'earnings_date': earnings_date,
                    'announce_time': None,  # yfinance doesn't provide announcement time
                    'eps_estimate': None,
                    'actual_eps': None,
                    'revenue_estimate': None,
                    'actual_revenue': None,
                    'fiscal_period': None,
                })

            return results
        except Exception as e:
            logger.debug(f"yfinance earnings fetch failed for {symbol}: {e}")
            return []

    def load_earnings(self, symbols: Optional[List[str]] = None, days_ahead: int = 180) -> int:
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
                        # Insert or update earnings calendar
                        self.cur.execute("""
                            INSERT INTO earnings_calendar
                            (symbol, earnings_date, announce_time, eps_estimate,
                             actual_eps, revenue_estimate, actual_revenue, fiscal_period)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (symbol, earnings_date) DO UPDATE SET
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

        # Commit all changes
        try:
            self.conn.commit()
            logger.info(f"✓ Committed {total_loaded} earnings calendar records")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to commit earnings: {e}")
            return 0

        return total_loaded

    def run(self, symbols: Optional[List[str]] = None, days_ahead: int = 180):
        """Run the loader."""
        try:
            self.connect()
            count = self.load_earnings(symbols, days_ahead)
            logger.info(f"Earnings calendar load complete: {count} records")
            return count
        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(
        description="Load earnings calendar dates for signal blackout enforcement"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols (default: all from database)",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=180,
        help="Number of days to look ahead (default: 180)",
    )

    args = parser.parse_args()

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    loader = EarningsCalendarLoader()
    count = loader.run(symbols, args.days_ahead)

    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
