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
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from loaders.loader_registry import all_tables, normalize_loader_name
from utils.db.context import DatabaseContext
from utils.db.local_file_lock import FileLockManager
from utils.dotenv_loader import load_env_local
from utils.loaders.status_manager import LoaderStatusManager, reap_stale_running_loaders

logger = logging.getLogger(__name__)


class _Tee:
    """Mirrors writes to an underlying stream and appends them to a log file.

    Line-buffered (flush after every write) so output survives an abrupt kill of this
    process, matching the same durability reasoning run_pipeline()'s per-loader
    _stream_and_capture already uses for subprocess output.
    """

    def __init__(self, stream: IO[str], log_path: Path) -> None:
        self._stream = stream
        self._file = open(log_path, "a", encoding="utf-8")

    def write(self, data: str) -> int:
        self._file.write(data)
        self._file.flush()
        return self._stream.write(data)

    def flush(self) -> None:
        self._file.flush()
        self._stream.flush()


# GAP FOUND 2026-08-16: this entry point never loaded .env.local - only
# scripts/run_local_orchestrator.py and algo/orchestration/orchestrator.py do (both via
# this same utils.dotenv_loader import). Every loader subprocess this script spawns
# inherits env = os.environ.copy() from THIS process, so any .env.local-only setting
# (e.g. API_REQUEST_TIMEOUT_SECONDS, PRICE_DATA_SOURCE) silently never reached
# scheduler-driven local backfills - confirmed live: a fresh shell here had DB_HOST/
# DB_NAME already set (baked in some other way) but not LOCAL_MODE, PRICE_DATA_SOURCE,
# or a newly-added API_REQUEST_TIMEOUT_SECONDS=30 fix, since nothing in this file's own
# import chain ever read the .env.local file itself. override=False in load_env_local()
# means this can't clobber the os.environ["LOCAL_MODE"]/["ENVIRONMENT"] set below, or any
# real env var already set - it only fills in gaps, and runs before those hardcoded
# lines so this script's own required overrides still always win.
load_env_local()

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
# BUG FOUND 2026-08-10 (via [[analyst_loaders_reloaded_and_local_parallelism_ban_20260810]]):
# this used to default to "4" for "local dev optimization". Live-reproduced: LOADER_PARALLELISM=4
# self-triggered the yfinance shared-IP circuit breaker from a single local machine, causing
# 84%+ false-failure rates on analyst loaders (same fix applied to scripts/run_loader.py).
# Default to 1 to match the value actually verified safe.
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "1"

# LIVE BUG FOUND 2026-08-17: insider_transaction_velocity killed at exactly the generic
# formula's 900s floor ("0% stall for >900s") while genuinely mid-download, not hung. Unlike
# company_info_sec (fixed 2026-08-16 by shrinking LOADER_CHUNK_SIZE so a partial flush lands
# inside the watchdog window), this loader has no early-flush option:
# CachedForm345Aggregator.get_velocity_metrics(wait_for_download=True) blocks on a single
# all-or-nothing threading.Event that only fires after all 12 quarters of SEC Form 3/4/5 bulk
# data finish downloading sequentially (no on-disk cache -
# utils/external/sec_form345_transaction_velocity_cached.py re-downloads every run), so zero
# DB-visible progress is possible before that completes. The loader itself budgets up to 1080s
# for this (CachedForm345Aggregator(..., timeout_seconds=1080) in
# load_insider_transaction_velocity.py) - live-confirmed today the download alone was still
# only 9/12 quarters in at the 900s mark. The generic per-loader formula's 900s floor is
# stricter than the loader's own designed download budget, so it was structurally guaranteed
# to kill this loader before its first possible DB write, every run.
STALL_TIMEOUT_FLOOR_OVERRIDES = {
    "insider_transaction_velocity": 1500,  # 1080s download budget + 420s margin
}


def _stall_timeout_for(loader: str, timeout: int) -> int:
    """SESSION 117: scale the stall-kill threshold to 20% of a loader's configured timeout,
    clamped to 15-30min, so loaders with long initialization periods aren't false-killed at a
    hardcoded 5min. STALL_TIMEOUT_FLOOR_OVERRIDES raises that floor further for specific
    loaders whose init phase is known to structurally exceed even the 15min default floor -
    see the module-level comment above."""
    stall_timeout = min(1800, max(900, int(timeout / 5)))
    return max(stall_timeout, STALL_TIMEOUT_FLOOR_OVERRIDES.get(loader, 0))


