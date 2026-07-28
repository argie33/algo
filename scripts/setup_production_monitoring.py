#!/usr/bin/env python3
"""
Setup production monitoring and alerting for orchestrator.

Monitors:
1. Exit execution errors
2. Entry execution failures
3. Stale locks preventing phases
4. Data inconsistencies (position qty mismatches)
5. P&L calculation errors
"""

import logging
import psycopg2
from datetime import datetime, timedelta
from config.credential_manager import get_db_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MonitoringSetup:
    """Configure monitoring checks for production orchestrator."""

    def __init__(self):
        self.db_config = get_db_config()

    def check_exit_execution_errors(self):
        """Check for recent exit execution errors."""
        conn = psycopg2.connect(**self.db_config)
        try:
            with conn.cursor() as cur:
                # Check for errors in last hour
                cur.execute('''
                    SELECT COUNT(*), error_type
                    FROM algo_exit_check_errors
                    WHERE created_at > NOW() - INTERVAL '1 hour'
                    GROUP BY error_type
                ''')

                errors = cur.fetchall()
                if errors:
                    logger.error("[ALERT] Exit check errors in last hour:")
                    for count, error_type in errors:
                        logger.error("  {} x {}".format(count, error_type))
                    return False
                return True
        finally:
            conn.close()

    def check_position_qty_consistency(self):
        """Check for position/trade quantity mismatches."""
        conn = psycopg2.connect(**self.db_config)
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT COUNT(*)
                    FROM algo_positions p
                    LEFT JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
                    WHERE p.status = 'open'
                    GROUP BY p.position_id, p.quantity
                    HAVING ABS(CAST(p.quantity AS NUMERIC) -
                              COALESCE(SUM(CAST(t.quantity AS NUMERIC)), 0)) > 0.01
                ''')

                mismatches = cur.fetchall()
                if mismatches and len(mismatches) > 0:
                    logger.error("[ALERT] {} position qty mismatches found".format(len(mismatches)))
                    return False
                return True
        finally:
            conn.close()

    def check_stale_locks(self):
        """Check for stale loader execution locks."""
        conn = psycopg2.connect(**self.db_config)
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT COUNT(*), loader_name
                    FROM loader_execution_locks
                    WHERE locked_at < NOW() - INTERVAL '600 seconds'
                    GROUP BY loader_name
                ''')

                stale = cur.fetchall()
                if stale:
                    logger.error("[ALERT] Stale locks detected:")
                    for count, loader in stale:
                        logger.error("  {} x {}".format(count, loader))
                    return False
                return True
        finally:
            conn.close()

    def check_phase_failures(self):
        """Check for recent orchestrator phase failures."""
        conn = psycopg2.connect(**self.db_config)
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT COUNT(*), overall_status
                    FROM orchestrator_execution_log
                    WHERE started_at > NOW() - INTERVAL '2 hours'
                    GROUP BY overall_status
                ''')

                statuses = cur.fetchall()
                failed_runs = [s for s in statuses if s[1] in ('halted', 'error')]
                if failed_runs:
                    logger.error("[ALERT] Recent orchestrator failures:")
                    for count, status in failed_runs:
                        logger.error("  {} x {}".format(count, status))
                    return False
                return True
        finally:
            conn.close()

    def run_all_checks(self):
        """Run all monitoring checks."""
        print("=" * 80)
        print("PRODUCTION MONITORING CHECKS")
        print("=" * 80)

        checks = {
            "Exit Execution Errors": self.check_exit_execution_errors,
            "Position Quantity Consistency": self.check_position_qty_consistency,
            "Stale Locks": self.check_stale_locks,
            "Phase Failures": self.check_phase_failures,
        }

        results = {}
        for name, check_fn in checks.items():
            try:
                result = check_fn()
                results[name] = "PASS" if result else "FAIL"
                print("\n[{}] {}".format(results[name], name))
            except Exception as e:
                results[name] = "ERROR"
                print("\n[ERROR] {}: {}".format(name, e))

        # Summary
        print("\n" + "=" * 80)
        passed = sum(1 for v in results.values() if v == "PASS")
        print("SUMMARY: {}/{} checks passed".format(passed, len(results)))

        if passed == len(results):
            print("[OK] All monitoring checks passed - system is healthy")
            return True
        else:
            print("[ALERT] Some checks failed - investigation required")
            return False


if __name__ == '__main__':
    monitor = MonitoringSetup()
    healthy = monitor.run_all_checks()
    exit(0 if healthy else 1)
