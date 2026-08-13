#!/usr/bin/env python3
"""Local loader scheduler for dev/test environments.

Usage:
  python scripts/local_loader_scheduler.py --now morning
  python scripts/local_loader_scheduler.py --now metrics
  python scripts/local_loader_scheduler.py --now signals
"""

import argparse
import collections
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import IO

from loaders.loader_registry import all_tables, normalize_loader_name
from utils.db.context import DatabaseContext
from utils.loaders.status_manager import LoaderStatusManager, reap_stale_running_loaders

logger = logging.getLogger(__name__)

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
# BUG FOUND 2026-08-10 (via [[analyst_loaders_reloaded_and_local_parallelism_ban_20260810]]):
# this used to default to "4" for "local dev optimization". Live-reproduced: LOADER_PARALLELISM=4
# self-triggered the yfinance shared-IP circuit breaker from a single local machine, causing
# 84%+ false-failure rates on analyst loaders (same fix applied to scripts/run_loader.py).
# Default to 1 to match the value actually verified safe.
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "1"


def _monitor_loader_progress(loader_filename: str, poll_interval_sec: int = 30, max_stall_sec: int = 300) -> bool:
    """Monitor loader progress while subprocess is running. Kill if stuck at 0% for too long.

    CRITICAL SESSION 106 FIX: Detect hung loaders during execution, not just after failure.
    Previously, a loader could hang at 0% for 27+ minutes while the orchestrator waited,
    and only the reaper (36-hour timeout) would eventually catch it. This function polls
    every poll_interval_sec and kills the process if completion_pct hasn't changed in
    max_stall_sec seconds.

    Args:
        loader_filename: e.g., "load_prices.py"
        poll_interval_sec: How often to check progress (default 30s)
        max_stall_sec: Kill if stuck >N seconds without progress (default 300s = 5 min)

    Returns:
        True if loader made progress / is still healthy, False if hung
    """
    try:
        tables = all_tables(loader_filename)
        if not tables:
            return True  # No tables to monitor, assume healthy

        primary_table = tables[0]
        last_pct = None
        last_pct_time = time.time()

        while True:
            time.sleep(poll_interval_sec)
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT completion_pct, last_updated FROM data_loader_status WHERE table_name = %s",
                        (primary_table,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return True  # Table doesn't exist yet, assume OK

                    current_pct, _last_updated = row
                    now = time.time()

                    # Check if progress has changed
                    if current_pct is not None and current_pct != last_pct:
                        last_pct = current_pct
                        last_pct_time = now
                        if current_pct > 0:
                            # Making progress, reset stall timer
                            continue

                    # Check stall condition
                    stall_duration = now - last_pct_time
                    if stall_duration > max_stall_sec and (last_pct is None or last_pct <= 0.0):
                        print(
                            f"[PROGRESS_MONITOR] {loader_filename}: STALLED at {last_pct or 0}% "
                            f"for {stall_duration:.0f}s (>{max_stall_sec}s threshold). "
                            f"Will signal process termination.",
                            file=sys.stderr,
                        )
                        return False  # Indicate hung

            except Exception as monitor_err:
                # Monitor errors shouldn't kill the loader, just log and continue
                logger.debug(f"[PROGRESS_MONITOR] Error checking {loader_filename}: {monitor_err}")
                continue
    except Exception as outer_err:
        logger.debug(f"[PROGRESS_MONITOR] Outer error: {outer_err}")
        return True  # Don't kill on monitor errors


def _mark_loader_failed_after_crash(loader_filename: str, error_message: str) -> None:
    """Best-effort: mark every table a crashed/timed-out loader owns as FAILED.

    Without this, subprocess.run() crashing or timing out left data_loader_status stuck
    at RUNNING indefinitely (no owning process, no error_message, no terminal status) -
    only reap_stale_running_loaders()'s 4-hour-later check on the *next* pipeline
    invocation would ever correct it. Live-confirmed 2026-08-10: quality_metrics/
    growth_metrics (via enhanced_quality_growth) died mid-run with no process alive and
    no status transition. Deliberately swallows its own errors - a failure to record the
    failure must never mask the original crash/timeout being reported by the caller.

    CRITICAL FIX SESSION 102: Also handle NOT_STARTED status (subprocess crashed before mark_running).
    Subprocess may die before runner.py calls mark_running(), leaving status=NOT_STARTED but execution_started/
    execution_completed set. The previous check only marked tables with status==RUNNING, leaving these stuck forever.
    Now unconditionally calls mark_failed() regardless of current status.
    """
    try:
        for table in all_tables(loader_filename):
            LoaderStatusManager(table).mark_failed(error_message)
    except Exception as mark_err:
        print(
            f"[LOCAL_SCHEDULER] WARNING: could not mark {loader_filename} tables FAILED after crash: {mark_err}",
            file=sys.stderr,
        )


PIPELINES = {
    "morning": [
        "prices",
        "technical",
        "market_status",
        "earnings_calendar",  # FIXED 2026-08-05: Minervini/Weinstein earnings blackout window (Phase 3)
        "trend_analysis",  # FIXED 2026-08-05: Setup/teardown detection for signal quality (Phase 7)
        "sector_industry",  # FIXED 2026-08-05: Sector rotation signals and industry rankings (Phase 5/7)
        # SESSION 103 FIX: Removed scores/buy_sell from morning - they depend on metrics
        # (value_quality_growth, enhanced_quality_growth, stability_metrics) which are only
        # in the metrics pipeline. Keeping them here caused scores/buy_sell to fail with
        # "validation failed: [metric table] is EMPTY". Result: buy_sell_daily never ran,
        # stayed stale forever, Monday halt on missing signals.
        # CORRECT PIPELINE ORDER: morning → metrics → signals
        # This allows morning to complete fast (prices+technical+reference data),
        # metrics to populate dimension tables, then signals to generate scores/buy_sell
        # with complete upstream data.
    ],
    "metrics": [
        # FIXED 2026-08-11: company_info must run first - valuations depends on it for
        # symbol lookups and metadata, preventing cascading failures when SEC rate limiting blocks company_info
        "company_info",
        # RE-ENABLED 2026-08-09: financial_statements with optimized per-symbol timeouts
        # CRITICAL DEPENDENCY: Must run BEFORE value_quality_growth (needs annual_income_statement, annual_balance_sheet, annual_cash_flow)
        "financial_statements",
        "valuations",  # SEC valuations (PE, PB, PS, PEG, FCF)
        # FIXED 2026-08-03: analyst_earnings_estimates must run BEFORE value_quality_growth
        "analyst_earnings_estimates",
        "value_quality_growth",  # CRITICAL: depends on valuations + analyst_earnings_estimates
        # FIXED 2026-08-03: enhanced_quality_growth must run after value_quality_growth
        "enhanced_quality_growth",
        # FIXED 2026-08-09: analyst_upgrade_downgrade & analyst_sentiment populate
        # analyst_upgrade_downgrade and analyst_sentiment_analysis tables used by signals
        "analyst_upgrades",
        "analyst_sentiment",
        "positioning",  # FIXED 2026-08-10: was "positioning_metrics" (not in registry)
        "stability_metrics",
    ],
    "signals": [
        "prices",
        "technical",
        "scores",
        "buy_sell",
        # ADDED 2026-08-10: same "no PIPELINES entry" bug class as the "reference" pipeline
        # fixes below - both registered (SHORTHAND_TO_FILENAME + LOADER_TIMEOUTS) but
        # reachable from no PIPELINES list, so untestable locally without bypassing the
        # scheduler. Placed after buy_sell to match terraform/modules/pipeline/main.tf's
        # production ordering (SignalQualityScores -> AlgoMetricsAfterSignals, both
        # downstream of signal generation).
        "signal_quality",
        "algo",
    ],
    # ADDED 2026-08-10: these 9 loaders had no PIPELINES entry, making them unreachable
    # locally via the sanctioned `--now {pipeline}` path - the only way to run/backfill them
    # was to invoke the script directly, bypassing this scheduler entirely (see
    # feedback_always_use_pipeline_scheduler_for_backfills). segment_metrics depends on
    # segment_info (see LOADER_DEPENDENCIES below - terraform/modules/pipeline/main.tf
    # documents this as a CRITICAL DEPENDENCY: "SecSegmentMetrics depends on sec_segment_info
    # being freshly populated"), so it's listed after. institutional/insider_holdings feed
    # positioning_metrics (also a terraform-documented CRITICAL DEPENDENCY) but are NOT wired
    # as a same-run LOADER_DEPENDENCIES entry here deliberately - unlike financial statements,
    # these are slow-changing filings (13F is quarterly) that positioning_metrics reads from
    # whatever's already in the table, not from this specific run; forcing a same-run
    # dependency would make every local "metrics" run wait on a quarterly-cadence reload it
    # doesn't need.
    "reference": [
        "company_info",
        "profile",
        "institutional",
        "insider_holdings",
        "insider_velocity",
        "sec_reports",
        "short_interest",
        "segment_info",
        "segment_metrics",
        # ADDED 2026-08-10: 10th loader in this same "no PIPELINES entry" bug class, missed
        # by the fix above - earnings_calendar_sec (SEC 10-K/10-Q filing-date earnings
        # calendar, the official replacement for yfinance earnings_date) was reachable
        # neither here nor anywhere else in PIPELINES despite having both a
        # SHORTHAND_TO_FILENAME entry ("earnings_sec") and a LOADER_TIMEOUTS entry -
        # DB-confirmed stale locally (earnings_calendar_sec's last local run was 10 days
        # before this fix) while production stays fresh via terraform's separately-wired
        # Step Functions EarningsCalendarSec state. Not to be confused with "earnings_calendar"
        # above (yfinance-backed announcement dates/EPS, a different table/concept).
        "earnings_sec",
        # ADDED 2026-08-10: same "registered but reachable from no PIPELINES list" gap,
        # for slow-changing/low-frequency reference data - all confirmed correctly wired
        # in terraform/modules/pipeline/main.tf's production Step Functions (FredEconomicData,
        # NaaimSentiment, AaiiSentiment, DividendData, StockSymbols), so this was purely a
        # local-backfill gap, not a production one. "dividends" is the one yfinance-backed
        # loader in this otherwise SEC/free-API pipeline - a single sequential yfinance
        # loader here doesn't reintroduce the parallel multi-loader yfinance IP-ban risk
        # documented for the "metrics" pipeline, but keep an eye on it if that changes.
        "constituents",
        "economic",
        "naaim",
        "aaii",
        "dividends",
    ],
}

# CRITICAL: Loader dependencies - some loaders must run before others
# Session 81/82 fix: enforce these dependencies to prevent silent data degradation
# CRITICAL FIX SESSION 86: Use shorthand names from PIPELINES/registry, not table names
# (bug found: "buy_sell_daily" != "buy_sell", "stock_scores" != "scores", etc.)
# SESSION 88 FIX: Added missing SEC-related dependencies to prevent cascading SEC failures
LOADER_DEPENDENCIES = {
    # financial_statements requires company_info first (SEC lookups need symbol CIK mapping)
    # FIX SESSION 89: Missing dependency was allowing cascades when SEC rate limits company_info
    "financial_statements": ["company_info"],
    # value_quality_growth reads valuations, analyst earnings, and financial_statements data
    # RE-ENABLED 2026-08-09: financial_statements was missing here even though the "metrics"
    # pipeline's own comment calls it a CRITICAL DEPENDENCY of value_quality_growth - the
    # dependency check silently never verified it, relying only on incidental list ordering
    # in PIPELINES["metrics"] to run it first.
    "value_quality_growth": ["financial_statements", "valuations", "analyst_earnings_estimates"],
    # Enhanced metrics layer depends on value_quality_growth base metrics
    "enhanced_quality_growth": ["value_quality_growth"],
    # sec_segment_metrics computes Herfindahl index / diversification from sec_segment_info -
    # terraform/modules/pipeline/main.tf documents this as a CRITICAL DEPENDENCY.
    "segment_metrics": ["segment_info"],
    # FIXED 2026-08-12: buy_sell requires fresh price and technical data for signals
    # FIX SESSION 86: Changed from "buy_sell_daily" (wrong) to "buy_sell" (correct shorthand)
    # SESSION 103 FIX: Also requires scores - buy_sell filters universe to only scored symbols
    "buy_sell": ["prices", "technical", "scores"],
    # scores requires value metrics to be available (for scoring algorithm)
    # FIX SESSION 86: Changed from "stock_scores" (wrong) to "scores" (correct shorthand)
    # SESSION 103 FIX: Also requires positioning and technical dependencies
    "scores": [
        "prices",
        "technical",
        "value_quality_growth",
        "enhanced_quality_growth",
        "positioning",
        "stability_metrics",
    ],
    # signal_quality requires buy_sell signals to exist before quality scoring
    # FIX SESSION 86: Changed from "buy_sell_daily" (wrong) to "buy_sell" (correct shorthand)
    "signal_quality": ["buy_sell"],
    # algo metrics depend on signals being generated first
    # FIX SESSION 86: Changed from "stock_scores" (wrong) to "scores" (correct shorthand)
    "algo": ["signal_quality", "scores"],
    # company_profile uses company metadata populated by company_info loader
    # FIXED 2026-08-12: Added missing dependency to prevent cascading failures
    # when SEC rate limiting blocks company_info
    "profile": ["company_info"],
    # SESSION 88 FIX: valuations depends on company_info for symbol and metadata lookups
    # (if company_info fails, valuations should be skipped rather than cascading failure)
    "valuations": ["company_info"],
    # earnings_sec requires company_info for CIK lookups (SESSION 89 FIX - missing dependency)
    "earnings_sec": ["company_info"],
    # insider_holdings requires company_info for shares_outstanding lookups (SESSION 90 FIX)
    # When company_info is stale/missing, insider holdings calculations use wrong denominators
    "insider_holdings": ["company_info"],
    # insider_velocity depends on insider_holdings for transaction history
    "insider_velocity": ["insider_holdings"],
    # SESSION 92 FIX: positioning_metrics reads company_info_sec shares_outstanding
    # Without this dependency, if company_info fails, positioning_metrics has missing data
    "positioning": ["company_info"],
    # SESSION 92 FIX: institutional_holdings_13f reads company_info_sec for symbol lookups
    "institutional": ["company_info"],
}


def _check_loader_dependencies(loader: str, completed_loaders: set[str]) -> bool:
    """Check if a loader's dependencies have completed.

    Args:
        loader: The loader name to check
        completed_loaders: Set of loader names that have already completed successfully

    Returns:
        True if all dependencies are met, False otherwise
    """
    dependencies = LOADER_DEPENDENCIES.get(loader, [])
    missing = [dep for dep in dependencies if dep not in completed_loaders]

    if missing:
        print(
            f"[LOCAL_SCHEDULER] ERROR: {loader} requires {missing} to run first, but they have not completed",
            file=sys.stderr,
        )
        return False
    return True


def run_pipeline(pipeline_name: str) -> int:  # noqa: C901
    """Run all loaders for a given pipeline."""
    loaders = PIPELINES.get(pipeline_name)
    if not loaders:
        print(f"ERROR: Unknown pipeline '{pipeline_name}'", file=sys.stderr)
        print(f"Valid pipelines: {', '.join(PIPELINES.keys())}", file=sys.stderr)
        return 1

    print(f"[LOCAL_SCHEDULER] Starting {pipeline_name} pipeline ({len(loaders)} loaders)...")

    # STALE-RUNNING REAPER: local dev has no equivalent of production's ECS-task-based
    # _kill_long_running_loaders (that makes real AWS ListTasks calls, which always fail
    # locally with no credentials - see orchestrator.py's "[OOM_PREVENTION] Could not
    # check/kill" warning). Without this, a crashed process or a scheduler still running
    # stale in-memory code from before a same-day timeout fix leaves data_loader_status
    # stuck at RUNNING indefinitely (see buy_sell_daily_stuck_running_74_hours_20260810,
    # where this exact auto-recovery was recommended but never implemented). Run it once
    # up front so this invocation starts from a clean bookkeeping slate.
    reaped = reap_stale_running_loaders()
    if reaped:
        print(f"[LOCAL_SCHEDULER] Reaped {len(reaped)} stale RUNNING loader(s): {', '.join(reaped)}")

    # SESSION 103 FIX: Auto-cleanup stale lock files before running loaders
    # Hung/crashed loaders don't delete their locks, causing subsequent invocations to block
    # indefinitely. SESSION 108 FIX: Reduce threshold from 30 min to 5 min - most loaders
    # complete in <5 min, so any lock older than 5 min is from a crashed/stuck process.
    try:
        import time as time_module

        lock_dir = Path(tempfile.gettempdir()) / "algo-locks"
        if lock_dir.exists():
            stale_lock_threshold_seconds = 5 * 60  # SESSION 108: 5 minutes (was 30)
            now = time_module.time()
            cleaned_locks = []
            for lock_file in lock_dir.glob("*.lock"):
                lock_age_seconds = now - lock_file.stat().st_mtime
                if lock_age_seconds > stale_lock_threshold_seconds:
                    lock_file.unlink()
                    cleaned_locks.append(lock_file.name)
            if cleaned_locks:
                print(
                    f"[LOCAL_SCHEDULER] Cleaned {len(cleaned_locks)} stale lock file(s): {', '.join(cleaned_locks)} "
                    f"(older than 5 min)"
                )
    except Exception as e:
        print(f"[LOCAL_SCHEDULER] WARNING: Could not clean stale locks: {e}", file=sys.stderr)

    repo_root = Path(__file__).parent.parent
    completed_loaders = set()  # Track completed loaders for dependency checking

    # CRITICAL FIX (SESSION 94): Import centralized timeout config to prevent mismatch-brittleness
    # SESSION 93 root cause: local_loader_scheduler had 75m for earnings_calendar while
    # phase1 retry had 45m, causing Friday timeouts to never recover by Monday. Now both
    # import from single source of truth (loaders/loader_timeout_config.py). This prevents
    # the exact mismatch that caused Monday cascades throughout Session 93.
    # (Note: LOADER_TIMEOUTS dict no longer used - instead call get_loader_timeout() for fail-fast validation)

    # BUG FOUND 2026-08-10 (live-reproduced): a single loader failure used to abort the
    # ENTIRE remaining pipeline (`return 1` below), even for loaders with zero declared
    # dependency on the one that failed - LOADER_DEPENDENCIES only lists 3 real dependency
    # edges (value_quality_growth/enhanced_quality_growth/segment_metrics); "buy_sell" isn't
    # in it at all. Live-reproduced: "scores" crashed on its own upstream-coverage data-
    # quality gate (value_metrics only 61.6% complete, an unrelated concurrent reload still
    # in progress), and "buy_sell" - positioned right after "scores" in the "signals"
    # pipeline purely by list order, with no real dependency on it - never even got attempted.
    # This is the root cause of buy_sell_daily's session-long staleness (see
    # buy_sell_daily_stuck_running_74_hours_20260810 and related memory entries chasing this
    # same symptom from the data side without finding this scheduler-side cause). Fixed to
    # skip only the failed loader and any loader that genuinely depends on it (still enforced
    # via _check_loader_dependencies below), not the whole rest of the pipeline.
    any_failed = False
    skipped_loaders = set()  # Track skipped loaders to skip their dependents

    for loader in loaders:
        # CRITICAL FIX (Session 81): Check loader dependencies before running
        # Prevents silent data degradation if a required upstream loader fails
        if not _check_loader_dependencies(loader, completed_loaders):
            # Check if dependency was skipped (doesn't exist in completed) or failed (in skipped)
            deps = LOADER_DEPENDENCIES.get(loader, [])
            missing = [dep for dep in deps if dep not in completed_loaders]
            if any(dep in skipped_loaders for dep in missing):
                print(
                    f"[LOCAL_SCHEDULER] SKIP {loader}: upstream loader(s) {missing} were skipped due to SEC issues",
                    file=sys.stderr,
                )
                skipped_loaders.add(loader)
                any_failed = True
                continue
            # CRITICAL FIX SESSION 102 #5: Track this skipped loader too
            # Previously we just did `continue` without adding to skipped_loaders,
            # causing cascading failures for downstream loaders that couldn't determine
            # WHY the upstream loader was missing (SEC rate limit vs crash).
            # Now we track it so downstream loaders know it was skipped intentionally.
            print(
                f"[LOCAL_SCHEDULER] SKIP {loader}: required upstream loader(s) {missing} did not complete",
                file=sys.stderr,
            )
            skipped_loaders.add(loader)
            any_failed = True
            continue

        # FIX 2026-08-12: Skip loaders with 3+ consecutive failures (need manual intervention)
        # Prevents broken loaders from cascading through the pipeline
        # SPECIAL CASE (Session 87): SEC loaders (company_info, earnings_sec, etc) hitting rate limits
        # should be skipped gracefully so dependents can proceed with cached data
        # SESSION 88 FIX: Detect SEC rate limiting earlier (2+ consecutive failures for SEC loaders)
        # and skip them before dependent loaders fail due to upstream unavailability
        try:
            from utils.db.connection import get_db_connection

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT consecutive_failures, error_message FROM data_loader_status WHERE table_name = %s",
                (loader,),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                failures, error_msg = row[0], row[1]
                if isinstance(failures, (int, float)):
                    failures_int = int(failures)
                    error_msg = error_msg or "(no error message)"
                    is_sec_issue = (
                        "rate limit" in error_msg.lower()
                        or "sec edgar" in error_msg.lower()
                        or "429" in error_msg.lower()
                    )

                    # SESSION 88: For SEC loaders, skip after just 2 failures (not 3+)
                    # SEC rate limiting is an external factor - retrying won't help once it starts
                    # For other loaders, require 3+ failures before skipping
                    should_skip = (is_sec_issue and failures_int >= 2) or (not is_sec_issue and failures_int >= 3)

                    if should_skip:
                        if is_sec_issue:
                            # SEC rate limiting - skip gracefully so dependents use cached data
                            print(
                                f"[LOCAL_SCHEDULER] SKIP {loader}: {failures_int} failures due to SEC rate limiting (429, too many requests) "
                                f"- proceeding with cached data. Error: {error_msg[:100]}",
                                file=sys.stderr,
                            )
                            skipped_loaders.add(loader)
                            any_failed = True
                        else:
                            # Non-SEC failure - needs manual intervention
                            print(
                                f"[LOCAL_SCHEDULER] SKIP {loader}: {failures_int} consecutive failures - needs manual fix. Error: {error_msg[:100]}",
                                file=sys.stderr,
                            )
                            skipped_loaders.add(loader)
                            any_failed = True
                        continue
        except Exception as e:
            print(f"[LOCAL_SCHEDULER] WARNING: Could not check {loader} failures: {e}", file=sys.stderr)

        # CRITICAL FIX (Session 97): Use get_loader_timeout() for fail-fast instead of .get() with silent default
        # Session 96 fixed the same bug in phase1_failsafe_retry.py but this code path was missed.
        # Silent .get(loader, 30*60) default allowed company_info_sec (180m) to silently truncate
        # to 30m if lookup failed, cascading failures to dependent loaders. Now raises if loader not registered.
        try:
            from loaders.loader_timeout_config import get_loader_timeout

            timeout = get_loader_timeout(loader)  # Fail-fast if not registered
        except RuntimeError:
            # Loader not registered - this is a configuration error that should be fixed,
            # not silently defaulted. But to avoid halting the entire pipeline on a single
            # registration gap, use a safe fallback and warn the user loudly.
            print(
                f"[LOCAL_SCHEDULER] CRITICAL: {loader} not registered in loader_timeout_config.py. "
                f"Using fallback 1800s but this MUST be fixed. See loader_timeout_config.py.",
                file=sys.stderr,
            )
            timeout = 30 * 60  # 30 min fallback - but this should never happen in production
        print(f"[LOCAL_SCHEDULER] Running {loader} loader (timeout: {timeout}s)...")
        try:
            # Convert shorthand name to filename (e.g., "prices" → "load_prices.py")
            loader_filename = normalize_loader_name(loader)
            env = os.environ.copy()
            # CRITICAL FIX 2026-08-10/13: loaders/runner.py enforces its OWN process-level watchdog
            # (LOADER_TIMEOUT env var, in seconds, via SIGALRM/os._exit(1)) completely
            # independent of this scheduler's own per-loader `timeout` above. A same-day fix
            # bumped LOADER_TIMEOUTS["enhanced_quality_growth"] to 150 min here, but that outer
            # subprocess.run() timeout never mattered - live-reproduced: the loader's own inner
            # watchdog fired first at exactly 120 min ("[TIMEOUT] Loader exceeded 120 minute
            # timeout. Exiting forcefully."), silently making the outer-timeout fix a no-op for
            # any loader whose real runtime falls between 120 min and its scheduler budget.
            # Propagate this loader's actual budget into the child so the two can never drift
            # apart again - the scheduler's LOADER_TIMEOUTS dict becomes the single source of
            # truth instead of two independently-maintained numbers.
            # CRITICAL FIX 2026-08-13: Pass LOADER_TIMEOUT in seconds (matching Terraform/runner.py)
            # not LOADER_TIMEOUT_MINUTES in minutes. This aligns local and production behavior.
            # CRITICAL FIX SESSION 102: Ensure LOADER_TIMEOUT is always set (never None/empty)
            # Empty or missing LOADER_TIMEOUT causes runner.py to fall back to 7200s (2h) default,
            # creating a timeout mismatch race condition. Always set it explicitly.
            loader_timeout_str = str(max(1, timeout))
            env["LOADER_TIMEOUT"] = loader_timeout_str
            if int(loader_timeout_str) != timeout:
                print(
                    f"[LOCAL_SCHEDULER] WARNING: LOADER_TIMEOUT str({timeout}) != int({loader_timeout_str})",
                    file=sys.stderr,
                )
            # ROOT-CAUSE FIX 2026-08-10: always invoke the loader module directly
            # (`python loaders/{file}.py`, exactly what terraform/modules/loaders/main.tf
            # runs in production), never scripts/run_loader.py's generic path.
            #
            # Previously only financial_statements/buy_sell/prices/trend_analysis/economic
            # were special-cased for direct invocation, and everything else fell through to
            # run_loader.py's generic OptimalLoader-class introspection path, which imports
            # the loader CLASS and calls .run() directly - it never reaches the module's own
            # main(). Each of those 5 was independently discovered and patched one at a time
            # ("Nth main()-bypass instance" commits) after main()-only logic silently never
            # ran locally: buy_sell's real completion thresholds, prices' essential-symbol
            # (SPY/QQQ/IWM/GLD/TLT/^VIX) merge, financial_statements' LOADER_STATEMENT_TYPE
            # fan-out, and trend_analysis/economic's plain function-based modules (no
            # OptimalLoader subclass at all, so the generic path couldn't even load them and
            # exited 1 immediately). A follow-up audit found the same bug class still live and
            # un-special-cased in load_technical_indicators.py (schema migrations + hang-
            # detection heartbeat, main()-only) and load_positioning_metrics.py (crash-safe
            # data_unavailable marking, main()-only) - patching those two in as a 6th and 7th
            # entry would just leave the next loader's main()-only logic as an 8th. Fixed at
            # the root instead: every loader now runs its real production entrypoint locally,
            # so there is no generic path left to silently diverge from production.
            if loader == "financial_statements":
                # load_financial_statements.py's main() fans LOADER_STATEMENT_TYPE="all" out
                # to all 6 statement/period combos via load_all_statements(); the class
                # constructor alone requires one specific combo to already be named.
                env["LOADER_STATEMENT_TYPE"] = "all"
            cmd = [sys.executable, f"loaders/{loader_filename}"]

            # CRITICAL FIX SESSION 102: Mark all output tables RUNNING BEFORE subprocess starts
            # Prevents NOT_STARTED stuck status when subprocess crashes before runner.py calls mark_running()
            # See root_cause_analysis: NOT_STARTED status never transitions if subprocess dies before mark_running()
            # SESSION 108 FIX: Fail-fast on pre-mark errors (don't proceed if DB update fails)
            # If we can't update the database, the subprocess shouldn't start either
            try:
                for table in all_tables(loader_filename):
                    LoaderStatusManager(table).mark_running()
                print(
                    f"[LOCAL_SCHEDULER] Pre-marked {loader} output tables as RUNNING (guard against early subprocess crash)"
                )
            except Exception as pre_mark_err:
                # SESSION 108 FIX: Don't silently proceed if pre-marking fails
                # A database issue here means the loader can't update status anyway
                print(
                    f"[LOCAL_SCHEDULER] CRITICAL: Could not pre-mark {loader_filename} tables as RUNNING: {pre_mark_err}. "
                    f"Database may be unavailable or tables missing. Aborting this loader. "
                    f"Status may need manual repair (run: python scripts/fix_loader_status_drift.py)",
                    file=sys.stderr,
                )
                _mark_loader_failed_after_crash(
                    loader_filename,
                    f"local_loader_scheduler: Failed to pre-mark RUNNING: {pre_mark_err}. Database issue or missing status row.",
                )
                any_failed = True
                continue

            # BUG FOUND 2026-08-11: subprocess.run() with no stdout/stderr capture meant a
            # crash only ever recorded a bare "exit code N" in data_loader_status.error_message
            # - the real traceback only existed in whatever terminal/log redirect happened to
            # be wrapping this scheduler invocation (if any), making a live-observed FAILED
            # row (e.g. company_info_sec: "subprocess exited with code 1") undiagnosable from
            # the DB alone. Switched to Popen with a tee'ing reader thread: output still
            # streams live to this process's own stdout exactly as before, but the last 40
            # lines are also kept and attached to the failure message on a non-zero exit.
            tail_lines: collections.deque[str] = collections.deque(maxlen=40)
            proc = subprocess.Popen(
                cmd,
                cwd=str(repo_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            def _stream_and_capture(pipe: IO[str], sink: "collections.deque[str]") -> None:
                for line in pipe:
                    sys.stdout.write(line)
                    sink.append(line.rstrip("\n"))
                pipe.close()

            assert proc.stdout is not None
            # SESSION 108 FIX: Non-daemon thread ensures we capture all output before using tail_lines
            # Daemon threads may be killed before reader finishes, losing diagnostic info
            reader_thread = threading.Thread(target=_stream_and_capture, args=(proc.stdout, tail_lines), daemon=False)
            reader_thread.start()
            scheduler_timeout = int(timeout * 1.1)
            scheduler_timeout_str = f"{scheduler_timeout}s ({scheduler_timeout // 60}m {scheduler_timeout % 60}s)"
            # SESSION 117 CRITICAL FIX: Stall timeout must be PER-LOADER, not hardcoded
            # Reason: Loaders with long initialization periods (symbol fetch, DB setup, request prep)
            # take 10-30+ minutes to reach >0% completion BEFORE any progress is made.
            # Previous hardcoded 300s (5 min) threshold was killing loaders like:
            # - analyst_sentiment (120m configured) during initialization - killed after 5+ min at 0%
            # - company_info_sec (540m configured) during initialization - killed after 5+ min at 0%
            # This caused cascading Monday failures: Friday killed loader → Sat-Sun status FAILED → Monday retry fails immediately
            # Fix: Scale stall timeout to loader's configured timeout
            # Formula: min(1800, max(900, timeout / 5)) = allow 20% of configured timeout for initialization
            # Examples: 30m loader gets 6min, 120m gets 24min, 540m gets capped at 30min (1800s)
            # Rationale: Even yfinance/SEC rate-limited loaders shouldn't take >30min of pure initialization
            stall_timeout = min(1800, max(900, int(timeout / 5)))  # Allow 20% of timeout, clamped 15-30 min
            progress_check_interval = 30  # Poll progress every 30 seconds

            # CRITICAL SESSION 106 FIX: Poll the subprocess and monitor progress
            # instead of blocking on wait(). This detects hung loaders at 0% within 5 min,
            # vs waiting 36 hours for the reaper.
            start_time = time.time()
            returncode = None
            stalled = False

            try:
                while True:
                    try:
                        returncode = proc.poll()  # Non-blocking check
                        if returncode is not None:
                            break  # Process finished

                        elapsed = time.time() - start_time
                        if elapsed > scheduler_timeout:
                            raise subprocess.TimeoutExpired(cmd, scheduler_timeout)

                        # Check progress periodically
                        if elapsed > 0 and int(elapsed) % progress_check_interval == 0:
                            if not _monitor_loader_progress(
                                loader_filename, poll_interval_sec=1, max_stall_sec=stall_timeout
                            ):
                                print(
                                    f"[LOCAL_SCHEDULER] {loader}: Process appears hung at 0% for {stall_timeout}s. Killing.",
                                    file=sys.stderr,
                                )
                                proc.kill()
                                stalled = True
                                break

                        time.sleep(1)
                    except (KeyboardInterrupt, SystemExit):
                        proc.kill()
                        raise

            except subprocess.TimeoutExpired:
                proc.kill()
                returncode = proc.wait()
                reader_thread.join(timeout=30)  # SESSION 108: Wait up to 30s for output capture
                lock_dir = Path(tempfile.gettempdir()) / "algo-locks"
                print(
                    f"[LOCAL_SCHEDULER] ERROR: {loader} loader timed out after {scheduler_timeout_str} "
                    f"(configured {timeout}s + 10% safety margin). "
                    f"Likely blocked by stale lock. Clean with: rm {lock_dir}/*.lock - "
                    f"continuing with remaining independent loaders",
                    file=sys.stderr,
                )
                tail = "\n".join(tail_lines)
                _mark_loader_failed_after_crash(
                    loader_filename,
                    f"local_loader_scheduler: timed out after {scheduler_timeout_str}. Last output:\n{tail}",
                )
                any_failed = True
                continue

            if stalled:
                proc.wait()
                reader_thread.join(timeout=30)  # SESSION 108: Wait up to 30s for output capture
                tail = "\n".join(tail_lines)
                _mark_loader_failed_after_crash(
                    loader_filename,
                    f"local_loader_scheduler: killed due to 0%% stall for >{stall_timeout}s. Last output:\n{tail}",
                )
                any_failed = True
                continue

            reader_thread.join(timeout=30)  # SESSION 108: Wait up to 30s for output capture to complete
            if returncode != 0:
                print(
                    f"[LOCAL_SCHEDULER] WARNING: {loader} loader failed (exit code {returncode}) - "
                    f"continuing with remaining independent loaders",
                    file=sys.stderr,
                )
                tail = "\n".join(tail_lines)
                _mark_loader_failed_after_crash(
                    loader_filename,
                    f"local_loader_scheduler: subprocess exited with code {returncode}. Last output:\n{tail}",
                )
                any_failed = True
                continue
            # Mark loader as completed for dependency checking of subsequent loaders
            completed_loaders.add(loader)
        except subprocess.TimeoutExpired:
            print(
                f"[LOCAL_SCHEDULER] ERROR: {loader} loader timed out after {timeout}s. "
                f"Likely blocked by stale lock. Run: rm -f /tmp/algo-locks/*.lock - "
                f"continuing with remaining independent loaders",
                file=sys.stderr,
            )
            _mark_loader_failed_after_crash(loader_filename, f"local_loader_scheduler: timed out after {timeout}s")
            any_failed = True
            continue

    if any_failed and not skipped_loaders:
        # Hard failures (not just SEC skips) - return error
        print(f"[LOCAL_SCHEDULER] {pipeline_name} pipeline completed with 1+ loader failure(s) - see warnings above")
        return 1
    if skipped_loaders:
        # SEC loaders were skipped gracefully - pipeline continues with cached data
        print(
            f"[LOCAL_SCHEDULER] {pipeline_name} pipeline completed with {len(skipped_loaders)} loader(s) skipped due to SEC rate limiting - continuing with cached data"
        )
        return 0  # Graceful degradation - not a critical failure
    print(f"[LOCAL_SCHEDULER] {pipeline_name} pipeline completed successfully")
    return 0


def _clean_all_locks() -> int:
    """Clean all stale lock files (SESSION 113 FIX: emergency manual override).

    Used when loaders are cascading FAILED due to stale locks from crashed processes.
    Removes all lock files older than 30 seconds (most loaders complete in <5min).
    """
    try:
        import time as time_module

        lock_dir = Path(tempfile.gettempdir()) / "algo-locks"
        if not lock_dir.exists():
            print("[LOCAL_SCHEDULER] No lock directory found - nothing to clean")
            return 0

        stale_threshold_seconds = 30  # Any lock >30s old is suspicious for normal operation
        now = time_module.time()
        cleaned_locks = []

        for lock_file in lock_dir.glob("*.lock"):
            lock_age_seconds = now - lock_file.stat().st_mtime
            if lock_age_seconds > stale_threshold_seconds:
                try:
                    lock_file.unlink()
                    cleaned_locks.append(lock_file.name)
                except Exception as e:
                    print(
                        f"[LOCAL_SCHEDULER] WARNING: Could not delete {lock_file.name}: {e}",
                        file=sys.stderr,
                    )

        if cleaned_locks:
            print(
                f"[LOCAL_SCHEDULER] Cleaned {len(cleaned_locks)} lock file(s) "
                f"(older than 30s): {', '.join(cleaned_locks)}"
            )
            return 0
        else:
            print("[LOCAL_SCHEDULER] No stale locks found (all <30s old)")
            return 0
    except Exception as e:
        print(f"[LOCAL_SCHEDULER] ERROR during lock cleanup: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Local loader scheduler")
    parser.add_argument(
        "--now",
        type=str,
        help="Run this pipeline immediately (morning|metrics|signals)",
    )
    parser.add_argument(
        "--clean-locks",
        action="store_true",
        help="SESSION 113 FIX: Remove all stale lock files (emergency override for cascading failures)",
    )
    args = parser.parse_args()

    # Handle --clean-locks flag
    if args.clean_locks:
        return _clean_all_locks()

    # Require --now if not cleaning locks
    if not args.now:
        parser.error("Either --now or --clean-locks is required")
        return 1

    # CRITICAL: Prevent concurrent scheduler invocations to avoid redundant loader runs
    # A single global scheduler lock ensures only one instance can run at a time
    scheduler_lock = Path(tempfile.gettempdir()) / "algo-scheduler.lock"
    if scheduler_lock.exists():
        # Check if lock is stale (> 12 hours, conservatively larger than max pipeline runtime ~4h)
        lock_age = time.time() - scheduler_lock.stat().st_mtime
        if lock_age < 43200:  # 12 hours in seconds
            print(
                f"[LOCAL_SCHEDULER] ERROR: Another scheduler instance is already running "
                f"(lock held for {lock_age:.0f}s). Cannot start duplicate run. "
                f"Wait for the existing instance to complete or manually remove {scheduler_lock} if stale.",
                file=sys.stderr,
            )
            return 1
        else:
            print(f"[LOCAL_SCHEDULER] Cleaning stale scheduler lock (age: {lock_age:.0f}s)")
            scheduler_lock.unlink()

    try:
        # Create lock before running pipeline
        scheduler_lock.touch()
        return run_pipeline(args.now)
    finally:
        # Always clean up lock on exit (success or failure)
        try:
            scheduler_lock.unlink()
        except Exception as e:
            print(f"[LOCAL_SCHEDULER] WARNING: Could not remove scheduler lock: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
