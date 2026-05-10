#!/usr/bin/env python3
"""
Alpaca Portfolio Data Loader - Optimal Pattern

Fetches real-time portfolio holdings and performance data from Alpaca Trading API.
Uses OptimalLoader for database management and execution tracking.

Loads:
- Current holdings from Alpaca /v2/positions endpoint
- Account metrics from Alpaca /v2/account endpoint
- Historical performance data (from account equity curve)

Note: This loader is PORTFOLIO-LEVEL (not per-symbol), so it overrides run()
to fetch all positions at once rather than iterating per-symbol.

Run:
    python3 loadalpacaportfolio.py [--parallelism 1]
"""

import argparse
import json as json_lib
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import List, Optional

import requests

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
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Alpaca configuration
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    logger.error("Alpaca API credentials not found in environment variables")
    sys.exit(1)


class AlpacaPortfolioLoader(OptimalLoader):
    """Load portfolio holdings and performance from Alpaca.

    Note: This is portfolio-level (not per-symbol), so it uses
    a simplified run() that fetches all positions at once.
    """

    table_name = "alpaca_positions"
    primary_key = ("symbol",)  # One row per position
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch all Alpaca positions (symbol parameter ignored for portfolio loader)."""
        try:
            url = f"{ALPACA_BASE_URL}/v2/positions"
            headers = self._get_alpaca_headers()

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            positions = response.json()
            if not isinstance(positions, list):
                return None

            # Add metadata to each position
            rows = []
            for pos in positions:
                row = {
                    "symbol": pos.get("symbol"),
                    "qty": float(pos.get("qty", 0)),
                    "avg_fill_price": float(pos.get("avg_fill_price", 0)),
                    "current_price": float(pos.get("current_price", 0)),
                    "market_value": float(pos.get("market_value", 0)),
                    "unrealized_pl": float(pos.get("unrealized_pl", 0)),
                    "unrealized_plpc": float(pos.get("unrealized_plpc", 0)),
                    "asset_id": pos.get("asset_id"),
                    "updated_at": datetime.utcnow().date(),
                }
                rows.append(row)

            return rows if rows else None
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions: {e}")
            return None

    def _get_alpaca_headers(self) -> dict:
        """Build Alpaca API headers."""
        return {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
            "Content-Type": "application/json",
        }

    def run(self, symbols=None, parallelism: int = 1, **kwargs) -> dict:
        """Portfolio loader: fetch ALL positions (ignore symbol list)."""
        start = time.time()
        logger.info("[%s] Starting load: portfolio-level (all positions)", self.table_name)

        self._execution_id = self._log_execution_start()

        try:
            # Fetch all positions at once (not per-symbol)
            rows = self.fetch_incremental(None, None)

            if not rows:
                logger.warning("[%s] No positions returned from Alpaca", self.table_name)
                self._stats["symbols_processed"] = 0
                self._log_execution_end(self._execution_id, "success")
                return self._stats

            # Transform and validate
            rows = self.transform(rows)
            before_quality = len(rows)
            rows = [r for r in rows if self._validate_row(r)]
            self._stats["rows_quality_dropped"] += before_quality - len(rows)

            # Bulk insert in chunks
            if rows:
                inserted = 0
                for chunk_start in range(0, len(rows), self.chunk_size):
                    chunk = rows[chunk_start : chunk_start + self.chunk_size]
                    inserted += self._bulk_insert(chunk)

                self._stats["rows_fetched"] = len(rows)
                self._stats["rows_inserted"] = inserted
                self._stats["symbols_processed"] = len(rows)

            self._stats["duration_sec"] = round(time.time() - start, 2)
            logger.info(
                "[%s] Done. positions=%d inserted=%d quality_drop=%d %.1fs",
                self.table_name,
                self._stats["rows_fetched"],
                self._stats["rows_inserted"],
                self._stats["rows_quality_dropped"],
                self._stats["duration_sec"],
            )
            self._log_execution_end(self._execution_id, "success")
        except Exception as e:
            logger.error(f"[{self.table_name}] Execution failed: {e}")
            self._log_execution_end(self._execution_id, "failed", str(e))
            raise

        return self._stats


import time  # Import at module level for run() method


def main():
    parser = argparse.ArgumentParser(description="Load Alpaca portfolio holdings")
    parser.add_argument("--parallelism", type=int, default=1, help="Concurrent workers (ignored for portfolio loader)")
    args = parser.parse_args()

    loader = AlpacaPortfolioLoader()
    try:
        stats = loader.run(parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_processed"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
