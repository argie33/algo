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
from typing import Any

# Set LOCAL_MODE for direct database access and to skip AWS-dependent operations
os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"

# BUG FOUND 2026-08-10 (via [[analyst_loaders_reloaded_and_local_parallelism_ban_20260810]]):
# this used to default to "4" under a "local dev has no shared-NAT-IP rate-limit constraint"
# rationale. Live-reproduced: LOADER_PARALLELISM=4 self-triggered the yfinance shared-IP
# circuit breaker from a single local machine (per-IP rate limiting doesn't care whether the
# IP is shared across AWS tasks or not), causing 84%+ false-failure rates on analyst loaders
# that were misdiagnosed as a real coverage-ceiling regression. Production's terraform config
# never goes above LOADER_PARALLELISM=2 for any loader (most are 1). Default to 1 to match the
# value that was actually verified safe; override explicitly per-run if a specific loader is
# confirmed not to hit shared rate limits (e.g. SEC-sourced loaders).
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "1"

# FIX: Configure Redis for price cache (reduces yfinance API calls by 90%)
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)

# Import loader registry (source of truth for loader → table mappings). These come after
# the os.environ LOCAL_MODE/LOADER_PARALLELISM setup above (pre-existing, not moved by this
# change) in case an imported module reads them at import time.
from loaders.loader_registry import GLOBAL_MODE_LOADERS, LOADER_TABLES  # noqa: E402
from utils.loaders.helpers import get_active_symbols  # noqa: E402

# BUG FOUND 2026-08-16: this file's own inline table-name list below was a hand-maintained,
# independently-drifted duplicate of loaders/loader_registry.py's GLOBAL_MODE_LOADERS -
# missing aaii_sentiment entirely and sector_ranking/industry_ranking (both real
# load_sector_industry_daily.py outputs). Derive it from the single source of truth instead.
_GLOBAL_MODE_TABLES: frozenset[str] = frozenset(t for f in GLOBAL_MODE_LOADERS for t in LOADER_TABLES.get(f, []))


def get_loader_class_for_file(loader_filename: str) -> type | None:
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


def update_watermarks_to_today(loader_filename: str, table_names: list[str], symbols: list[str] | None = None) -> None:
    """Update loader_watermarks for the processed symbols to today's date.

    CRITICAL FIX for LOCAL_MODE data freshness (Session 211):
    When --force-refresh completes, update watermarks so next run doesn't skip data.
    Without this, loaders see old watermarks and skip refresh (data ages 1-2 days per run).

    CONSOLIDATED (Session 48): Use loader_filename to look up canonical loader name,
    eliminating the hardcoded table_to_loader dict that kept diverging from registry.

    BUG FIX 2026-08-10: this used to (a) always blast ALL active symbols regardless of
    whether --symbols/--limit restricted the actual run to a subset, and (b) re-derive the
    loader identity per table via a table->loader dict rebuilt from the FULL LOADER_TABLES
    registry - which silently resolves to the WRONG loader whenever two loaders share an
    output table (e.g. quality_metrics/growth_metrics are written by both
    load_value_quality_growth_metrics.py and load_enhanced_quality_growth_metrics.py; the
    dict-overwrite always picked whichever loader appears later in LOADER_TABLES, not the
    one actually invoked). Live-confirmed: `run_loader.py load_value_quality_growth_metrics.py
    --symbols AAT --force-refresh` (a single-symbol test) blasted the ENTIRE ~4917-symbol
    universe's watermark to "today" under the load_enhanced_quality_growth_metrics identity -
    falsely marking 4916 symbols that were never touched as already fresh, which would make
    every subsequent incremental (non-force) run of that loader silently skip them. Fixed by
    (a) using the loader_filename argument directly - the caller already knows definitively
    which loader this is, no re-derivation needed - and (b) only touching the caller-supplied
    `symbols` list when one was given, instead of always pulling the full active universe.

    Args:
        loader_filename: Loader file (e.g., 'load_prices.py') - the loader actually invoked.
        table_names: Output table names.
        symbols: Symbols actually processed this run. None means a genuine full-universe run
            (no --symbols/--limit restriction), so all active symbols are updated.
    """
    import psycopg2

    today_str = date.today().isoformat()
    map_loader_name = loader_filename.replace(".py", "")

    try:
        if symbols is None:
            symbols = get_active_symbols(timeout_secs=60)

        if not symbols:
            logger.warning("[WATERMARK] No symbols to update - skipping watermark update")
            return

        logger.info(f"[WATERMARK] Updating {map_loader_name} watermarks for {len(symbols)} symbols to {today_str}")

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()

        # Update watermarks for each of this loader's own output tables
        for table_name in table_names:
            if table_name not in LOADER_TABLES.get(loader_filename, []):
                logger.warning(f"[WATERMARK] {table_name} not owned by {loader_filename}, skipping")
                continue

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
                    (map_loader_name, symbol, today_str, today_str),
                )

            conn.commit()
            logger.info(f"[WATERMARK] ✓ Updated {map_loader_name} watermarks ({len(symbols)} symbols) for {table_name}")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"[WATERMARK] Failed to update watermarks: {e}", exc_info=True)