def _monitor_loader_progress(
    loader_filename: str,
    proc: "subprocess.Popen[str]",
    deadline: float,
    poll_interval_sec: int = 30,
    max_stall_sec: int = 300,
) -> bool:
    """Monitor loader progress while subprocess is running. Kill if stuck at 0% for too long.

    ROOT-CAUSE FIX 2026-08-16: this function used to take only `loader_filename` and never
    checked the actual subprocess at all - its own `while True` loop only ever returned via
    the stall-detected `return False` (or the rare "table doesn't exist yet" early-outs), with
    no path for "the loader actually finished". Since the caller's outer poll loop only
    re-checks `proc.poll()`/its own scheduler_timeout AFTER this call returns, that outer
    supervision was effectively dead code for the entire runtime of any loader past the first
    30s tick - this function silently became the only thing deciding when the loader run
    ended, and it could only ever decide "stalled", never "done". Live-confirmed 2026-08-16:
    company_info_sec's log shows its last write at 11:19:55 (11.5 min into the run) but
    data_loader_status wasn't marked FAILED until 16:19:56 - 5 hours later, not the intended
    30-minute stall_timeout - because something (most likely DB pool contention inside this
    loop's own polling queries) kept the inner loop from ever reaching its stall check cleanly,
    and there was no independent process-exit or deadline check to bound the damage. Now checks
    `proc.poll()` every tick (returns True immediately so the caller's own loop reads the real
    exit code) and bails past `deadline` (returns True so the caller's own scheduler_timeout
    enforcement can fire), so a genuinely finished or genuinely runaway process is never
    mistaken for - or masked by - a stall.

    CRITICAL SESSION 106 FIX: Detect hung loaders during execution, not just after failure.
    Previously, a loader could hang at 0% for 27+ minutes while the orchestrator waited,
    and only the reaper (36-hour timeout) would eventually catch it. This function polls
    every poll_interval_sec and kills the process if completion_pct hasn't changed in
    max_stall_sec seconds.

    FALSE-POSITIVE FIX (2026-08-16): completion_pct is only ever written once, at the very
    end of OptimalLoader._update_final_status() - confirmed via repo-wide grep, only 2 of
    ~40 OptimalLoader subclasses (load_technical_indicators.py,
    load_value_quality_growth_metrics.py) call update_progress() mid-run. Every other
    loader's completion_pct sits frozen at 0 (or its pre-run value) for the loader's ENTIRE
    duration, so this watchdog's "stuck at 0% for max_stall_sec" check was true for those
    loaders even while they were actively working. Live-confirmed 2026-08-16:
    earnings_calendar got killed with "hung at 0% for 1440s" while its own table's
    MAX(updated_at) matched the kill timestamp almost exactly - real per-symbol progress the
    whole time, just never reflected in completion_pct. Added the primary table's own row
    count as a second liveness signal (increases as an event-log-style loader like
    earnings_calendar writes rows, even for symbols with no data - see its
    `_unavailable_record` marker rows).

    SECOND FALSE-POSITIVE FIX (2026-08-16): row count also fails to move for upsert-style
    loaders keyed by symbol (e.g. company_info_sec, PRIMARY KEY (symbol)) once every symbol
    already has a row - every write is an UPDATE, not an INSERT, so COUNT(*) stays flat for
    the loader's entire run just like completion_pct. Live-confirmed 2026-08-16:
    company_info_sec was killed at the 30-minute stall_timeout while its log showed real
    per-symbol SEC EDGAR progress (100/4922 at +76s, 200/4922 at +150s - a real ~60min total
    runtime, more than double the 30min clamp) and company_info_sec's row count sat at a
    static 5529 the entire time (all symbols already had rows from a prior run). Now also
    tracks MAX(updated_at) on the primary table as a third liveness signal, when that column
    exists - catches UPDATE-driven progress that neither completion_pct nor COUNT(*) can see.
    Only calls it a real stall if ALL signals that exist for this table are flat for
    max_stall_sec - preserves detection of a genuinely hung process (nothing written
    anywhere) without false-killing one that's writing/updating rows but not calling
    update_progress().

    Args:
        loader_filename: e.g., "load_prices.py"
        proc: the running subprocess.Popen - polled every tick so a real process exit is
            never mistaken for a stall
        deadline: time.time() value past which this call gives up and returns True, handing
            control back to the caller's own scheduler_timeout enforcement
        poll_interval_sec: How often to check progress (default 30s)
        max_stall_sec: Kill if stuck >N seconds without progress (default 300s = 5 min)

    Returns:
        True if the process exited, the deadline passed, or the loader is still healthy;
        False only when a genuine stall was detected and the caller should kill the process
    """
    try:
        tables = all_tables(loader_filename)
        if not tables:
            return True  # No tables to monitor, assume healthy

        primary_table = tables[0]
        last_pct = None
        last_pct_time = time.time()
        last_row_count = None
        last_row_count_time = time.time()
        last_max_updated = None
        last_max_updated_time = time.time()

        has_updated_at = False
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = 'updated_at'",
                    (primary_table,),
                )
                has_updated_at = cur.fetchone() is not None
        except Exception:
            has_updated_at = False  # Can't confirm the column - skip this signal, not fatal

        while True:
            time.sleep(poll_interval_sec)
            try:
                # Real process exit / deadline checks come before anything DB-related so they
                # can't be starved by DB pool contention or a slow query - see ROOT-CAUSE FIX
                # note above. Returning True here just hands control back to the caller's own
                # `while True` loop, which re-checks proc.poll()/elapsed on its very next
                # iteration. Kept inside this try/except like every other check in this loop -
                # a transient error here should be tolerated, not treated as "definitely done",
                # same "monitor errors shouldn't kill the loader" policy as the rest of the loop.
                if proc.poll() is not None:
                    return True

                now = time.time()
                if now >= deadline:
                    return True

                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT completion_pct, last_updated FROM data_loader_status WHERE table_name = %s",
                        (primary_table,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return True  # Table doesn't exist yet, assume OK

                    current_pct, _last_updated = row

                    # Check if progress has changed
                    if current_pct is not None and current_pct != last_pct:
                        last_pct = current_pct
                        last_pct_time = now
                        if current_pct > 0:
                            # Making progress, reset stall timer
                            continue

                    # Secondary liveness signal: has the primary table itself grown?
                    # table_name here always comes from all_tables() (loader_registry.py's
                    # static registry), never user input - same trust convention already
                    # used for dynamic table names elsewhere in this file.
                    cur.execute(f"SELECT COUNT(*) FROM {primary_table}")
                    row_count_result = cur.fetchone()
                    current_row_count = row_count_result[0] if row_count_result else None
                    if current_row_count is not None and current_row_count != last_row_count:
                        last_row_count = current_row_count
                        last_row_count_time = now

                    # Tertiary liveness signal: for upsert-style loaders (symbol-keyed
                    # tables where every row already exists), COUNT(*) never moves either -
                    # MAX(updated_at) catches UPDATE-driven progress that neither of the
                    # above can see.
                    if has_updated_at:
                        cur.execute(f"SELECT MAX(updated_at) FROM {primary_table}")
                        max_updated_result = cur.fetchone()
                        current_max_updated = max_updated_result[0] if max_updated_result else None
                        if current_max_updated is not None and current_max_updated != last_max_updated:
                            last_max_updated = current_max_updated
                            last_max_updated_time = now

                    # Check stall condition - only a real stall if NO signal that exists for
                    # this table moved
                    stall_duration = now - last_pct_time
                    row_stall_duration = now - last_row_count_time
                    updated_at_stall_duration = now - last_max_updated_time
                    is_stalled = (
                        stall_duration > max_stall_sec
                        and row_stall_duration > max_stall_sec
                        and (last_pct is None or last_pct <= 0.0)
                        and (not has_updated_at or updated_at_stall_duration > max_stall_sec)
                    )
                    if is_stalled:
                        print(
                            f"[PROGRESS_MONITOR] {loader_filename}: STALLED at {last_pct or 0}% "
                            f"for {stall_duration:.0f}s (>{max_stall_sec}s threshold), "
                            f"{primary_table} row count also unchanged for {row_stall_duration:.0f}s"
                            + (
                                f", updated_at also unchanged for {updated_at_stall_duration:.0f}s. "
                                if has_updated_at
                                else ". "
                            )
                            + "Will signal process termination.",
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
        # local-backfill gap, not a production one.
        # CORRECTED 2026-08-17: this comment used to claim "dividends" is the one
        # yfinance-backed loader in this pipeline - false. load_dividend_data.py has always
        # been SEC EDGAR-only (XBRL + 8-K Item 2.02 dividend extraction), confirmed via
        # `git log --follow` back to its creation - never a yfinance import. In fact NONE of
        # this "reference" pipeline's loaders touch yfinance - every one is SEC EDGAR, FRED,
        # FINRA, or an official NASDAQ/NYSE listing feed (constituents' S&P-500-membership
        # flag is the one Wikipedia-sourced exception - no free official source publishes
        # S&P Dow Jones Indices' proprietary membership list, see this loader's own comment).
        # The yfinance-dependent analyst loaders (analyst_upgrades/analyst_sentiment/
        # analyst_earnings_estimates - consensus data with no free official replacement) live
        # in the separate "metrics" pipeline above, not here.
        "constituents",
        "economic",
        "naaim",
        "aaii",
        "dividends",
    ],
}

# ADDED 2026-08-17: recovery from a mass-failure (e.g. a scheduler parent process killed
# mid-run, orphaning tables across all 4 pipelines simultaneously - see
# mass_phantom_running_05_32_23 incident) previously required a human to hand-launch a
# separate polling watcher script per affected pipeline name. That's exactly how signals
# (stock_scores, stability_metrics, buy_sell_daily, signal_quality_scores) sat FAILED for 8+
# hours after one such incident: watchers got started for metrics/reference/morning but
# nobody remembered signals, and it had no active retry at all. `--now all` runs every
# pipeline in one invocation/one lock acquisition so recovery is one command, not N
# separately-tracked scripts where one can silently get forgotten. Order follows the
# documented dependency chain (morning -> metrics -> signals); reference has no ordering
# dependency on the others so it runs last.
ALL_PIPELINES_ORDER = ["morning", "metrics", "signals", "reference"]

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


