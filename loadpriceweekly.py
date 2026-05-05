#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Weekly Price Loader - Optimal Pattern.

Demonstrates OptimalLoader with weekly aggregation.
Inherits watermarks, dedup, multi-source routing, and bulk COPY.

Run:
    python3 loadpriceweekly.py [--symbols AAPL,MSFT] [--parallelism 4]
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


class PriceWeeklyLoader(OptimalLoader):
    table_name = "price_weekly"
    primary_key = ("symbol", "week_start")
    watermark_field = "week_start"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch weekly OHLCV via the data source router."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since + timedelta(days=1)

        if start >= end:
            return None

        rows = self.router.fetch_ohlcv(symbol, start, end)
        return self._aggregate_to_weekly(rows) if rows else None

    def _aggregate_to_weekly(self, rows: List[dict]) -> List[dict]:
        """Aggregate daily OHLCV to weekly bars."""
        if not rows:
            return []
        weeks = {}
        for row in rows:
            date_str = row.get("date")
            if not date_str:
                continue
            d = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
            week_start = d - timedelta(days=d.weekday())
            key = (row.get("symbol"), week_start.isoformat())
            if key not in weeks:
                weeks[key] = {
                    "symbol": row["symbol"],
                    "date": week_start.isoformat(),
                    "week_start": week_start.isoformat(),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": 0,
                }
            else:
                weeks[key]["high"] = max(weeks[key]["high"] or 0, row.get("high") or 0)
                weeks[key]["low"] = min(weeks[key]["low"] or float('inf'), row.get("low") or float('inf'))
                weeks[key]["close"] = row.get("close")
            weeks[key]["volume"] = (weeks[key]["volume"] or 0) + (row.get("volume") or 0)
        return list(weeks.values())

    def transform(self, rows):
        """Filter out zero-volume weeks."""
        return [r for r in rows if r.get("volume", 0) > 0]

    def _validate_row(self, row: dict) -> bool:
        """Validate weekly bar structure."""
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
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal price_weekly loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=4, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = PriceWeeklyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
