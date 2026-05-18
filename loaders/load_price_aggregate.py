#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Price Aggregate Loader — weekly and monthly OHLCV bars derived from daily prices.

Timeframe determined by LOADER_TYPE env var (stock_prices_weekly / stock_prices_monthly)
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





class PriceAggregateLoader(OptimalLoader):

    def __init__(self, timeframe: str):
        assert timeframe in ("weekly", "monthly")
        self.timeframe = timeframe
        if timeframe == "weekly":
            self.table_name = "price_weekly"
            self.primary_key = ("symbol", "date")
            self.watermark_field = "date"
        else:
            self.table_name = "price_monthly"
            self.primary_key = ("symbol", "date")
            self.watermark_field = "date"
        super().__init__()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        end = date.today()
        start = (end - timedelta(days=5 * 365)) if since is None else (since + timedelta(days=1))
        if start >= end:
            return None
        # FIX: Read from price_daily (RDS) instead of re-fetching from API
        rows = self._fetch_price_daily(symbol, start, end)
        return self._aggregate(rows) if rows else None

    def _fetch_price_daily(self, symbol: str, start: date, end: date) -> Optional[List[dict]]:
        """Read daily prices from RDS (not API) to avoid double-fetching."""
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date, open, high, low, close, volume FROM price_daily "
                "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                (symbol, start.isoformat(), end.isoformat()),
            )
            rows = cur.fetchall()
            if not rows:
                return None
            return [
                {
                    "date": r[0].isoformat() if hasattr(r[0], 'isoformat') else str(r[0]),
                    "open": float(r[1]) if r[1] is not None else None,
                    "high": float(r[2]) if r[2] is not None else None,
                    "low": float(r[3]) if r[3] is not None else None,
                    "close": float(r[4]) if r[4] is not None else None,
                    "volume": int(r[5]) if r[5] is not None else None,
                    "symbol": symbol,
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Error reading price_daily for {symbol}: {e}")
            return None
        finally:
            cur.close()

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
    parser = argparse.ArgumentParser(description="Price aggregate loader (weekly/monthly)")
    parser.add_argument("--timeframe", choices=["weekly", "monthly"],
                        help="Aggregation timeframe (defaults to LOADER_TYPE env var)")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument("--parallelism", type=int, default=16)
    args = parser.parse_args()

    timeframe = _resolve_timeframe(args.timeframe)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = PriceAggregateLoader(timeframe)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

