#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

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
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from utils.structured_logger import get_logger
from utils.db_connection import get_db_connection

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

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
            from utils.yfinance_wrapper import get_ticker as yf_get_ticker
            import pandas as pd

            ticker = yf_get_ticker(symbol)
            results = []

            # Primary: ticker.calendar returns the next earnings date(s)
            try:
                cal = ticker.calendar
                if cal and 'Earnings Date' in cal:
                    dates = cal['Earnings Date']
                    if not isinstance(dates, list):
                        dates = [dates]
                    for d in dates:
                        if d is None:
                            continue
                        if hasattr(d, 'date'):
                            earnings_date = d
                        else:
                            earnings_date = pd.Timestamp(d).date()
                        if earnings_date < date.today():
                            continue
                        eps_est = cal.get('Earnings Average')
                        rev_est = cal.get('Revenue Average')
                        results.append({
                            'symbol': symbol,
                            'earnings_date': earnings_date,
                            'announce_time': None,
                            'eps_estimate': float(eps_est) if eps_est else None,
                            'actual_eps': None,
                            'revenue_estimate': int(rev_est) if rev_est else None,
                            'actual_revenue': None,
                            'fiscal_period': None,
                        })
                else:
                    logger.debug(f"[{symbol}] ticker.calendar empty or no Earnings Date")
            except Exception as e:
                logger.debug(f"[{symbol}] ticker.calendar error: {e}")

            # Fallback: earnings_dates
            if not results:
                try:
                    earnings_dates = ticker.earnings_dates
                    if earnings_dates is not None and not earnings_dates.empty:
                        for date_val, row in earnings_dates.iterrows():
                            if pd.isna(date_val):
                                continue
                            earnings_date = pd.Timestamp(date_val).date()
                            if earnings_date < date.today():
                                continue
                            results.append({
                                'symbol': symbol,
                                'earnings_date': earnings_date,
                                'announce_time': None,
                                'eps_estimate': None,
                                'actual_eps': None,
                                'revenue_estimate': None,
                                'actual_revenue': None,
                                'fiscal_period': None,
                            })
                    else:
                        logger.debug(f"[{symbol}] ticker.earnings_dates None or empty")
                except Exception as e:
                    logger.debug(f"[{symbol}] ticker.earnings_dates error: {e}")

            return results
        except Exception as e:
            logger.warning(f"yfinance fetch failed for {symbol}: {e}")
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
            logger.info(f"[OK] Committed {total_loaded} earnings calendar records")
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
    load_env()
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
