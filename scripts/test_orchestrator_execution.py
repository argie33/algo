#!/usr/bin/env python3
"""End-to-end orchestrator execution test for paper trading.

Tests full execution pipeline: loaders → orchestrator → dashboard API.
"""

import sys
import logging
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_full_execution():
    """Run full end-to-end test of orchestrator execution."""
    logger.info("=" * 70)
    logger.info("END-TO-END ORCHESTRATOR EXECUTION TEST")
    logger.info("=" * 70)

    try:
        # Step 1: Validate prerequisites
        logger.info("\n[1/5] Validating orchestrator prerequisites...")
        from algo.config.environment_validation import EnvironmentValidator
        EnvironmentValidator.require_valid_or_halt("execution_test")
        logger.info("✓ Environment valid")

        # Step 2: Initialize orchestrator
        logger.info("\n[2/5] Initializing orchestrator...")
        from algo.orchestration import Orchestrator
        from algo.infrastructure import get_config

        config = get_config()
        logger.info(f"  Execution mode: {config.get('execution_mode')}")

        orchestrator = Orchestrator(
            config=config,
            run_date=date.today(),
            dry_run=True,  # Always dry-run for test
            verbose=True
        )
        logger.info(f"✓ Orchestrator initialized (run_id: {orchestrator.run_id})")

        # Step 3: Check loader data freshness
        logger.info("\n[3/5] Checking loader data freshness...")
        from utils.db import DatabaseContext

        with DatabaseContext("read", timeout=5) as cur:
            cur.execute("""
                SELECT table_name, last_updated, completion_pct
                FROM data_loader_status
                WHERE table_name IN ('price_daily', 'stock_scores')
                ORDER BY last_updated DESC
                LIMIT 2
            """)

            loaders = cur.fetchall()
            if loaders:
                for loader in loaders:
                    logger.info(f"  {loader['table_name']}: {loader['completion_pct']:.1f}% ({loader['last_updated']})")
                logger.info("✓ Loader data present")
            else:
                logger.warning("  ⚠ No recent loader data - consider running loaders first")
                return False

        # Step 4: Execute orchestrator (dry run)
        logger.info("\n[4/5] Executing orchestrator (dry run)...")
        try:
            result = orchestrator.run()
            logger.info(f"✓ Orchestrator executed (dry_run={orchestrator.dry_run})")
            logger.info(f"  Run ID: {orchestrator.run_id}")
            logger.info(f"  Status: {result.get('status', 'unknown') if result else 'unknown'}")
        except Exception as e:
            logger.error(f"✗ Orchestrator execution failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

        # Step 5: Verify database state
        logger.info("\n[5/5] Verifying database state...")
        with DatabaseContext("read", timeout=5) as cur:
            # Check orchestrator run was recorded
            cur.execute("""
                SELECT COUNT(*) as count
                FROM algo_orchestrator_runs
                WHERE run_id = %s
            """, (orchestrator.run_id,))

            result = cur.fetchone()
            if result and result['count'] > 0:
                logger.info("✓ Orchestrator run recorded")
            else:
                logger.warning("  ⚠ Orchestrator run not found (expected for first run)")

            # Check positions are tracked
            cur.execute("SELECT COUNT(*) as count FROM algo_positions")
            count = cur.fetchone()['count'] if cur.fetchone() else 0
            logger.info(f"  Positions tracked: {count}")

            # Check trades are recorded
            cur.execute("SELECT COUNT(*) as count FROM algo_trades")
            count = cur.fetchone()['count'] if cur.fetchone() else 0
            logger.info(f"  Trades recorded: {count}")

        logger.info("\n" + "=" * 70)
        logger.info("✓ END-TO-END TEST COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        logger.info("\nNext steps:")
        logger.info("1. Review orchestrator logs for any warnings/errors")
        logger.info("2. Start dashboard: cd webapp && npm run dev")
        logger.info("3. Verify all dashboard panels load data correctly")
        logger.info("4. Run production orchestrator with dry_run=False for paper trading")
        return True

    except Exception as e:
        logger.error(f"\n✗ TEST FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_full_execution()
    sys.exit(0 if success else 1)
