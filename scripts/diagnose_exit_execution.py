#!/usr/bin/env python3
"""Diagnose Phase 6 exit execution issues.

This script tests Phase 6 in real (non-dry-run) mode to identify actual failure modes
that don't show up in dry-run testing.
"""

import os
import sys
import logging
from datetime import date as _date

# Setup environment
os.environ['ENVIRONMENT'] = 'development'
os.environ['LOCAL_MODE'] = 'true'

logging.basicConfig(level=logging.DEBUG, format='%(name)s: %(message)s')
logger = logging.getLogger(__name__)

def test_phase6_execution():
    """Test Phase 6 exit execution with real database state."""
    from algo.infrastructure import AlgoConfig
    from algo.orchestration.halt_flag_manager import HaltFlagManager
    from algo.reporting import AlertManager
    from algo.orchestrator.phase6_exit_execution import run as run_phase6
    from algo.orchestrator.phase_result import PhaseResult
    from utils.db import DatabaseContext

    logger.info("=" * 80)
    logger.info("PHASE 6 REAL EXECUTION TEST")
    logger.info("=" * 80)

    # Load config
    config = AlgoConfig()
    logger.info(f"Config loaded: execution_mode={config.get('execution_mode')}")

    # Check database state
    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
        open_positions = cur.fetchone()[0]
        logger.info(f"Open positions in DB: {open_positions}")

        # Check for orphaned trades
        cur.execute("""SELECT COUNT(*) FROM algo_trades
                       WHERE position_id IS NULL AND status IN ('filled', 'open')""")
        orphaned = cur.fetchone()[0]
        logger.info(f"Orphaned trades: {orphaned}")

        # Check exposure daily for regime
        cur.execute("""SELECT regime, is_entry_allowed, exposure_pct
                       FROM market_exposure_daily WHERE date = CURRENT_DATE LIMIT 1""")
        daily = cur.fetchone()
        if daily:
            logger.info(f"Market exposure: regime={daily[0]}, entry_allowed={daily[1]}, exposure={daily[2]}%")
        else:
            logger.warning("No market exposure data for today")

    # Try to run Phase 6 with real execution
    try:
        alerts = AlertManager()
        halt_mgr = HaltFlagManager(alerts, lambda *args, **kw: None)

        # Get Phase 3 position recommendations (empty list for now)
        position_recs = []

        # Get Phase 5 exposure actions (empty list for now)
        exposure_actions = []

        logger.info("\n[ATTEMPT 1] Running Phase 6 with dry_run=True (should work)...")
        result_dry = run_phase6(
            config=config,
            run_date=_date.today(),
            dry_run=True,
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=lambda *args, **kw: None,
            position_recs=position_recs,
            exposure_actions=exposure_actions,
            check_halt_flag=lambda: False,
            executor=None,
        )
        logger.info(f"Dry-run result: {result_dry.status}")

        logger.info("\n[ATTEMPT 2] Running Phase 6 with dry_run=False (real execution)...")
        result_real = run_phase6(
            config=config,
            run_date=_date.today(),
            dry_run=False,
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=lambda *args, **kw: None,
            position_recs=position_recs,
            exposure_actions=exposure_actions,
            check_halt_flag=lambda: False,
            executor=None,
        )
        logger.info(f"Real execution result: {result_real.status}")
        logger.info(f"Error: {result_real.error if result_real.error else 'None'}")

    except Exception as e:
        logger.error(f"EXCEPTION in Phase 6: {type(e).__name__}: {e}", exc_info=True)
        return False

    logger.info("\n" + "=" * 80)
    logger.info("DIAGNOSIS COMPLETE")
    logger.info("=" * 80)
    return True

if __name__ == '__main__':
    success = test_phase6_execution()
    sys.exit(0 if success else 1)
