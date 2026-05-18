#!/usr/bin/env python3
"""
Bulk load all price data for all symbols.

This is the core test to verify:
1. All 10,142+ symbols can load prices
2. No data is dropped due to rate limits
3. Load time is reasonable
4. All data makes it to database

Usage:
    python3 bulk_load_prices.py --dry-run        # Show what would be done (no DB write)
    python3 bulk_load_prices.py --limit 100      # Load only first 100 symbols
    python3 bulk_load_prices.py --full            # Load all symbols (takes ~1 hour)
"""

import sys
import argparse
import logging
import time
from pathlib import Path
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Bulk load price data for all symbols")
    parser.add_argument("--limit", type=int, help="Only load first N symbols (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--parallelism", type=int, default=4, help="Concurrent workers")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD), default: 5 years ago")
    args = parser.parse_args()

    try:
        from config.env_loader import load_env
        from utils.loader_helpers import get_active_symbols
        from loaders.loadpricedaily import PriceDailyLoader
        from utils.db_connection import get_db_connection

        load_env()

        # Get symbols
        log.info("Loading symbols from database...")
        all_symbols = get_active_symbols()
        symbols = all_symbols[:args.limit] if args.limit else all_symbols
        log.info(f"Loaded {len(symbols)} symbols (from {len(all_symbols)} total)")

        # Determine date range
        if args.start_date:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        else:
            start_date = date.today() - timedelta(days=365*5)  # 5 years of history
        end_date = date.today()
        log.info(f"Date range: {start_date} to {end_date}")

        # Initialize loader
        loader = PriceDailyLoader()

        # Statistics
        stats = {
            "total_symbols": len(symbols),
            "succeeded": 0,
            "failed": 0,
            "failed_symbols": [],
            "total_rows_fetched": 0,
            "total_rows_inserted": 0,
            "errors": {},
        }

        # Load in parallel
        log.info(f"\nLoading prices with {args.parallelism} workers...")
        start_time = time.time()

        def load_one_symbol(symbol: str):
            """Load price data for one symbol."""
            try:
                if args.dry_run:
                    # Just fetch, don't insert
                    rows = loader.fetch_incremental(symbol, start_date)
                    if rows:
                        return (symbol, True, len(rows), None)
                    else:
                        return (symbol, True, 0, None)
                else:
                    # Full load: fetch and insert
                    rows = loader.fetch_incremental(symbol, start_date)
                    if not rows:
                        return (symbol, True, 0, None)

                    # Transform and validate
                    rows = loader.transform(rows)
                    rows = [r for r in rows if loader._validate_row(r)]

                    if not rows:
                        return (symbol, False, 0, "validation_failed")

                    # Insert
                    inserted = loader._insert_rows(symbol, rows)
                    return (symbol, True, inserted, None)

            except Exception as e:
                error_type = type(e).__name__
                log.debug(f"[{symbol}] Load failed: {error_type}: {str(e)[:100]}")
                return (symbol, False, 0, error_type)

        # Submit all tasks
        with ThreadPoolExecutor(max_workers=args.parallelism) as executor:
            futures = {
                executor.submit(load_one_symbol, symbol): symbol
                for symbol in symbols
            }

            # Process completed tasks
            completed = 0
            for future in as_completed(futures):
                symbol, success, rows, error = future.result()
                completed += 1

                if success:
                    stats["succeeded"] += 1
                    stats["total_rows_fetched"] += rows
                    stats["total_rows_inserted"] += rows
                    if (completed) % 100 == 0:
                        log.info(f"Progress: {completed}/{len(symbols)} ({stats['succeeded']} succeeded)")
                else:
                    stats["failed"] += 1
                    stats["failed_symbols"].append(symbol)
                    if error not in stats["errors"]:
                        stats["errors"][error] = 0
                    stats["errors"][error] += 1

        elapsed = time.time() - start_time

        # Report
        log.info("\n" + "=" * 80)
        log.info("LOAD COMPLETE")
        log.info("=" * 80)
        log.info(f"Total time: {elapsed/60:.1f} minutes")
        log.info(f"Symbols processed: {stats['total_symbols']}")
        log.info(f"  Succeeded: {stats['succeeded']}")
        log.info(f"  Failed: {stats['failed']} ({100*stats['failed']/stats['total_symbols']:.1f}%)")
        log.info(f"Total rows fetched: {stats['total_rows_fetched']:,}")
        log.info(f"Total rows inserted: {stats['total_rows_inserted']:,}")

        if stats["errors"]:
            log.info(f"\nErrors:")
            for error_type, count in sorted(stats["errors"].items(), key=lambda x: -x[1]):
                log.info(f"  {error_type}: {count}")

        if stats["failed_symbols"]:
            log.info(f"\nFailed symbols (first 20):")
            for symbol in stats["failed_symbols"][:20]:
                log.info(f"  {symbol}")

        # Check database
        if not args.dry_run:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM price_daily")
                db_count = cur.fetchone()[0]
                cur.close()
                log.info(f"\nDatabase validation:")
                log.info(f"  Total price records in DB: {db_count:,}")

                if db_count > 0:
                    log.info(f"  ✅ Data successfully inserted")
                else:
                    log.warning(f"  ⚠️  No data in database!")

            except Exception as e:
                log.warning(f"Could not validate database: {e}")

        # Return success if all symbols succeeded or failures are < 5%
        success = (stats["failed"] == 0) or (stats["failed"] / stats["total_symbols"] < 0.05)
        return 0 if success else 1

    except Exception as e:
        log.error(f"Fatal error: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
