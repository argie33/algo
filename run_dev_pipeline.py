#!/usr/bin/env python3
"""Local development pipeline coordinator.

Runs loaders → orchestrator → checks data freshness automatically.
Emulates AWS EventBridge Scheduler + Step Functions locally.

Usage:
  python run_dev_pipeline.py                # Run current pipeline now
  python run_dev_pipeline.py --morning      # Force morning pipeline
  python run_dev_pipeline.py --eod          # Force EOD pipeline
  python run_dev_pipeline.py --full         # Full refresh (all loaders)
  python run_dev_pipeline.py --watch 3600   # Auto-run every 1 hour
  python run_dev_pipeline.py --fast         # Skip slow loaders (yfinance)
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Environment setup
os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["SKIP_ORCHESTRATOR_LOCK"] = "true"

LOADERS_DIR = Path("loaders")

# Fast loaders (< 5 min)
FAST_LOADERS = [
    "load_market_constituents.py",
    "load_market_health_daily.py",
    "load_market_exposure_daily.py",
    "load_economic_data.py",
]

# Morning pipeline (prices + technical = 20 min)
MORNING_LOADERS = [
    "load_prices.py",
    "load_technical_indicators.py",
]

# EOD pipeline (financials + fundamentals = 60 min)
# CONSOLIDATED STRUCTURE (Session 217+):
# - load_market_status_daily.py replaces: load_market_health_daily + load_market_exposure_daily + load_market_sentiment
# - load_value_quality_growth_metrics.py replaces: load_quality_growth_metrics + parts of load_yfinance_derived_metrics
# - load_positioning_metrics.py is the new critical-path positioning data (split from yfinance_derived_metrics)
# Old loaders (load_quality_growth_metrics.py, load_market_health_daily.py) deleted - see git log for details
EOD_LOADERS = [
    "load_market_status_daily.py",         # Consolidated: market health + exposure + sentiment (replaces 3 loaders)
    "load_financial_statements.py",        # SEC financials (prices, balance sheets, cash flow)
    "load_value_quality_growth_metrics.py", # SEC-based value + quality + growth metrics
    "load_positioning_metrics.py",         # Institutional/insider/short data (CRITICAL for stock_scores)
    "load_yfinance_snapshot.py",           # Optional: analyst sentiment + earnings dates (dashboard enrichment)
]

# Computed pipeline (scores + signals = 60 min)
# DEPENDENCY ORDER CRITICAL:
# 1. load_positioning_metrics.py MUST run before load_stock_scores (stock_scores reads positioning_metrics)
# 2. load_stock_scores.py must complete before load_buy_sell_daily (buy_sell uses scores)
# 3. All other loaders follow (order not critical)
COMPUTED_LOADERS = [
    "load_positioning_metrics.py",      # Phase 2: Positioning metrics for stock scoring (CRITICAL for stock_scores)
    "load_stock_scores.py",             # Phase 3: Composite scores (reads all 5 metric tables)
    "load_buy_sell_daily.py",           # Phase 4: Buy/sell signals (uses scores + technical indicators)
    "load_sector_performance.py",       # Phase 5: Sector returns (enrichment)
    "load_trend_analysis.py",           # Phase 5: Trend template scoring
    "load_risk_metrics_daily.py",       # Phase 6: Stability metrics (enrichment)
    "load_market_exposure_daily.py",    # Phase 6: Market regime detection
    "load_algo_metrics_daily.py",       # Phase 6: Portfolio metrics (dashboard only)
]

# Full pipeline (all loaders)
FULL_LOADERS = MORNING_LOADERS + EOD_LOADERS + COMPUTED_LOADERS


def run_command(cmd: list[str], description: str, timeout: int = 600, in_loaders_dir: bool = False) -> bool:
    """Run a shell command and return success status."""
    print(f"  [{description}]...", end=" ", flush=True)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=LOADERS_DIR if in_loaders_dir else None,
        )
        if result.returncode == 0:
            print("[OK]")
            return True
        else:
            error = result.stderr[-100:] if result.stderr else ""
            print(f"[FAIL] {error}")
            return False
    except subprocess.TimeoutExpired:
        print("[TIMEOUT]")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def run_loaders(loader_list: list[str], skip_slow: bool = False) -> dict:
    """Run a list of loaders and return stats."""
    success = 0
    failed = 0

    for loader in loader_list:
        # Skip slow loaders if requested
        if skip_slow and "yfinance_snapshot" in loader:
            print(f"  [{loader}]... [SKIPPED - slow loader]")
            continue

        # Check if loader exists
        loader_path = LOADERS_DIR / loader
        if not loader_path.exists():
            print(f"  [{loader}]... [NOT FOUND]")
            failed += 1
            continue

        if run_command(["python", loader], loader, in_loaders_dir=True):
            success += 1
        else:
            failed += 1

    return {"success": success, "failed": failed, "total": len(loader_list)}


def run_pipeline(pipeline_name: str, loaders: list[str], skip_slow: bool = False) -> None:
    """Run a pipeline and orchestrator."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)

    print(f"\n{'='*70}")
    print(f"{pipeline_name} PIPELINE")
    print(f"{'='*70}")
    print(f"Start: {now.strftime('%H:%M:%S %Z')}")
    print()

    start_time = time.time()

    # Run loaders
    print("Step 1: Running data loaders...")
    loader_stats = run_loaders(loaders, skip_slow=skip_slow)
    print(f"  Result: {loader_stats['success']}/{loader_stats['total']} loaders succeeded")

    if loader_stats["failed"] > 0:
        print(f"  [WARN] {loader_stats['failed']} loaders failed - proceeding anyway")

    # Run orchestrator
    print("\nStep 2: Running orchestrator (9 phases)...")
    orch_ok = run_command(
        ["python", "scripts/run_local_orchestrator.py"],
        "orchestrator",
        timeout=300
    )

    # Check data freshness
    print("\nStep 3: Checking data freshness...")
    fresh_ok = run_command(
        ["python", "check_system_health.py"],
        "system health check",
        timeout=30
    )

    elapsed = time.time() - start_time
    print()
    print(f"{'='*70}")
    print(f"{pipeline_name} complete ({elapsed:.0f}s)")
    print(f"{'='*70}\n")


