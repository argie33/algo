#!/usr/bin/env python3
"""Run quarterly financial data loaders."""

import subprocess
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Quarterly loaders that support --period flag
quarterly_loaders = [
    ('load_income_statement.py', ['--period', 'quarterly']),
    ('load_balance_sheet.py', ['--period', 'quarterly']),
    ('load_cash_flow.py', ['--period', 'quarterly']),
]

logger.info("\n" + "="*70)
logger.info("Running quarterly financial data loaders")
logger.info("="*70 + "\n")

failed = []
successful = []
total_start = time.time()

for loader_file, args in quarterly_loaders:
    logger.info(f"Running {loader_file} {' '.join(args)}...")
    start = time.time()

    try:
        result = subprocess.run(
            ['python3', loader_file] + args,
            capture_output=True,
            text=True,
            timeout=300
        )

        elapsed = time.time() - start
        if result.returncode == 0:
            logger.info(f"  SUCCESS ({elapsed:.1f}s)")
            successful.append((loader_file, elapsed))
        else:
            logger.error(f"  FAILED ({elapsed:.1f}s)")
            logger.error(f"  stderr: {result.stderr[:200]}")
            failed.append((loader_file, result.stderr[:200]))
    except subprocess.TimeoutExpired:
        logger.error(f"  TIMEOUT (>300s)")
        failed.append((loader_file, "timeout"))
    except Exception as e:
        logger.error(f"  ERROR: {str(e)[:100]}")
        failed.append((loader_file, str(e)))

total_elapsed = time.time() - total_start
logger.info(f"\n{'='*70}")
logger.info(f"Quarterly loaders: {len(successful)} successful, {len(failed)} failed ({total_elapsed:.1f}s total)")
if failed:
    logger.info("\nFailed loaders:")
    for loader, error in failed:
        logger.info(f"  - {loader}: {error}")
logger.info("="*70 + "\n")

sys.exit(0 if not failed else 1)
