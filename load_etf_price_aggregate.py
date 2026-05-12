#!/usr/bin/env python3
"""
ETF Price Aggregate Loader — weekly and monthly OHLCV bars derived from daily ETF prices.

Timeframe determined by LOADER_TYPE env var (etf_prices_weekly / etf_prices_monthly)
or --timeframe CLI flag for manual runs.
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

from optimal_loader import OptimalLoader

from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _resolve_timeframe(cli_arg: Optional[str]) -> str:
    if cli_arg:
        return cli_arg
    loader_type = os.getenv("LOADER_TYPE", "")
    return "monthly" if "monthly" in loader_type else "weekly"


class EtfPriceAggregateLoader(OptimalLoader):

    def __init__(self, timeframe: str):
        assert timeframe in ("weekly", "monthly")
        self.timeframe = timeframe
        if timeframe == "weekly":
            self.table_name = "etf_price_weekly"
            self.primary_key = ("symbol", "week_start")
            self.watermark_field = "week_start"
        else:
            self.table_name = "etf_price_monthly"
            self.primary_key = ("symbol", "month_start")
            self.watermark_field = "month_start"
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
                pk_field = "week_start"
            else:
                bucket_start = d.replace(day=1)
                pk_field = "month_start"
            key = (row.get("symbol"), bucket_start.isoformat())
            if key not in buckets:
                buckets[key] = {
                    "symbol": row["symbol"],
                    "date": bucket_start.isoformat(),
                    pk_field: bucket_start.isoformat(),
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


def get_active_symbols() -> List[str]:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=credential_manager.get_db_credentials()["password"],
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM etf_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
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
