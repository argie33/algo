#!/usr/bin/env python3
"""
Earnings Estimate Revisions Loader - Optimal Pattern

Tracks how analyst consensus estimates are changing over time.
Fetches estimate trends and revision counts from DataSourceRouter.

Uses OptimalLoader for watermarking, dedup, and bulk inserts.

Run:
    python3 loadearningsrevisions.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import argparse
import json as json_lib
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

from credential_manager import get_credential_manager
from optimal_loader import OptimalLoader

_credential_manager = get_credential_manager()

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath

try:
    from dotenv import load_dotenv as _load_dotenv

    _env_file = _DotenvPath(__file__).resolve().parent / ".env.local"
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class EarningsRevisionsLoader(OptimalLoader):
    """Load earnings estimate revisions from DataSourceRouter."""

    table_name = "earnings_estimate_revisions"
    primary_key = ("symbol", "period", "snapshot_date")
    watermark_field = "snapshot_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch estimate revisions for symbol from router."""
        try:
            # Get revisions from router (fetches from yfinance/Polygon)
            revisions = self.router.fetch_earnings_revisions(symbol)

            if not revisions:
                return None

            # Parse revisions into rows
            rows = []
            snapshot_date = date.today()

            for period, data in revisions.items():
                if not isinstance(data, dict):
                    continue

                row = {
                    "symbol": symbol,
                    "period": period,
                    "snapshot_date": snapshot_date,
                    "up_last_7d": int(data.get("up_last_7d", 0)),
                    "up_last_30d": int(data.get("up_last_30d", 0)),
                    "down_last_7d": int(data.get("down_last_7d", 0)),
                    "down_last_30d": int(data.get("down_last_30d", 0)),
                }
                rows.append(row)

            return rows if rows else None
        except Exception as e:
            logger.debug(f"Earnings revisions fetch failed for {symbol}: {e}")
            return None

    def _validate_row(self, row: dict) -> bool:
        """Validate earnings revisions row."""
        if not super()._validate_row(row):
            return False
        try:
            # All numeric fields must exist
            return all(
                isinstance(row.get(field), (int, float))
                for field in ["up_last_7d", "up_last_30d", "down_last_7d", "down_last_30d"]
            )
        except (KeyError, TypeError):
            return False


def get_active_symbols() -> List[str]:
    """Pull active symbols from stocks table."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=_credential_manager.get_db_credentials()["password"],
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE symbol IS NOT NULL ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load earnings estimate revisions")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=4, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = EarningsRevisionsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
