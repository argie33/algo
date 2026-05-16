#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Stock Symbols Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadstocksymbols.py [--symbols AAPL,MSFT] [--parallelism 8]
"""


try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
from credential_helper import get_db_password, get_db_config
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


class StockSymbolsLoader(OptimalLoader):
    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch symbol metadata only (not price data)."""
        # Just return metadata for the symbol - no time series data
        return [{
            "symbol": symbol,
            "name": f"{symbol} Company",  # Placeholder
            "exchange": "NASDAQ",  # Placeholder
            "market_cap": 0,
            "sector": "Technology",  # Placeholder
            "industry": "Unknown",  # Placeholder
        }]

    def transform(self, rows):
        """Transform rows."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate row."""
        return super()._validate_row(row)


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stocks table, or use seed list if empty."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            symbols = [r[0] for r in cur.fetchall()]
            if symbols:
                return symbols
    finally:
        conn.close()

    # Bootstrap: if database is empty, use seed list of popular stocks
    return [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BERKB', 'JPM', 'V',
        'JNJ', 'WMT', 'PG', 'XOM', 'MA', 'HD', 'DIS', 'MCD', 'KO', 'ADBE',
        'NFLX', 'PEP', 'CSCO', 'INTC', 'AMD', 'CRM', 'IBM', 'BKNG', 'ORCL',
        'BA', 'HON', 'MMM', 'UPS', 'CVX', 'MRK', 'ABBV', 'TMO', 'COST',
    ]


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

