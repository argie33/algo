#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
ETF Price Aggregate Loader — weekly and monthly OHLCV bars derived from daily ETF prices.

Timeframe determined by LOADER_TYPE env var (etf_prices_weekly / etf_prices_monthly)
or --timeframe CLI flag for manual runs.
"""
from utils.structured_logger import get_logger

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
logger = get_logger(__name__)
import os
from datetime import date, timedelta
from typing import List, Optional
from config.env_loader import load_env
from utils.loader_helpers import _resolve_timeframe
from utils.loader_helpers import get_active_symbols

from utils.optimal_loader import OptimalLoader





class EtfPriceAggregateLoader(OptimalLoader):

    def __init__(self, timeframe: str):
        assert timeframe in ("weekly", "monthly")
        self.timeframe = timeframe
        if timeframe == "weekly":
            self.table_name = "etf_price_weekly"
            self.primary_key = ("symbol", "date")
            self.watermark_field = "date"
        else:
            self.table_name = "etf_price_monthly"
            self.primary_key = ("symbol", "date")
            self.watermark_field = "date"
        super().__init__()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        end = date.today()
        start = (end - timedelta(days=5 * 365)) if since is None else (since + timedelta(days=1))
        if start >= end:
            return None
        rows = self.router.fetch_ohlcv(symbol, start, end)
        return self._aggregate(rows) if rows else None

    def _aggregate(self, rows: List[dict]) -> List[dict]:
        buckets = {}
        for row in rows:
            date_str = row.get("date")
            if not date_str:
                continue
            d = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
            if self.timeframe == "weekly":
                bucket_start = d - timedelta(days=d.weekday())
            else:
                bucket_start = d.replace(day=1)
            key = (row.get("symbol"), bucket_start.isoformat())
            if key not in buckets:
                buckets[key] = {
                    "symbol": row["symbol"],
                    "date": bucket_start.isoformat(),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": 0,
                }
            else:
                buckets[key]["high"] = max(buckets[key]["high"] or 0, row.get("high") or 0)
                buckets[key]["low"] = min(buckets[key]["low"] or float("inf"), row.get("low") or float("inf"))
                buckets[key]["close"] = row.get("close")
            buckets[key]["volume"] = (buckets[key]["volume"] or 0) + (row.get("volume") or 0)
        return list(buckets.values())

    def transform(self, rows):
        return [r for r in rows if r.get("volume", 0) > 0]

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        try:
            return row["high"] >= row["low"] and row["close"] > 0 and row["open"] > 0
        except (KeyError, TypeError):
            return False



def main():
    load_env()
    parser = argparse.ArgumentParser(description="ETF price aggregate loader (weekly/monthly)")
    parser.add_argument("--timeframe", choices=["weekly", "monthly"],
                        help="Aggregation timeframe (defaults to LOADER_TYPE env var)")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all ETFs.")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    timeframe = _resolve_timeframe(args.timeframe)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = EtfPriceAggregateLoader(timeframe)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

