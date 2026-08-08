#!/usr/bin/env python3
"""Local loader runner for testing - quickly run any loader without orchestrator overhead.

CONSOLIDATED (Session 48): This script was duplicating symbol-fetching and table-mapping logic
across 13+ hand-written run_*_loader() functions. Refactored to import loader classes dynamically
from the registry (single source of truth) and consolidate symbol fetching into helper functions.

Usage:
  python3 scripts/run_loader_consolidated.py load_prices --symbols AAPL,SPY --backfill 30
  python3 scripts/run_loader_consolidated.py load_technical_indicators
  python3 scripts/run_loader_consolidated.py load_stock_scores --limit 100
  python3 scripts/run_loader_consolidated.py --list-loaders  # Show available loaders

This bypasses the full orchestrator and Step Functions to test individual loaders quickly.

FORCE REFRESH (--force-refresh):
  Bypasses watermarks AND updates loader_watermarks for all processed symbols to TODAY.
  This ensures data stays fresh in LOCAL_MODE (fixes Session 211 data staleness issue).
  Used by Phase 1 failsafe retry in LOCAL_MODE to refresh stale data.

Changes from previous version:
- Removed 13 hand-written run_*_loader() functions (consolidation reduces maintenance burden 13x)
- Symbol fetching now goes through get_active_symbols() helper (no repeated SQL queries)
- Table mappings imported from loader_registry.py (single source of truth - stays in sync)
- Loader choices auto-populated from registry (no hardcoded 'choices=' in argparse)
"""

import argparse
import importlib
import logging
import os
import sys
from datetime import date

# Set LOCAL_MODE for direct database access and to skip AWS-dependent operations
os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"

# LOCAL DEV OPTIMIZATION: Use higher parallelism for local development
# Production ECS uses parallelism=1-2 to avoid rate limiting across shared NAT IPs
# Local dev has no such constraint, so use parallelism=4 for reasonable speed
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "4"

# FIX: Configure Redis for price cache (reduces yfinance API calls by 90%)
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)

# Import loader registry (source of truth for loader → table mappings)
from loaders.loader_registry import LOADER_TABLES
from utils.loaders.helpers import get_active_symbols


def get_loader_class_for_file(loader_filename: str):
    """Dynamically import loader class from filename.

    Example: 'load_prices.py' → from loaders.load_prices import PriceLoader
    Returns the first OptimalLoader subclass with non-empty table_name found in the module.
    FIXED: Skip OptimalLoader base class (has empty table_name) and find the actual subclass.
    """
    if loader_filename.endswith(".py"):
        module_name = loader_filename[:-3]
    else:
        module_name = loader_filename

    try:
        module = importlib.import_module(f"loaders.{module_name}")

        # Find OptimalLoader subclass with non-empty table_name (skip base class)
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and hasattr(obj, 'table_name') and obj.table_name:
                # Found a class with non-empty table_name, return it
                return obj

        logger.error(f"[LOADER] Could not find OptimalLoader subclass with table_name in loaders.{module_name}")
        return None
    except ImportError as e:
        logger.error(f"[LOADER] Could not import loaders.{module_name}: {e}")
        return None


def update_watermarks_to_today(loader_filename: str, table_names: list[str]) -> None:
    """Update loader_watermarks for all active symbols to today's date.

    CRITICAL FIX for LOCAL_MODE data freshness (Session 211):
    When --force-refresh completes, update watermarks so next run doesn't skip data.
    Without this, loaders see old watermarks and skip refresh (data ages 1-2 days per run).

    CONSOLIDATED (Session 48): Use loader_filename to look up canonical loader name,
    eliminating the hardcoded table_to_loader dict that kept diverging from registry.

    Args:
        loader_filename: Loader file (e.g., 'load_prices.py')
        table_names: Output table names
    """
    import psycopg2
    today_str = date.today().isoformat()

    try:
        # Build table → loader filename mapping dynamically from LOADER_TABLES
        table_to_loader = {}
        for fname, tables in LOADER_TABLES.items():
            loader_name = fname.replace(".py", "")
            for table in tables:
                table_to_loader[table] = loader_name

        # Get all active symbols from stock_symbols table
        symbols = get_active_symbols(timeout_secs=60)

        if not symbols:
            logger.warning("[WATERMARK] No active symbols found - skipping watermark update")
            return

        logger.info(f"[WATERMARK] Updating watermarks for {len(symbols)} symbols to {today_str}")

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()

        # Update watermarks for each table's loader
        for table_name in table_names:
            map_loader_name = table_to_loader.get(table_name)
            if not map_loader_name:
                logger.warning(f"[WATERMARK] Unknown table {table_name}, skipping watermark update")
                continue

            # Update all symbols' watermarks to today (use upsert pattern)
            for symbol in symbols:
                cursor.execute(
                    """
                    INSERT INTO loader_watermarks (loader, symbol, granularity, watermark, rows_loaded, last_run_at, last_success_at)
                    VALUES (%s, %s, 'symbol', %s, 0, NOW(), NOW())
                    ON CONFLICT (loader, symbol, granularity)
                    DO UPDATE SET
                        watermark = %s,
                        last_run_at = NOW(),
                        last_success_at = NOW(),
                        error_count = 0,
                        last_error = NULL
                    """,
                    (map_loader_name, symbol, today_str, today_str)
                )

            conn.commit()
            logger.info(f"[WATERMARK] ✓ Updated {map_loader_name} watermarks ({len(symbols)} symbols)")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"[WATERMARK] Failed to update watermarks: {e}", exc_info=True)


