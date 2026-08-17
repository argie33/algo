"""Unified loader runner - consolidates boilerplate across all data loaders.

This module provides a single entry point for running any OptimalLoader subclass,
eliminating ~25 lines of duplicated main() boilerplate from each of the 42 loaders.

Usage:
    from loaders.runner import run_loader
    from loaders.load_quality_metrics import QualityMetricsLoader

    if __name__ == "__main__":
        sys.exit(run_loader(QualityMetricsLoader))

Benefits:
- Reduces loader files from ~230 lines to ~180 lines (eliminates main/argparse/error handling)
- Single source of truth for loader invocation pattern
- Easier to add new flags (e.g., --backfill-days) to all loaders at once
- Reduces token burn when reading multiple loaders (boilerplate is here, not repeated)
"""

import argparse
import logging
import os
import signal
import socket
import threading

from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# CRITICAL: Loader timeout enforcement (prevents hung processes from blocking orchestrator)
# Session 278 audit found 2 hung loaders (4.6h, 2.0h stuck) that prevented orchestrator from proceeding
# CRITICAL FIX 2026-08-02: Make timeout configurable instead of hardcoded
# CRITICAL FIX 2026-08-13: Read LOADER_TIMEOUT (set by Terraform in seconds) not LOADER_TIMEOUT_MINUTES
# SESSION 107 FIX: Default now comes from loader_timeout_config.py, not hardcoded 7200s
# This prevents timeout race conditions where env var not set uses 2h while config specifies 24h (prices)
LOADER_TIMEOUT_SECONDS = None  # Will be set per-loader by run_loader() after instantiating loader_class


def _set_timeout_for_loader(loader_class: type) -> None:
    """Set LOADER_TIMEOUT_SECONDS based on actual loader's configured timeout.

    This runs once in run_loader() after loader_class is known (at line 110).
    Reads from loaders/loader_timeout_config.py instead of using hardcoded 7200s default.

    CRITICAL (Session 108 FIX): Ensure SIGALRM fires BEFORE subprocess timeout so process
    has chance to handle signal and clean up. Timeout order must be:
    1. runner.py SIGALRM (fires first, allows graceful cleanup)
    2. scheduler subprocess.run(timeout=...) (fires second, kills if SIGALRM failed)
    3. failsafe subprocess timeout (fires last, backup kill)

    Use NO SAFETY MARGIN on SIGALRM (fires at exactly configured timeout).
    Scheduler adds 1.1x, failsafe adds 1.25x, so order is correct: 1.0x < 1.1x < 1.25x

    CRITICAL: Prevents race where env var missing → 2h default, but config specifies 24h (prices).
    Session 93+ has repeatedly proven that timeout mismatches cause Monday cascades.
    """
    global LOADER_TIMEOUT_SECONDS
    if LOADER_TIMEOUT_SECONDS is not None:
        return  # Already set (shouldn't happen, but guard against double-call)

    # CRITICAL FIX SESSION 107: Check LOADER_TIMEOUT env var first (for Terraform override),
    # then fall back to per-loader config, not hardcoded 7200s default
    timeout_seconds_env = os.environ.get("LOADER_TIMEOUT")
    if timeout_seconds_env:
        try:
            timeout_seconds = int(timeout_seconds_env)
            if timeout_seconds <= 0:
                raise ValueError(f"LOADER_TIMEOUT must be positive, got {timeout_seconds}")
            # SESSION 108 FIX: Use exact configured timeout (no margin) so SIGALRM fires first
            LOADER_TIMEOUT_SECONDS = timeout_seconds
            debug_val = os.environ.get("LOADER_TIMEOUT_DEBUG")
            if debug_val and debug_val.lower() in ("1", "true", "yes"):
                logger.info(
                    f"[CONFIG] LOADER_TIMEOUT set to {LOADER_TIMEOUT_SECONDS}s ({LOADER_TIMEOUT_SECONDS // 60}m) "
                    f"from env var LOADER_TIMEOUT={timeout_seconds_env}s (no margin - fires before scheduler)"
                )
            return
        except ValueError as e:
            logger.warning(f"[CONFIG] Invalid LOADER_TIMEOUT env var: {e}. Falling back to per-loader config.")

    # CRITICAL FIX SESSION 107: Fall back to loader_timeout_config.py, not hardcoded 7200s
    # This respects the actual timeouts configured for each loader (prices: 1440m, company_info: 540m, etc.)
    try:
        from loaders.loader_timeout_config import get_loader_timeout

        loader_table_name = getattr(loader_class, "table_name", "unknown")
        configured_timeout = get_loader_timeout(loader_table_name)
        # SESSION 108 FIX: Use exact configured timeout (no margin) so SIGALRM fires BEFORE scheduler's 1.1x
        # Ensures timeout order: SIGALRM(1.0x) → scheduler(1.1x) → failsafe(1.25x)
        LOADER_TIMEOUT_SECONDS = configured_timeout
        debug_val = os.environ.get("LOADER_TIMEOUT_DEBUG")
        if debug_val and debug_val.lower() in ("1", "true", "yes"):
            logger.info(
                f"[CONFIG] LOADER_TIMEOUT set to {LOADER_TIMEOUT_SECONDS}s ({LOADER_TIMEOUT_SECONDS // 60}m) "
                f"from loader_timeout_config.py for {loader_table_name} (no margin - fires before scheduler)"
            )
    except Exception as config_err:
        logger.warning(
            f"[CONFIG] Could not load timeout from loader_timeout_config.py for {loader_class}: {config_err}. "
            f"Using fallback timeout of 86400s (24 hours). This is a catch-all for any loader that couldn't be configured."
        )
        # SESSION 108 FIX: Use 24-hour (86400s) fallback instead of 72-minute
        # The old 4320s default was too short and caused premature timeouts on slow loaders
        # 24 hours is safe for all real-world loaders (longest is prices at 1440m = 24h anyway)
        LOADER_TIMEOUT_SECONDS = 86400


