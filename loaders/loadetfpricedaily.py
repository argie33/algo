#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
ETF Daily Price Loader - Loads ETF daily OHLCV data from Alpaca/yfinance.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadetfpricedaily.py [--symbols SPY,QQQ] [--parallelism 8]
"""

import argparse
import logging
import os
import psycopg2
from datetime import date, timedelta
from typing import List, Optional

from config.env_loader import load_env
from utils.logging_setup import get_logger
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)




class ETFPriceDailyLoader(OptimalLoader):
    table_name = "etf_price_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch OHLCV via the data source router."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since + timedelta(days=1)

        if start >= end:
            return None

        return self.router.fetch_ohlcv(symbol, start, end)

    def transform(self, rows):
        """Filter out zero-volume bars."""
        return [r for r in rows if r.get("volume", 0) > 0]

    def _validate_row(self, row: dict) -> bool:
        """Add price-range sanity check."""
        if not super()._validate_row(row):
            return False
        try:
            return (
                row["high"] >= row["low"]
                and row["close"] > 0
                and row["open"] > 0
            )
        except (KeyError, TypeError):
            return False


def get_active_etf_symbols() -> List[str]:
    """Pull active ETF symbols from database or use defaults."""
    from utils.db_connection import get_db_connection
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    except (psycopg2.Error, OSError) as e:
        logging.warning(f"Failed to fetch ETF symbols: {e}")
        return ["SPY", "QQQ", "IWM", "EEM", "EFA"]
    finally:
        if conn:
            try:
                conn.close()
            except psycopg2.Error:
                pass


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Optimal etf_price_daily loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all ETFs from database.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_etf_symbols()

    loader = ETFPriceDailyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

