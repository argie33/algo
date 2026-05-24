#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Analyst Ratings Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadanalystupgradedowngrade.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
import argparse
import logging
logger = logging.getLogger(__name__)
import sys
import os
from pathlib import Path
from config.env_loader import load_env
from datetime import date, timedelta
from typing import List, Optional

load_env()

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

try:
    from config.credential_helper import get_db_password, get_db_config
    from utils.loader_helpers import get_active_symbols
except ImportError:
    # Fallback if config modules don't exist - use env vars directly
    # DB_HOST is REQUIRED - no localhost fallback
    def _get_db_host():
        host = os.getenv('DB_HOST')
        if not host:
            raise ValueError("DB_HOST environment variable is required")
        return host

    get_db_password = lambda: os.getenv('DB_PASSWORD')
    get_db_config = lambda: {
        'host': _get_db_host(),
        'port': int(os.getenv('DB_PORT', 5432)),
        'user': os.getenv('DB_USER', 'postgres'),
        'database': os.getenv('DB_NAME', 'stocks'),
    }

try:
    from utils.optimal_loader import OptimalLoader
except ImportError:
    # Fallback: create simple loader class if utils not available
    OptimalLoader = object




class AnalystRatingsLoader(OptimalLoader):
    table_name = "analyst_upgrade_downgrade"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch analyst upgrades/downgrades from yfinance."""
        try:
            from utils.yfinance_wrapper import get_ticker
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
                ud_date = idx.date() if hasattr(idx, 'date') else idx
                results.append({
                    'symbol': symbol,
                    'action_date': ud_date,
                    'firm': row.get('Firm', ''),
                    'new_rating': row.get('To Grade', ''),
                    'old_rating': row.get('From Grade'),
                    'action': row.get('Action', '')
                })

            return results if results else None
        except Exception:
            # Any error - skip this symbol gracefully
            return None

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        return super()._validate_row(row)



def main():
    load_env()
    parser = argparse.ArgumentParser(description="Optimal analyst_ratings loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
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

