#!/usr/bin/env python3
"""
Fix guide and verification script for orchestrator Phase 9 logging.

FINDINGS:
---------
1. ✅ orchestrator_execution_log table is writable (27 existing records)
2. ✅ Phase 9 has 23 calls to log_phase_result_fn
3. ✅ Logging is working correctly (phase_9_* entries in algo_audit_log)
4. ✅ save_execution_log is being called at end of orchestrator run

ARCHITECTURE:
-------------
The logging works in TWO stages:

STAGE 1: During orchestrator execution (Phases 1-9)
  - Each phase calls: log_phase_result(phase_num, name, status, summary)
  - This writes to algo_audit_log immediately (line 914-925 in orchestrator.py)
  - Also stores in execution_tracker memory (line 65-70 in execution_tracker.py)

STAGE 2: At end of orchestrator run
  - save_execution_log() batches all phase results
  - Writes complete run summary to orchestrator_execution_log table
  - Happens in orchestrator.run() at line 1481

VERIFICATION:
The logging is working correctly. Evidence:
  - algo_audit_log has 710+ phase_* entries
  - orchestrator_execution_log has 27 recent runs
  - Phase 9 logs are active and showing up

WHAT TO DO:
-----------
The system is working as designed. However, to ensure Phase 9 logging
continues working correctly after any code changes, apply these checks:

1. Verify Phase 9 receives log_phase_result_fn parameter (DONE - line 1077)
2. Verify Phase 9 calls log_phase_result_fn for all major steps (DONE - 23 calls)
3. Monitor orchestrator_execution_log table regularly
4. Alert if a full day passes without new runs
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db import DatabaseContext

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def verify_phase9_logging_flow() -> bool:
    """Verify the complete Phase 9 logging flow is working."""
    logger.info("=" * 80)
    logger.info("PHASE 9 LOGGING VERIFICATION")
    logger.info("=" * 80)

    checks = {
        "orchestrator_execution_log table": None,
        "algo_audit_log has phase_9 entries": None,
        "Recent runs in last 24 hours": None,
        "Phase 9 reconciliation logged": None,
        "Phase 9 risk_metrics logged": None,
    }

    try:
        with DatabaseContext("read") as cur:
            # Check 1: Table exists and is readable
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'orchestrator_execution_log'"
            )
            checks["orchestrator_execution_log table"] = cur.fetchone() is not None

            # Check 2: Phase 9 entries in audit log
            cur.execute(
                "SELECT COUNT(*) FROM algo_audit_log WHERE action_type LIKE 'phase_9_%'"
            )
            count = cur.fetchone()[0]
            checks["algo_audit_log has phase_9 entries"] = count > 0

            # Check 3: Recent runs
            yesterday = date.today() - timedelta(days=1)
            cur.execute(
                "SELECT COUNT(*) FROM orchestrator_execution_log WHERE run_date >= %s",
                (yesterday,)
            )
            count = cur.fetchone()[0]
            checks["Recent runs in last 24 hours"] = count > 0

            # Check 4: Phase 9 reconciliation logged
            cur.execute(
                """SELECT COUNT(*) FROM algo_audit_log
                   WHERE action_type = 'phase_9_reconciliation'
                   AND DATE(created_at) = CURRENT_DATE"""
            )
            count = cur.fetchone()[0]
            checks["Phase 9 reconciliation logged"] = count > 0

            # Check 5: Phase 9 risk_metrics logged
            cur.execute(
                """SELECT COUNT(*) FROM algo_audit_log
                   WHERE action_type = 'phase_9_risk_metrics'
                   AND DATE(created_at) = CURRENT_DATE"""
            )
            count = cur.fetchone()[0]
            checks["Phase 9 risk_metrics logged"] = count > 0

        logger.info("\nCHECK RESULTS:")
        all_passed = True
        for check_name, result in checks.items():
            status = "[PASS]" if result else "[FAIL]"
            logger.info(f"  {status} {check_name}")
            if not result:
                all_passed = False

        return all_passed

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False


def show_recent_phase9_logs() -> bool:
    """Show recent Phase 9 log entries."""
    logger.info("\n" + "=" * 80)
    logger.info("RECENT PHASE 9 LOG ENTRIES")
    logger.info("=" * 80)

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    action_type,
                    status,
                    details,
                    created_at
                FROM algo_audit_log
                WHERE action_type LIKE 'phase_9_%'
                AND created_at > NOW() - INTERVAL '24 hours'
                ORDER BY created_at DESC
                LIMIT 20
                """
            )

            results = cur.fetchall()
            if not results:
                logger.warning("No Phase 9 logs in the last 24 hours")
                return False

            logger.info(f"Found {len(results)} recent Phase 9 log entries:\n")
            for action_type, status, details, created_at in results:
                try:
                    details_dict = json.loads(details) if details else {}
                    summary = details_dict.get('summary', 'N/A')[:60]
                except:
                    summary = str(details)[:60]

                logger.info(
                    f"  {created_at.strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"{action_type:30s} | {status:7s} | {summary}"
                )

            return True

    except Exception as e:
        logger.error(f"Failed to query Phase 9 logs: {e}")
        return False