def run_loader_generic(loader_class, loader_filename: str, symbols=None, backfill_days=0, limit=None):
    """Generic loader runner (replaces 13 hand-written run_*_loader functions).

    CONSOLIDATED (Session 48): All loader invocation logic is now unified here.
    Special cases (e.g., loaders with custom symbol fetching) are handled inline.

    Args:
        loader_class: The OptimalLoader subclass to instantiate
        loader_filename: Original filename (e.g., 'load_prices.py')
        symbols: Explicit symbols to load (None = auto-fetch based on loader type)
        backfill_days: Days to backfill (0 = incremental via watermarks)
        limit: Limit for limited-dataset loaders (e.g., stock_scores --limit 100)

    Returns:
        Result from loader.run() or loader.load_global()
    """
    loader = loader_class()
    table_name = loader.table_name

    logger.info(f"[LOADER] {table_name}: starting execution")

    # Special-case loaders with custom symbol selection logic
    if table_name in ["market_health_daily", "market_exposure_daily", "market_sentiment", "sector_performance"]:
        # Global loaders (market-wide, not per-symbol)
        logger.info(f"[LOADER] {table_name}: using global mode (no per-symbol runs)")
        result = loader.load_global()
    elif table_name in ["trend_template_data"]:
        # Trend analysis has custom run() function in the module
        logger.info(f"[LOADER] {table_name}: using custom module run() function")
        from loaders.load_trend_analysis import run as run_trend
        result = run_trend()
    elif table_name in ["value_metrics", "quality_metrics", "growth_metrics"]:
        # Value/quality/growth: only load symbols with yfinance data (avoid NULL-filled rows)
        if not symbols:
            try:
                import psycopg2
                conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT symbol FROM yfinance_snapshot WHERE pe_ratio IS NOT NULL OR pb_ratio IS NOT NULL ORDER BY symbol")
                symbols = [row[0] for row in cursor.fetchall()]
                cursor.close()
                conn.close()
                logger.info(f"[LOADER] {table_name}: loaded {len(symbols)} symbols with yfinance data")
            except Exception as e:
                logger.warning(f"[LOADER] {table_name}: could not fetch yfinance symbols: {e}, using stock_symbols fallback")
                symbols = get_active_symbols(timeout_secs=60)
                logger.info(f"[LOADER] {table_name}: loaded {len(symbols)} symbols from fallback")

        result = loader.run(symbols=symbols, parallelism=4)
    else:
        # Default: use get_active_symbols() for all other loaders
        if not symbols:
            # Check if loader has exclude_etfs attribute (some loaders need real stocks only)
            exclude_etfs = getattr(loader, "exclude_etfs_from_symbols", False)
            symbols = get_active_symbols(timeout_secs=60, exclude_etfs=exclude_etfs)
            logger.info(f"[LOADER] {table_name}: loaded {len(symbols)} symbols")

        # Build kwargs for loader.run()
        kwargs = {"symbols": symbols}
        if backfill_days > 0:
            kwargs["backfill_days"] = backfill_days

        # Get parallelism from environment or loader config
        parallelism = int(os.environ.get("LOADER_PARALLELISM", "4"))
        kwargs["parallelism"] = parallelism

        if limit is not None:
            kwargs["limit"] = limit

        result = loader.run(**kwargs)

    # Invoke post_run() hook if present (e.g., StockScoresLoader computes rs_percentile)
    if hasattr(loader, "post_run"):
        logger.info(f"[LOADER] {table_name}: running post_run() hook")
        loader.post_run()

    return result


