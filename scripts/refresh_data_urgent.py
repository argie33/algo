#!/usr/bin/env python3
"""URGENT: Refresh stale data that's preventing Phase 7 from generating signals.

Critical loaders haven't run since July 10-11 and signals are 75+ hours stale.
This script manually triggers all critical loaders to load fresh data NOW.

Usage:
  python3 scripts/refresh_data_urgent.py
"""

import subprocess
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def run_loader(loader_name, *args):
    """Run a loader via run_loader.py and report results."""
    cmd = ['python3', 'scripts/run_loader.py', loader_name] + list(args)
    logger.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            # Extract rows inserted from output
            if 'rows_inserted' in result.stdout:
                logger.info(f"[OK] {loader_name} - check logs for details")
            else:
                logger.info(f"[OK] {loader_name}")
            return True
        else:
            logger.error(f"[FAILED] {loader_name}: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"[TIMEOUT] {loader_name} exceeded 300s")
        return False
    except Exception as e:
        logger.error(f"[ERROR] {loader_name}: {e}")
        return False

def main():
    logger.info("=" * 70)
    logger.info("URGENT DATA REFRESH")
    logger.info("=" * 70)
    logger.info("Refreshing stale metric data to unlock Phase 7 signal generation")
    logger.info("")

    loaders_to_run = [
        ('prices', '--backfill', '2'),
        ('health', ''),
        ('technical', ''),
        ('metrics', ''),
        ('scores', ''),
    ]

    results = {}
    for loader_info in loaders_to_run:
        loader_name = loader_info[0]
        args = [a for a in loader_info[1:] if a]
        logger.info("")
        logger.info(f"[{len(results)+1}/{len(loaders_to_run)}] {loader_name}...")
        results[loader_name] = run_loader(loader_name, *args)

    logger.info("")
    logger.info("=" * 70)
    logger.info("REFRESH RESULTS")
    logger.info("=" * 70)

    passed = [k for k, v in results.items() if v]
    failed = [k for k, v in results.items() if not v]

    logger.info(f"Passed: {len(passed)}/{len(results)}")
    for name in passed:
        logger.info(f"  [OK] {name}")

    if failed:
        logger.error(f"Failed: {len(failed)}/{len(results)}")
        for name in failed:
            logger.error(f"  [FAIL] {name}")
        return 1
    else:
        logger.info("All loaders succeeded! Data refresh complete.")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Run orchestrator: python3 scripts/trigger_orchestrator.py --run morning --mode paper")
        logger.info("  2. Dashboard should show fresh signals")
        return 0

if __name__ == '__main__':
    sys.exit(main())