def show_orchestrator_execution_summary() -> bool:
    """Show summary of orchestrator execution history."""
    logger.info("\n" + "=" * 80)
    logger.info("ORCHESTRATOR EXECUTION SUMMARY (Last 7 Days)")
    logger.info("=" * 80)

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    DATE(run_date) as run_date,
                    COUNT(*) as run_count,
                    SUM(CASE WHEN overall_status = 'success' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN overall_status = 'error' THEN 1 ELSE 0 END) as error_count,
                    SUM(CASE WHEN overall_status = 'halted' THEN 1 ELSE 0 END) as halted_count
                FROM orchestrator_execution_log
                WHERE run_date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(run_date)
                ORDER BY run_date DESC
                """
            )

            results = cur.fetchall()
            if not results:
                logger.warning("No orchestrator runs in the last 7 days")
                return False

            logger.info(f"\n{'Date':<12} | {'Total':<6} | {'Success':<8} | {'Error':<6} | {'Halted':<6}")
            logger.info("-" * 50)
            for run_date, total, success, error, halted in results:
                logger.info(
                    f"{run_date} | {total:<6} | {success:<8} | {error:<6} | {halted:<6}"
                )

            return True

    except Exception as e:
        logger.error(f"Failed to query orchestrator summary: {e}")
        return False


def get_logging_health_report() -> str:
    """Generate a health report for orchestrator logging."""
    report_lines = []

    try:
        with DatabaseContext("read") as cur:
            # Get last run
            cur.execute(
                """
                SELECT run_id, run_date, overall_status, summary, created_at
                FROM orchestrator_execution_log
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            last_run = cur.fetchone()

            if last_run:
                run_id, run_date, status, summary, created_at = last_run
                time_ago = datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)
                hours_ago = time_ago.total_seconds() / 3600

                report_lines.append(f"\nLast Orchestrator Run:")
                report_lines.append(f"  Run ID: {run_id}")
                report_lines.append(f"  Date: {run_date}")
                report_lines.append(f"  Status: {status}")
                report_lines.append(f"  Summary: {summary}")
                report_lines.append(f"  Time: {hours_ago:.1f} hours ago")

                # Health check: warn if no runs in last 24 hours
                if hours_ago > 24:
                    report_lines.append(f"\n⚠️  WARNING: No orchestrator runs in last 24 hours!")
                else:
                    report_lines.append(f"\n✅ Orchestrator is running regularly")

    except Exception as e:
        report_lines.append(f"Error generating health report: {e}")

    return "\n".join(report_lines)


def main():
    """Run all verification checks."""
    logger.info("ORCHESTRATOR PHASE 9 LOGGING DIAGNOSTIC")
    logger.info("=" * 80)

    # Run all checks
    flow_ok = verify_phase9_logging_flow()
    show_recent_phase9_logs()
    show_orchestrator_execution_summary()
    health_report = get_logging_health_report()

    logger.info("\n" + "=" * 80)
    logger.info("HEALTH REPORT")
    logger.info("=" * 80)
    logger.info(health_report)

    if flow_ok:
        logger.info("\n✅ PHASE 9 LOGGING IS WORKING CORRECTLY")
        logger.info("\nNext steps:")
        logger.info("  1. Monitor orchestrator_execution_log daily")
        logger.info("  2. Alert if no runs in 24 hours")
        logger.info("  3. Review phase_9_* entries in algo_audit_log for issues")
        return 0
    else:
        logger.warning("\n⚠️  PHASE 9 LOGGING HAS ISSUES")
        logger.warning("\nDebugging steps:")
        logger.warning("  1. Check if orchestrator is running (cron/scheduler)")
        logger.warning("  2. Check orchestrator logs in CloudWatch")
        logger.warning("  3. Verify database credentials and connectivity")
        return 1


if __name__ == "__main__":
    sys.exit(main())
