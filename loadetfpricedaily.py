#!/usr/bin/env python3
"""
ETF Daily Price Loader - Optimal Pattern.

Loads ETF daily OHLCV data from Alpaca/yfinance.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadetfpricedaily.py [--symbols SPY,QQQ] [--parallelism 8]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


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
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "stocks"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "stocks"),
        )
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    except:
        return ["SPY", "QQQ", "IWM", "EEM", "EFA"]
    finally:
        try:
            conn.close()
        except:
            pass


def main():
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