def _check_loader_dependencies(
    loader: str,
    completed_loaders: set[str],
    own_pipeline_loaders: set[str],
    run_scope: set[str] | None = None,
) -> bool:
    """Check if a loader's dependencies have completed.

    Args:
        loader: The loader name to check
        completed_loaders: Set of loader names that have already completed successfully
        own_pipeline_loaders: ADDED 2026-08-17: every loader declared in PIPELINES[this
            pipeline] (the full roster, independent of --loaders scoping). A dependency
            outside this set lives in an entirely DIFFERENT pipeline - e.g. "scores" in
            PIPELINES["signals"] depends on "value_quality_growth"/"enhanced_quality_growth"/
            "positioning"/"stability_metrics", all of which only exist in PIPELINES["metrics"].
            completed_loaders starts empty on every run_pipeline() call and only ever gains
            entries from loaders THIS invocation executes, so a cross-pipeline dependency can
            NEVER appear in it - not for a standalone `--now signals`, and not even for
            `--now all` (each pipeline in ALL_PIPELINES_ORDER gets its own run_pipeline() call
            with its own fresh completed_loaders). Live-reproduced 2026-08-17: a `--now signals`
            run hard-failed scores/buy_sell/signal_quality/algo on this exact gate minutes after
            a `metrics` run had freshly completed value_quality_growth/enhanced_quality_growth/
            positioning/stability_metrics in a separate process - this is the root cause of
            stock_scores/signal_quality_scores sitting FAILED for days while their actual
            upstream data was hours-fresh. Treat cross-pipeline dependencies as always
            assumed-fresh (trust DB state) - the exact same trust model `run_scope` below
            already applies to deliberately-excluded --loaders, just unconditional here since
            these deps could never be satisfied in-process regardless of --loaders. Same-
            pipeline dependencies (e.g. enhanced_quality_growth needing value_quality_growth
            within one "metrics" run) keep full same-run enforcement - only the pipeline split
            itself is exempted, not genuine same-run ordering.
        run_scope: ADDED 2026-08-17 for --loaders: the set of loaders actually included in
            this invocation (None means "the whole pipeline" - normal full-run behavior,
            unchanged). A dependency that isn't in run_scope was deliberately excluded by
            the operator (e.g. `--now metrics --loaders positioning,stability_metrics` to
            skip company_info/financial_statements because they're fresh from a prior run
            or already being refreshed by a concurrent scheduler instance) - treat it as
            satisfied by existing DB state rather than failing the dependent loader, since
            requiring every transitive dependency defeats the entire point of a scoped
            subset run.

    Returns:
        True if all dependencies are met, False otherwise
    """
    dependencies = LOADER_DEPENDENCIES.get(loader, [])
    same_pipeline_deps = [dep for dep in dependencies if dep in own_pipeline_loaders]
    cross_pipeline_deps = [dep for dep in dependencies if dep not in own_pipeline_loaders]

    missing = [
        dep for dep in same_pipeline_deps if dep not in completed_loaders and (run_scope is None or dep in run_scope)
    ]
    assumed_fresh = [dep for dep in cross_pipeline_deps if dep not in completed_loaders] + [
        dep
        for dep in same_pipeline_deps
        if dep not in completed_loaders and run_scope is not None and dep not in run_scope
    ]
    if assumed_fresh:
        print(
            f"[LOCAL_SCHEDULER] {loader}: assuming upstream {assumed_fresh} is already fresh "
            f"(cross-pipeline or excluded from this --loaders run, not re-checked)"
        )

    if missing:
        print(
            f"[LOCAL_SCHEDULER] ERROR: {loader} requires {missing} to run first, but they have not completed",
            file=sys.stderr,
        )
        return False
    return True


def _cleanup_stale_lock_files() -> None:
    """Auto-cleanup stale lock files before running loaders (SESSION 103 FIX).

    Hung/crashed loaders don't delete their locks, causing subsequent invocations to block
    indefinitely.

    BUG FIX (2026-08-17): SESSION 108's flat 5-minute file-age threshold reimplemented, in a
    second unpatched location, the exact bug already fixed once in
    utils/db/local_file_lock.py's FileLockManager (see that file's _cleanup_expired_locks
    docstring, commit 676c6c949): per-loader lock TTLs derive from real SLA timeouts (up to
    1440min for prices, 540min for company_info_sec - loaders/loader_timeout_config.py), so
    any lock older than 5 minutes but still legitimately held had it stolen out from under
    the live loader. Live-caught 2026-08-17: this exact sweep, run unconditionally on every
    pipeline startup, deleted sec_segment_info.lock/current_reports_8k.lock/
    dividend_data.lock/insider_transaction_velocity.lock out from under the `reference`
    pipeline (PID 29036) while it was actively writing sec_segment_info - a `signals`
    pipeline startup has no business touching `reference`'s locks at all, since the two now
    run concurrently under separate scheduler locks (see _lock_paths_for_pipeline). Fix:
    delegate to FileLockManager.cleanup_expired_locks(), which checks each lock's own
    recorded expiry first and only falls back to file age for locks whose content can't be
    parsed - instead of a third from-scratch reimplementation of the same cleanup logic.
    """
    try:
        deleted_count = FileLockManager(enable_auto_cleanup=False).cleanup_expired_locks()
        if deleted_count:
            print(f"[LOCAL_SCHEDULER] Cleaned {deleted_count} expired lock file(s) (content-based TTL)")
    except Exception as e:
        print(f"[LOCAL_SCHEDULER] WARNING: Could not clean stale locks: {e}", file=sys.stderr)


