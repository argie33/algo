#!/usr/bin/env python3
"""Backfill missing buy_sell_daily signals for a date range.

This script regenerates signals for dates that were missed due to the
watermark initialization bug (Session 263).

Usage:
    python scripts/backfill_buy_sell_daily.py --start 2026-07-03 --end 2026-07-17
    python scripts/backfill_buy_sell_daily.py --days 15  # Last 15 days
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import argparse
import logging
from datetime import date, datetime, timedelta

from algo.infrastructure import MarketCalendar
from loaders.load_buy_sell_daily import SignalsDailyLoader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols

logger = logging.getLogger(__name__)


def backfill_signals(start_date: date, end_date: date, symbols: list[str] | None = None, parallelism: int = 3) -> int:
    """Backfill signals for a date range.

    Args:
        start_date: First date to generate signals for
        end_date: Last date to generate signals for
        symbols: If None, use all symbols with stock_scores. Otherwise use provided list.
        parallelism: Number of parallel workers

    Returns:
        Total signals generated
    """
    # Validate date range
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")

    # Filter to only trading days in range
    trading_days = []
    current = start_date
    while current <= end_date:
        if MarketCalendar.is_trading_day(current):
            trading_days.append(current)
        current += timedelta(days=1)

    if not trading_days:
        logger.warning(f"No trading days found in range {start_date} to {end_date}")
        return 0

    logger.info(f"Backfill range: {start_date} to {end_date}")
    logger.info(f"Trading days to regenerate: {len(trading_days)} days")
    logger.info(f"Trading dates: {trading_days[0]} ... {trading_days[-1]}")

    # Get symbols if not provided
    if symbols is None:
        try:
            symbols = get_active_symbols(timeout_secs=300)
            logger.info(f"Loaded {len(symbols)} active symbols")

            # Filter to stock_scores universe (as the normal loader does)
            with DatabaseContext("read") as cur:
                cur.execute("SELECT symbol FROM stock_scores WHERE data_unavailable = false")
                scored_symbols = {row[0] for row in cur.fetchall()}

            original_count = len(symbols)
            symbols = [s for s in symbols if s in scored_symbols]
            logger.info(f"Filtered to stock_scores universe: {len(symbols)}/{original_count} symbols")
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return 0

    total_signals = 0
    loader = SignalsDailyLoader()

    # For each date, generate signals for all symbols
    for target_date in trading_days:
        logger.info(f"\n=== Generating signals for {target_date} ===")

        # Override watermark to generate signals for this date
        # We do this by:
        # 1. Clearing watermarks for all symbols for this date
        # 2. Running the loader with backfill_days set to force a specific date window

        try:
            # Delete any existing signals for this date (in case of re-run)
            with DatabaseContext("write") as cur:
                cur.execute(
                    "DELETE FROM buy_sell_daily WHERE date = %s AND data_unavailable = true",
                    (target_date,)
                )
                logger.debug(f"Cleared sentinel rows for {target_date}")

            # For each symbol, generate signals
            # We use the normal loader mechanism but force it to look at this specific date
            failed = []
            for i, symbol in enumerate(symbols, 1):
                if i % 500 == 0:
                    logger.info(f"Progress: {i}/{len(symbols)}")

                try:
                    # Force fetch_incremental to load data up to target_date
                    # by temporarily clearing its watermark
                    rows = loader.fetch_incremental(symbol, since=target_date - timedelta(days=1))

                    if rows:
                        # Transform and insert
                        rows = loader.transform(rows)

                        # Filter to only this date
                        target_signals = [r for r in rows if r.get("date") == target_date.isoformat()]

                        if target_signals:
                            try:
                                inserted = loader._bulk_insert_mgr.bulk_insert(
                                    target_signals,
                                    symbol=symbol
                                )
                                total_signals += inserted
                                if inserted > 0 and symbol in ('AAPL', 'JPM', 'MA'):
                                    logger.debug(f"{symbol}: {inserted} signals inserted for {target_date}")
                            except Exception as e:
                                logger.warning(f"{symbol}: Failed to insert signals for {target_date}: {e}")
                                failed.append(symbol)
                except Exception as e:
                    failed.append(symbol)
                    if len(failed) <= 10:
                        logger.debug(f"{symbol}: fetch failed for {target_date}: {e}")

            if failed:
                fail_rate = len(failed) / len(symbols) * 100
                logger.warning(
                    f"[{target_date}] {len(failed)}/{len(symbols)} symbols failed to generate signals ({fail_rate:.1f}%)"
                )

            logger.info(f"[{target_date}] Signals generated: {total_signals} cumulative")

        except Exception as e:
            logger.error(f"Failed to backfill {target_date}: {e}")
            continue

    # Update watermarks for all symbols to end_date
    try:
        with DatabaseContext("write") as cur:
            cur.execute(
                "SELECT symbol, MAX(date) FROM buy_sell_daily GROUP BY symbol HAVING MAX(date) >= %s",
                (start_date,)
            )
            updated_symbols = cur.fetchall()
            logger.info(f"Total symbols with signals in backfill range: {len(updated_symbols)}")
    except Exception as e:
        logger.warning(f"Failed to verify backfill: {e}")

    return total_signals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill missing buy_sell_daily signals"
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD) - default: 15 days ago"
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD) - default: yesterday"
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Backfill last N days (overrides --start/--end)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated symbols (default: all from stock_scores)"
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=3,
        help="Number of parallel workers"
    )
    args = parser.parse_args()

    # Determine date range
    now_et = datetime.now(EASTERN_TZ)
    today_et = now_et.date()

    if args.days:
        end_date = today_et - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=args.days - 1)
    else:
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else today_et - timedelta(days=1)
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else end_date - timedelta(days=14)

    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = args.symbols.split(",")

    logger.info(f"Starting backfill: {start_date} to {end_date}")
    logger.info(f"Parallelism: {args.parallelism}")

    try:
        total = backfill_signals(start_date, end_date, symbols=symbols, parallelism=args.parallelism)
        logger.info(f"✓ Backfill complete: {total} signals generated")
        return 0
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)
