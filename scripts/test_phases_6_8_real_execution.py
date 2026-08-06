#!/usr/bin/env python3
"""Test Phase 6 and 8 with real execution logic (not dry-run) to find actual bugs.

This script bypasses the market hours guard to allow testing outside trading hours.
It uses the current database state to execute Phase 6 (exit execution) and Phase 8
(entry execution) with real trading logic and captures all errors for fixing.
"""

import os
import sys
import logging
from datetime import date as _date
from pathlib import Path

# Setup path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# CRITICAL: Set LOCAL_MODE FIRST before any imports
if "LAMBDA_TASK_ROOT" not in os.environ:
    os.environ.setdefault("LOCAL_MODE", "true")
    os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_phase_6():
    """Test Phase 6 (exit execution) with real execution logic."""
    logger.info("\n" + "="*80)
    logger.info("TESTING PHASE 6: EXIT EXECUTION (REAL EXECUTION MODE)")
    logger.info("="*80 + "\n")

    try:
        from algo.infrastructure.config.main import AlgoConfig
        from algo.reporting import AlertManager
        from algo.orchestrator.phase3_position_monitor import run as run_phase3
        from algo.orchestrator.phase5_exposure_policy import run as run_phase5
        from algo.orchestrator.phase6_exit_execution import run as run_phase6
        from utils.db import DatabaseContext

        # Load config
        config = AlgoConfig()
        logger.info(f"Config loaded successfully")

        # Get position recommendations from Phase 3 (simulate)
        alerts = AlertManager()
        run_date = _date.today()

        # Run Phase 3 to get position recommendations
        logger.info("Running Phase 3 (position monitor) to get recommendations...")
        phase3_result = run_phase3(
            config=config,
            run_date=run_date,
            dry_run=False,  # REAL execution
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=lambda *a, **k: None,
        )

        position_recs = phase3_result.data.get("position_recs", []) if phase3_result.data else []
        logger.info(f"Phase 3 returned {len(position_recs)} position recommendations")

        # Run Phase 5 to get exposure actions
        logger.info("Running Phase 5 (exposure policy) to get actions...")
        phase5_result = run_phase5(
            config=config,
            run_date=run_date,
            dry_run=False,  # REAL execution
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=lambda *a, **k: None,
        )

        exposure_actions = phase5_result.data.get("exposure_actions", []) if phase5_result.data else []
        logger.info(f"Phase 5 returned {len(exposure_actions)} exposure actions")

        # Now run Phase 6 with real execution
        logger.info("Running Phase 6 (exit execution) with REAL execution logic...")
        phase6_result = run_phase6(
            config=config,
            run_date=run_date,
            dry_run=False,  # REAL execution - this is the critical test
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=lambda *a, **k: None,
            position_recs=position_recs,
            exposure_actions=exposure_actions,
        )

        logger.info(f"Phase 6 completed with status: {phase6_result.status}")
        logger.info(f"Phase 6 data: {phase6_result.data}")
        logger.info("✅ PHASE 6 PASSED WITH REAL EXECUTION")
        return True

    except Exception as e:
        logger.exception(f"❌ PHASE 6 FAILED WITH REAL EXECUTION: {type(e).__name__}: {e}")
        return False

def test_phase_8():
    """Test Phase 8 (entry execution) with real execution logic."""
    logger.info("\n" + "="*80)
    logger.info("TESTING PHASE 8: ENTRY EXECUTION (REAL EXECUTION MODE)")
    logger.info("="*80 + "\n")

    try:
        from algo.infrastructure.config.main import AlgoConfig
        from algo.reporting import AlertManager
        from algo.orchestrator.phase7_signal_generation import run as run_phase7
        from algo.orchestrator.phase8_entry_execution import run as run_phase8

        # Load config
        config = AlgoConfig()
        logger.info(f"Config loaded successfully")

        # Get signals from Phase 7
        alerts = AlertManager()
        run_date = _date.today()

        # CRITICAL: Get exposure constraints from Phase 5
        logger.info("Running Phase 5 (exposure policy) to get constraints for Phase 7...")
        from algo.orchestrator.phase5_exposure_policy import run as run_phase5
        phase5_result = run_phase5(
            config=config,
            run_date=run_date,
            dry_run=False,  # REAL execution
            alerts=AlertManager(),
            verbose=True,
            log_phase_result_fn=lambda *a, **k: None,
        )
        exposure_constraints = phase5_result.data.get("constraints") if phase5_result.data else None
        logger.info(f"Phase 5 returned exposure_constraints: {exposure_constraints}")

        logger.info("Running Phase 7 (signal generation) to get entry signals...")
        phase7_result = run_phase7(
            run_date=run_date,
            dry_run=False,  # REAL execution
            verbose=True,
            log_phase_result_fn=lambda *a, **k: None,
            exposure_constraints=exposure_constraints,
            config=config.to_dict() if hasattr(config, 'to_dict') else config,
        )

        signals = phase7_result.data.get("qualified_trades", []) if phase7_result.data else []
        logger.info(f"Phase 7 returned {len(signals)} qualified trades")

        # Run Phase 8 with real execution
        logger.info("Running Phase 8 (entry execution) with REAL execution logic...")
        phase8_result = run_phase8(
            config=config,
            run_date=run_date,
            dry_run=False,  # REAL execution - this is the critical test
            verbose=True,
            log_phase_result_fn=lambda *a, **k: None,
            qualified_trades=signals,
        )

        logger.info(f"Phase 8 completed with status: {phase8_result.status}")
        logger.info(f"Phase 8 data: {phase8_result.data}")
        logger.info("✅ PHASE 8 PASSED WITH REAL EXECUTION")
        return True

    except Exception as e:
        logger.exception(f"❌ PHASE 8 FAILED WITH REAL EXECUTION: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    phase6_ok = test_phase_6()
    phase8_ok = test_phase_8()

    logger.info("\n" + "="*80)
    logger.info("TEST SUMMARY")
    logger.info("="*80)
    logger.info(f"Phase 6: {'✅ PASSED' if phase6_ok else '❌ FAILED'}")
    logger.info(f"Phase 8: {'✅ PASSED' if phase8_ok else '❌ FAILED'}")

    if not (phase6_ok and phase8_ok):
        logger.error("Some phases failed. Check logs above for details.")
        sys.exit(1)
    else:
        logger.info("All phases passed!")
        sys.exit(0)
