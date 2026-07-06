#!/usr/bin/env python3
"""
Test script to verify orchestrator_execution_log table is writable
and that Phase 9 logging is properly wired.

Usage:
  python scripts/test_orchestrator_logging.py --check-writes
  python scripts/test_orchestrator_logging.py --check-phase9
  python scripts/test_orchestrator_logging.py --full
"""

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db import DatabaseContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def ensure_orchestrator_tables_exist() -> bool:
    """Verify orchestrator_execution_log table exists and create if needed."""
    logger.info("=" * 80)
    logger.info("STEP 1: Ensure orchestrator tables exist")
    logger.info("=" * 80)

    try:
        with DatabaseContext("write") as cur:
            # Create orchestrator_execution_log table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orchestrator_execution_log (
                    id SERIAL PRIMARY KEY,
                    run_id VARCHAR(50) NOT NULL UNIQUE,
                    run_date DATE NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    overall_status VARCHAR(20) NOT NULL,
                    phase_results JSONB,
                    summary TEXT,
                    halt_reason TEXT,
                    phases_completed INTEGER,
                    phases_halted INTEGER,
                    phases_errored INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_run_date
                ON orchestrator_execution_log(run_date DESC)
            """)

            logger.info("[OK] orchestrator_execution_log table exists or created")

            # Verify table is accessible
            cur.execute("SELECT COUNT(*) FROM orchestrator_execution_log")
            count = cur.fetchone()[0]
            logger.info(f"[OK] Table is readable: {count} existing records")

            return True
    except Exception as e:
        logger.error(f"[FAILED] Could not ensure orchestrator tables: {e}")
        return False


def test_orchestrator_writes() -> bool:
    """Insert a test record to verify table is writable."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Test writing to orchestrator_execution_log")
    logger.info("=" * 80)

    test_run_id = f"TEST-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    test_date = date.today()

    try:
        with DatabaseContext("write") as cur:
            # Insert test record
            phase_results = [
                {"phase": "1", "name": "data_freshness", "status": "success", "summary": "Test data fresh"},
                {"phase": "2", "name": "circuit_breakers", "status": "success", "summary": "Test circuit breaker ok"},
                {"phase": "9", "name": "reconciliation", "status": "success", "summary": "Test reconciliation ok"},
            ]

            cur.execute("""
                INSERT INTO orchestrator_execution_log
                (run_id, run_date, started_at, completed_at, overall_status, phase_results,
                 summary, halt_reason, phases_completed, phases_halted, phases_errored)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                test_run_id,
                test_date,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
                "success",
                json.dumps(phase_results),
                "Test execution successful",
                None,
                3,
                0,
                0,
            ))

            logger.info(f"[OK] Inserted test record: {test_run_id}")

            # Verify record was written
            cur.execute(
                "SELECT run_id, overall_status, phases_completed FROM orchestrator_execution_log WHERE run_id = %s",
                (test_run_id,)
            )
            result = cur.fetchone()
            if result:
                logger.info(f"[OK] Test record verified: {result}")
                return True
            else:
                logger.error(f"[FAILED] Test record not found after insert")
                return False

    except Exception as e:
        logger.error(f"[FAILED] Could not write test record: {e}")
        return False


def check_phase9_logging_wiring() -> bool:
    """Check if Phase 9 is properly calling log_phase_result_fn."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Check Phase 9 logging implementation")
    logger.info("=" * 80)

    phase9_file = project_root / "algo" / "orchestrator" / "phase9_reconciliation.py"

    if not phase9_file.exists():
        logger.error(f"[FAILED] Phase 9 file not found: {phase9_file}")
        return False

    with open(phase9_file, 'r') as f:
        phase9_code = f.read()

    # Check for key logging calls in Phase 9
    required_logs = [
        "log_phase_result_fn",
        "reconciliation",
        "pnl_validation",
        "exit_reconciliation_audit",
        "portfolio_snapshot",
        "circuit_breaker_metrics",
        "risk_metrics",
        "performance",
    ]

    missing_logs = []
    for log_name in required_logs:
        if f'"{log_name}"' not in phase9_code and f"'{log_name}'" not in phase9_code:
            missing_logs.append(log_name)

    if missing_logs:
        logger.warning(f"[WARN] Missing logging for: {missing_logs}")

    # Count log_phase_result_fn calls
    log_call_count = phase9_code.count("log_phase_result_fn(")
    logger.info(f"[OK] Found {log_call_count} log_phase_result_fn() calls in Phase 9")

    if log_call_count >= 8:
        logger.info("[OK] Phase 9 has comprehensive logging coverage")
        return True
    else:
        logger.warning(f"[WARN] Phase 9 has only {log_call_count} logging calls (expected ~8+)")
        return False