def run_loader_generic(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change
    loader_class: type,
    loader_filename: str,
    symbols: list[str] | None = None,
    backfill_days: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
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
    # FIX: Financial statements loader needs env vars to be set before instantiation
    if loader_filename == "load_financial_statements.py":
        if "LOADER_STATEMENT_TYPE" not in os.environ:
            os.environ["LOADER_STATEMENT_TYPE"] = "income"
        if "LOADER_PERIOD" not in os.environ:
            os.environ["LOADER_PERIOD"] = "annual"

    loader = loader_class()
    table_name = loader.table_name

    logger.info(f"[LOADER] {table_name}: starting execution")

    # Special-case loaders with custom symbol selection logic
    if table_name in _GLOBAL_MODE_TABLES:
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
            if hasattr(loader, "output_tables") and loader.output_tables:
                for secondary_table in loader.output_tables:
                    if secondary_table != table_name:
                        secondary_mgr = LoaderStatusManager(secondary_table)
                        secondary_mgr.mark_completed(current_run_symbols_loaded=1, current_run_symbol_count=1)
                        logger.info(f"[LOADER] {secondary_table}: marked as COMPLETED")
        else:
            status_mgr.mark_failed(error_message="Global loader returned 0 rows - no data produced", completion_pct=0.0)
            logger.info(f"[LOADER] {table_name}: marked as FAILED (no rows produced)")
            # Also mark secondary tables as failed
            if hasattr(loader, "output_tables") and loader.output_tables:
                for secondary_table in loader.output_tables:
                    if secondary_table != table_name:
                        secondary_mgr = LoaderStatusManager(secondary_table)
                        secondary_mgr.mark_failed(
                            error_message="Global loader returned 0 rows - no data produced", completion_pct=0.0
                        )
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
                cursor.execute(
                    "SELECT DISTINCT symbol FROM yfinance_snapshot WHERE pe_ratio IS NOT NULL OR pb_ratio IS NOT NULL ORDER BY symbol"
                )
                symbols = [row[0] for row in cursor.fetchall()]
                cursor.close()
                conn.close()
                logger.info(f"[LOADER] {table_name}: loaded {len(symbols)} symbols with yfinance data")
            except Exception as e:
                logger.warning(
                    f"[LOADER] {table_name}: could not fetch yfinance symbols: {e}, using stock_symbols fallback"
                )
                symbols = get_active_symbols(timeout_secs=60)
                logger.info(f"[LOADER] {table_name}: loaded {len(symbols)} symbols from fallback")

        if limit is not None:
            symbols = symbols[:limit]

        # BUG FOUND 2026-08-10: hardcoded parallelism=4 here bypassed the LOADER_PARALLELISM
        # env var entirely (see the fix at the top of this file) - this branch would still
        # self-trigger the yfinance shared-IP circuit breaker regardless of the env default.
        result = loader.run(symbols=symbols, parallelism=int(os.environ.get("LOADER_PARALLELISM", "1")))
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
            # CRITICAL FIX: Increase timeout from 60s to 300s (5 min) to handle database lock contention
            # Session 105: Under concurrent orchestrator load, get_active_symbols() with 60s timeout
            # was timing out frequently, causing failsafe retries to run with 0 symbols.
            # This resulted in "only X/0 symbols loaded" errors. Increasing to 300s matches
            # the timeout used in load_prices.py's main() function (line 3597).
            symbols = get_active_symbols(timeout_secs=300, exclude_etfs=exclude_etfs)
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
        kwargs: dict[str, Any] = {"symbols": symbols}
        if backfill_days > 0:
            kwargs["backfill_days"] = backfill_days

        # Get parallelism from environment or loader config
        # CRITICAL: Default to "1" to match LOADER_PARALLELISM env default (line 49)
        # Parallelism=4 causes yfinance rate limiting on shared NAT IP (verified broken in session 82)
        parallelism = int(os.environ.get("LOADER_PARALLELISM", "1"))
        kwargs["parallelism"] = parallelism

        result = loader.run(**kwargs)

    # Invoke post_run() hook if present (e.g., StockScoresLoader computes rs_percentile)
    if hasattr(loader, "post_run"):
        logger.info(f"[LOADER] {table_name}: running post_run() hook")
        loader.post_run()

    # loader_class is intentionally the bare `type` (any registered OptimalLoader subclass,
    # resolved dynamically at runtime by get_loader_class_for_file) rather than a narrower
    # bound, so loader.run()'s actual return type - dict[str, Any] per OptimalLoader.run() -
    # is invisible to mypy here; the declared return type documents the real contract.
    return result  # type: ignore[no-any-return]


def main() -> int:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change
    # Build available loaders from registry
    loader_files = sorted(LOADER_TABLES.keys())

    parser = argparse.ArgumentParser(description="Run individual loaders for testing")
    parser.add_argument(
        "loader", help="Loader file or shorthand name to run (e.g., 'prices', 'load_prices.py', 'technical_indicators')"
    )
    parser.add_argument("--symbols", help="CSV list of symbols (prices only)")
    parser.add_argument(
        "--backfill", type=int, default=0, help="Days to backfill (default: 0 = load incremental data using watermarks)"
    )
    parser.add_argument("--limit", type=int, help="Limit for limited-dataset loaders")
    parser.add_argument(
        "--run-date",
        help="Run date (YYYY-MM-DD) for loader execution (default: today). Used by Phase 1 failsafe to set correct data expectations.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--force-refresh", action="store_true", help="Force refresh by bypassing watermarks and updating status"
    )
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
            print("Use --list-loaders to see available loaders", file=sys.stderr)
            return 1

        if loader_filename not in LOADER_TABLES:
            logger.error(f"[LOADER] Unknown loader: {loader_filename}")
            print(f"ERROR: Unknown loader '{loader_filename}'", file=sys.stderr)
            print("Use --list-loaders to see available loaders", file=sys.stderr)
            return 1

        table_names = LOADER_TABLES[loader_filename]
        logger.info(f"[LOADER] Running {loader_filename} (outputs: {', '.join(table_names)})")

        # Mark loaders as RUNNING if force-refresh
        # FIXED 2026-08-10: previously opened its own raw psycopg2 connection hardcoded to
        # "dbname=stocks user=stocks host=localhost" (ignoring DB_HOST/DB_USER/DB_PASSWORD/
        # DB_NAME entirely - silently wrong or unauthenticated outside this exact local setup)
        # and hand-rolled the UPDATE without clearing execution_completed/symbols_loaded/
        # completion_pct/error_message - reintroducing, via this second bypass path, the exact
        # stale-progress bug that LoaderStatusManager.mark_running() was fixed for in a58ecc5b5.
        # Live-confirmed 2026-08-10: market_health_daily/market_sentiment/earnings_calendar/
        # market_exposure_daily/stock_scores all showed execution_started newer than a
        # leftover execution_completed from a prior run after a --force-refresh pass. Reusing
        # the canonical, tested LoaderStatusManager closes both gaps at once.
        if args.force_refresh:
            from utils.loaders.status_manager import LoaderStatusManager

            for table_name in table_names:
                try:
                    LoaderStatusManager(table_name).mark_running()
                except Exception as e:
                    logger.warning(f"[FORCE_REFRESH] Could not update status to RUNNING for {table_name}: {e}")
            logger.info(f"[FORCE_REFRESH] Marked {table_names} as RUNNING")

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
            loader_class, loader_filename, symbols=symbols, backfill_days=args.backfill, limit=args.limit
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
            #
            # BUG FIX 2026-08-10: only pass an explicit `symbols` list (from --symbols) through -
            # previously this always updated the FULL active universe regardless of --symbols/
            # --limit, falsely marking untouched symbols as fresh (see
            # update_watermarks_to_today's docstring). A --limit-restricted run's actual symbol
            # subset isn't surfaced back to this scope, so skip the watermark update entirely
            # rather than guess/blast the whole universe.
            if args.limit and not symbols:
                logger.warning(
                    f"[WATERMARK] Skipping watermark update: --force-refresh --limit {args.limit} "
                    f"only processed a subset of symbols not known at this scope - blasting the "
                    f"full active universe would falsely mark unprocessed symbols as fresh."
                )
            else:
                try:
                    update_watermarks_to_today(loader_filename, table_names, symbols=symbols)
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