def run_pipeline(pipeline_name: str, loader_filter: set[str] | None = None) -> int:  # noqa: C901
    """Run all loaders for a given pipeline.

    Args:
        loader_filter: ADDED 2026-08-17 (--loaders flag) - if given, only run the named
            loaders (still in the pipeline's declared order), skipping the rest without
            treating them as failed. Lets an operator backfill just what's needed (e.g.
            positioning/stability_metrics) instead of an all-or-nothing multi-hour run,
            without bypassing the scheduler (see feedback_always_use_pipeline_scheduler_for_backfills
            - the point is to avoid direct loader invocation, not to force full-pipeline-or-nothing).
    """
    loaders = PIPELINES.get(pipeline_name)
    if not loaders:
        print(f"ERROR: Unknown pipeline '{pipeline_name}'", file=sys.stderr)
        print(f"Valid pipelines: {', '.join(PIPELINES.keys())}", file=sys.stderr)
        return 1

    # Captured before loader_filter narrows `loaders` below - see _check_loader_dependencies'
    # own_pipeline_loaders docstring for why this must be the full declared roster.
    own_pipeline_loaders = set(loaders)

    if loader_filter is not None:
        unknown = loader_filter - set(loaders)
        if unknown:
            print(
                f"ERROR: --loaders {sorted(unknown)} not in '{pipeline_name}' pipeline. "
                f"Valid loaders for {pipeline_name}: {', '.join(loaders)}",
                file=sys.stderr,
            )
            return 1
        loaders = [loader for loader in loaders if loader in loader_filter]

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

    _cleanup_stale_lock_files()

    repo_root = Path(__file__).parent.parent
    completed_loaders: set[str] = set()  # Track completed loaders for dependency checking

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
    skipped_loaders = set()  # Track skipped loaders to skip their dependents
    # ROOT-CAUSE FIX 2026-08-16: `skipped_loaders` was used for BOTH true graceful SEC-rate-
    # limit skips AND every hard failure that has a downstream dependent (crashes, stalls,
    # timeouts, non-SEC 3+-failure skips all land a dependent in `skipped_loaders` too via the
    # cascade branch below). The final return-code check below only tested "is skipped_loaders
    # non-empty", so ANY real crash with so much as one dependent silently returned 0 - live-
    # reproduced: a synthetic non-SEC failure on a loader with a dependent produced
    # "pipeline completed with 1 loader(s) skipped due to SEC rate limiting" and exit code 0,
    # even though nothing was actually SEC-related. `graceful_skips` now tracks ONLY loaders
    # confirmed skipped for a real SEC/rate-limit reason (or cascaded purely from one), so the
    # exit code can't be laundered through an unrelated downstream skip.
    graceful_skips = set()
    hard_failure = False

    for loader in loaders:
        # CRITICAL FIX (Session 81): Check loader dependencies before running
        # Prevents silent data degradation if a required upstream loader fails
        if not _check_loader_dependencies(loader, completed_loaders, own_pipeline_loaders, run_scope=loader_filter):
            # Check if dependency was skipped (doesn't exist in completed) or failed (in skipped)
            # Scoped to same-pipeline deps only - cross-pipeline deps are never the reason
            # _check_loader_dependencies returned False (see its own docstring), so including
            # them here would misleadingly imply they're still required.
            deps = [dep for dep in LOADER_DEPENDENCIES.get(loader, []) if dep in own_pipeline_loaders]
            missing = [dep for dep in deps if dep not in completed_loaders]
            missing_skipped = [dep for dep in missing if dep in skipped_loaders]
            if missing_skipped:
                # Only a graceful cascade if EVERY missing-and-skipped dependency was itself
                # a graceful (SEC) skip - one hard-failed dependency makes this a hard cascade.
                if all(dep in graceful_skips for dep in missing_skipped):
                    print(
                        f"[LOCAL_SCHEDULER] SKIP {loader}: upstream loader(s) {missing} were skipped due to SEC issues",
                        file=sys.stderr,
                    )
                    skipped_loaders.add(loader)
                    graceful_skips.add(loader)
                else:
                    print(
                        f"[LOCAL_SCHEDULER] SKIP {loader}: upstream loader(s) {missing} were skipped due to a "
                        f"non-SEC failure",
                        file=sys.stderr,
                    )
                    skipped_loaders.add(loader)
                    hard_failure = True
                continue
            # CRITICAL FIX SESSION 102 #5: Track this skipped loader too
            # Previously we just did `continue` without adding to skipped_loaders,
            # causing cascading failures for downstream loaders that couldn't determine
            # WHY the upstream loader was missing (SEC rate limit vs crash).
            # Now we track it so downstream loaders know it was skipped intentionally.
            # A dependency that neither completed nor was ever marked skipped means it flat-out
            # failed (crashed/timed out/stalled) without going through the skip bookkeeping -
            # treat conservatively as a hard failure rather than assume graceful degradation.
            print(
                f"[LOCAL_SCHEDULER] SKIP {loader}: required upstream loader(s) {missing} did not complete",
                file=sys.stderr,
            )
            skipped_loaders.add(loader)
            hard_failure = True
            continue

        # FIX 2026-08-12: Skip loaders with 3+ consecutive failures (need manual intervention)
        # Prevents broken loaders from cascading through the pipeline
        # SPECIAL CASE (Session 87): SEC loaders (company_info, earnings_sec, etc) hitting rate limits
        # should be skipped gracefully so dependents can proceed with cached data
        # SESSION 88 FIX: Detect SEC rate limiting earlier (2+ consecutive failures for SEC loaders)
        # and skip them before dependent loaders fail due to upstream unavailability
        try:
            from utils.db.connection import get_db_connection

            # BUG FIX 2026-08-17: this queried data_loader_status.table_name using `loader`
            # (the PIPELINES shorthand, e.g. "company_info", "financial_statements") directly.
            # But table_name stores the loader's real output table(s) (e.g. "company_info_sec",
            # "annual_income_statement"), which only coincidentally equals the shorthand for 4 of
            # 35 registered loaders (naaim, stability_metrics, analyst_earnings_estimates,
            # earnings_calendar) - live-confirmed today. For the other 31, this SELECT always
            # returned zero rows, so the entire consecutive-failures skip and SEC-rate-limit
            # graceful-skip block below (SESSION 87/88) was silently dead code for almost every
            # loader: a persistently-failing or rate-limited loader would never be skipped, just
            # retried every single run. Resolve to the loader's real primary output table first.
            real_table = all_tables(normalize_loader_name(loader))[0]

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT consecutive_failures, error_message FROM data_loader_status WHERE table_name = %s",
                (real_table,),
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
                    # ROOT-CAUSE FIX 2026-08-16: reap_stale_running_loaders() marks an abandoned
                    # (no owning process alive) loader FAILED with an "[REAPED]" error_message,
                    # incrementing consecutive_failures exactly like a real repeated failure would.
                    # Live-reproduced: stability_metrics hit consecutive_failures=6 purely from one
                    # abandoned-run reap cascade (same underlying incident as the earnings_calendar
                    # deadlock documented in price_daily_20260814_missing_load_monitor - that one
                    # was fixed with a one-off manual reset; this generalizes it). Without this,
                    # the loader never gets a chance to actually run again and self-reset the
                    # counter on success - a permanent false deadlock from a single dead process,
                    # indistinguishable at the DB level from a genuinely broken loader.
                    #
                    # BUG FIX 2026-08-17: only matched the automatic reaper's literal "[REAPED]"
                    # prefix, not a manual reap's "[MANUAL REAP" prefix (same abandoned-process
                    # situation, written by a human running LoaderStatusManager.mark_failed()
                    # directly instead of the automatic sweep) - live-reproduced on
                    # sec_segment_info, which a session had manually reaped with that exact
                    # wording and which then sat blocked at the 3-failure threshold below.
                    # lambda/api/routes/algo_handlers/market.py's _is_reaped_artifact() already
                    # recognized both prefixes; this generalizes the same fix here.
                    is_reaped_only = error_msg.strip().startswith(("[REAPED]", "[MANUAL REAP"))

                    # SESSION 88: For SEC loaders, skip after just 2 failures (not 3+)
                    # SEC rate limiting is an external factor - retrying won't help once it starts
                    # For other loaders, require 3+ failures before skipping - but not when the
                    # most recent failure was just an abandoned-process reap, not a real bug.
                    should_skip = (is_sec_issue and failures_int >= 2) or (
                        not is_sec_issue and not is_reaped_only and failures_int >= 3
                    )

                    if is_reaped_only and not is_sec_issue and failures_int >= 3:
                        print(
                            f"[LOCAL_SCHEDULER] {loader}: {failures_int} consecutive failures but most "
                            f"recent was an abandoned-process reap, not a real failure - allowing retry "
                            f"instead of permanently skipping.",
                            file=sys.stderr,
                        )

                    if should_skip:
                        if is_sec_issue:
                            # SEC rate limiting - skip gracefully so dependents use cached data
                            print(
                                f"[LOCAL_SCHEDULER] SKIP {loader}: {failures_int} failures due to SEC rate limiting (429, too many requests) "
                                f"- proceeding with cached data. Error: {error_msg[:100]}",
                                file=sys.stderr,
                            )
                            skipped_loaders.add(loader)
                            graceful_skips.add(loader)
                        else:
                            # Non-SEC failure - needs manual intervention
                            print(
                                f"[LOCAL_SCHEDULER] SKIP {loader}: {failures_int} consecutive failures - needs manual fix. Error: {error_msg[:100]}",
                                file=sys.stderr,
                            )
                            skipped_loaders.add(loader)
                            hard_failure = True
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
            if loader == "company_info":
                # ROOT-CAUSE FIX 2026-08-16: OptimalLoader._configure_chunk_size() defaults to
                # a local (non-AWS) chunk_size of up to 50,000 rows - bigger than
                # company_info_sec's entire ~4,922-symbol universe, so it accumulates every
                # symbol in memory and performs exactly ONE bulk write, at full completion.
                # Live-confirmed 2026-08-16: 52 symbols genuinely fetched from SEC (real
                # per-symbol warnings logged, e.g. "[AVAT] SEC API facts missing 'dei'
                # namespace") over ~6 minutes, but company_info_sec.updated_at never moved -
                # zero DB-visible progress the entire time. Combined with the stall watchdog's
                # hardcoded 1800s (30min) cap (`_monitor_loader_progress`, itself scaled from
                # this loader's 540min configured timeout under the assumption that 30min is
                # enough for "pure initialization" - true for other loaders, false here since
                # the whole run before its first write can exceed 30min), this loader is
                # structurally guaranteed to be killed as "stalled" on every single local run,
                # regardless of health - not a transient issue, a design incompatibility.
                # Forcing a small chunk size makes it flush every ~N symbols instead, so the
                # watchdog's row-count/updated_at liveness signal actually reflects real
                # progress well inside the 30min window.
                #
                # LOWERED 100->25 2026-08-16: at the observed live SEC EDGAR fetch rate
                # (52 symbols/~6min, ~8.7 symbols/min), a 100-symbol chunk needs ~11.5min
                # to reach its first flush - live-confirmed 0 DB-visible progress across two
                # consecutive attempts (~8min and ~6min each) that were externally restarted
                # (repeated manual `--now metrics` invocations hitting "Another scheduler
                # instance is already running" ~7min apart) before that first flush ever
                # landed. Every restart re-fetches from the same still-unmoved watermark,
                # so the loader was perpetually stuck re-doing its first ~7 minutes of work.
                # 25 symbols flushes in ~3min - inside even a fast impatient-restart cadence,
                # so genuine progress survives regardless of who/what restarts the pipeline.
                env["LOADER_CHUNK_SIZE"] = "25"
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
                hard_failure = True
                continue

            # BUG FOUND 2026-08-11: subprocess.run() with no stdout/stderr capture meant a
            # crash only ever recorded a bare "exit code N" in data_loader_status.error_message
            # - the real traceback only existed in whatever terminal/log redirect happened to
            # be wrapping this scheduler invocation (if any), making a live-observed FAILED
            # row (e.g. company_info_sec: "subprocess exited with code 1") undiagnosable from
            # the DB alone. Switched to Popen with a tee'ing reader thread: output still
            # streams live to this process's own stdout exactly as before, but the last 40
            # lines are also kept and attached to the failure message on a non-zero exit.
            #
            # GAP FOUND 2026-08-16: the 40-line tail is not enough when the loader itself is
            # chatty (e.g. DB_CONTEXT enter/exit tracing) - the actual root-cause warning (SEC
            # "rate limited (429)"/"forbidden (403)" retries, which is exactly what preceded a
            # live company_info_sec stall-kill this session) scrolls out of the deque long
            # before the kill, leaving only unrelated commit/rollback noise in error_message and
            # making the failure undiagnosable from the DB - the same class of gap the 2026-08-11
            # fix above closed for exit-code crashes, just not for stalls/timeouts. Also write the
            # full stream to a per-run log file so the complete history survives regardless of
            # how noisy the loader is.
            logs_dir = repo_root / "logs"
            logs_dir.mkdir(exist_ok=True)
            full_log_path = logs_dir / f"{loader_filename.replace('.py', '')}_{int(time.time())}.log"
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

            def _stream_and_capture(pipe: IO[str], sink: "collections.deque[str]", log_path: Path, header: str) -> None:
                # GAP FOUND 2026-08-16: a subprocess that dies (killed, crashes at interpreter
                # startup, etc.) before writing a single line of its own output left this file
                # at 0 bytes - live-observed repeatedly today (price_daily, stock_scores, and
                # others each produced several 0-byte logs across a ~4h window during an active
                # company_info_sec backfill holding the global scheduler lock). A 0-byte log is
                # indistinguishable from "never ran" and defeats the entire point of this
                # tee-capture mechanism (added 2026-08-11 specifically so failures are
                # diagnosable from the log file, not just a bare exit code). Writing the command
                # and start time immediately - before blocking on the child's output - guarantees
                # every log file carries at least that much, even for a near-instant death.
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write(header)
                    log_file.flush()
                    for line in pipe:
                        sys.stdout.write(line)
                        sink.append(line.rstrip("\n"))
                        log_file.write(line)
                pipe.close()

            assert proc.stdout is not None
            # GAP FOUND 2026-08-16 (same day as the header itself): a real Popen.pid is always
            # an int, but tests/unit/test_local_loader_scheduler_direct_invocation.py mocks
            # subprocess.Popen for every real loader name (including company_info_sec) to
            # exercise run_pipeline()'s full shorthand coverage - proc.pid on that mock is a
            # MagicMock, not an int. Before this header existed those runs just produced a
            # harmless 0-byte log; printing the MagicMock repr verbatim would instead leave a
            # confusing fake-looking entry in a REAL loader's log file. Same guard style as the
            # proc.poll() non-int check below - never trust an unvalidated attribute into a
            # diagnostic file meant for a human debugging a real run.
            log_pid = proc.pid if isinstance(proc.pid, int) else "<unknown>"
            log_header = (
                f"[LOCAL_SCHEDULER] cmd={cmd} pid={log_pid} "
                f"started={time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n"
            )
            # SESSION 108 FIX: Non-daemon thread ensures we capture all output before using tail_lines
            # Daemon threads may be killed before reader finishes, losing diagnostic info
            reader_thread = threading.Thread(
                target=_stream_and_capture, args=(proc.stdout, tail_lines, full_log_path, log_header), daemon=False
            )
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
            # See STALL_TIMEOUT_FLOOR_OVERRIDES / _stall_timeout_for() above for per-loader floor overrides.
            stall_timeout = _stall_timeout_for(loader, timeout)  # Allow 20% of timeout, clamped 15-30 min
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
                        # DEFENSIVE FIX 2026-08-16: proc.poll() on a real subprocess.Popen can
                        # only ever return None (still running) or an int (exit code) - by
                        # contract, nothing else. Live-confirmed this was violated: a mocked
                        # Popen with an unconfigured .poll() leaked through (likely a debug/test
                        # script that patched subprocess.Popen without exiting the patch context)
                        # and proc.poll() returned a truthy MagicMock, which this loop then
                        # treated as "process finished" and formatted straight into
                        # data_loader_status.error_message ("subprocess exited with code
                        # <MagicMock ...>"), corrupting company_info_sec's real status row while
                        # the actual subprocess was still alive and working. Refuse to trust a
                        # non-int/non-None poll() result - fall back to a real blocking wait()
                        # for the true result instead of persisting garbage.
                        if returncode is not None and not isinstance(returncode, int):
                            print(
                                f"[LOCAL_SCHEDULER] WARNING: {loader}: proc.poll() returned "
                                f"non-int/non-None value {returncode!r} - ignoring and falling "
                                f"back to proc.wait() for the real exit code.",
                                file=sys.stderr,
                            )
                            returncode = proc.wait()
                            break
                        if returncode is not None:
                            break  # Process finished

                        elapsed = time.time() - start_time
                        if elapsed > scheduler_timeout:
                            raise subprocess.TimeoutExpired(cmd, scheduler_timeout)

                        # Check progress periodically
                        if elapsed > 0 and int(elapsed) % progress_check_interval == 0:
                            if not _monitor_loader_progress(
                                loader_filename,
                                proc,
                                start_time + scheduler_timeout,
                                poll_interval_sec=1,
                                max_stall_sec=stall_timeout,
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
                    f"local_loader_scheduler: timed out after {scheduler_timeout_str}. "
                    f"Full log: {full_log_path}. Last output:\n{tail}",
                )
                hard_failure = True
                continue

            if stalled:
                proc.wait()
                reader_thread.join(timeout=30)  # SESSION 108: Wait up to 30s for output capture
                tail = "\n".join(tail_lines)
                _mark_loader_failed_after_crash(
                    loader_filename,
                    f"local_loader_scheduler: killed due to 0%% stall for >{stall_timeout}s. "
                    f"Full log: {full_log_path}. Last output:\n{tail}",
                )
                hard_failure = True
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
                    f"local_loader_scheduler: subprocess exited with code {returncode}. "
                    f"Full log: {full_log_path}. Last output:\n{tail}",
                )
                hard_failure = True
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
            hard_failure = True
            continue

    if hard_failure:
        # ROOT-CAUSE FIX 2026-08-16: was `if any_failed and not skipped_loaders`, which
        # incorrectly returned 0 (success) for a real crash/timeout/stall as soon as it had
        # any downstream dependent, since that dependent also landed in `skipped_loaders`.
        # See the `graceful_skips`/`hard_failure` bookkeeping added above.
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


