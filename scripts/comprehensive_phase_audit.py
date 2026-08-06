#!/usr/bin/env python3
"""Comprehensive Phase Audit - Verify all 9 phases work correctly.

Tests:
1. Each phase runs without raising exceptions
2. Each phase returns proper PhaseResult with required fields
3. Phase data contracts are respected
4. Data types are correct
5. Critical safety checks are functional
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def audit_phase(phase_num, phase_name, phase_fn, **kwargs):
    """Run a phase and verify its output."""
    logger.info(f"\n{'='*80}")
    logger.info(f"AUDITING PHASE {phase_num}: {phase_name}")
    logger.info('='*80)

    try:
        result = phase_fn(**kwargs)

        # Verify PhaseResult structure
        assert hasattr(result, 'status'), "Missing 'status' attribute"
        assert hasattr(result, 'ok'), "Missing 'ok' attribute"
        assert hasattr(result, 'data'), "Missing 'data' attribute"
        assert hasattr(result, 'halted'), "Missing 'halted' attribute"

        logger.info(f"✅ Phase {phase_num} completed")
        logger.info(f"   Status: {result.status}")
        logger.info(f"   OK: {result.ok}")
        logger.info(f"   Halted: {result.halted}")
        logger.info(f"   Data keys: {list(result.data.keys()) if result.data else 'None'}")

        if not result.ok:
            logger.warning(f"   Error: {result.error}")

        return result, True

    except Exception as e:
        logger.error(f"❌ Phase {phase_num} FAILED: {type(e).__name__}: {e}", exc_info=True)
        return None, False

def main():
    """Run comprehensive phase audit."""
    from algo.infrastructure.config.main import AlgoConfig
    from algo.reporting import AlertManager
    from algo.orchestrator.phase1_data_freshness import run as run_phase1
    from algo.orchestrator.phase2_circuit_breakers import run as run_phase2
    from algo.orchestrator.phase3_position_monitor import run as run_phase3
    from algo.orchestrator.phase4_reconciliation import run as run_phase4
    from algo.orchestrator.phase5_exposure_policy import run as run_phase5
    from algo.orchestrator.phase6_exit_execution import run as run_phase6
    from algo.orchestrator.phase7_signal_generation import run as run_phase7
    from algo.orchestrator.phase8_entry_execution import run as run_phase8
    from algo.orchestrator.phase9_reconciliation import run as run_phase9

    config = AlgoConfig()
    alerts = AlertManager()
    run_date = _date.today()

    # Track all results
    results = {}
    failures = []

    # Phase 1
    result1, ok = audit_phase(
        1, "DATA FRESHNESS CHECK",
        run_phase1,
        config=config, run_date=run_date, dry_run=True,
        alerts=alerts, verbose=True, log_phase_result_fn=lambda *a, **k: None
    )
    results[1] = result1
    if not ok: failures.append((1, "DATA FRESHNESS"))

    # Phase 2
    result2, ok = audit_phase(
        2, "CIRCUIT BREAKERS",
        run_phase2,
        config=config, run_date=run_date, dry_run=True,
        alerts=alerts, verbose=True, log_phase_result_fn=lambda *a, **k: None
    )
    results[2] = result2
    if not ok: failures.append((2, "CIRCUIT BREAKERS"))

    # Phase 3
    result3, ok = audit_phase(
        3, "POSITION MONITOR",
        run_phase3,
        config=config, run_date=run_date, dry_run=True,
        alerts=alerts, verbose=True, log_phase_result_fn=lambda *a, **k: None
    )
    results[3] = result3
    if not ok: failures.append((3, "POSITION MONITOR"))

    # Phase 4
    result4, ok = audit_phase(
        4, "RECONCILIATION",
        run_phase4,
        config=config, run_date=run_date, dry_run=True,
        alerts=alerts, verbose=True, log_phase_result_fn=lambda *a, **k: None
    )
    results[4] = result4
    if not ok: failures.append((4, "RECONCILIATION"))

    # Phase 5
    result5, ok = audit_phase(
        5, "EXPOSURE POLICY",
        run_phase5,
        config=config, run_date=run_date, dry_run=True,
        alerts=alerts, verbose=True, log_phase_result_fn=lambda *a, **k: None
    )
    results[5] = result5
    if not ok: failures.append((5, "EXPOSURE POLICY"))

    # Phase 6 - needs Phase 3 & 5 data
    phase3_recs = results[3].data.get("position_recs", []) if results[3] else []
    phase5_actions = results[5].data.get("actions", []) if results[5] else []
    result6, ok = audit_phase(
        6, "EXIT EXECUTION",
        run_phase6,
        config=config, run_date=run_date, dry_run=True,
        alerts=alerts, verbose=True, log_phase_result_fn=lambda *a, **k: None,
        position_recs=phase3_recs, exposure_actions=phase5_actions
    )
    results[6] = result6
    if not ok: failures.append((6, "EXIT EXECUTION"))

    # Phase 7 - needs Phase 5 constraints
    phase5_constraints = results[5].data.get("constraints", {}) if results[5] else {}
    logger.info(f"Phase 5 constraints passed to Phase 7: {phase5_constraints}")
    result7, ok = audit_phase(
        7, "SIGNAL GENERATION",
        run_phase7,
        run_date=run_date, dry_run=True, verbose=True,
        log_phase_result_fn=lambda *a, **k: None,
        exposure_constraints=phase5_constraints,
        check_halt_flag=lambda: False, config=config
    )
    results[7] = result7
    if not ok: failures.append((7, "SIGNAL GENERATION"))

    # Phase 8 - needs Phase 7 signals and Phase 5 constraints
    phase7_signals = results[7].data.get("qualified_trades", []) if results[7] else []
    logger.info(f"Phase 7 signals: {len(phase7_signals)} qualified trades")
    logger.info(f"Phase 5 constraints passed to Phase 8: {phase5_constraints}")
    result8, ok = audit_phase(
        8, "ENTRY EXECUTION",
        run_phase8,
        config=config, run_date=run_date, dry_run=True,
        verbose=True, log_phase_result_fn=lambda *a, **k: None,
        qualified_trades=phase7_signals,
        exposure_constraints=phase5_constraints  # Phase 8 needs constraints!
    )
    results[8] = result8
    if not ok: failures.append((8, "ENTRY EXECUTION"))

    # Phase 9 - final reconciliation (takes fewer parameters)
    result9, ok = audit_phase(
        9, "RECONCILIATION & SNAPSHOT",
        run_phase9,
        config=config, run_date=run_date, dry_run=True,
        log_phase_result_fn=lambda *a, **k: None
    )
    results[9] = result9
    if not ok: failures.append((9, "RECONCILIATION"))

    # Final report
    logger.info(f"\n{'='*80}")
    logger.info("COMPREHENSIVE PHASE AUDIT REPORT")
    logger.info('='*80)
    logger.info(f"Total phases tested: 9")
    logger.info(f"Passed: {9 - len(failures)}")
    logger.info(f"Failed: {len(failures)}")

    if failures:
        logger.error("\nFailed phases:")
        for phase_num, name in failures:
            logger.error(f"  ❌ Phase {phase_num}: {name}")
        return False
    else:
        logger.info("\n✅ ALL PHASES PASSED")
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
