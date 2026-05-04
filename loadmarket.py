#!/usr/bin/env python3
"""
Market Overview Loader - Optimal Pattern.

Loads market-wide metrics (indices, breadth, volatility, etc).
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadmarket.py [--parallelism 4]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

from optimal_loader import OptimalLoader

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class MarketLoader(OptimalLoader):
    table_name = "market_overview"
    primary_key = ("index_name", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch market indices (SPY, QQQ, IWM, etc)."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=365)
        else:
            start = since + timedelta(days=1)

        if start >= end:
            return None

        indices = ["SPY", "QQQ", "IWM", "VIX"]
        market_data = []

        for idx in indices:
            try:
                rows = self.router.fetch_ohlcv(idx, start, end)
                if rows:
                    for row in rows:
                        market_data.append({
                            "index_name": idx,
                            "date": row.get("date"),
                            "close": float(row.get("close", 0)),
                            "volume": int(row.get("volume", 0)),
                            "market_cap": None,
                            "advance_decline_ratio": None,
                            "vix": None,
                        })
            except Exception as e:
                logging.debug(f"Market data fetch error for {idx}: {e}")
                continue

        return market_data if market_data else None

    def transform(self, rows):
        """Filter valid rows."""
        return [r for r in rows if r.get("close", 0) > 0]

    def _validate_row(self, row: dict) -> bool:
        """Validate market row."""
        if not super()._validate_row(row):
            return False
        return row.get("close", 0) > 0 and row.get("date") is not None


def main():
    parser = argparse.ArgumentParser(description="Optimal market loader")
    parser.add_argument("--parallelism", type=int, default=1, help="Concurrent workers")
    args = parser.parse_args()

    loader = MarketLoader()
    try:
        stats = loader.run(["market"], parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