def _timeout_handler(_signum: int, _frame: object) -> None:
    """Signal handler for SIGALRM timeout. Raises RuntimeError to interrupt hung loader."""
    # LOADER_TIMEOUT_SECONDS must be non-None here (set by _setup_timeout before signal handler installed)
    if LOADER_TIMEOUT_SECONDS is None:
        timeout_msg = "Loader execution exceeded timeout (timeout value unknown)"
    else:
        timeout_str = f"{LOADER_TIMEOUT_SECONDS // 60} minutes"
        timeout_msg = f"Loader execution exceeded timeout of {LOADER_TIMEOUT_SECONDS}s ({timeout_str})"
    raise RuntimeError(timeout_msg)


def _force_exit_on_timeout() -> None:
    """threading.Timer callback for the Windows fallback path - log then exit forcefully.

    SESSION 89 FIX: Improved timeout enforcement for hung loaders
    - Log all active threads for debugging
    - Exit immediately without cleanup (may be stuck in DB transaction)
    """
    import threading as th

    active_threads = th.enumerate()
    thread_info = "; ".join(f"{t.name}(daemon={t.daemon})" for t in active_threads if not t.name.startswith("Timer"))
    timeout_str = f"{LOADER_TIMEOUT_SECONDS // 60} minute" if LOADER_TIMEOUT_SECONDS else "N/A"
    logger.critical(
        f"[TIMEOUT] Loader exceeded {timeout_str} timeout. Exiting forcefully. Active threads: {thread_info}"
    )
    os._exit(1)


def _setup_timeout() -> None:
    """Set up process-level timeout using signal.SIGALRM (Unix-like systems).

    Falls back gracefully on Windows where signal.SIGALRM is unavailable.
    ECS tasks can still be terminated by AWS if they exceed overall task timeout (900s default).

    SESSION 89 FIX: Improved timeout diagnostics for hung loaders
    """
    # LOADER_TIMEOUT_SECONDS must be set by _set_timeout_for_loader() before this is called
    if LOADER_TIMEOUT_SECONDS is None:
        raise RuntimeError(
            "[TIMEOUT] LOADER_TIMEOUT_SECONDS not set. Call _set_timeout_for_loader(loader_class) first."
        )
    timeout_min = LOADER_TIMEOUT_SECONDS // 60
    timeout_sec = LOADER_TIMEOUT_SECONDS % 60
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(LOADER_TIMEOUT_SECONDS)  # guarded by hasattr above; SIGALRM/alarm are Unix-only
        logger.info(
            f"[TIMEOUT] SIGALRM timeout set to {timeout_min}m {timeout_sec}s (env LOADER_TIMEOUT={LOADER_TIMEOUT_SECONDS}s)"
        )
    else:
        logger.warning(
            f"[TIMEOUT] SIGALRM not available (Windows). "
            f"Using threading.Timer fallback for {timeout_min}m {timeout_sec}s (env LOADER_TIMEOUT={LOADER_TIMEOUT_SECONDS}s)"
        )
        timer = threading.Timer(LOADER_TIMEOUT_SECONDS, _force_exit_on_timeout)
        timer.daemon = True
        timer.start()
        logger.info("[TIMEOUT] threading.Timer started successfully")


