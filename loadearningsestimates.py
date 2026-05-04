#!/usr/bin/env python3
"""
Earnings Estimates Loader - Optimal Pattern.

Loads analyst earnings estimates and growth projections.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadearningsestimates.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
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


class EarningsEstimatesLoader(OptimalLoader):
    table_name = "earnings_estimates"
    primary_key = ("symbol", "fiscal_year", "period_type")
    watermark_field = "fiscal_year"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch earnings estimates via data source router."""
        try:
            estimates = self.router.fetch_earnings(symbol)
            if not estimates:
                return None
            since_year = int(since) if since else 2000
            filtered = [e for e in estimates if e.get("fiscal_year", 0) > since_year]
            return filtered if filtered else None
        except Exception as e:
            logging.debug(f"Estimates fetch error for {symbol}: {e}")
            return None

    def transform(self, rows):
        """Rows are already clean from data source router."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate estimates row."""
        if not super()._validate_row(row):
            return False
        try:
            return (
                row.get("fiscal_year") is not None
                and row.get("period_type") is not None
                and row.get("fiscal_year") > 1990
                and row.get("fiscal_year") < 2100
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
    parser = argparse.ArgumentParser(description="Optimal earnings_estimates loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = EarningsEstimatesLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
