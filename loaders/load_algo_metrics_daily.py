#!/usr/bin/env python3
"""
Algo Metrics Daily - composite loader for all metric calculations.

Runs all metric loaders in dependency order:
1. trend_criteria_data (Minervini/Weinstein templates)
2. swing_trader_scores (swing trading rank)
3. signal_quality_scores (buy/sell signal quality)
4. growth_metrics (growth scoring)
5. value_metrics (value scoring)
6. quality_metrics (quality scoring)

Run: python3 load_algo_metrics_daily.py [--symbols AAPL,MSFT]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import subprocess
import logging
from typing import List, Optional
from config.env_loader import load_env
from utils.structured_logger import get_logger

logger = get_logger(__name__)

# Loaders in dependency order
METRIC_LOADERS = [
    ("loaders/load_trend_criteria_data.py", []),
    ("loaders/load_swing_trader_scores.py", []),
    ("loaders/load_signal_quality_scores.py", []),
    ("loaders/load_growth_metrics.py", []),
    ("loaders/load_value_metrics.py", []),
    ("loaders/load_quality_metrics.py", []),
]

def run_loader(script: str, args: List[str]) -> bool:
    """Run a single loader. Return True if successful."""
    try:
        logger.info(f"Running {Path(script).name} {' '.join(args)}")
        cmd = ["python3", script] + args
        result = subprocess.run(
            cmd,
            capture_output=False,
            timeout=1800,  # 30 min for heavy compute
        )
        if result.returncode != 0:
            logger.error(f"  FAILED: {script} exited with code {result.returncode}")
            return False
        logger.info(f"  OK: {script}")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"  TIMEOUT: {script}")
        return False
    except Exception as e:
        logger.error(f"  ERROR: {script}: {e}")
        return False

def main():
    """Run all metric loaders in order."""
    load_env()

    # Get symbol list from command line if provided
    extra_args = []
    if "--symbols" in sys.argv:
        idx = sys.argv.index("--symbols")
        if idx + 1 < len(sys.argv):
            extra_args = ["--symbols", sys.argv[idx + 1]]

    logger.info("Starting Algo Metrics Daily loader pipeline")

    failed = []
    for script, args in METRIC_LOADERS:
        full_args = args + extra_args
        if not run_loader(script, full_args):
            failed.append(script)

    if failed:
        logger.error(f"FAILED LOADERS: {len(failed)}")
        for script in failed:
            logger.error(f"  - {script}")
        sys.exit(1)

    logger.info("All metric loaders completed successfully")
    sys.exit(0)

if __name__ == "__main__":
    main()
