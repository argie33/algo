#!/usr/bin/env python3
"""Test full orchestrator execution in real (non-dry-run) mode.

This script runs the complete orchestrator to identify any remaining issues
in actual execution vs. dry-run testing.
"""

import os
import sys
import logging
from datetime import date as _date

# Setup environment
os.environ['ENVIRONMENT'] = 'development'
os.environ['LOCAL_MODE'] = 'true'

# Use minimal logging to see actual issues
for logger_name in ['boto3', 'botocore', 'urllib3']:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Run full orchestrator and report results."""
    from algo.orchestration.orchestrator import Orchestrator

    logger.info("=" * 80)
    logger.info("FULL ORCHESTRATOR TEST (REAL EXECUTION MODE)")
    logger.info("=" * 80)

    try:
        orchestrator = Orchestrator(
            config=None,  # Will load from database
            run_date=_date.today(),
            dry_run=False,  # REAL EXECUTION
            verbose=True
        )

        logger.info(f"\nRunning orchestrator...")
        result = orchestrator.run()

        logger.info(f"\n{'='*80}")
        logger.info(f"ORCHESTRATOR RUN COMPLETED")
        logger.info(f"{'='*80}")
        logger.info(f"Result: {result}")

        return 0 if result else 1

    except Exception as e:
        logger.error(f"ORCHESTRATOR FAILED: {type(e).__name__}: {e}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