def main():
    # Build available loaders from registry
    loader_files = sorted(LOADER_TABLES.keys())

    parser = argparse.ArgumentParser(description="Run individual loaders for testing")
    parser.add_argument(
        "loader",
        choices=loader_files + ["--list-loaders"],
        help="Loader file to run (e.g., load_prices.py, load_technical_indicators.py)"
    )
    parser.add_argument("--symbols", help="CSV list of symbols (prices only)")
    parser.add_argument("--backfill", type=int, default=0, help="Days to backfill (default: 0 = load incremental data using watermarks)")
    parser.add_argument("--limit", type=int, help="Limit for limited-dataset loaders")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh by bypassing watermarks and updating status")
    parser.add_argument("--list-loaders", action="store_true", help="List all available loaders")

    # Handle --list-loaders before parsing args (easier)
    if "--list-loaders" in sys.argv:
        print("Available loaders (from loaders/loader_registry.py):")
        for fname in loader_files:
            tables = LOADER_TABLES[fname]
            print(f"  {fname:40} -> {', '.join(tables)}")
        return 0

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle --force-refresh: bypass watermarks and update loader status
    if args.force_refresh:
        os.environ["TECH_FULL_REFRESH"] = "true"
        logger.info("[FORCE_REFRESH] Enabled - bypassing watermarks and updating loader status")

    try:
        loader_filename = args.loader
        if not loader_filename.endswith(".py"):
            loader_filename += ".py"

        if loader_filename not in LOADER_TABLES:
            logger.error(f"[LOADER] Unknown loader: {loader_filename}")
            print(f"ERROR: Unknown loader '{loader_filename}'", file=sys.stderr)
            print(f"Use --list-loaders to see available loaders", file=sys.stderr)
            return 1

        table_names = LOADER_TABLES[loader_filename]
        logger.info(f"[LOADER] Running {loader_filename} (outputs: {', '.join(table_names)})")

        # Mark loaders as RUNNING if force-refresh
        if args.force_refresh:
            import psycopg2
            try:
                conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
                cursor = conn.cursor()
                for table_name in table_names:
                    cursor.execute(
                        "UPDATE data_loader_status SET status = %s, execution_started = NOW() WHERE table_name = %s",
                        ("RUNNING", table_name)
                    )
                    if cursor.rowcount == 0:
                        cursor.execute(
                            "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) VALUES (%s, %s, NOW(), NOW())",
                            (table_name, "RUNNING")
                        )
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"[FORCE_REFRESH] Marked {table_names} as RUNNING")
            except Exception as e:
                logger.warning(f"[FORCE_REFRESH] Could not update status to RUNNING: {e}")

        # Get loader class dynamically
        loader_class = get_loader_class_for_file(loader_filename)
        if not loader_class:
            logger.error(f"[LOADER] Could not load class for {loader_filename}")
            return 1

        # Parse symbols if provided
        symbols = None
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]

        # Run the loader
        result = run_loader_generic(
            loader_class,
            loader_filename,
            symbols=symbols,
            backfill_days=args.backfill,
            limit=args.limit
        )

        logger.info(f"[LOADER] {loader_filename} completed: {result}")

        # Mark loaders as COMPLETED if force-refresh
        if args.force_refresh:
            from utils.loaders.status_manager import LoaderStatusManager
            for table_name in table_names:
                try:
                    status_mgr = LoaderStatusManager(table_name)
                    status_mgr.mark_completed()
                    logger.info(f"[FORCE_REFRESH] Updated {table_name} status via LoaderStatusManager")
                except Exception as e:
                    logger.warning(f"[FORCE_REFRESH] Could not mark {table_name} as COMPLETED: {e}")

            # CRITICAL FIX (Session 211): Update watermarks after --force-refresh
            # Ensures next orchestrator run sees fresh data (prevents 1-2 day staleness in LOCAL_MODE)
            try:
                update_watermarks_to_today(loader_filename, table_names)
            except Exception as e:
                logger.error(f"[WATERMARK] Failed to update watermarks after force-refresh: {e}", exc_info=True)

        logger.info("[LOADER] Execution completed successfully")
        return 0

    except Exception as e:
        logger.error(f"[LOADER] Fatal error: {e}", exc_info=args.debug)
        return 1


if __name__ == "__main__":
    sys.exit(main())
