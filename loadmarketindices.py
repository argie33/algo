#!/usr/bin/env python3
"""
Market Indices Loader - Load major market indices into price_daily.

Fetches OHLCV data for market indices (^GSPC, ^IXIC, ^NYA, ^RUT) and stores
in the price_daily table. Required for distribution days calculation in
load_market_health_daily.py.

Run:
    python3 loadmarketindices.py [--parallelism 4]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

from optimal_loader import OptimalLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


class MarketIndicesLoader(OptimalLoader):
    table_name = "price_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch market index OHLCV data from data source router."""
        end = date.today()
        if since is None:
            start = date(2020, 1, 1)
        else:
            # For incremental, just fetch from watermark onward
            start = since

        try:
            rows = self.router.fetch_ohlcv(symbol, start=start, end=end)
            if not rows:
                return None

            # Normalize to price_daily schema
            return [
                {
                    "symbol": symbol,
                    "date": r["date"],
                    "open": float(r["open"]) if r.get("open") else None,
                    "high": float(r["high"]) if r.get("high") else None,
                    "low": float(r["low"]) if r.get("low") else None,
                    "close": float(r["close"]) if r.get("close") else None,
                    "volume": int(r["volume"]) if r.get("volume") else None,
                }
                for r in rows
            ]
        except Exception as e:
            log.error("Failed to fetch %s: %s", symbol, e)
            return None

    def transform(self, rows):
        """Market indices are already clean from fetch."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate market index row."""
        if not super()._validate_row(row):
            return False
        # Require at least close price and date
        return row.get("close") is not None and row.get("date") is not None


def main():
    parser = argparse.ArgumentParser(description="Market indices loader")
    parser.add_argument("--parallelism", type=int, default=4, help="Concurrent workers")
    args = parser.parse_args()

    # Load major market indices
    symbols = ['^GSPC', '^IXIC', '^NYA', '^RUT']

    loader = MarketIndicesLoader(backfill_days=365)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    log.info("Market indices load complete: %s", stats)
    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
