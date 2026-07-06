#!/usr/bin/env python3
"""
Orchestrator Logging Monitoring & Alerting Integration

Provides reusable functions for:
- Health checks
- Alerting on failures
- Dashboard metrics
- Trend analysis
- Export to monitoring systems
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db import DatabaseContext


class OrchestratorLoggingMonitor:
    """Monitor orchestrator execution logs and provide health metrics."""

    @staticmethod
    def get_last_run() -> dict[str, Any] | None:
        """Get the last orchestrator run details."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        run_id, run_date, overall_status, started_at, completed_at,
                        phases_completed, phases_halted, phases_errored,
                        summary, halt_reason, phase_results
                    FROM orchestrator_execution_log
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
                result = cur.fetchone()
                if not result:
                    return None

                (
                    run_id, run_date, status, started_at, completed_at,
                    phases_completed, phases_halted, phases_errored,
                    summary, halt_reason, phase_results
                ) = result

                return {
                    "run_id": run_id,
                    "run_date": str(run_date),
                    "status": status,
                    "started_at": started_at.isoformat() if started_at else None,
                    "completed_at": completed_at.isoformat() if completed_at else None,
                    "duration_seconds": (
                        (completed_at - started_at).total_seconds()
                        if completed_at and started_at
                        else None
                    ),
                    "phases": {
                        "completed": phases_completed,
                        "halted": phases_halted,
                        "errored": phases_errored,
                    },
                    "summary": summary,
                    "halt_reason": halt_reason,
                    "phase_results": json.loads(phase_results) if phase_results else [],
                }
        except Exception as e:
            return None

    @staticmethod
    def get_success_rate(days: int = 7) -> dict[str, Any]:
        """Calculate orchestrator success rate over specified days."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN overall_status = 'success' THEN 1 ELSE 0 END) as success,
                        SUM(CASE WHEN overall_status = 'error' THEN 1 ELSE 0 END) as error,
                        SUM(CASE WHEN overall_status = 'halted' THEN 1 ELSE 0 END) as halted,
                        SUM(CASE WHEN overall_status = 'skipped' THEN 1 ELSE 0 END) as skipped
                    FROM orchestrator_execution_log
                    WHERE run_date >= CURRENT_DATE - INTERVAL '%d days'
                    """ % days
                )
                result = cur.fetchone()
                if not result:
                    return {}

                total, success, error, halted, skipped = result
                success_pct = (success / total * 100) if total > 0 else 0

                return {
                    "total_runs": total,
                    "success": success or 0,
                    "error": error or 0,
                    "halted": halted or 0,
                    "skipped": skipped or 0,
                    "success_pct": round(success_pct, 1),
                    "period_days": days,
                }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def get_phase9_metrics(days: int = 7) -> dict[str, Any]:
        """Get Phase 9 specific metrics."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total_logs,
                        COUNT(DISTINCT DATE(created_at)) as days_with_logs,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                        SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error,
                        SUM(CASE WHEN status = 'warn' THEN 1 ELSE 0 END) as warn
                    FROM algo_audit_log
                    WHERE action_type LIKE 'phase_9_%%'
                    AND created_at > NOW() - INTERVAL '%d days'
                    """ % days
                )
                result = cur.fetchone()
                if not result:
                    return {}

                total_logs, days_with_logs, success, error, warn = result
                total_logs = total_logs or 0
                success_pct = (success / total_logs * 100) if total_logs > 0 else 0

                return {
                    "total_log_entries": total_logs,
                    "days_active": days_with_logs or 0,
                    "success": success or 0,
                    "error": error or 0,
                    "warn": warn or 0,
                    "success_pct": round(success_pct, 1),
                    "period_days": days,
                }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def check_orchestrator_running(hours: int = 24) -> bool:
        """Check if orchestrator has run recently."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM orchestrator_execution_log
                    WHERE created_at > NOW() - INTERVAL '%d hours'
                    """ % hours
                )
                count = cur.fetchone()[0]
                return count > 0
        except:
            return False

    @staticmethod
    def get_error_summary(hours: int = 24) -> list[dict[str, Any]]:
        """Get summary of recent errors in Phase 9."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        action_type,
                        status,
                        COUNT(*) as count,
                        MAX(created_at) as latest
                    FROM algo_audit_log
                    WHERE action_type LIKE 'phase_9_%%'
                    AND status IN ('error', 'critical')
                    AND created_at > NOW() - INTERVAL '%d hours'
                    GROUP BY action_type, status
                    ORDER BY count DESC
                    """ % hours
                )
                results = cur.fetchall()
                return [
                    {
                        "step": action_type,
                        "status": status,
                        "count": count,
                        "latest": latest.isoformat() if latest else None,
                    }
                    for action_type, status, count, latest in results
                ]
        except Exception as e:
            return []

    @staticmethod
    def get_run_duration_stats(days: int = 7) -> dict[str, Any]:
        """Get orchestrator run duration statistics."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - started_at))), 1) as avg_duration,
                        MAX(EXTRACT(EPOCH FROM (completed_at - started_at))) as max_duration,
                        MIN(EXTRACT(EPOCH FROM (completed_at - started_at))) as min_duration
                    FROM orchestrator_execution_log
                    WHERE started_at > NOW() - INTERVAL '%d days'
                    AND completed_at IS NOT NULL
                    """ % days
                )
                result = cur.fetchone()
                if not result:
                    return {}

                avg_duration, max_duration, min_duration = result
                return {
                    "avg_duration_seconds": avg_duration or 0,
                    "max_duration_seconds": max_duration or 0,
                    "min_duration_seconds": min_duration or 0,
                    "period_days": days,
                }
        except Exception as e:
            return {"error": str(e)}


