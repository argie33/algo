"""Real-time health monitoring for loader system.

Tracks loader performance, data freshness, and system health.
Provides early warning for potential issues.
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class LoaderHealthMonitor:
    """Monitors health of loader system."""

    def __init__(self, conn: Any):
        """Initialize monitor with database connection."""
        self.conn = conn
        self.status = HealthStatus.HEALTHY
        self.checks: list[dict[str, Any]] = []

    def check_loader_execution_rate(self, hours: int = 24) -> dict[str, Any]:
        """Check if loaders are executing at expected frequency."""
        cur = self.conn.cursor()
        cur.execute(f"""
            SELECT
                loader_name,
                COUNT(*) as executions,
                ROUND(100.0 * COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) / COUNT(*), 1) as success_rate
            FROM data_loader_runs
            WHERE execution_date > CURRENT_DATE - INTERVAL '{hours} hours'
            GROUP BY loader_name
            HAVING COUNT(*) = 0
        """)

        missing_loaders = cur.fetchall()
        check = {
            "name": "Loader Execution Rate",
            "status": HealthStatus.HEALTHY.value if not missing_loaders else HealthStatus.CRITICAL.value,
            "details": {
                "loaders_without_recent_runs": len(missing_loaders),
                "missing_loaders": [row[0] for row in missing_loaders],
            },
        }

        if missing_loaders:
            self.status = HealthStatus.CRITICAL
            logger.error(f"Critical: {len(missing_loaders)} loaders have no recent executions")

        return check

    def check_data_freshness(self) -> dict[str, Any]:
        """Check if critical output tables have fresh data."""
        cur = self.conn.cursor()

        tables_to_check = {
            "price_daily": ("date", 24),
            "technical_data_daily": ("date", 24),
            "stock_scores": ("created_at", 24),
            "buy_sell_daily": ("date", 24),
            "algo_metrics_daily": ("date", 24),
        }

        stale_tables = []
        for table, (date_col, max_hours) in tables_to_check.items():
            try:
                query = f"""
                    SELECT COUNT(*), MAX({date_col})
                    FROM {table}
                    WHERE {date_col} < CURRENT_TIMESTAMP - INTERVAL '{max_hours} hours'
                """
                cur.execute(query)
                stale_count, _max_date = cur.fetchone()

                if stale_count > 0:
                    pct_stale = 100 * stale_count / max(1, self._get_table_row_count(table))
                    if pct_stale > 10:
                        stale_tables.append((table, pct_stale))
            except Exception as e:
                logger.warning(f"Could not check freshness of {table}: {e!s}")

        check = {
            "name": "Data Freshness",
            "status": HealthStatus.HEALTHY.value if not stale_tables else HealthStatus.DEGRADED.value,
            "details": {
                "stale_tables": len(stale_tables),
                "tables_with_stale_data": stale_tables,
            },
        }

        if stale_tables:
            self.status = HealthStatus.DEGRADED
            for table, pct in stale_tables:
                logger.warning(f"Degraded: {table} has {pct:.1f}% stale data")

        return check

    def check_orchestrator_health(self) -> dict[str, Any]:
        """Check orchestrator execution health."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total_runs,
                COUNT(CASE WHEN overall_status = 'success' THEN 1 END) as successful,
                MAX(started_at) as latest_run
            FROM algo_orchestrator_runs
            WHERE started_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """)

        total, successful, latest = cur.fetchone()
        success_rate = (100 * successful / total) if total > 0 else 0

        check = {
            "name": "Orchestrator Health",
            "status": HealthStatus.HEALTHY.value if success_rate >= 80 else HealthStatus.DEGRADED.value,
            "details": {
                "total_runs_24h": total,
                "successful_runs": successful,
                "success_rate_pct": round(success_rate, 1),
                "latest_run": str(latest) if latest else None,
            },
        }

        if success_rate < 80:
            self.status = HealthStatus.DEGRADED
            logger.warning(f"Degraded: Orchestrator success rate {success_rate:.1f}%")

        return check

    def check_database_health(self) -> dict[str, Any]:
        """Check database connectivity and performance."""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM pg_tables WHERE table_schema = 'public'")
            table_count = cur.fetchone()[0]

            check = {
                "name": "Database Health",
                "status": HealthStatus.HEALTHY.value,
                "details": {
                    "tables": table_count,
                    "connection": "OK",
                },
            }
            return check
        except Exception as e:
            check = {
                "name": "Database Health",
                "status": HealthStatus.CRITICAL.value,
                "details": {
                    "error": str(e),
                },
            }
            self.status = HealthStatus.CRITICAL
            logger.error(f"Critical: Database connection failed: {e!s}")
            return check

    def _get_table_row_count(self, table: str) -> int:
        """Get row count for a table."""
        try:
            cur = self.conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]
        except Exception:
            return 0

    def get_health_report(self) -> dict[str, Any]:
        """Get comprehensive health report."""
        self.checks = [
            self.check_database_health(),
            self.check_loader_execution_rate(),
            self.check_data_freshness(),
            self.check_orchestrator_health(),
        ]

        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": self.status.value,
            "checks": self.checks,
        }

    def log_health_report(self):
        """Log health report."""
        report = self.get_health_report()
        logger.info(f"System Health: {report['overall_status'].upper()}")

        for check in report["checks"]:
            logger.info(f"  {check['name']}: {check['status'].upper()}")
            for key, value in check["details"].items():
                logger.info(f"    {key}: {value}")

        return report
