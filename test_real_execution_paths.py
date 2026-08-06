#!/usr/bin/env python3
"""Test Phase 6/8 real execution paths to find actual bugs.

This test:
1. Simulates real execution mode (not dry-run)
2. Checks constraint passing from Phase 5 → Phase 6/8
3. Validates trade execution logic
4. Checks for data integrity issues (orphaned trades, position mismatches)
"""

import os
import sys
os.environ.setdefault('LOCAL_MODE', 'true')
os.environ.setdefault('ENVIRONMENT', 'development')

from utils.dotenv_loader import load_env_local
load_env_local()

from datetime import date as _date
from datetime import datetime, timezone
import logging
import json

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Import orchestrator components
from algo.infrastructure.config.main import AlgoConfig
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_registry import PhaseRegistry
from algo.orchestrator.phase5_exposure_policy import run as run_phase5
from algo.orchestrator.phase6_exit_execution import run as run_phase6
from algo.orchestrator.phase8_entry_execution import run as run_phase8
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext

logger.info("=" * 70)
logger.info("PHASE 6/8 REAL EXECUTION PATH TEST")
logger.info("=" * 70)

# Setup
run_date = _date.today()
config = AlgoConfig()
alerts = AlertManager()
executor = OrchestratorPhaseExecutor(config, lambda: False)  # halt_check_fn returns False (not halted)

def log_phase_result_fn(phase_num, name, status, result_msg=""):
    """Stub for phase logging."""
    logger.info(f"  [{status.upper()}] Phase {phase_num} ({name}): {result_msg}")

# TEST 1: Check Phase 5 constraints are generated
print("\n[TEST 1] Phase 5 Exposure Constraints Generation")
print("-" * 70)
phase5_result = None
exposure_constraints = {}
try:
    # Note: In real execution, Phase 5 would read market conditions
    # For testing, we manually execute Phase 5
    phase5_result = run_phase5(
        config=config,
        run_date=run_date,
        dry_run=False,  # Real mode
        alerts=alerts,
        verbose=False,
        log_phase_result_fn=log_phase_result_fn,
    )

    if phase5_result.status not in ['ok', 'degraded']:
        logger.error(f"❌ Phase 5 failed: {phase5_result.error}")
        sys.exit(1)

    phase5_data = phase5_result.data or {}
    exposure_constraints = phase5_data.get("constraints", {})

    if not exposure_constraints:
        logger.error("❌ Phase 5 returned no constraints!")
        sys.exit(1)

    logger.info(f"✓ Phase 5 constraints generated:")
    for key in ['tier_name', 'halt_new_entries', 'max_concentration_pct', 'max_new_positions_today']:
        logger.info(f"  {key}: {exposure_constraints.get(key)}")

except Exception as e:
    logger.error(f"❌ Phase 5 execution failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# TEST 2: Check Phase 6 receives constraints properly
print("\n[TEST 2] Phase 6 Constraint Passthrough")
print("-" * 70)
try:
    # Get Phase 6 data from Phase 3 (position monitor)
    # Note: position_recommendations table doesn't exist - use algo_position_recommendations instead
    position_recs = []
    try:
        with DatabaseContext("read") as cur:
            # Try to fetch position recommendations - table may not exist in test DB
            cur.execute("""
                SELECT id, symbol, recommendation FROM algo_position_recommendations
                WHERE date_generated = %s
                LIMIT 10
            """, (run_date,))
            rows = cur.fetchall()
            for row in rows:
                position_recs.append({
                    'position_id': row[0],
                    'symbol': row[1],
                    'action': 'force_exit' if 'exit' in str(row[2]).lower() else 'hold'
                })
    except Exception as e:
        logger.warning(f"Could not get position recommendations (expected in test): {e}")
        position_recs = []

    # Get Phase 5 exposure_actions
    exposure_actions = []  # Phase 5 typically returns empty for this

    # Execute Phase 6 in REAL mode (not dry_run)
    # IMPORTANT: Match orchestrator.py's call signature exactly (line 1795)
    phase6_result = run_phase6(
        config,
        run_date,
        False,  # dry_run=False for REAL mode
        alerts,
        False,  # verbose=False
        log_phase_result_fn,
        position_recs,
        exposure_actions,
        executor=executor,
        exposure_constraints=exposure_constraints,  # Pass from Phase 5
    )

    if phase6_result.status not in ['ok', 'degraded']:
        logger.error(f"❌ Phase 6 failed: {phase6_result.error}")
        # Don't sys.exit() - continue testing to find more issues
    else:
        logger.info(f"✓ Phase 6 executed: status={phase6_result.status}")
        phase6_data = phase6_result.data or {}
        logger.info(f"  Exits executed: {phase6_data.get('exits_executed', 0)}")
        logger.info(f"  Stop-raises: {phase6_data.get('stop_raises_executed', 0)}")

except Exception as e:
    logger.error(f"❌ Phase 6 execution failed: {e}")
    import traceback
    traceback.print_exc()

# TEST 3: Check Phase 8 constraint handling
print("\n[TEST 3] Phase 8 Exposure Constraints Usage")
print("-" * 70)
try:
    # Phase 8 is called via executor in real flow
    # IMPORTANT: Match orchestrator.py's call signature exactly (line 1887)
    phase8_result = run_phase8(
        config,
        run_date,
        False,  # dry_run=False for REAL mode
        False,  # verbose=False
        log_phase_result_fn,
        check_halt_flag=lambda: False,  # halt_check_fn
        executor=executor,
    )

    if phase8_result.status not in ['ok', 'degraded', 'skipped']:
        logger.error(f"❌ Phase 8 failed: {phase8_result.error}")
    else:
        logger.info(f"✓ Phase 8 executed: status={phase8_result.status}")
        phase8_data = phase8_result.data or {}
        logger.info(f"  Trades executed: {phase8_data.get('trades_executed', 0)}")
        logger.info(f"  Trades skipped: {phase8_data.get('trades_skipped', 0)}")

except Exception as e:
    logger.error(f"❌ Phase 8 execution failed: {e}")
    import traceback
    traceback.print_exc()

# TEST 4: Check for data integrity issues
print("\n[TEST 4] Data Integrity Checks")
print("-" * 70)
try:
    with DatabaseContext("read") as cur:
        # Check for orphaned trades
        cur.execute("""
            SELECT COUNT(*) FROM algo_trades
            WHERE position_id IS NULL
            AND status IN ('filled', 'partially_filled', 'open')
            AND updated_at > now() - interval '1 hour'
        """)
        result = cur.fetchone()
        orphaned_count = result[0] if result else 0
        if orphaned_count > 0:
            logger.error(f"❌ Found {orphaned_count} orphaned trades (position_id=NULL) in past hour")
        else:
            logger.info("✓ No orphaned trades found")

        # Check for position/trade mismatches
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions ap
            WHERE ap.status = 'open'
            AND (ap.trade_ids_arr IS NULL OR array_length(ap.trade_ids_arr, 1) = 0)
        """)
        result = cur.fetchone()
        mismatch_count = result[0] if result else 0
        if mismatch_count > 0:
            logger.error(f"❌ Found {mismatch_count} positions with NULL/empty trade_ids_arr")
        else:
            logger.info("✓ All positions have valid trade_id references")

except Exception as e:
    logger.error(f"❌ Data integrity check failed: {e}")

print("\n" + "=" * 70)
logger.info("TEST COMPLETE - Check results above for issues")
print("=" * 70)