# ============================================================================
# Alert Generation Functions
# ============================================================================


def generate_health_alert() -> dict[str, Any]:
    """Generate a health status alert."""
    monitor = OrchestratorLoggingMonitor()

    alerts = []
    metrics = {}

    # Check if orchestrator is running
    if not monitor.check_orchestrator_running(hours=24):
        alerts.append({
            "severity": "CRITICAL",
            "message": "Orchestrator has not run in the last 24 hours",
            "action": "Check orchestrator scheduler and logs",
        })

    # Get success rate
    success_metrics = monitor.get_success_rate(days=1)
    metrics["success_rate"] = success_metrics

    if success_metrics.get("success_pct", 100) < 70:
        alerts.append({
            "severity": "WARNING",
            "message": f"Low orchestrator success rate: {success_metrics['success_pct']}%",
            "details": success_metrics,
            "action": "Review orchestrator_execution_log for failures",
        })

    # Get Phase 9 metrics
    phase9_metrics = monitor.get_phase9_metrics(days=1)
    metrics["phase9"] = phase9_metrics

    if phase9_metrics.get("success_pct", 100) < 80:
        alerts.append({
            "severity": "WARNING",
            "message": f"Phase 9 success rate low: {phase9_metrics['success_pct']}%",
            "details": phase9_metrics,
            "action": "Review Phase 9 logs in algo_audit_log",
        })

    # Check for recent errors
    error_summary = monitor.get_error_summary(hours=6)
    if error_summary:
        alerts.append({
            "severity": "WARNING",
            "message": f"Phase 9 errors detected in last 6 hours",
            "details": error_summary,
            "action": "Review error logs",
        })

    # Get last run
    last_run = monitor.get_last_run()
    metrics["last_run"] = last_run

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
        "metrics": metrics,
        "status": "HEALTHY" if not alerts else "UNHEALTHY",
    }


# ============================================================================
# Export Functions for Monitoring Systems
# ============================================================================


