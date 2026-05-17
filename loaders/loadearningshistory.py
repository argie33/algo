#!/usr/bin/env python3
import sys
from utils.logging_setup import get_logger
from pathlib import Path

# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Earnings History Loader - Optimal Pattern.

Loads historical earnings dates and actual EPS.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadearningshistory.py [--symbols AAPL,MSFT] [--parallelism 8]
"""


try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
from config.credential_helper import get_db_password, get_db_config
from utils.loader_helpers import get_active_symbols
import logging
logger = get_logger(__name__)
import os
import sys
from config.env_loader import load_env
from datetime import date
from typing import List, Optional

from utils.optimal_loader import OptimalLoader




class EarningsHistoryLoader(OptimalLoader):
    table_name = "earnings_history"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "earnings_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch earnings history via data source router."""
        try:
            earnings = self.router.fetch_earnings(symbol)
            if not earnings:
                return []
            return earnings
        except Exception as e:
            logging.debug(f"Earnings fetch error for {symbol}: {e}")
            return []

    def transform(self, rows):
        """Rows are already clean from data source router."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate earnings row."""
        if not super()._validate_row(row):
            return False
        try:
            ed = row.get("earnings_date")
            if ed is None:
                return False
            # Handle both date objects and numeric timestamps
            if isinstance(ed, date):
                return ed.year > 1990
            return int(ed) > 1990
        except (KeyError, TypeError, ValueError):
            return False



def main():
    load_env()
    parser = argparse.ArgumentParser(description="Optimal earnings_history loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = EarningsHistoryLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

