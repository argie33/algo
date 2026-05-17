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
from config.credential_helper import get_db_password, get_db_config

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
from utils.optimal_loader import OptimalLoader

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

s [%(levelname)s] %(name)s: %(message)s",
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
            df = self.router.fetch_eps_revisions(symbol)

            if df is None or (hasattr(df, 'empty') and df.empty):
                return None

            rows = []
            snapshot_date = date.today()

            # yfinance returns DataFrame: index=period ('0q','+1q','0y','+1y'),
            # columns: upLast7days, upLast30days, downLast30days, downLast90days
            for period, row_data in df.iterrows():
                rows.append({
                    "symbol": symbol,
                    "period": str(period),
                    "snapshot_date": snapshot_date,
                    "up_last_7d": int(row_data.get("upLast7days", 0) or 0),
                    "up_last_30d": int(row_data.get("upLast30days", 0) or 0),
                    "down_last_30d": int(row_data.get("downLast30days", 0) or 0),
                    "down_last_90d": int(row_data.get("downLast90days", 0) or 0),
                })

            return rows if rows else None
        except Exception as e:
            logger.debug(f"Earnings revisions fetch failed for {symbol}: {e}")
            return None

    def _validate_row(self, row: dict) -> bool:
        """Validate earnings revisions row."""
        if not super()._validate_row(row):
            return False
        return bool(row.get("symbol") and row.get("period") and row.get("snapshot_date"))


def get_active_symbols() -> List[str]:
    """Pull active symbols from stocks table."""
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
