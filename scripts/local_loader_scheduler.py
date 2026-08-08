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
        # FIXED 2026-08-03: registered in loader_registry.py but never scheduled anywhere -
        # see scripts/run_loader.py's run_analyst_earnings_estimates_loader() docstring.
        # Must run BEFORE value_quality_growth - that loader joins this table by symbol to
        # compute forward_pe (see load_analyst_earnings_estimates.py's module docstring).
        "analyst_earnings_estimates",
        "value_quality_growth",
        # FIXED 2026-08-03: same orphaned-loader bug - see run_enhanced_quality_growth_loader()
        # docstring. Must run after value_quality_growth (enhances its output rows).
        "enhanced_quality_growth",
        "positioning_metrics",
        "stability_metrics",
    ],
    "signals": [
        "prices",
        "technical",
        "scores",
        "buy_sell",
    ],
}


def run_pipeline(pipeline_name: str) -> int:
    """Run all loaders for a given pipeline."""
    loaders = PIPELINES.get(pipeline_name)
    if not loaders:
        print(f"ERROR: Unknown pipeline '{pipeline_name}'", file=sys.stderr)
        print(f"Valid pipelines: {', '.join(PIPELINES.keys())}", file=sys.stderr)
        return 1

    print(f"[LOCAL_SCHEDULER] Starting {pipeline_name} pipeline ({len(loaders)} loaders)...")
    repo_root = Path(__file__).parent.parent

    # CRITICAL FIX: Loader-specific timeouts
    # Prevents hangs when loaders block on lock acquisition from crashed previous runs.
    # Timeout must exceed: lock acquisition retry budget (5-50 min) + actual loader runtime (10-30 min)
    # Set conservatively: price_daily can take 60+ min on large universe, so budget 90 min
    LOADER_TIMEOUTS = {
        "prices": 90 * 60,           # 90 min - price_daily is slowest loader (5000+ symbols @ ~1s each)
        "technical": 30 * 60,        # 30 min - in-database vectorized computation, fast
        "market_status": 15 * 60,    # 15 min - market status loaders are fast
        "earnings_calendar": 20 * 60, # 20 min - yfinance with 8s per-symbol timeout
        "trend_analysis": 15 * 60,   # 15 min - trend analysis is fast
        "sector_industry": 15 * 60,  # 15 min - sector/industry loaders are fast
        "analyst_earnings_estimates": 20 * 60,  # 20 min
        "value_quality_growth": 40 * 60,        # 40 min - slower API calls
        "enhanced_quality_growth": 25 * 60,     # 25 min
        "positioning_metrics": 30 * 60,         # 30 min
        "stability_metrics": 30 * 60,           # 30 min
    }

    for loader in loaders:
        timeout = LOADER_TIMEOUTS.get(loader, 30 * 60)  # 30 min default
        print(f"[LOCAL_SCHEDULER] Running {loader} loader (timeout: {timeout}s)...")
        try:
            result = subprocess.run(
                [sys.executable, "scripts/run_loader.py", loader],
                cwd=str(repo_root),
                env=os.environ.copy(),
                timeout=timeout,
            )
            if result.returncode != 0:
                print(
                    f"[LOCAL_SCHEDULER] WARNING: {loader} loader failed (exit code {result.returncode})",
                    file=sys.stderr,
                )
                return 1
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
