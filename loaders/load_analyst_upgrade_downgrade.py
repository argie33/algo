#!/usr/bin/env python3

# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Analyst Ratings Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadanalystupgradedowngrade.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import argparse
import logging
import sys


logger = logging.getLogger(__name__)
from datetime import date
from typing import Optional

from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader


class AnalystRatingsLoader(OptimalLoader):
    table_name = "analyst_upgrade_downgrade"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch analyst upgrades/downgrades from yfinance."""
        try:
            from utils.external.yfinance import get_ticker
        except ImportError:
            return None

        ticker = get_ticker(symbol)
        if not ticker:
            return None

        try:
            upgrades_downgrades = ticker.upgrades_downgrades

            if upgrades_downgrades is None or upgrades_downgrades.empty:
                return None

            results = []
            for idx, row in upgrades_downgrades.iterrows():
                ud_date = idx.date() if hasattr(idx, "date") else idx
                results.append(
                    {
                        "symbol": symbol,
                        "action_date": ud_date,
                        "firm": row.get("Firm", ""),
                        "new_rating": row.get("To Grade", ""),
                        "old_rating": row.get("From Grade"),
                        "action": row.get("Action", ""),
                    }
                )

            return results if results else None
        except Exception as e:
            raise RuntimeError(
                f"[ANALYST_RATINGS] Failed to fetch ratings for {self.symbol}: {e}. "
                "Cannot generate signals without analyst data."
            )

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        return super()._validate_row(row)


def main():
    parser = argparse.ArgumentParser(description="Optimal analyst_ratings loader")
    parser.add_argument(
        "--symbols", help="Comma-separated symbols. Default: all from stocks table."
    )
    parser.add_argument("--parallelism", type=int, default=2, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols(timeout_secs=60)

    loader = AnalystRatingsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
