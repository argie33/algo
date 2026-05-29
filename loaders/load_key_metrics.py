#!/usr/bin/env python3
"""Key Metrics Loader - Market cap, shares outstanding, 52-week highs/lows.

Fetches market capitalization and key metrics from yfinance.
Populates key_metrics table required by /api/scores endpoint.

Run: python3 loaders/load_key_metrics.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date
from typing import List, Optional, Dict

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.yfinance_wrapper import get_ticker

logger = get_logger(__name__)


class KeyMetricsLoader(OptimalLoader):
    table_name = "key_metrics"
    primary_key = ("symbol",)
    watermark_field = None  # No date-based watermark, update all at once

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch key metrics for a single symbol."""
        try:
            metrics = self._fetch_key_metrics(symbol)
            if metrics:
                return [metrics]
            return []
        except Exception as e:
            logger.debug(f"Key metrics fetch failed for {symbol}: {e}")
            return []

    def _fetch_key_metrics(self, symbol: str) -> Optional[Dict]:
        """Fetch key metrics from yfinance with retry logic."""
        try:
            ticker = get_ticker(symbol)
            info = ticker.info

            # Extract key metrics
            market_cap = info.get('marketCap')
            held_insiders = info.get('heldPercentInsiders')
            held_institutions = info.get('heldPercentInstitutions')

            # Must have at least market cap
            if not market_cap:
                logger.debug(f"{symbol}: No market cap from yfinance")
                return None

            return {
                'ticker': symbol,
                'symbol': symbol,
                'market_cap': float(market_cap) if market_cap else None,
                'held_percent_insiders': float(held_insiders) if held_insiders else None,
                'held_percent_institutions': float(held_institutions) if held_institutions else None,
            }
        except Exception as e:
            logger.debug(f"yfinance fetch failed for {symbol}: {e}")
            return None


def main():
    try:
        load_env()
    except Exception as e:
        logger.error(f"Failed to load environment: {e}", exc_info=True)
        return 1

    parser = argparse.ArgumentParser(description="Load key metrics")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=8, help="Parallel workers")
    args = parser.parse_args()

    try:
        if args.symbols:
            symbols = args.symbols.split(",")
            logger.info(f"Using {len(symbols)} symbols from command line")
        else:
            logger.info("Fetching active symbols from database...")
            symbols = get_active_symbols(timeout_secs=300)
            if not symbols:
                logger.warning("No symbols found in stock_symbols table - exiting")
                return 1
            logger.info(f"Loaded {len(symbols)} active symbols")
    except Exception as e:
        logger.error(f"Failed to get symbols: {e}", exc_info=True)
        return 1

    logger.info(f"Starting key metrics loader with {len(symbols)} symbols, parallelism={args.parallelism}")
    loader = KeyMetricsLoader()
    try:
        result = loader.run(symbols, parallelism=args.parallelism)
        logger.info(f"Key metrics load completed: {result}")
        return 0
    except Exception as e:
        logger.error(f"Key metrics load failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
