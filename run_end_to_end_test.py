#!/usr/bin/env python3
"""End-to-End Orchestrator Test - All 9 Phases"""
import sys
import logging
from datetime import date, datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def run_orchestrator_test():
    """Execute full orchestrator through all 9 phases."""
    logger.info("=" * 80)
    logger.info("FULL ORCHESTRATOR END-TO-END TEST (DRY-RUN)")
    logger.info("=" * 80)

    from algo.orchestration import Orchestrator
    from algo.infrastructure import get_config
    from utils.db import DatabaseContext

    config = get_config()
    orchestrator = Orchestrator(
        config=config,
        run_date=date.today(),
        dry_run=True,
        verbose=True,
        run_id=f"TEST-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    )

    logger.info(f"Run ID: {orchestrator.run_id}")
    logger.info(f"Dry Run: {orchestrator.dry_run}")

    try:
        logger.info("\n" + "=" * 80)
        logger.info("EXECUTING ORCHESTRATOR")
        logger.info("=" * 80)

        result = orchestrator.run()

        logger.info("\n" + "=" * 80)
        logger.info("EXECUTION COMPLETE")
        logger.info("=" * 80)

        # Print results
        logger.info(f"\nSuccess: {result.get('success')}")
        logger.info(f"Halted: {result.get('halted')}")

        # Check database
        with DatabaseContext("read", timeout=10) as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM algo_portfolio_snapshots WHERE snapshot_date = %s", (date.today(),))
            snapshots = cur.fetchone()['cnt'] if cur.fetchone() else 0
            logger.info(f"\nPortfolio snapshots today: {snapshots}")

            cur.execute("SELECT COUNT(*) as cnt FROM algo_positions WHERE status = 'open'")
            positions = cur.fetchone()['cnt'] if cur.fetchone() else 0
            logger.info(f"Open positions: {positions}")

        return result.get('success', False)

    except Exception as e:
        logger.error(f"\nORCHESTRATOR FAILED: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = run_orchestrator_test()
    sys.exit(0 if success else 1)