def check_orchestrator_logging_integration() -> bool:
    """Check if orchestrator.py properly integrates with execution_tracker."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 4: Check orchestrator.py logging integration")
    logger.info("=" * 80)

    orch_file = project_root / "algo" / "orchestration" / "orchestrator.py"

    if not orch_file.exists():
        logger.error(f"[FAILED] Orchestrator file not found: {orch_file}")
        return False

    with open(orch_file, 'r') as f:
        orch_code = f.read()

    # Check for key integration points
    checks = {
        "execution_tracker imported": "get_tracker()" in orch_code,
        "log_phase_result method defined": "def log_phase_result(" in orch_code,
        "orchestrator_execution_log written": "INSERT INTO orchestrator_execution_log" in orch_code,
        "save_execution_log called": "save_execution_log(" in orch_code or "execution_tracker" in orch_code,
    }

    all_ok = True
    for check_name, result in checks.items():
        status = "[OK]" if result else "[MISSING]"
        logger.info(f"{status} {check_name}")
        if not result:
            all_ok = False

    return all_ok


def query_recent_orchestrator_runs() -> bool:
    """Query recent orchestrator runs to see logging in action."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Query recent orchestrator runs")
    logger.info("=" * 80)

    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    run_id,
                    run_date,
                    overall_status,
                    phases_completed,
                    phases_halted,
                    phases_errored,
                    summary,
                    created_at
                FROM orchestrator_execution_log
                ORDER BY created_at DESC
                LIMIT 5
            """)

            results = cur.fetchall()
            if not results:
                logger.warning("[WARN] No orchestrator runs logged yet")
                return False

            logger.info(f"[OK] Found {len(results)} recent orchestrator runs:")
            for row in results:
                run_id, run_date, status, completed, halted, errored, summary, created = row
                logger.info(
                    f"  {run_id}: {status} on {run_date} "
                    f"(phases: {completed} ok, {halted} halted, {errored} error) - {summary[:60]}"
                )

            return True
    except Exception as e:
        logger.error(f"[FAILED] Could not query orchestrator runs: {e}")
        return False


def check_audit_log_entries() -> bool:
    """Check if phase logs are also being written to algo_audit_log."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 6: Check algo_audit_log for phase entries")
    logger.info("=" * 80)

    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    action_type,
                    status,
                    COUNT(*) as count
                FROM algo_audit_log
                WHERE action_type LIKE 'phase_%'
                GROUP BY action_type, status
                ORDER BY action_type DESC
                LIMIT 10
            """)

            results = cur.fetchall()
            if not results:
                logger.warning("[WARN] No phase logs in algo_audit_log yet")
                return False

            logger.info(f"[OK] Found {len(results)} phase log entries in algo_audit_log:")
            for action_type, status, count in results:
                logger.info(f"  {action_type}: {count} entries (status: {status})")

            return True
    except Exception as e:
        logger.error(f"[FAILED] Could not query algo_audit_log: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("ORCHESTRATOR LOGGING VERIFICATION")
    logger.info("=" * 80)

    results = {
        "Tables exist": ensure_orchestrator_tables_exist(),
        "Database writes": test_orchestrator_writes(),
        "Phase 9 logging": check_phase9_logging_wiring(),
        "Orchestrator integration": check_orchestrator_logging_integration(),
        "Audit log entries": check_audit_log_entries(),
        "Recent runs": query_recent_orchestrator_runs(),
    }

    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)

    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        logger.info(f"{status} {test_name}")

    all_passed = all(results.values())

    if all_passed:
        logger.info("\n[SUCCESS] All checks passed!")
        return 0
    else:
        logger.warning("\n[WARNING] Some checks failed. Review the fixes below.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
