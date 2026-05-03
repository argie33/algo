#!/usr/bin/env python3
"""
Stock Symbols Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadstocksymbols.py [--symbols AAPL,MSFT] [--parallelism 8]
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


class StockSymbolsLoader(OptimalLoader):
    table_name = "stock_symbols"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch incremental data."""
        try:
            rows = self.router.fetch_ohlcv(symbol, since or date(2020, 1, 1), date.today())
            return rows if rows else None
        except Exception as e:
            logging.debug(f"Fetch error for {symbol}: {e}")
            return None

    def transform(self, rows):
        """Transform rows."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate row."""
        return super()._validate_row(row)


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stocks table."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stocks ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal stock_symbols loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = StockSymbolsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
