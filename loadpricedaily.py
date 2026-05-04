#!/usr/bin/env python3
"""
Daily Price Loader - Optimal Pattern with watermarks + multi-source + bulk inserts.

Demonstrates the new pattern combining:
- Watermark-based incremental (load only what's new)
- Bloom filter dedup (skip already-loaded rows)
- Multi-source fallback (Alpaca → yfinance)
- PostgreSQL COPY bulk inserts
- Source-health tracking
- Per-symbol error isolation with parallel execution

Run:
    python3 loadpricedaily.py [--symbols AAPL,MSFT] [--parallelism 4]
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


class PriceDailyLoader(OptimalLoader):
    table_name = "price_daily"
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
        """Filter out zero-volume bars (often indicate missing data)."""
        return [r for r in rows if r.get("volume", 0) > 0]

    def _validate_row(self, row: dict) -> bool:
        """Add price-range sanity check on top of default PK check."""
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
    """Pull active symbols from the canonical universe table."""
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
            # Canonical universe lives in stock_symbols; prefer that. Fall back
            # to company_profile.ticker if stock_symbols is missing.
            cur.execute("""SELECT EXISTS (SELECT 1 FROM information_schema.tables
                           WHERE table_schema='public' AND table_name='stock_symbols')""")
            if cur.fetchone()[0]:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            else:
                cur.execute("SELECT DISTINCT ticker FROM company_profile ORDER BY ticker")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal price_daily loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=4, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = PriceDailyLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
