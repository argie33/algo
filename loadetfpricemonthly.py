#!/usr/bin/env python3
"""
ETF Monthly Price Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadetfpricemonthly.py [--symbols SPY,QQQ] [--parallelism 8]
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


class ETFPriceMonthlyLoader(OptimalLoader):
    table_name = "etf_price_monthly"
    primary_key = ("symbol", "month_start")
    watermark_field = "month_start"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch monthly OHLCV via the data source router."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since + timedelta(days=1)

        if start >= end:
            return None

        rows = self.router.fetch_ohlcv(symbol, start, end)
        return self._aggregate_to_monthly(rows) if rows else None

    def _aggregate_to_monthly(self, rows: List[dict]) -> List[dict]:
        """Aggregate daily OHLCV to monthly bars."""
        if not rows:
            return []
        months = {}
        for row in rows:
            date_str = row.get("date")
            if not date_str:
                continue
            d = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
            month_start = d.replace(day=1)
            key = (row.get("symbol"), month_start.isoformat())
            if key not in months:
                months[key] = {
                    "symbol": row["symbol"],
                    "month_start": month_start.isoformat(),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": 0,
                }
            else:
                months[key]["high"] = max(months[key]["high"] or 0, row.get("high") or 0)
                months[key]["low"] = min(months[key]["low"] or float('inf'), row.get("low") or float('inf'))
                months[key]["close"] = row.get("close")
            months[key]["volume"] = (months[key]["volume"] or 0) + (row.get("volume") or 0)
        return list(months.values())

    def transform(self, rows):
        """Filter out zero-volume months."""
        return [r for r in rows if r.get("volume", 0) > 0]

    def _validate_row(self, row: dict) -> bool:
        """Validate monthly bar structure."""
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
    parser = argparse.ArgumentParser(description="Optimal etf_price_monthly loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all ETFs from database.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_etf_symbols()

    loader = ETFPriceMonthlyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