def get_current_pipeline() -> tuple[str, list[str]] | None:
    """Determine which pipeline should run at current time."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    hour = now.hour
    minute = now.minute

    # Morning: 2 AM ET (1:30 - 2:30)
    if (hour == 1 and minute >= 30) or (hour == 2 and minute < 30):
        return ("Morning", MORNING_LOADERS)

    # EOD: 4 PM ET (3:30 - 4:30)
    if (hour == 15 and minute >= 30) or (hour == 16 and minute < 30):
        return ("EOD", EOD_LOADERS)

    # Computed: 7 PM ET (6:30 - 7:30)
    if (hour == 18 and minute >= 30) or (hour == 19 and minute < 30):
        return ("Computed", COMPUTED_LOADERS)

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local development pipeline coordinator"
    )
    parser.add_argument(
        "--morning", action="store_true", help="Run morning pipeline (prices + technical)"
    )
    parser.add_argument(
        "--eod", action="store_true", help="Run EOD pipeline (financials + metrics)"
    )
    parser.add_argument(
        "--computed", action="store_true", help="Run computed pipeline (scores + signals)"
    )
    parser.add_argument(
        "--full", action="store_true", help="Full refresh (all loaders)"
    )
    parser.add_argument(
        "--watch",
        type=int,
        metavar="SECONDS",
        help="Watch mode: run on schedule every N seconds"
    )
    parser.add_argument(
        "--fast", action="store_true", help="Skip slow loaders (yfinance)"
    )

    args = parser.parse_args()

    # Determine pipeline
    if args.full:
        pipeline = ("FULL REFRESH", FULL_LOADERS)
    elif args.morning:
        pipeline = ("Morning", MORNING_LOADERS)
    elif args.eod:
        pipeline = ("EOD", EOD_LOADERS)
    elif args.computed:
        pipeline = ("Computed", COMPUTED_LOADERS)
    else:
        # Determine by current time
        pipeline = get_current_pipeline()
        if not pipeline:
            print("No scheduled pipeline for current time.")
            print("Specify: --morning, --eod, --computed, --full, or --watch SECONDS")
            sys.exit(0)

    # Run watch mode if requested
    if args.watch:
        print(f"Watch mode: Pipeline every {args.watch}s (Ctrl+C to exit)")
        iteration = 0
        try:
            while True:
                iteration += 1
                et = ZoneInfo("America/New_York")
                now = datetime.now(et)
                print(f"\n>>> ITERATION {iteration} - {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

                # Re-check pipeline in watch mode
                current = get_current_pipeline()
                if current:
                    run_pipeline(current[0], current[1], skip_slow=args.fast)
                else:
                    print("(No scheduled pipeline for current time)")

                print(f"Next check in {args.watch}s (Ctrl+C to exit)...")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\n\nWatch mode interrupted.")
            sys.exit(0)
    else:
        # Run once
        run_pipeline(pipeline[0], pipeline[1], skip_slow=args.fast)


if __name__ == "__main__":
    main()
