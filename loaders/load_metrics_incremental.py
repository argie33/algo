#!/usr/bin/env python3
"""Incremental metrics loader - fills in missing data on a schedule.

Loads only symbols that DON'T have data yet, with slow parallelism
to avoid yfinance rate limits. Run this on a daily/weekly schedule.

Usage:
  python3 loaders/load_metrics_incremental.py --type stability --batch-size 500 --parallelism 2
  python3 loaders/load_metrics_incremental.py --type positioning --batch-size 500 --parallelism 2
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date
from typing import List

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.db_connection import get_db_connection

logger = get_logger(__name__)


def get_missing_symbols(loader_type: str, batch_size: int) -> List[str]:
    """Get symbols that don't have data for this loader_type."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if loader_type == "stability":
            table = "stability_metrics"
        elif loader_type == "positioning":
            table = "positioning_metrics"
        elif loader_type == "growth":
            table = "growth_metrics"
        else:
            raise ValueError(f"Unknown loader_type: {loader_type}")

        # Get all active symbols
        all_symbols = get_active_symbols(timeout_secs=60)

        # Get symbols that already have data
        cur.execute(f"SELECT symbol FROM {table}")
        have_data = set(row[0] for row in cur.fetchall())

        cur.close()
        conn.close()

        # Return symbols missing data, limited to batch_size
        missing = [s for s in all_symbols if s not in have_data]
        return missing[:batch_size]

    except Exception as e:
        logger.error(f"Error getting missing symbols: {e}")
        return []


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Incremental metrics loader")
    parser.add_argument("--type", required=True, choices=["stability", "positioning", "growth"],
                       help="Which metrics to load")
    parser.add_argument("--batch-size", type=int, default=500,
                       help="Max symbols to load in this run (default: 500)")
    parser.add_argument("--parallelism", type=int, default=2,
                       help="Concurrent workers (keep low to avoid rate limits, default: 2)")
    args = parser.parse_args()

    # Get symbols missing data
    missing_symbols = get_missing_symbols(args.type, args.batch_size)
    if not missing_symbols:
        logger.info(f"{args.type} metrics: all {get_active_symbols()} symbols already loaded")
        return 0

    logger.info(f"Loading {args.type} metrics for {len(missing_symbols)} missing symbols")

    # Run appropriate loader
    if args.type == "stability":
        from loaders.load_stability_metrics import StabilityMetricsLoader
        loader = StabilityMetricsLoader()
    elif args.type == "positioning":
        from loaders.load_positioning_metrics import PositioningMetricsLoader
        loader = PositioningMetricsLoader()
    else:  # growth
        from loaders.load_growth_metrics_yfinance import GrowthMetricsYfinanceLoader
        loader = GrowthMetricsYfinanceLoader()

    try:
        stats = loader.run(missing_symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(missing_symbols), 1)
    logger.info(f"{args.type} metrics: {stats.get('symbols_succeeded', 0)}/{len(missing_symbols)} loaded "
                f"({fail_rate*100:.1f}% failed)")

    if fail_rate > 0.2:
        logger.error(f"Too many failures for {args.type}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
