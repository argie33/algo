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
# LOCAL DEV OPTIMIZATION: Set higher parallelism for local development
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "4"

# Import registry mapping to convert shorthand names to filenames
from loaders.loader_registry import normalize_loader_name


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
        "financial_statements": 30 * 60,         # 30 min - SEC EDGAR batch queries (5500+ symbols)
        "sec_valuations": 30 * 60,               # 30 min - valuation computation from SEC data
        # Fundamental metrics (API-heavy)
        "value_quality_growth": 40 * 60,         # 40 min - multi-source aggregation
        "enhanced_quality_growth": 25 * 60,      # 25 min - earnings surprise calculations
        "analyst_earnings_estimates": 20 * 60,   # 20 min - yfinance per-symbol calls
        "analyst_sentiment": 20 * 60,            # 20 min - yfinance analyst data
        "analyst_upgrades": 20 * 60,             # 20 min - yfinance recommendation data
        # Sector/industry
        "sector_industry": 15 * 60,              # 15 min - daily aggregation (3 output tables)
        # Company information (SEC API calls)
        "company_info": 15 * 60,                 # 15 min - SEC EDGAR lookups
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
            if loader == "financial_statements":
                # load_financial_statements.py can't go through scripts/run_loader.py:
                # run_loader.py instantiates ConsolidatedFinancialStatementsLoader directly
                # (loader_class()), which requires LOADER_STATEMENT_TYPE to already name ONE
                # of the 6 statement/period combos - it never reaches this module's own
                # main(), where LOADER_STATEMENT_TYPE="all" fans out to all 6 combos via
                # load_all_statements(). Must invoke the module directly instead.
                env["LOADER_STATEMENT_TYPE"] = "all"
                cmd = [sys.executable, f"loaders/{loader_filename}"]
            else:
                cmd = [sys.executable, "scripts/run_loader.py", loader_filename]
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
                return 1
            # Mark loader as completed for dependency checking of subsequent loaders
            completed_loaders.add(loader)
        except subprocess.TimeoutExpired:
            print(
                f"[LOCAL_SCHEDULER] ERROR: {loader} loader timed out after {timeout}s. "
                f"Likely blocked by stale lock. Run: rm -f /tmp/algo-locks/*.lock",
                file=sys.stderr,
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
