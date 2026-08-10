#!/usr/bin/env python3
"""Local loader scheduler for dev/test environments.

Usage:
  python scripts/local_loader_scheduler.py --now morning
  python scripts/local_loader_scheduler.py --now metrics
  python scripts/local_loader_scheduler.py --now signals
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
# BUG FOUND 2026-08-10 (via [[analyst_loaders_reloaded_and_local_parallelism_ban_20260810]]):
# this used to default to "4" for "local dev optimization". Live-reproduced: LOADER_PARALLELISM=4
# self-triggered the yfinance shared-IP circuit breaker from a single local machine, causing
# 84%+ false-failure rates on analyst loaders (same fix applied to scripts/run_loader.py).
# Default to 1 to match the value actually verified safe.
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "1"

# Import registry mapping to convert shorthand names to filenames
from loaders.loader_registry import all_tables, normalize_loader_name
from utils.loaders.status_manager import LoaderStatusManager, reap_stale_running_loaders


def _mark_loader_failed_after_crash(loader_filename: str, error_message: str) -> None:
    """Best-effort: mark every table a crashed/timed-out loader owns as FAILED.

    Without this, subprocess.run() crashing or timing out left data_loader_status stuck
    at RUNNING indefinitely (no owning process, no error_message, no terminal status) -
    only reap_stale_running_loaders()'s 4-hour-later check on the *next* pipeline
    invocation would ever correct it. Live-confirmed 2026-08-10: quality_metrics/
    growth_metrics (via enhanced_quality_growth) died mid-run with no process alive and
    no status transition. Deliberately swallows its own errors - a failure to record the
    failure must never mask the original crash/timeout being reported by the caller.
    """
    try:
        for table in all_tables(loader_filename):
            LoaderStatusManager(table).mark_failed(error_message)
    except Exception as mark_err:
        print(
            f"[LOCAL_SCHEDULER] WARNING: could not mark {loader_filename} tables FAILED "
            f"after crash: {mark_err}",
            file=sys.stderr,
        )


PIPELINES = {
    "morning": [
        "prices",
        "technical",
        "market_status",
        "earnings_calendar",  # FIXED 2026-08-05: Minervini/Weinstein earnings blackout window (Phase 3)
        "trend_analysis",     # FIXED 2026-08-05: Setup/teardown detection for signal quality (Phase 7)
        "sector_industry",    # FIXED 2026-08-05: Sector rotation signals and industry rankings (Phase 5/7)
    ],
    "metrics": [
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
LOADER_DEPENDENCIES = {
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


def run_pipeline(pipeline_name: str) -> int:
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

    repo_root = Path(__file__).parent.parent
    completed_loaders = set()  # Track completed loaders for dependency checking

    # CRITICAL FIX: Loader-specific timeouts
    # Prevents hangs when loaders block on lock acquisition from crashed previous runs.
    # Timeout must exceed: lock acquisition retry budget (5-50 min) + actual loader runtime (10-30 min)
    # Set conservatively: price_daily can take 60+ min on large universe, so budget 90 min
    LOADER_TIMEOUTS = {
        # Core pricing & market data (heaviest workloads)
        "prices": 90 * 60,                       # 90 min - slowest (5000+ symbols @ ~1s each)
        "technical": 30 * 60,                    # 30 min - vectorized in-database computation
        "constituents": 10 * 60,                 # 10 min - light (static symbol list)
        "economic": 10 * 60,                     # 10 min - light (FRED + DXY index)
        # Market status & sentiment (fast API calls)
        "market_status": 15 * 60,                # 15 min - 3 tables (health/exposure/sentiment)
        "naaim": 10 * 60,                        # 10 min - published weekly
        "aaii": 10 * 60,                         # 10 min - published weekly
        # Technical analysis
        "trend_analysis": 15 * 60,               # 15 min - template pattern matching
        "momentum": 30 * 60,                     # 30 min - risk metrics (momentum + stability)
        "stability_metrics": 30 * 60,            # 30 min - alias for momentum
        "valuations": 20 * 60,                   # 20 min - SEC API calls
        # SEC/Financial data (batch API calls)
        # BUG FOUND 2026-08-10: 30 min was never enough for a genuine full-universe local
        # reload - live-reproduced twice this session, each run making comparable, real
        # progress (~2000-2500 of ~4900 symbols fetched via SEC EDGAR, one statement/period
        # combo at a time) but still short of completion at the 1800s mark, so
        # subprocess.TimeoutExpired killed it both times before it ever reached the
        # loaders after it in the pipeline (sec_valuations, value_quality_growth, etc.) -
        # `_check_loader_dependencies()` only tracks loaders completed *within this same
        # invocation* (a local `completed_loaders` set, not real DB freshness), so there is
        # no way to skip financial_statements even when its data is already fresh from a
        # separate production run. Bumped to match this loader's real full-universe runtime
        # (matches the ~3.5h whole-pipeline figure in memory, of which this loader is the
        # largest chunk), consistent with how "prices" already budgets 90 min for a
        # comparably-sized universe.
        "financial_statements": 150 * 60,        # 150 min - SEC EDGAR batch queries (5500+ symbols, 6 statement/period combos each)
        "sec_valuations": 30 * 60,               # 30 min - valuation computation from SEC data
        # Fundamental metrics (API-heavy)
        "value_quality_growth": 40 * 60,         # 40 min - multi-source aggregation
        # BUG FOUND 2026-08-10: 25 min was calibrated before a same-day fix
        # (loader_audit_and_fixes_20260810 memory) added a 0.3s inter-symbol pacing delay
        # plus longer yfinance retry/backoff (max_retries=4, backoff=3.0s) to survive
        # sustained per-IP throttling - live-reproduced same day: 904 symbols processed in
        # the full 1500s before subprocess.run's timeout killed it (~1.66 symbols/sec),
        # extrapolating to ~135 min for the full ~4900-symbol universe. This also clobbers
        # quality_metrics/growth_metrics' status: this loader shares those 2 output tables
        # with value_quality_growth (which runs first and completes cleanly), calls its own
        # mark_running() on them at its own start, and a timeout here left them stuck
        # RUNNING despite value_quality_growth's real, fresh, healthy data underneath.
        "enhanced_quality_growth": 150 * 60,     # 150 min - earnings surprise calcs w/ yfinance throttle pacing
        "analyst_earnings_estimates": 20 * 60,   # 20 min - yfinance per-symbol calls
        "analyst_sentiment": 20 * 60,            # 20 min - yfinance analyst data
        "analyst_upgrades": 20 * 60,             # 20 min - yfinance recommendation data
        # Sector/industry
        "sector_industry": 15 * 60,              # 15 min - daily aggregation (3 output tables)
        # Company information (SEC API calls)
        # BUG FOUND 2026-08-10 (systematic follow-up on
        # local_scheduler_second_wave_orphaned_loaders_20260810's flagged-but-deferred item):
        # 15 min was mathematically impossible to meet. SecEdgarClient's RateLimiter is fixed
        # at 2 req/sec (utils/external/sec_edgar_client.py) and is a single instance shared
        # across all symbols regardless of LOADER_PARALLELISM (parallelism doesn't help - the
        # limiter throttles total throughput, not per-thread), and this loader makes exactly
        # one rate-limited call per symbol (get_submissions(); symbol_to_cik() is a local cache
        # lookup, no network). With ~4940 active symbols, the zero-retry floor alone is
        # 4940/2 = 2470s (~41 min) - already 2.7x this budget. DB-confirmed a real production
        # run on 2026-08-08 used a 3603s (60 min) budget and STILL timed out (realistic retry/
        # backoff overhead from occasional 429/503 responses easily pushes a full run past an
        # hour). Bumped to 120 min for real margin, matching how financial_statements
        # (150 min) was already sized for its own well-diagnosed real-world runtime.
        "company_info": 120 * 60,                # 120 min - SEC EDGAR lookups, ~4900 symbols @ 2 req/sec floor
        "profile": 10 * 60,                      # 10 min - uses cached company_info
        "dividends": 15 * 60,                    # 15 min - yfinance dividend data
        # Holdings & positioning
        "positioning": 30 * 60,                  # 30 min - multi-source aggregation
        "positioning_metrics": 30 * 60,          # 30 min - alias for positioning loader
        "institutional": 15 * 60,                # 15 min - SEC Schedule 13G parsing
        "insider_holdings": 15 * 60,             # 15 min - SEC Form 4/5 parsing
        "short_interest": 10 * 60,               # 10 min - FINRA data
        "insider_velocity": 15 * 60,             # 15 min - SEC Form 3/4/5 transaction analysis
        # Earnings calendar & SEC data
        "earnings_calendar": 20 * 60,            # 20 min - yfinance earnings_dates window
        "earnings_sec": 15 * 60,                 # 15 min - SEC filing date extraction
        "sec_reports": 10 * 60,                  # 10 min - 8-K report scanning
        "segment_info": 15 * 60,                 # 15 min - segment data extraction
        "segment_metrics": 15 * 60,              # 15 min - segment aggregation
        # Trading signals
        "scores": 25 * 60,                       # 25 min - scoring algorithm
        "signal_quality": 15 * 60,               # 15 min - signal quality metrics
        "algo": 20 * 60,                         # 20 min - algo-specific metrics
        "buy_sell": 15 * 60,                     # 15 min - buy/sell signal generation
    }

    for loader in loaders:
        # CRITICAL FIX (Session 81): Check loader dependencies before running
        # Prevents silent data degradation if a required upstream loader fails
        if not _check_loader_dependencies(loader, completed_loaders):
            return 1

        timeout = LOADER_TIMEOUTS.get(loader, 30 * 60)  # 30 min default
        print(f"[LOCAL_SCHEDULER] Running {loader} loader (timeout: {timeout}s)...")
        try:
            # Convert shorthand name to filename (e.g., "prices" → "load_prices.py")
            loader_filename = normalize_loader_name(loader)
            env = os.environ.copy()
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
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                env=env,
                timeout=timeout,
            )
            if result.returncode != 0:
                print(
                    f"[LOCAL_SCHEDULER] WARNING: {loader} loader failed (exit code {result.returncode})",
                    file=sys.stderr,
                )
                _mark_loader_failed_after_crash(
                    loader_filename, f"local_loader_scheduler: subprocess exited with code {result.returncode}"
                )
                return 1
            # Mark loader as completed for dependency checking of subsequent loaders
            completed_loaders.add(loader)
        except subprocess.TimeoutExpired:
            print(
                f"[LOCAL_SCHEDULER] ERROR: {loader} loader timed out after {timeout}s. "
                f"Likely blocked by stale lock. Run: rm -f /tmp/algo-locks/*.lock",
                file=sys.stderr,
            )
            _mark_loader_failed_after_crash(
                loader_filename, f"local_loader_scheduler: timed out after {timeout}s"
            )
            return 1

    print(f"[LOCAL_SCHEDULER] {pipeline_name} pipeline completed successfully")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Local loader scheduler")
    parser.add_argument(
        "--now",
        type=str,
        required=True,
        help="Run this pipeline immediately (morning|metrics|signals)",
    )
    args = parser.parse_args()

    return run_pipeline(args.now)


if __name__ == "__main__":
    sys.exit(main())