def _pid_alive(pid: int) -> bool:
    # Fails safe: any uncertainty (can't run tasklist, permission denied, etc.) reports
    # "alive" so we never auto-clear a lock we're not actually sure is dead - the 12h
    # age-based fallback in _acquire_scheduler_lock still catches genuinely stuck-forever cases.
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in out.stdout
        except Exception:
            return True
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return True


def _lock_owner_info(scheduler_lock: Path) -> str:
    # LIVE-INCIDENT FIX 2026-08-17: a concurrent session force-killed this scheduler's
    # owning process mid-run (see concurrent_sessions_live_collision_20260817 in memory),
    # leaving an orphaned lock that nothing could distinguish from a slow-but-alive run
    # without manually cross-referencing OS process lists. The lock file used to be
    # written empty (os.O_WRONLY, no content) - recording "pid=<n> pipeline=<name>
    # started=<iso>" here lets both humans and future scheduler invocations check PID
    # liveness directly instead of guessing from age alone, and lets whoever's debugging
    # a "stuck" run verify it's actually dead before killing it.
    try:
        content = scheduler_lock.read_text().strip()
        return content if content else "(no owner info recorded - pre-fix lock format)"
    except (FileNotFoundError, OSError):
        return "(lock vanished while reading)"


def _try_acquire_lock(scheduler_lock: Path, pipeline_name: str) -> bool:
    try:
        fd = os.open(str(scheduler_lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        owner_info = f"pid={os.getpid()} pipeline={pipeline_name} started={datetime.now(timezone.utc).isoformat()}"
        os.write(fd, owner_info.encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


# RAISED 2026-08-17 from 1800s (30 min): live-measured the "metrics" pipeline's single
# slowest step (enhanced_quality_growth, ~5000 symbols x per-symbol sequential yfinance
# earnings/estimates calls at the mandatory LOADER_PARALLELISM=1) alone taking ~2.5h, with 3
# more per-symbol steps (analyst_upgrades, analyst_sentiment, stability_metrics) still queued
# behind it in PIPELINES["metrics"] - full-pipeline runtime of 6-8h is a realistic steady
# state, not an incident-day anomaly. This value no longer needs to cover "reference" waiting
# on metrics (see _lock_paths_for_pipeline - reference has its own lock now and never
# contends with metrics at all) but "morning"'s 2 AM trigger can still land behind a metrics
# run that started late or ran long the previous evening (7 PM ET start), and 30 min was
# never going to cover a multi-hour overrun there either. Safe to raise now that
# _try_claim_waiter_slot (below) caps this at exactly one waiting process per pipeline name
# regardless of how long it waits - previously a longer timeout would have meant more
# redundant waiters each burning a python process for that much longer. A dead owner is
# still reclaimed immediately regardless of this timeout (see the owner-liveness check
# below), and each individual loader has its own stall watchdog - so a lock held this long
# by a live owner means real, if slow, progress, not a hang this timeout needs to catch.
LOCK_WAIT_TIMEOUT_SECONDS = 28800  # 8h - must outlast metrics' realistic worst-case runtime
LOCK_POLL_INTERVAL_SECONDS = 60


def _waiter_marker_path(pipeline_name: str) -> Path:
    return Path(tempfile.gettempdir()) / f"algo-scheduler-waiting-{pipeline_name}.marker"


def _try_claim_waiter_slot(pipeline_name: str) -> bool:
    """Claim the single "currently waiting for this pipeline" slot, or detect a live one.

    ADDED 2026-08-17 (live pileup): once a live incident put multiple humans/watchers/Task
    Scheduler restarts all after the same recovery, up to 23 separate `--now reference`
    invocations were observed live, each independently spin-waiting up to
    LOCK_WAIT_TIMEOUT_SECONDS (30 min) for the same lock. None of them could possibly
    succeed any sooner than whichever was first in line - every extra waiter beyond the
    first was pure waste (a whole python process + DB pool + 30 min of log noise) with zero
    chance of doing anything the first waiter wasn't already going to do. Only one process
    should ever be waiting for a given pipeline name at a time; everyone else finds out
    immediately and exits instead of queueing redundantly. Same dead-owner-reclaim pattern
    as the scheduler lock itself, so a crashed waiter's marker doesn't block forever.
    """
    marker = _waiter_marker_path(pipeline_name)
    try:
        fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}".encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            content = marker.read_text().strip()
        except (FileNotFoundError, OSError):
            return _try_claim_waiter_slot(pipeline_name)  # vanished between calls - retry once

        owner_pid = None
        for token in content.split():
            if token.startswith("pid="):
                try:
                    owner_pid = int(token.split("=", 1)[1])
                except ValueError:
                    pass

        if owner_pid is not None and not _pid_alive(owner_pid):
            try:
                marker.unlink()
            except FileNotFoundError:
                pass
            return _try_claim_waiter_slot(pipeline_name)

        return False


def _release_waiter_slot(pipeline_name: str) -> None:
    try:
        _waiter_marker_path(pipeline_name).unlink()
    except FileNotFoundError:
        pass


def _queue_path_for_lock(scheduler_lock: Path) -> Path:
    return Path(str(scheduler_lock) + ".queue")


def _register_queue_ticket(queue_path: Path, pipeline_name: str) -> None:
    """Append this process to the FIFO queue for a lock. Atomic (O_APPEND is a single
    kernel-level write for a line this short), so concurrent registrants can't interleave
    into a corrupt line - see _acquire_scheduler_lock for why ordering matters here."""
    try:
        fd = os.open(str(queue_path), os.O_CREAT | os.O_APPEND | os.O_WRONLY)
        os.write(fd, f"pid={os.getpid()} pipeline={pipeline_name}\n".encode())
        os.close(fd)
    except OSError as e:
        print(f"[LOCAL_SCHEDULER] WARNING: could not register queue ticket: {e}", file=sys.stderr)


def _unregister_queue_ticket(queue_path: Path, pid: int) -> None:
    try:
        lines = queue_path.read_text().splitlines()
    except (FileNotFoundError, OSError):
        return
    remaining = [line for line in lines if f"pid={pid} " not in line + " "]
    try:
        if remaining:
            queue_path.write_text("\n".join(remaining) + "\n")
        else:
            queue_path.unlink()
    except (FileNotFoundError, OSError):
        pass


def _is_next_in_queue(queue_path: Path, pid: int) -> bool:
    """True if no other live-pid ticket is ahead of `pid` in this lock's FIFO queue.

    ROOT-CAUSE FIX 2026-08-17: _try_acquire_lock's os.open(O_CREAT|O_EXCL) is atomic, but
    WHO gets to attempt it every poll tick was pure luck of timing - live-observed:
    "morning" queued for the shared lock at 16:01 UTC (waiting on a long "metrics" run),
    but "signals" started fresh at 16:16:30 UTC, the exact instant "metrics" released the
    lock, and its very first (unqueued) acquire attempt won before "morning"'s next 60s
    poll tick ever fired - a process that had been waiting 15+ minutes lost to one that had
    been alive for 2 seconds. This makes acquisition FIFO: a process may only attempt
    _try_acquire_lock if it is first in line (or the queue is empty/only contains itself),
    so a late arrival can never race a lock's release against an existing waiter.

    Also prunes dead-pid entries opportunistically (crashed waiters never got to call
    _unregister_queue_ticket), so the queue can't accumulate stale entries forever.
    """
    try:
        lines = queue_path.read_text().splitlines()
    except (FileNotFoundError, OSError):
        return True  # No queue at all - nobody is ahead of us.

    live_entries: list[tuple[int, str]] = []
    for line in lines:
        entry_pid = None
        for token in line.split():
            if token.startswith("pid="):
                try:
                    entry_pid = int(token.split("=", 1)[1])
                except ValueError:
                    pass
        if entry_pid is not None and (entry_pid == pid or _pid_alive(entry_pid)):
            live_entries.append((entry_pid, line))

    if len(live_entries) != len(lines):
        # Some dead-pid entries were dropped - persist the pruned queue.
        try:
            if live_entries:
                queue_path.write_text("\n".join(line for _pid, line in live_entries) + "\n")
            else:
                queue_path.unlink()
        except (FileNotFoundError, OSError):
            pass

    if not live_entries:
        return True
    return live_entries[0][0] == pid


def _acquire_scheduler_lock(scheduler_lock: Path, pipeline_name: str) -> int | None:
    """Acquire the scheduler lock, checking owner liveness before reclaiming or rejecting.

    ADDED 2026-08-17: if the lock is held by a live, non-stale owner, waits and retries for
    up to LOCK_WAIT_TIMEOUT_SECONDS instead of failing on the first attempt. Absorbs the
    common case of a prior pipeline still finishing when the next one's trigger fires (e.g.
    a long metrics run still active when the evening/reference scheduled tasks start) - this
    used to require a human (or an ad hoc watcher script) noticing the failure and retrying
    manually; at least 8-10 redundant one-off watcher scripts existed for exactly this reason
    during the 2026-08-17 live incident (see MEMORY.md). Task Scheduler's own
    -RestartCount/-RestartInterval settings still provide a second layer of retry on top of
    this for longer overruns.

    Only one process waits for a given pipeline_name at a time (see _try_claim_waiter_slot) -
    a second concurrent request for the same pipeline exits immediately instead of piling on.
    Across DIFFERENT pipeline names sharing this lock (morning/metrics/signals), acquisition
    is FIFO by arrival order (see _is_next_in_queue) - a later arrival can never race an
    existing waiter for a just-released lock.

    Returns None on success (lock held by us), or an exit code (1) if acquisition failed.
    """
    queue_path = _queue_path_for_lock(scheduler_lock)
    pid = os.getpid()
    waited = 0.0
    announced_wait = False
    claimed_waiter_slot = False
    registered_ticket = False
    try:
        while True:
            if _is_next_in_queue(queue_path, pid) and _try_acquire_lock(scheduler_lock, pipeline_name):
                return None

            if not claimed_waiter_slot:
                if not _try_claim_waiter_slot(pipeline_name):
                    print(
                        f"[LOCAL_SCHEDULER] Another instance is already waiting to run "
                        f"'{pipeline_name}' - exiting immediately instead of queueing a "
                        "redundant second waiter. That instance will run it once the lock "
                        "frees up; wait for it instead of launching another.",
                        file=sys.stderr,
                    )
                    return 1
                claimed_waiter_slot = True

            if not registered_ticket:
                _register_queue_ticket(queue_path, pipeline_name)
                registered_ticket = True

            # Lock is held (or was, a moment ago) - check liveness first, then staleness age.
            owner_info = _lock_owner_info(scheduler_lock)
            owner_pid = None
            for token in owner_info.split():
                if token.startswith("pid="):
                    try:
                        owner_pid = int(token.split("=", 1)[1])
                    except ValueError:
                        pass

            owner_dead = owner_pid is not None and not _pid_alive(owner_pid)

            try:
                lock_age = time.time() - scheduler_lock.stat().st_mtime
            except FileNotFoundError:
                # Released between our failed acquire and this stat() - retry immediately,
                # don't count this negligible race window against the wait budget.
                time.sleep(0.5)
                continue

            if owner_dead or lock_age >= 43200:  # 12 hours in seconds
                if owner_dead:
                    print(f"[LOCAL_SCHEDULER] Lock owner (pid={owner_pid}) confirmed dead - clearing lock immediately.")
                # Stale (owner confirmed dead, or past the 12h age fallback) - clear it and
                # make one retry attempt. If we lose this retry too, a genuinely fresh
                # instance beat us fairly; fall through to the wait loop rather than looping
                # forever here.
                try:
                    scheduler_lock.unlink()
                    print(f"[LOCAL_SCHEDULER] Cleaned stale scheduler lock (age: {lock_age:.0f}s, owner: {owner_info})")
                except FileNotFoundError:
                    pass
                if _is_next_in_queue(queue_path, pid) and _try_acquire_lock(scheduler_lock, pipeline_name):
                    return None
                continue

            # Live owner, not stale - wait and retry rather than failing immediately, up to
            # LOCK_WAIT_TIMEOUT_SECONDS.
            if waited >= LOCK_WAIT_TIMEOUT_SECONDS:
                print(
                    f"[LOCAL_SCHEDULER] ERROR: Another scheduler instance is still running "
                    f"after waiting {waited:.0f}s (lock held for {lock_age:.0f}s, {owner_info}). "
                    f"Giving up. Wait for the existing instance to complete, or verify PID "
                    f"{owner_pid} is actually dead (e.g. "
                    f'`tasklist /FI "PID eq {owner_pid}"`) before manually removing '
                    f"{scheduler_lock} - killing a live session's run destroys its progress.",
                    file=sys.stderr,
                )
                return 1

            if not announced_wait:
                print(
                    f"[LOCAL_SCHEDULER] Lock held by a live instance ({owner_info}, held for "
                    f"{lock_age:.0f}s) - waiting up to {LOCK_WAIT_TIMEOUT_SECONDS:.0f}s for it "
                    "to finish instead of failing immediately."
                )
                announced_wait = True
            elif int(waited) % 300 == 0:  # log roughly every 5 min
                print(f"[LOCAL_SCHEDULER] Still waiting for scheduler lock ({waited:.0f}s so far)...")

            time.sleep(LOCK_POLL_INTERVAL_SECONDS)
            waited += LOCK_POLL_INTERVAL_SECONDS
    finally:
        if claimed_waiter_slot:
            _release_waiter_slot(pipeline_name)
        if registered_ticket:
            _unregister_queue_ticket(queue_path, pid)


def _lock_paths_for_pipeline(pipeline_name: str) -> list[Path]:
    """Which physical lock file(s) a pipeline needs held before it's safe to run.

    ADDED 2026-08-17: "reference" (company profile/13F/insider holdings/SEC filings/short
    interest/segment info+metrics/earnings-calendar-SEC/index constituents/economic/NAAIM/
    AAII/dividends) is 100% SEC EDGAR/FRED/FINRA/NASDAQ - confirmed via PIPELINES["reference"]
    above, it never touches yfinance. SEC EDGAR already has its own cross-process rate gate
    (_cross_process_wait in utils/external/sec_edgar_client.py, added 2026-08-16 for exactly
    this "multiple local processes hitting the same API" scenario). The other three pipelines
    (morning/signals/metrics) all touch yfinance, which has no such cross-process protection
    and must stay serialized under LOADER_PARALLELISM=1 (a real yfinance ban was
    self-triggered at parallelism=4 - see MEMORY.md). Giving "reference" its own lock lets it
    run concurrently with a long "metrics" run instead of always queuing behind it -
    live-measured metrics at ~4.6h steady-state runtime (5000 symbols x sequential per-symbol
    yfinance earnings/estimates calls), which routinely eats into reference's own 4.5h buffer
    (7:00 PM -> 11:30 PM ET) and left reference-pipeline tables (sec_segment_info,
    dividend_data, current_reports_8k, ...) sitting stale for no reason other than an
    unnecessary lock dependency. Per-table locking (utils/optimal_loader.py) is a second
    layer of protection for the one loader both pipelines share (company_info) - this split
    only removes serialization that was never actually required, real per-table conflicts
    still resolve safely (one waits for the other's per-table lock).

    "all" is the manual incident-recovery command (not an automated nightly trigger, see its
    --now help text) and runs every pipeline sequentially in one process, including
    reference - it holds BOTH locks for its whole duration so a concurrently-triggered
    standalone "reference" run can't race its own in-process reference step.
    """
    tmp = Path(tempfile.gettempdir())
    shared_lock = tmp / "algo-scheduler.lock"
    reference_lock = tmp / "algo-scheduler-reference.lock"
    if pipeline_name == "reference":
        return [reference_lock]
    if pipeline_name == "all":
        return [shared_lock, reference_lock]
    return [shared_lock]


def main() -> int:
    # FIXED 2026-08-16: this process's own top-level output (pipeline start, lock
    # rejections, pre-mark errors) was bare print()/stderr with zero persistent capture -
    # only each individual loader SUBPROCESS's stdout gets tee'd to logs/load_*.log inside
    # run_pipeline(). Live-confirmed: a burst of ~13 loaders (including company_info_sec)
    # got 0-byte log files at 16:53 and 17:06 today while a `--now reference` run already
    # held the lock - the rejecting scheduler instance's own "Another scheduler instance is
    # already running" message went only to whatever terminal launched it (never captured
    # to disk), so the whole failed attempt left no trace anywhere data_loader_status or
    # this repo's log files could surface it. Tee this process's own stdout/stderr to a
    # durable, append-only log for every invocation from the very first line, including
    # ones that get rejected before run_pipeline() is ever entered.
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    sys.stdout = _Tee(sys.stdout, logs_dir / "scheduler_invocations.log")
    sys.stderr = _Tee(sys.stderr, logs_dir / "scheduler_invocations.log")

    parser = argparse.ArgumentParser(description="Local loader scheduler")
    parser.add_argument(
        "--now",
        type=str,
        help="Run this pipeline immediately (morning|metrics|signals|reference|all). "
        "'all' runs every pipeline in dependency order under one lock acquisition - the "
        "standard recovery command after a mass-failure, instead of hand-launching a "
        "separate retry watcher per pipeline.",
    )
    parser.add_argument(
        "--clean-locks",
        action="store_true",
        help="SESSION 113 FIX: Remove all stale lock files (emergency override for cascading failures)",
    )
    parser.add_argument(
        "--loaders",
        type=str,
        default=None,
        help="ADDED 2026-08-17: comma-separated subset of shorthand loader names to run within "
        "the --now pipeline (e.g. 'positioning,stability_metrics'), instead of every loader in "
        "it. Dependencies excluded from the subset are assumed already-fresh from prior/"
        "concurrent runs rather than re-checked. Not valid with --now=all.",
    )
    args = parser.parse_args()
    if args.loaders and args.now == "all":
        parser.error("--loaders is not valid with --now=all (ambiguous which pipeline it scopes)")
        return 1
    loader_filter = {name.strip() for name in args.loaders.split(",") if name.strip()} if args.loaders else None
    print(
        f"[LOCAL_SCHEDULER] Invoked: --now={args.now} --clean-locks={args.clean_locks} "
        f"--loaders={sorted(loader_filter) if loader_filter else None} (pid={os.getpid()})"
    )

    # Handle --clean-locks flag
    if args.clean_locks:
        return _clean_all_locks()

    # Require --now if not cleaning locks
    if not args.now:
        parser.error("Either --now or --clean-locks is required")
        return 1

    # CRITICAL: Prevent concurrent scheduler invocations to avoid redundant loader runs
    # A scheduler lock ensures only one instance of a given resource class can run at a time.
    #
    # FIXED 2026-08-16: the original check-then-act (`.exists()` then `.touch()`) has a
    # classic TOCTOU race - two scheduler processes starting within the same window can
    # both see no lock present and both proceed to touch() and enter run_pipeline(), each
    # unaware of the other. Live-observed symptom matching this exactly: overlapping
    # `--now reference` and `--now metrics` runs, where every loader in the second
    # pipeline collided with per-loader/per-table locks the first pipeline already held
    # and exited near-instantly with zero output. os.open() with O_CREAT|O_EXCL is atomic
    # at the OS level - only one of two racing processes can win it.
    lock_paths = _lock_paths_for_pipeline(args.now)

    acquired_locks: list[Path] = []
    lock_failure: int | None = None
    for lock_path in lock_paths:
        lock_failure = _acquire_scheduler_lock(lock_path, args.now)
        if lock_failure is not None:
            break
        acquired_locks.append(lock_path)

    if lock_failure is not None:
        # Partial acquisition (only relevant for "all", which needs two locks) - release
        # whatever we did get so we don't strand a lock nobody will ever clean up.
        for lock_path in reversed(acquired_locks):
            try:
                lock_path.unlink()
            except Exception:
                pass
        return lock_failure

    pipelines_to_run = ALL_PIPELINES_ORDER if args.now == "all" else [args.now]

    try:
        exit_code = 0
        for pipeline_name in pipelines_to_run:
            code = run_pipeline(pipeline_name, loader_filter=loader_filter)
            if code != 0:
                exit_code = code
                print(
                    f"[LOCAL_SCHEDULER] '{pipeline_name}' pipeline exited {code}; continuing to "
                    "remaining pipelines in --now=all so one failure doesn't block the rest",
                    file=sys.stderr,
                )
        return exit_code
    finally:
        # Always clean up locks on exit (success or failure)
        for lock_path in acquired_locks:
            try:
                lock_path.unlink()
            except Exception as e:
                print(f"[LOCAL_SCHEDULER] WARNING: Could not remove {lock_path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