def run_loader(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
    loader_class: type[OptimalLoader],
    description: str | None = None,
    global_mode: bool = False,
) -> int:
    """Execute a loader with standard argument parsing and error handling.

    Args:
        loader_class: The OptimalLoader subclass to instantiate and run.
        description: Optional description for argparse (defaults to loader table_name).
        global_mode: If True, call load_global() for market-wide loaders (no symbol args).
                    If False (default), call run(symbols) for per-symbol loaders.

    Returns:
        Exit code: 0 on success, 1 if fail_rate > 5%.
    """
    # SESSION 107 FIX: Set timeout based on loader's actual config, not hardcoded default
    _set_timeout_for_loader(loader_class)
    _setup_timeout()
    socket.setdefaulttimeout(30.0)

    parser = argparse.ArgumentParser(description=description or f"{loader_class.table_name} loader")

    if not global_mode:
        parser.add_argument("--symbols", help="Comma-separated symbols. Default: all active symbols.")
        parser.add_argument(
            "--parallelism",
            type=int,
            default=get_default_parallelism(loader_class.table_name),
            help="Number of parallel workers (default: per-loader config).",
        )
        # Validate BACKFILL_DAYS env var before using it
        backfill_default = None
        backfill_env = os.environ.get("BACKFILL_DAYS")
        if backfill_env:
            try:
                backfill_default = int(backfill_env)
                if backfill_default < 0:
                    raise ValueError("BACKFILL_DAYS must be >= 0")
            except ValueError as e:
                raise ValueError(
                    f"[LOADER] BACKFILL_DAYS env var '{backfill_env}' is invalid: {e}. "
                    f"Must be a non-negative integer (e.g., 7 to backfill 7 days, 0 for no backfill). "
                    f"Set via container environment or --backfill-days command line argument."
                ) from e

        parser.add_argument(
            "--backfill-days",
            type=int,
            default=backfill_default,
            help="Refetch last N days instead of using watermark (for recovery/validation). "
            "Falls back to the BACKFILL_DAYS env var (set this when triggering via ECS RunTask "
            "container overrides, since environment variables can be overridden per-invocation "
            "without needing to know or reconstruct the container's full command).",
        )

    args = parser.parse_args()

    loader = loader_class()
    try:
        if global_mode:
            import time

            start_time = time.time()
            result = loader.load_global()
            execution_duration: float | None = time.time() - start_time

            if result > 0:
                logger.info(f"SUCCESS: {result} records loaded in {execution_duration:.2f}s")
                # Mark completion for global-mode loaders (same as per-symbol mode)
                from utils.loaders.status_manager import LoaderStatusManager

                status_mgr = LoaderStatusManager(loader.table_name)
                # For global loaders, pass row count as both symbol_count and symbols_loaded
                # to indicate 100% completion (1 "symbol" = "market", fully processed)
                status_mgr.mark_completed(
                    execution_duration_sec=execution_duration,
                    current_run_symbols_loaded=1,
                    current_run_symbol_count=1,
                )

                # Mark secondary tables as completed too
                if hasattr(loader, "output_tables") and loader.output_tables:
                    for secondary_table in loader.output_tables:
                        if secondary_table != loader.table_name:
                            secondary_mgr = LoaderStatusManager(secondary_table)
                            secondary_mgr.mark_completed(
                                execution_duration_sec=execution_duration,
                                current_run_symbols_loaded=1,
                                current_run_symbol_count=1,
                            )
                return 0
            else:
                logger.error(f"FAILED: No records loaded in {execution_duration:.2f}s")
                # Mark as failed in status
                from utils.loaders.status_manager import LoaderStatusManager

                status_mgr = LoaderStatusManager(loader.table_name)
                status_mgr.mark_failed(
                    error_message="Global loader returned 0 rows - no data produced",
                    completion_pct=0.0,
                )
                # Mark secondary tables as failed too
                if hasattr(loader, "output_tables") and loader.output_tables:
                    for secondary_table in loader.output_tables:
                        if secondary_table != loader.table_name:
                            secondary_mgr = LoaderStatusManager(secondary_table)
                            secondary_mgr.mark_failed(
                                error_message="Global loader returned 0 rows - no data produced",
                                completion_pct=0.0,
                            )
                return 1
        else:
            # Per-symbol mode
            if args.symbols:
                symbols = [s.strip().upper() for s in args.symbols.split(",")]
            else:
                # Check if this loader needs real stocks only (exclude ETFs)
                exclude_etfs = getattr(loader, "exclude_etfs_from_symbols", False)
                symbols = get_active_symbols(timeout_secs=60, exclude_etfs=exclude_etfs)

            if args.backfill_days:
                stats = loader.run(
                    symbols,
                    parallelism=args.parallelism,
                    backfill_days=args.backfill_days,
                )
            else:
                stats = loader.run(symbols, parallelism=args.parallelism)

            # Assess success: fail if fail_rate exceeds loader's configured threshold.
            # Loaders with limited data coverage (growth/value/stability/quality metrics)
            # may have higher expected failure rates for symbols without financial data.
            # Runner defers to the loader's max_fail_rate to avoid contradicting its judgment.
            if "symbols_failed" not in stats:
                raise RuntimeError(
                    f"[LOADER] Stats missing 'symbols_failed' key. "
                    f"Loader contract violation: expected stats dict with failure count, got {list(stats.keys())}. "
                    f"Cannot determine load success/failure without explicit failure count."
                )
            symbols_failed = stats["symbols_failed"]
            if not isinstance(symbols_failed, int):
                raise TypeError(
                    f"[LOADER] 'symbols_failed' must be int, got {type(symbols_failed).__name__}: {symbols_failed}. "
                    f"Stats tracking corrupted."
                )
            fail_rate = symbols_failed / max(len(symbols), 1)

            # CRITICAL: Get max_fail_rate with safety fallback
            # Don't use bare getattr default (15%) - it's too lenient and masks incomplete loads
            # (Previous price loader bug: 95.75% completion marked COMPLETE due to defaulting to 15%)
            try:
                # Try to get from loader's property first (preferred, config-driven)
                max_fail_rate_pct = loader.max_fail_rate
            except (AttributeError, Exception) as e:
                # Fallback: if property fails, log WARNING and use conservative default
                loader_name = loader.table_name if hasattr(loader, "table_name") else loader_class.__name__
                logger.warning(
                    f"[LOADER {loader_name}] Could not read max_fail_rate property (using fallback): {type(e).__name__}: {e}. "
                    f"Using fallback 5.0% instead of dangerous 15.0% default."
                )
                max_fail_rate_pct = 5.0  # Conservative fallback, not 15%

            max_fail_rate = max_fail_rate_pct / 100.0

            # ERROR COUNT PROPAGATION FIX: Surface error counts to loader status for dashboard visibility
            # Allows operators to distinguish "100% success" from "95% success, 5% failed"
            symbols_loaded = stats.get("symbols_loaded") or 0
            # LoaderStats (utils/loader_stats.py) tracks this as "duration_sec" - "execution_duration_sec"
            # is the data_loader_status DB column name, not a stats dict key. Reading the DB column name
            # here always returned None, so every runner.py-driven loader (all but load_prices.py, which
            # has its own bespoke main()) left execution_duration_sec NULL and the dashboard's Duration
            # column showed "--" for every table except price_daily.
            duration_sec_raw = stats.get("duration_sec")
            execution_duration = float(duration_sec_raw) if duration_sec_raw is not None else None

            # CRITICAL LOGGING: Record max_fail_rate so we can debug status issues
            loader_name = loader.table_name if hasattr(loader, "table_name") else loader_class.__name__
            logger.info(
                f"[LOADER {loader_name}] Completion assessment: "
                f"loaded={symbols_loaded}/{len(symbols)} ({fail_rate * 100:.2f}% failed), "
                f"max_fail_rate={max_fail_rate * 100:.2f}%, "
                f"result={'FAIL' if fail_rate > max_fail_rate else 'PASS'}"
            )

            if fail_rate > max_fail_rate:
                logger.error(f"Too many failures: {symbols_failed}/{len(symbols)} ({fail_rate * 100:.1f}%)")
                # Still mark in status so operators see partial failures
                from utils.loaders.status_manager import LoaderStatusManager

                status_mgr = LoaderStatusManager(loader.table_name)
                status_mgr.mark_failed(
                    error_message=f"{symbols_failed} symbols failed to load (fail rate {fail_rate * 100:.1f}% exceeds limit {max_fail_rate * 100:.0f}%)",
                    completion_pct=((symbols_loaded / len(symbols)) * 100) if len(symbols) > 0 else 0,
                    retry_count=stats.get("retry_count"),
                    http_status=stats.get("http_status_code"),
                )
                # CRITICAL FIX: secondary output tables (e.g. load_sector_industry_daily's
                # sector_ranking/industry_ranking) were only ever marked on the SUCCESS path
                # below. On failure they kept whatever status they had from their last
                # successful run - a stale "completed" row that staleness monitors and Phase 1
                # freshness checks read as fine, hiding that this run never refreshed them.
                if hasattr(loader, "output_tables") and loader.output_tables:
                    for secondary_table in loader.output_tables:
                        if secondary_table != loader.table_name:
                            LoaderStatusManager(secondary_table).mark_failed(
                                error_message=f"Primary loader {loader.table_name} failed (fail rate exceeded): {symbols_failed} symbols failed",
                            )
                return 1

            # Some loaders define post-run steps (e.g. StockScoresLoader.post_run computes
            # RS percentiles via a batch rank query) that must run after all per-symbol
            # writes complete. This hook was previously defined but never invoked.
            if hasattr(loader, "post_run"):
                loader.post_run()

            # Mark completion with error count visibility so dashboard shows partial success (e.g. "95 of 100 succeeded")
            #
            # BUG FIX: this call used to omit min_completion_pct, so LoaderStatusManager.mark_completed()
            # fell back to its own hardcoded 98% default when re-deriving completion_pct from the
            # symbol_count/symbols_loaded row this same function just verified against the loader's
            # REAL max_fail_rate (line 258's fail_rate > max_fail_rate check, just passed to reach this
            # line). For any loader with max_fail_rate > 2% - i.e. any loader that legitimately expects
            # more than 2% of symbols to lack data (ADRs, foreign filers, delisted symbols, thin
            # coverage - common: quality/growth/value metrics at 20%, financial statements at 15%) -
            # a run that correctly PASSED this function's own fail-rate gate moments above could still
            # land between (100-max_fail_rate)% and 98%, and this redundant mark_completed() call would
            # then flip it straight back to FAILED using the wrong, stricter threshold - directly
            # contradicting the PASS verdict this same function just computed. Passing the loader's own
            # threshold keeps this call consistent with the gate above instead of second-guessing it.
            min_completion_pct = max(0.0, 100.0 - max_fail_rate_pct)
            from utils.loaders.status_manager import LoaderStatusManager

            status_mgr = LoaderStatusManager(loader.table_name)
            status_mgr.mark_completed(
                execution_duration_sec=execution_duration,
                symbols_failed=symbols_failed if symbols_failed > 0 else None,  # Only log if there were failures
                min_completion_pct=min_completion_pct,
            )

            # For loaders that write to multiple tables, also record execution time for secondary tables
            # (e.g., load_sector_industry_daily writes to sector_performance, sector_ranking, industry_ranking).
            # Same min_completion_pct fix as above - these secondary tables share the primary's fail-rate
            # verdict (output_tables means "rises and falls with the primary loader run"), so they must be
            # judged against the same threshold that verdict was computed with, not the 98% default.
            if hasattr(loader, "output_tables") and loader.output_tables:
                for secondary_table in loader.output_tables:
                    if secondary_table != loader.table_name:
                        secondary_mgr = LoaderStatusManager(secondary_table)
                        secondary_mgr.mark_completed(
                            execution_duration_sec=execution_duration,
                            min_completion_pct=min_completion_pct,
                        )

            return 0
    except Exception as e:
        loader_name = loader.table_name if hasattr(loader, "table_name") else loader_class.__name__
        logger.error(f"[LOADER FATAL] {loader_name} loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # CRITICAL FIX: OptimalLoader.run() marks its own (primary) table failed internally,
        # but secondary output_tables (e.g. sector_ranking/industry_ranking for
        # load_sector_industry_daily) are never touched on a crash - only on success below.
        # Without this they keep a stale prior "completed" status that hides the fact this
        # run never refreshed them.
        if hasattr(loader, "output_tables") and loader.output_tables:
            from utils.loaders.status_manager import LoaderStatusManager

            for secondary_table in loader.output_tables:
                if secondary_table != loader.table_name:
                    try:
                        LoaderStatusManager(secondary_table).mark_failed(
                            error_message=f"Primary loader {loader_name} crashed: {type(e).__name__}: {str(e)[:200]}",
                        )
                    except Exception as mark_err:
                        logger.error(
                            f"[LOADER FATAL] Failed to mark secondary table {secondary_table} as failed: {mark_err}"
                        )
        return 1
    finally:
        loader.close()