def export_to_cloudwatch_metrics() -> dict[str, float]:
    """Export metrics for CloudWatch."""
    monitor = OrchestratorLoggingMonitor()

    metrics = {}

    # Success rate
    success = monitor.get_success_rate(days=1)
    metrics["OrchestratorSuccessRate"] = success.get("success_pct", 0)
    metrics["OrchestratorTotalRuns"] = success.get("total_runs", 0)

    # Phase 9 metrics
    phase9 = monitor.get_phase9_metrics(days=1)
    metrics["Phase9SuccessRate"] = phase9.get("success_pct", 0)
    metrics["Phase9Errors"] = phase9.get("error", 0)

    # Run duration
    duration = monitor.get_run_duration_stats(days=1)
    metrics["OrchestratorAvgDuration"] = duration.get("avg_duration_seconds", 0)

    return metrics


def export_to_prometheus() -> str:
    """Export metrics in Prometheus format."""
    metrics = export_to_cloudwatch_metrics()

    lines = []
    lines.append("# HELP orchestrator_success_rate Orchestrator success rate percentage")
    lines.append("# TYPE orchestrator_success_rate gauge")
    lines.append(f"orchestrator_success_rate {metrics.get('OrchestratorSuccessRate', 0)}")

    lines.append("# HELP phase9_success_rate Phase 9 success rate percentage")
    lines.append("# TYPE phase9_success_rate gauge")
    lines.append(f"phase9_success_rate {metrics.get('Phase9SuccessRate', 0)}")

    lines.append("# HELP phase9_errors Phase 9 error count")
    lines.append("# TYPE phase9_errors counter")
    lines.append(f"phase9_errors {metrics.get('Phase9Errors', 0)}")

    lines.append("# HELP orchestrator_avg_duration Average orchestrator run duration in seconds")
    lines.append("# TYPE orchestrator_avg_duration gauge")
    lines.append(f"orchestrator_avg_duration {metrics.get('OrchestratorAvgDuration', 0)}")

    return "\n".join(lines)


# ============================================================================
# Example Usage
# ============================================================================


def main():
    """Demonstrate monitoring functions."""
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("=" * 80)
    logger.info("ORCHESTRATOR LOGGING MONITORING EXAMPLES")
    logger.info("=" * 80)

    monitor = OrchestratorLoggingMonitor()

    # Example 1: Get last run
    logger.info("\n1. Last Orchestrator Run:")
    last_run = monitor.get_last_run()
    if last_run:
        logger.info(f"   Run ID: {last_run['run_id']}")
        logger.info(f"   Status: {last_run['status']}")
        logger.info(f"   Duration: {last_run['duration_seconds']}s")
    else:
        logger.warning("   No runs found")

    # Example 2: Get success rate
    logger.info("\n2. Success Rate (Last 7 Days):")
    success = monitor.get_success_rate(days=7)
    logger.info(f"   Total: {success.get('total_runs', 0)}")
    logger.info(f"   Success: {success.get('success_pct', 0)}%")

    # Example 3: Get Phase 9 metrics
    logger.info("\n3. Phase 9 Metrics:")
    phase9 = monitor.get_phase9_metrics(days=7)
    logger.info(f"   Log entries: {phase9.get('total_log_entries', 0)}")
    logger.info(f"   Success rate: {phase9.get('success_pct', 0)}%")

    # Example 4: Check if running
    logger.info("\n4. Orchestrator Health:")
    is_running = monitor.check_orchestrator_running(hours=24)
    logger.info(f"   Running: {'Yes' if is_running else 'No'}")

    # Example 5: Generate health alert
    logger.info("\n5. Health Alert:")
    alert = generate_health_alert()
    logger.info(f"   Status: {alert['status']}")
    logger.info(f"   Alerts: {len(alert['alerts'])}")
    for a in alert['alerts']:
        logger.warning(f"   - {a['severity']}: {a['message']}")

    # Example 6: Export metrics
    logger.info("\n6. CloudWatch Metrics:")
    metrics = export_to_cloudwatch_metrics()
    for name, value in metrics.items():
        logger.info(f"   {name}: {value}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ Monitoring examples complete")


if __name__ == "__main__":
    main()
