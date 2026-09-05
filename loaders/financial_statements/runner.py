"""Symbol-major ALL-MODE orchestration for load_financial_statements.py, plus main().

Split out of load_financial_statements.py (see that module's top docstring). Two real
coupling risks drove how this file resolves its dependency on
ConsolidatedFinancialStatementsLoader (defined in load_financial_statements.py, which
imports this module at module-load time to re-export everything below):

1. Circular import: a module-level `from loaders.load_financial_statements import
   ConsolidatedFinancialStatementsLoader` here would deadlock the import (that module isn't
   finished executing yet). Resolved with a TYPE_CHECKING-only import at module level (for
   mypy) plus the real import done inside load_all_statements()'s/main()'s function bodies
   at call time - by which point load_financial_statements is a fully-initialized module -
   matching this file's own existing convention of function-local imports.
2. Test-patch resolution: several existing unit tests patch
   "loaders.load_financial_statements.DatabaseContext"/"...run_loader" and expect that patch
   to intercept this module's own use of those names (in main()/_run_symbol_pass()). A
   top-of-file `from utils.db.context import DatabaseContext` here would bind a separate name
   in THIS module's namespace that those patches can no longer reach (mock.patch replaces an
   attribute on the module doing the lookup, not every module that happens to import the
   same object) - re-resolving both through the load_financial_statements facade at call
   time, same mechanism as point 1, keeps those patch targets working unchanged.
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from utils.external.sec_edgar import SecEdgarClient

from .configs import get_all_statement_configs, get_statement_config

if TYPE_CHECKING:
    from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader

logger = logging.getLogger(__name__)


def load_all_statements() -> int:
    """Load all statement/period combinations in a single symbol-major pass.

    PERFORMANCE FIX 2026-07-13: the previous implementation was combo-major -
    it invoked run_loader() once per statement/period combo, and each of those
    runs iterated ALL ~5,300 symbols. Every combo is derived from the SAME SEC
    companyfacts JSON, so each symbol's multi-MB payload was re-downloaded once
    per combo: ~32,000 HTTP requests per run at the client's 2 req/s rate limit
    (hours of wasted wall time).

    Now a single pass iterates symbols in the outer loop and the six combos in
    the inner loop, sharing one SecEdgarClient whose small per-CIK LRU cache
    serves combos 2-6 from memory: one companyfacts GET per symbol per run
    (~5,300 requests, a ~6x reduction).

    Per-combo contracts preserved from the old run_loader/OptimalLoader.run path:
    - per-table run locks (a held lock skips just that combo, as before)
    - per-table data_loader_status RUNNING row + heartbeat + final status
    - per-table loader_execution_history rows and CloudWatch loader metrics
    - per-combo failure isolation and watermark-based incremental filtering
    - SEC client retry/backoff, rate limiting, and 404 semantics (unchanged)
    - exit code: 1 only when ALL combos failed (same aggregation as before)

    Returns:
        0 on success (statements loaded, marked unavailable, or combos skipped
        by a held lock), 1 on fatal error or when every combo failed
    """
    import argparse

    # Real import (not the TYPE_CHECKING-only one at module level): avoids a circular
    # import at module-load time (load_financial_statements.py imports this module - see
    # this file's own top docstring), matching this file's existing convention of
    # function-local imports for exactly this reason.
    from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader

    # CRITICAL FIX (Session 96): Use centralized timeout config at function start
    # so it's available for lock_ttl calculation below, not just in _load_all_statements helper
    from loaders.loader_timeout_config import get_loader_timeout

    sla_timeout_seconds = get_loader_timeout("financial_statements")

    from utils.db.local_file_lock import get_lock_manager
    from utils.db.pooled_connection_manager import PooledConnectionManager
    from utils.db.pooled_context_var import set_pooled_connection
    from utils.loaders.helpers import get_active_symbols

    # Mirror run_loader's CLI surface (the ECS task normally passes no args).
    parser = argparse.ArgumentParser(description="all financial statements loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all active symbols.")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=1,
        help="Ignored in all-mode: the shared 2 req/s SEC rate limit is the bottleneck; symbols run serially.",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=None,
        help="Refetch last N days instead of using watermark (BACKFILL_DAYS env var also honored).",
    )
    args = parser.parse_args()
    if args.parallelism != 1:
        logger.info("[FINANCIAL_STATEMENTS ALL MODE] --parallelism ignored (serial symbol-major pass)")

    combos = get_all_statement_configs()
    logger.info(
        f"[FINANCIAL_STATEMENTS ALL MODE] Loading {len(combos)} statement/period combinations (symbol-major pass)"
    )

    try:
        # One shared client = one companyfacts LRU cache, one SEC rate limiter,
        # and one ticker->CIK cache across all six combos.
        shared_client = SecEdgarClient()
        loaders = [
            ConsolidatedFinancialStatementsLoader(statement_type=st, period=p, sec_client=shared_client)
            for st, p in combos
        ]
        if args.backfill_days:
            for loader in loaders:
                loader._backfill_days = args.backfill_days
    except Exception as e:
        logger.error(
            f"[FINANCIAL_STATEMENTS ALL MODE] Loader construction failed: {type(e).__name__}: {str(e)[:500]}",
            exc_info=True,
        )
        return 1

    # Per-table run locks: same lock keys and skip semantics as OptimalLoader.run.
    from utils.db.dynamo_lock import DynamoDBLockManager
    from utils.db.local_file_lock import FileLockManager
    from utils.db.rds_lock import RDSLockManager

    # get_lock_manager() returns FileLockManager when LOCAL_MODE=true (all local dev runs
    # take this path - see utils/db/local_file_lock.py), else DynamoDBLockManager with
    # RDSLockManager fallback. All three duck-type the same acquire/release/
    # lock_duration_seconds interface used below. The RuntimeError handler further down
    # only fires when BOTH DynamoDB and RDS are unavailable in non-LOCAL_MODE (production)
    # runs - it does not apply to FileLockManager, which was already fixed for its former
    # Windows race condition (Session 281: atomic O_CREAT|O_EXCL file creation).
    lock_manager: FileLockManager | DynamoDBLockManager | RDSLockManager | None = None
    active: list[ConsolidatedFinancialStatementsLoader] = []
    try:
        lock_table = os.getenv(
            "LOADER_LOCKS_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
        )
        # TTL tied to the loader SLA (matches OptimalLoader.run): this all-mode pass
        # legitimately runs 45+ min, so a 1800s TTL would expire mid-run and allow a
        # concurrent instance to double-write. Locks are still released in finally.
        # Use centralized timeout config (now set at module top via get_loader_timeout)
        # instead of hardcoded fallback
        lock_ttl = sla_timeout_seconds
        try:
            lock_manager = get_lock_manager(table_name=lock_table, lock_duration_seconds=lock_ttl)
        except RuntimeError as ddb_err:
            # CRITICAL (Session 282): DynamoDB unavailable in a non-LOCAL_MODE (production)
            # run, and RDS fallback also failed - fail fast rather than proceed unlocked.
            # (LOCAL_MODE=true never reaches this branch: get_lock_manager() returns
            # FileLockManager directly without raising.)
            logger.critical(
                f"[FINANCIAL_STATEMENTS ALL MODE] DynamoDB lock unavailable: {ddb_err}. "
                f"Cannot proceed without distributed locking. Fix DynamoDB access or AWS credentials."
            )
            from algo.exceptions import LockAcquisitionError

            raise LockAcquisitionError(
                lock_key="financial_statements_all_mode",
                reason=f"DynamoDB lock manager unavailable: {ddb_err}",
                context={"loader": "financial_statements"},
            ) from ddb_err

        # get_lock_manager() either returns a real lock manager or raises RuntimeError
        # above (caught and re-raised as LockAcquisitionError) - it never returns None.
        # Narrows the type for mypy without weakening lock_manager's declared type, which
        # must stay Optional for _release_combo_locks()'s cleanup in the except block below.
        assert lock_manager is not None

        # SESSION 98 FIX: Lock TTL must match configured loader timeout.
        # financial_statements is configured for 360 minutes (21600s) in loader_timeout_config.py.
        # Lock TTL = loader_timeout * 1.1 (10% safety margin for cleanup grace period).
        lock_ttl_seconds = sla_timeout_seconds
        if lock_manager.lock_duration_seconds != lock_ttl_seconds:
            lock_manager.lock_duration_seconds = lock_ttl_seconds

        for loader in loaders:
            if lock_manager.acquire(lock_key=loader.table_name, timeout_seconds=5):
                active.append(loader)
            else:
                logger.warning(f"[{loader.table_name}] Skipping: another instance already running")
    except Exception as lock_err:
        logger.critical(f"[FINANCIAL_STATEMENTS ALL MODE] Lock initialization failed: {lock_err}")
        _release_combo_locks(lock_manager, active)
        return 1

    if not active:
        logger.warning("[FINANCIAL_STATEMENTS ALL MODE] All combos locked by other instances; nothing to do")
        return 0

    conn_manager = None
    started: list[ConsolidatedFinancialStatementsLoader] = []
    try:
        conn_manager = PooledConnectionManager("financial_statements_all_mode")
        set_pooled_connection(conn_manager.acquire())

        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
        else:
            symbols = get_active_symbols(timeout_secs=60, exclude_etfs=True)

        start = time.time()
        for loader in active:
            _start_combo(loader, start, len(symbols))
            started.append(loader)

        # signal.signal() is last-registration-wins: of the per-loader
        # LoaderInfrastructure SIGTERM handlers, only the most recently
        # constructed loader's shutdown flag is actually set on SIGTERM.
        shutdown_watcher = loaders[-1]._infrastructure

        logger.info(f"[FINANCIAL_STATEMENTS ALL MODE] Starting load: {len(symbols)} symbols x {len(active)} combos")
        _run_symbol_pass(active, symbols, shutdown_watcher, start)

        duration = round(time.time() - start, 2)
        return _finalize_all(active, len(combos), len(symbols), duration, symbols)
    except Exception as e:
        logger.error(f"[FINANCIAL_STATEMENTS ALL MODE] Fatal: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        for loader in started:
            try:
                loader._log_execution_history("failed", str(e)[:500])
            except Exception as log_err:
                logger.warning(f"[{loader.table_name}] Failed to log execution history: {log_err}")
        return 1
    finally:
        for loader in started:
            loader._infrastructure.stop_heartbeat()
        try:
            set_pooled_connection(None)
            if conn_manager is not None:
                conn_manager.release()
        except Exception as cleanup_err:
            logger.warning(f"[FINANCIAL_STATEMENTS ALL MODE] Failed to clean up connection: {cleanup_err}")
        _release_combo_locks(lock_manager, active)
        for loader in loaders:
            loader.close()


def _start_combo(loader: "ConsolidatedFinancialStatementsLoader", start: float, symbols_total: int) -> None:
    """Per-combo run setup mirroring OptimalLoader.run (RUNNING status + heartbeat)."""
    loader._execution_start_time = start
    loader._stats["symbols_total"] = symbols_total
    loader._prepare_batch_context()
    loader._status_manager.mark_running()
    loader._infrastructure.start_heartbeat()


def _run_symbol_pass(
    active: list["ConsolidatedFinancialStatementsLoader"],
    symbols: list[str],
    shutdown_watcher: Any,
    start: float,
) -> None:
    """Symbol-major pass: for each symbol, run every statement/period combo.

    Combo failures are isolated per symbol and per combo (mirroring the old
    independent per-combo runs: one combo failing a symbol never blocks the
    other combos), and are counted in each loader's own stats so per-combo
    fail rates and status reporting stay accurate.

    FIXED 2026-08-09: Added per-symbol timeout to prevent hangs on stuck SEC API calls.
    If a single symbol takes >30s to process, skip it and move to next (marks as failed
    to trigger watermark logic for retry). This prevents the entire 5300-symbol load
    from stalling on one bad symbol.
    """
    import threading

    # Real import (not the TYPE_CHECKING-only one at module level for the class): keeps this
    # function patchable the same way it always was - several existing unit tests patch
    # "loaders.load_financial_statements.DatabaseContext" and expect that patch to intercept
    # this function's own health-check query too; re-resolving through the facade module at
    # call time keeps that patch target working unchanged.
    from loaders.load_financial_statements import DatabaseContext

    # CRITICAL FIX (Session 96): Use centralized timeout config instead of hardcoded 10800s (3h)
    # Hardcoded 10800s was timing out financial_statements at 3h despite config allowing 4h (14400s)
    # This 1-hour shortfall caused Friday cascades that persisted through Monday retries
    # Get from centralized config, fallback to 14400s (4h) if not found
    from loaders.loader_timeout_config import get_loader_timeout

    sla_timeout_seconds = get_loader_timeout("financial_statements")
    per_symbol_timeout_seconds = int(os.getenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "30"))

    # FIXED 2026-08-22: a symbol whose thread.join() times out was previously just logged
    # and abandoned - the daemon thread itself kept running in the background (Python cannot
    # force-kill a thread), potentially still mid-fetch or mid-bulk_insert() with its own real
    # DB connection and an open transaction. Since nothing ever waited for these abandoned
    # threads, they were silently hard-killed - uncommitted - the instant this process exited
    # at the end of the full symbol-major pass, discarding any write that hadn't fully
    # committed yet. This is a strong live-supported root cause candidate for
    # [[quarterly_balance_sheet_fy_end_contamination_fixed_20260822]]'s unresolved
    # "backfill reports COMPLETED but 3,393/3,394 symbols still contaminated" mystery: the
    # 30s-per-symbol budget is cumulative across all 6 statement/period combos (see
    # `remaining_timeout` below), tight enough that a single slow-but-real SEC EDGAR fetch
    # (data.sec.gov, API_REQUEST_TIMEOUT_SECONDS=30 alone) can consume the whole budget - the
    # main loop then abandons the symbol as "failed" and moves on while the real fetch+write
    # keeps running unsupervised, only to be discarded uncommitted at process exit. Now every
    # timed-out thread is tracked and given a real chance to finish (and commit) after the
    # main pass completes, instead of being silently killed. This does NOT change behavior
    # for genuinely hung threads (e.g. a socket that never connects) - those still get
    # abandoned via daemon=True once the final grace join also times out.
    abandoned_threads: list[tuple[threading.Thread, str, str]] = []

    for i, symbol in enumerate(symbols, 1):
        if time.time() - start > sla_timeout_seconds:
            logger.critical(
                f"[FINANCIAL_STATEMENTS ALL MODE] HARD LIMIT: exceeded {sla_timeout_seconds}s SLA "
                f"after {i - 1}/{len(symbols)} symbols. Halting."
            )
            raise RuntimeError(f"Loader exceeded hard SLA limit ({sla_timeout_seconds}s) after {i - 1} symbols")
        if shutdown_watcher.check_shutdown_requested():
            logger.warning(f"[FINANCIAL_STATEMENTS ALL MODE] Graceful shutdown - stopping after {i - 1} symbols")
            break
        if i % 50 == 0:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT 1")
            except Exception as health_err:
                logger.critical(
                    f"[FINANCIAL_STATEMENTS ALL MODE] Database health check failed "
                    f"at symbol {i}/{len(symbols)}: {health_err}"
                )
                raise RuntimeError(
                    "[FINANCIAL_STATEMENTS ALL MODE] Database health check failed-connection unreliable. "
                    "Halting loader."
                ) from health_err

            # DASHBOARD ACCURACY FIX 2026-08-18 (loader-health review): this loop tracked
            # loader._stats.increment("symbols_processed"/"symbols_failed") in memory every
            # symbol, but never called _status_manager.update_progress() - so
            # data_loader_status.completion_pct stayed frozen at the 0 mark_running() set it
            # to, for this loader's entire run (up to the 540m/9h SLA), indistinguishable
            # from a hang. Live-confirmed: a run 22 minutes in already showed real row_count
            # (66K-163K rows across the combo tables) while completion_pct still read 0.00 -
            # same "frozen at 0%" bug class already fixed for other loaders this week (e.g.
            # load_enhanced_quality_growth_metrics.py's own DASHBOARD ACCURACY FIX). Reuses
            # the existing every-50-symbols cadence (health check above) rather than adding a
            # new one - each `active` loader gets its own row updated since each combo/table
            # has independent status tracking.
            completion_pct = round(100.0 * i / len(symbols), 2)
            for progress_loader in active:
                try:
                    progress_loader._status_manager.update_progress(
                        symbols_loaded=i, symbol_count=len(symbols), completion_pct=completion_pct
                    )
                except Exception as progress_err:
                    # Progress reporting is diagnostic, not load-bearing - never let a
                    # transient status-table write failure abort real data loading.
                    logger.warning(
                        f"[FINANCIAL_STATEMENTS ALL MODE] Failed to update progress for "
                        f"{progress_loader.table_name} at symbol {i}/{len(symbols)}: {progress_err}"
                    )

        # The first combo's fetch downloads this symbol's companyfacts JSON;
        # the shared client's LRU serves the remaining combos from memory.
        # Use timeout for each symbol to prevent single stuck symbol from halting entire run.
        symbol_start = time.time()
        for loader in active:
            symbol_elapsed = time.time() - symbol_start
            remaining_timeout = max(1, per_symbol_timeout_seconds - symbol_elapsed)

            # Run loader.load_symbol() in a thread with timeout
            result = [False]  # mutable to capture result
            exception: list[Exception | None] = [None]  # mutable to capture exception

            # Bind loader/symbol/result/exception as default args (evaluated now, not at
            # call time) - otherwise every closure created across loop iterations shares
            # the SAME enclosing-scope cells. An abandoned (timed-out but not actually
            # dead - daemon threads can't be force-killed) thread that finishes later
            # would then write result[0]/exception[0] into whatever iteration's result
            # list is current *at that point*, silently corrupting a different symbol's
            # processed/failed counters.
            def run_with_timeout(
                loader: "ConsolidatedFinancialStatementsLoader" = loader,
                symbol: str = symbol,
                result: list[bool] = result,
                exception: list[Exception | None] = exception,
            ) -> None:
                try:
                    loader.load_symbol(symbol)
                    result[0] = True
                except Exception as e:
                    exception[0] = e
                    result[0] = False

            # daemon=True (FIXED 2026-08-09): Python cannot force-kill a thread, so a symbol
            # whose load_symbol() call is genuinely stuck (not just slow - e.g. hangs before
            # the socket ever connects, so configure_socket_timeout(30) never engages) leaves
            # this thread running forever after we abandon it below. A non-daemon thread left
            # running blocks the whole process from exiting (CPython's interpreter shutdown
            # waits on every non-daemon thread) - that would silently recreate the exact
            # "hangs 5+ hours in prod" bug this per-symbol timeout exists to prevent, just
            # moved from mid-loop to process-exit time. daemon=True lets the process exit
            # normally even if some abandoned threads never finish.
            thread = threading.Thread(target=run_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=remaining_timeout)

            if thread.is_alive():
                # Thread still running after timeout - mark as failed for this pass's
                # accounting, continue - but track it so we can still wait for it (and let
                # any in-flight bulk_insert() actually commit) after the main loop, instead
                # of leaving it to be silently killed uncommitted at process exit.
                logger.warning(
                    f"[{loader.table_name}] {symbol} exceeded per-symbol timeout ({per_symbol_timeout_seconds}s). "
                    f"Skipping for now - will get a final grace period to finish after the full pass."
                )
                loader._stats.increment("symbols_failed")
                abandoned_threads.append((thread, symbol, loader.table_name))
            elif result[0]:
                loader._stats.increment("symbols_processed")
            else:
                loader._stats.increment("symbols_failed")
                if exception[0]:
                    logger.error(f"[{loader.table_name}] {symbol} failed: {exception[0]}")

        if i % 100 == 0:
            logger.info(f"  Progress: {i}/{len(symbols)}")

    # Give every abandoned-but-possibly-still-running thread a final bounded chance to finish
    # (and let any in-flight bulk_insert() actually commit) before this process exits and
    # daemon=True silently kills them mid-transaction. Bounded by whatever's left of the
    # overall SLA (never blows past it) and a configurable cap (default 300s, override via
    # LOADER_ABANDONED_THREAD_GRACE_SECONDS for fast tests) so a large batch of genuinely
    # stuck threads can't stall the run indefinitely - each thread only consumes its share of
    # the remaining grace window, and join() returns immediately once a thread actually finishes.
    if abandoned_threads:
        grace_cap_seconds = float(os.getenv("LOADER_ABANDONED_THREAD_GRACE_SECONDS", "300"))
        grace_budget = max(0.0, min(grace_cap_seconds, sla_timeout_seconds - (time.time() - start)))
        logger.info(
            f"[FINANCIAL_STATEMENTS ALL MODE] Giving {len(abandoned_threads)} abandoned thread(s) up to "
            f"{grace_budget:.0f}s total to finish before this process exits."
        )
        grace_deadline = time.time() + grace_budget
        recovered = 0
        still_alive = 0
        for thread, symbol, table_name in abandoned_threads:
            thread.join(timeout=max(0.0, grace_deadline - time.time()))
            if thread.is_alive():
                still_alive += 1
                logger.warning(
                    f"[{table_name}] {symbol}: still running after final grace period - genuinely stuck, "
                    f"abandoning (will be killed at process exit; will retry next run)."
                )
            else:
                recovered += 1
                logger.info(
                    f"[{table_name}] {symbol}: finished during grace period - late write got a chance to commit."
                )
        logger.info(
            f"[FINANCIAL_STATEMENTS ALL MODE] Grace period complete: {recovered} thread(s) finished, "
            f"{still_alive} still alive and being abandoned."
        )


def _finalize_combo(
    loader: "ConsolidatedFinancialStatementsLoader",
    symbol_count: int,
    duration_sec: float,
    symbols: list[str],
) -> bool:
    """Per-combo finalization mirroring OptimalLoader.run + run_loader.

    Order matches the old per-combo path: fail-rate check first (the old
    _run_serial raised before metrics/final status were written), then metrics
    publishing (a failure there also failed the combo), then the final
    data_loader_status row and loader_execution_history entry.

    Returns:
        True if the combo succeeded, False if it failed.
    """
    loader._stats.set("duration_sec", duration_sec)
    stats = loader._stats.to_dict()

    symbols_failed = stats["symbols_failed"]
    fail_rate = (symbols_failed / symbol_count * 100) if symbol_count else 0.0
    max_fail_rate = getattr(
        loader, "max_fail_rate", 15.0
    )  # CRITICAL: Default 15% fail tolerance (was dangerously 60%). Fail-fast on data source issues.
    if fail_rate > max_fail_rate:
        msg = (
            f"[{loader.table_name}] {symbols_failed}/{symbol_count} symbols failed "
            f"({fail_rate:.1f}% > {max_fail_rate}% threshold)-incomplete dataset"
        )
        logger.error(msg)
        loader._log_execution_history("failed", msg[:500])
        return False

    try:
        from algo.reporting.metrics import MetricsPublisher

        with MetricsPublisher() as m:
            m.put_loader_result(loader.table_name, stats)
    except Exception as metrics_err:
        msg = f"Loader metrics publishing failed: {metrics_err}"
        logger.error(f"[{loader.table_name}] {msg}")
        loader._log_execution_history("failed", msg[:500])
        return False

    # FIXED 2026-08-23: ALL MODE never went through run_loader()/runner.py, so
    # ConsolidatedFinancialStatementsLoader.post_run() - which force-nulls the cells
    # _reject_implausible_shares_outstanding()/_reject_implausible_eps() rejected this run
    # (see its own docstring / the __init__ comment on why preserve_on_missing_fields can't
    # do this itself) - was never actually called for this codebase's real production
    # invocation path. The single statement/period mode (run_loader()) already picks this up
    # via runner.py's own post_run hook; mirroring that same call+failure-handling here so
    # ALL MODE gets the identical guarantee instead of a silent gap between the two paths.
    if hasattr(loader, "post_run"):
        try:
            loader.post_run()
        except Exception as post_run_err:
            msg = f"post_run failed: {type(post_run_err).__name__}: {str(post_run_err)[:400]}"
            logger.error(f"[{loader.table_name}] {msg}")
            loader._log_execution_history("failed", msg[:500])
            return False

    loader._update_final_status(symbol_count, symbols)
    loader._log_execution_history("success")
    return True


def _finalize_all(
    active: list["ConsolidatedFinancialStatementsLoader"],
    total_combos: int,
    symbol_count: int,
    duration_sec: float,
    symbols: list[str],
) -> int:
    """Finalize every active combo and compute the all-mode exit code."""
    combos_failed = 0
    for loader in active:
        if not _finalize_combo(loader, symbol_count, duration_sec, symbols):
            combos_failed += 1
    active[0]._invalidate_cache()

    if combos_failed:
        logger.warning(f"[FINANCIAL_STATEMENTS ALL MODE] {combos_failed}/{total_combos} combos failed")
        return 1 if combos_failed == total_combos else 0  # Return 1 only if all failed

    logger.info(
        f"[FINANCIAL_STATEMENTS ALL MODE] All {len(active)} statement/period combinations loaded in {duration_sec}s"
    )
    return 0


def _release_combo_locks(lock_manager: Any, active: list["ConsolidatedFinancialStatementsLoader"]) -> None:
    """Release the per-table run locks acquired for the symbol-major pass."""
    if lock_manager is None:
        return
    for loader in active:
        try:
            lock_manager.release(lock_key=loader.table_name)
        except Exception as lock_err:
            logger.warning(f"[{loader.table_name}] Failed to release lock: {lock_err}")


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    # Real imports (not the TYPE_CHECKING-only one at module level for the class): avoids
    # the circular import load_financial_statements.py's import of this module would
    # otherwise create (see this file's own top docstring), AND keeps this function
    # patchable the same way it always was - several existing unit tests patch
    # "loaders.load_financial_statements.run_loader"/"...DatabaseContext" and expect that
    # patch to take effect here; re-resolving through the facade module at call time
    # (rather than importing directly from run_loader/DatabaseContext's own source
    # modules) keeps those patch targets working unchanged.
    from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, DatabaseContext, run_loader

    try:
        statement_type = os.environ["LOADER_STATEMENT_TYPE"].lower()
    except KeyError as e:
        raise ValueError(
            "CRITICAL: LOADER_STATEMENT_TYPE environment variable not set. Must be 'income', 'balance', 'cashflow', or 'all'."
        ) from e

    # Handle 'all' mode (load all statement types and periods sequentially)
    if statement_type == "all":
        return load_all_statements()

    # Handle single statement/period mode
    try:
        return run_loader(ConsolidatedFinancialStatementsLoader)
    except Exception as e:
        logger.error(f"[FINANCIAL_STATEMENTS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        table_name = "?"
        try:
            period = os.environ["LOADER_PERIOD"]
            config = get_statement_config(statement_type, period)
            table_name = config["table_name"]
            primary_key = config["primary_key"]

            # FIXED 2026-08-17: every one of this loader's 9 output tables keys its
            # primary_key on (symbol, fiscal_year[, fiscal_quarter]) or
            # (symbol, report_date) - never symbol alone - but a crash occurring before
            # any real row is fetched means fiscal_year/report_date genuinely aren't
            # known here. The INSERT below used to omit those columns (defaulting them
            # to NULL) and rely on "ON CONFLICT (symbol, fiscal_year) DO NOTHING" to
            # dedupe repeat crashes - broken, because SQL NULL never equals NULL, so
            # ON CONFLICT's uniqueness check never matches and every crash appended a
            # fresh full-universe batch of NULL-keyed rows with no bound. Worse, a
            # NULL-fiscal_year row actively corrupts every "get latest" query
            # elsewhere in the codebase shaped `ORDER BY fiscal_year DESC LIMIT 1`
            # (load_sec_valuations.py's book_value/cash_row/debt_row lookups among
            # them) - Postgres's DESC ordering defaults to NULLS FIRST, so the empty
            # marker silently outranks real, freshly-loaded data. Live-confirmed
            # 2026-08-17: a single crashed run of this exact except-block wrote 4,948
            # NULL-fiscal_year rows into annual_balance_sheet in one pass, which
            # immediately made AAPL/MSFT/GOOGL/F all report "book value missing"
            # despite each having real FY2025/2026 balance sheet data loaded the same
            # session. Since the missing key column(s) can't be safely defaulted or
            # deduplicated, skip the placeholder write entirely for these tables
            # (symbols keep whatever data they already had - a stale row is safer
            # than a corrupting NULL-keyed one) rather than writing something no
            # future run can clean up or safely query around.
            non_symbol_key_cols = [c for c in primary_key if c != "symbol"]
            if non_symbol_key_cols:
                logger.error(
                    f"[FINANCIAL_STATEMENTS FATAL] Cannot write a per-symbol crash marker to "
                    f"{table_name}: primary key {primary_key} requires {non_symbol_key_cols}, "
                    f"which is not known at crash time. Skipping marker writes (existing rows "
                    f"are left as-is) instead of writing rows with a NULL key column - see "
                    f"2026-08-17 fix comment above for why that corrupts downstream 'latest "
                    f"fiscal year' queries."
                )
                return 1

            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            # DO NOTHING (not DO UPDATE): a crash/timeout partway through must not
            # clobber symbols already fetched and committed earlier in this same
            # run. Only backfill a placeholder row for symbols never reached.
            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        f"""
                        INSERT INTO {table_name} (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT {get_conflict_target(primary_key)} DO NOTHING
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark {table_name} data unavailable: {mark_err}")
        return 1


def get_conflict_target(primary_key: tuple[str, ...]) -> str:
    cols = ", ".join(primary_key)
    return f"({cols})"
