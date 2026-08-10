#!/usr/bin/env python3
"""Local loader runner for testing - quickly run any loader without orchestrator overhead.

CONSOLIDATED (Session 48): This script was duplicating symbol-fetching and table-mapping logic
across 13+ hand-written run_*_loader() functions. Refactored to import loader classes dynamically
from the registry (single source of truth) and consolidate symbol fetching into helper functions.

Usage:
  python3 scripts/run_loader.py load_prices --symbols AAPL,SPY --backfill 30
  python3 scripts/run_loader.py load_technical_indicators
  python3 scripts/run_loader.py load_stock_scores --limit 100
  python3 scripts/run_loader.py --list-loaders  # Show available loaders

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

    FIXED (Session 49): Use registry to identify the loader instead of checking class attributes.
    The table_name is set in __init__, not as a class attribute, so introspection fails.
    Instead, we use LOADER_TABLES to know which file should exist, then import it.

    FIXED (Current session): Support legacy loaders that don't inherit from OptimalLoader
    (e.g., VectorizedTechnicalLoader). Fall back to finding any class matching pattern.
    """
    if loader_filename.endswith(".py"):
        module_name = loader_filename[:-3]
    else:
        module_name = loader_filename

    try:
        module = importlib.import_module(f"loaders.{module_name}")

        # Find any OptimalLoader subclass in the module (don't check table_name)
        from utils.optimal_loader import OptimalLoader
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and issubclass(obj, OptimalLoader) and obj is not OptimalLoader:
                # Found a loader subclass (not the base class itself)
                return obj

        # Fallback: If no OptimalLoader found, look for any class that looks like a loader
        # (e.g., VectorizedTechnicalLoader, legacy loaders that predate OptimalLoader)
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and "Loader" in attr_name and obj.__module__.startswith("loaders"):
                logger.info(f"[LOADER] Using legacy loader class: {attr_name}")
                return obj

        logger.error(f"[LOADER] Could not find OptimalLoader subclass in loaders.{module_name}")
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
    if table_name in ["stock_symbols", "etf_symbols", "market_health_daily", "market_exposure_daily", "market_sentiment", "sector_performance"]:
        # Global loaders (market-wide, not per-symbol)
        logger.info(f"[LOADER] {table_name}: using global mode (no per-symbol runs)")
        result = loader.load_global()
        # For global loaders, mark completion status (loader.load_global() doesn't update status)
        from utils.loaders.status_manager import LoaderStatusManager
        status_mgr = LoaderStatusManager(table_name)
        if result > 0:
            status_mgr.mark_completed(current_run_symbols_loaded=1, current_run_symbol_count=1)
            logger.info(f"[LOADER] {table_name}: marked as COMPLETED")
            # Also mark secondary tables if this loader has output_tables
            if hasattr(loader, 'output_tables') and loader.output_tables:
                for secondary_table in loader.output_tables:
                    if secondary_table != table_name:
                        secondary_mgr = LoaderStatusManager(secondary_table)
                        secondary_mgr.mark_completed(current_run_symbols_loaded=1, current_run_symbol_count=1)
                        logger.info(f"[LOADER] {secondary_table}: marked as COMPLETED")
        else:
            status_mgr.mark_failed(error_message="Global loader returned 0 rows - no data produced", completion_pct=0.0)
            logger.info(f"[LOADER] {table_name}: marked as FAILED (no rows produced)")
            # Also mark secondary tables as failed
            if hasattr(loader, 'output_tables') and loader.output_tables:
                for secondary_table in loader.output_tables:
                    if secondary_table != table_name:
                        secondary_mgr = LoaderStatusManager(secondary_table)
                        secondary_mgr.mark_failed(error_message="Global loader returned 0 rows - no data produced", completion_pct=0.0)
                        logger.info(f"[LOADER] {secondary_table}: marked as FAILED")
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

        if limit is not None:
            symbols = symbols[:limit]

        result = loader.run(symbols=symbols, parallelism=4)
    elif table_name in ["technical_data_daily"]:
        # VectorizedTechnicalLoader: custom run signature
        if not symbols:
            symbols = get_active_symbols(timeout_secs=60)
            logger.info(f"[LOADER] {table_name}: loaded {len(symbols)} symbols")

        if limit is not None:
            symbols = symbols[:limit]

        since_date = None
        if backfill_days > 0:
            from datetime import date, timedelta
            since_date = date.today() - timedelta(days=backfill_days)

        result = loader.run(symbols=symbols, since_date=since_date)
    else:
        # Default: use get_active_symbols() for all other loaders
        if not symbols:
            # Check if loader has exclude_etfs attribute (some loaders need real stocks only)
            exclude_etfs = getattr(loader, "exclude_etfs_from_symbols", False)
            symbols = get_active_symbols(timeout_secs=60, exclude_etfs=exclude_etfs)
            logger.info(f"[LOADER] {table_name}: loaded {len(symbols)} symbols")

        # BUG FOUND 2026-08-10: this used to pass limit through as kwargs["limit"] straight
        # into loader.run() - but no loader's run() (OptimalLoader's base signature, or any
        # subclass's override, including StockScoresLoader - the loader this module's own
        # docstring gives as the "--limit 100" usage example) actually accepts a `limit`
        # keyword argument. Every --limit invocation crashed with "unexpected keyword
        # argument 'limit'" for every single loader, including the documented example.
        # Truncating the symbols list here (a testing/dev convenience: "only touch N
        # symbols") is the correct, universal semantic and matches what every caller of
        # --limit actually wants, without needing each loader class to special-case it.
        if limit is not None:
            symbols = symbols[:limit]

        # Build kwargs for loader.run()
        kwargs = {"symbols": symbols}
        if backfill_days > 0:
            kwargs["backfill_days"] = backfill_days

        # Get parallelism from environment or loader config
        parallelism = int(os.environ.get("LOADER_PARALLELISM", "4"))
        kwargs["parallelism"] = parallelism

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
        help="Loader file or shorthand name to run (e.g., 'prices', 'load_prices.py', 'technical_indicators')"
    )
    parser.add_argument("--symbols", help="CSV list of symbols (prices only)")
    parser.add_argument("--backfill", type=int, default=0, help="Days to backfill (default: 0 = load incremental data using watermarks)")
    parser.add_argument("--limit", type=int, help="Limit for limited-dataset loaders")
    parser.add_argument("--run-date", help="Run date (YYYY-MM-DD) for loader execution (default: today). Used by Phase 1 failsafe to set correct data expectations.")
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

    # Handle --run-date: pass orchestrator's run_date to loader (Phase 1 failsafe override)
    if args.run_date:
        os.environ["ORCHESTRATOR_RUN_DATE"] = args.run_date
        logger.info(f"[RUN_DATE] Set ORCHESTRATOR_RUN_DATE={args.run_date} for loader execution")

    # Handle --force-refresh: bypass watermarks and update loader status
    if args.force_refresh:
        os.environ["TECH_FULL_REFRESH"] = "true"
        logger.info("[FORCE_REFRESH] Enabled - bypassing watermarks and updating loader status")

    try:
        loader_arg = args.loader

        # Normalize loader name (supports shorthand, filename, with/without .py)
        from loaders.loader_registry import normalize_loader_name
        try:
            loader_filename = normalize_loader_name(loader_arg)
        except ValueError as e:
            logger.error(f"[LOADER] {e}")
            print(f"ERROR: {e}", file=sys.stderr)
            print(f"Use --list-loaders to see available loaders", file=sys.stderr)
            return 1

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
        any_table_failed = False
        if args.force_refresh:
            from utils.loaders.status_manager import LoaderStatusManager

            for table_name in table_names:
                try:
                    status_mgr = LoaderStatusManager(table_name)
                    # BUG FOUND 2026-08-10: this used to call mark_completed() unconditionally
                    # here, with no inspection of `result` at all. Most loaders (OptimalLoader
                    # subclasses - see utils/optimal_loader.py's run()) already call their own
                    # mark_completed()/mark_failed() internally based on real completion_pct,
                    # BEFORE this code runs. Calling mark_completed() again unconditionally
                    # afterward didn't just fail to add a check - it actively CLOBBERED a
                    # legitimate mark_failed() the loader itself had already recorded moments
                    # earlier, back to COMPLETED. Phase 1's failsafe retry (the only caller
                    # that passes --force-refresh) decides "recovered" from this subprocess's
                    # exit code, which main() always returns 0 for as long as no exception
                    # propagated - so a loader that correctly detected and reported a real
                    # partial/full failure was reported as both COMPLETED in the DB and
                    # "recovered" to the caller, exactly the fail-open "fabricate success"
                    # shape this codebase's governance comments explicitly forbid elsewhere.
                    # Fix: only apply this fallback when the table is still RUNNING (i.e. the
                    # loader doesn't self-manage terminal status at all, e.g. legacy loaders
                    # without OptimalLoader's status hooks) - respect whatever terminal status
                    # a self-managing loader already recorded.
                    current = status_mgr.get_status()
                    if current and current.get("status") == "RUNNING":
                        status_mgr.mark_completed()
                        logger.info(f"[FORCE_REFRESH] Updated {table_name} status via LoaderStatusManager")
                    else:
                        status_value = current.get("status") if current else "unknown"
                        logger.info(
                            f"[FORCE_REFRESH] {table_name} already has a terminal status "
                            f"({status_value}) from the loader's own run() - not overwriting it."
                        )
                        if status_value not in ("COMPLETED", "HEALTHY"):
                            # The loader itself decided this run did not succeed - propagate
                            # that as a real failure instead of returning exit code 0
                            # regardless, which is what let phase1_failsafe_retry.py mark this
                            # "recovered" for a run that had actually failed (see fix comment
                            # above this block).
                            any_table_failed = True
                except Exception as e:
                    logger.warning(f"[FORCE_REFRESH] Could not check/mark {table_name} status: {e}")

            # CRITICAL FIX (Session 211): Update watermarks after --force-refresh
            # Ensures next orchestrator run sees fresh data (prevents 1-2 day staleness in LOCAL_MODE)
            try:
                update_watermarks_to_today(loader_filename, table_names)
            except Exception as e:
                logger.error(f"[WATERMARK] Failed to update watermarks after force-refresh: {e}", exc_info=True)

        if any_table_failed:
            logger.error(
                "[LOADER] Execution completed but at least one output table's own run() "
                "recorded a non-success terminal status - returning exit code 1 so callers "
                "(e.g. Phase 1 failsafe retry) don't treat this as recovered."
            )
            return 1

        logger.info("[LOADER] Execution completed successfully")
        return 0

    except Exception as e:
        logger.error(f"[LOADER] Fatal error: {e}", exc_info=args.debug)
        # BUG FOUND 2026-08-10: a crash here (e.g. run_loader_generic() raising) happens
        # AFTER --force-refresh already marked every output table RUNNING (see that block
        # above) but BEFORE this function's own terminal-status logic ever runs - so nothing
        # corrected the RUNNING row, identical in shape to the bug that block itself was
        # fixed for. Only touches tables still showing RUNNING - never overwrites a real
        # terminal status the loader's own run() managed to record before crashing.
        if args.force_refresh:
            try:
                from utils.loaders.status_manager import LoaderStatusManager

                loader_filename_for_cleanup = normalize_loader_name(args.loader)
                for table_name in LOADER_TABLES.get(loader_filename_for_cleanup, []):
                    status_mgr = LoaderStatusManager(table_name)
                    current = status_mgr.get_status()
                    if current and current.get("status") == "RUNNING":
                        status_mgr.mark_failed(f"run_loader.py crashed: {type(e).__name__}: {str(e)[:200]}")
            except Exception as cleanup_err:
                logger.warning(f"[LOADER] Could not clean up status after crash: {cleanup_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
