#!/usr/bin/env python3
"""Database health monitoring specialist for Orchestrator.

Extracted responsibilities:
- Database connectivity checks
- Connection pool monitoring
- Table validation
- System diagnostics
- Verifying ECS task termination (called by Orchestrator._kill_long_running_loaders())

A full duplicate of Orchestrator._kill_long_running_loaders() itself used to live
here too (dead code, never called - only verify_task_stopped() below was actually
used by the orchestrator) and was removed 2026-08-05.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

import psycopg2

from algo.infrastructure.constants import DB_STATEMENT_TIMEOUT_MS
from utils.db import DatabaseContext, assert_safe_table

logger = logging.getLogger(__name__)


class DatabaseHealthMonitor:
    """Monitor database connectivity, pool health, and long-running tasks."""

    def __init__(self, alerts: Any) -> None:
        """Initialize with alert manager for reporting health issues.

        Args:
            alerts: AlertManager instance for escalation
        """
        self.alerts = alerts

    def check_db_connectivity(self) -> bool:
        """Test if database is reachable. Returns True if OK, False if failed."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT 1")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def check_connection_pool_health(self) -> None:
        """Monitor RDS connection pool and alert if approaching limits."""
        try:
            from algo.monitoring import check_stuck_connections, get_pool_status

            status = get_pool_status()
            logger.debug(
                f"[RDS_POOL] Status: {status['active_connections']}/{status['max_connections']} "
                f"({status['usage_pct']:.0f}%)"
            )

            if status["stuck_connections_count"] > 0:
                logger.warning(f"[RDS_POOL] Found {status['stuck_connections_count']} stuck connections")
                check_stuck_connections()
        except (KeyError, ValueError, AttributeError) as e:
            logger.warning(f"[RDS_POOL] Could not check connection pool health: {e}")

    def health_check_diagnostics(self) -> None:
        """Log system health status: what's working, what's not, what's stale."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"SET statement_timeout = {DB_STATEMENT_TIMEOUT_MS}"
                )  # Configurable timeout for large table scans

                tables_to_check = [
                    ("price_daily", "Prices"),
                    ("market_health_daily", "Market health"),
                    ("market_exposure_daily", "Market exposure"),
                    ("buy_sell_daily", "Buy/sell signals (Phase 5)"),
                    ("trend_template_data", "Trend template"),
                    ("sector_ranking", "Sector ranking"),
                ]

                logger.info("  Table Freshness Status:")
                try:
                    for table, _desc in tables_to_check:
                        assert_safe_table(table)

                    union_parts = []
                    for table, _desc in tables_to_check:
                        table_safe = assert_safe_table(table)
                        union_parts.append(
                            f"SELECT '{table}' as table_name, MAX(date) as latest_date FROM {table_safe}"
                        )

                    union_query = " UNION ALL ".join(union_parts)
                    cur.execute(union_query)

                    dates_by_table = {}
                    for row in cur.fetchall():
                        row_dict = dict(row)
                        dates_by_table[row_dict["table_name"]] = row_dict["latest_date"]

                    for table, desc in tables_to_check:
                        try:
                            latest_date = dates_by_table.get(table)
                            if latest_date:
                                from datetime import date as date_type
                                from datetime import datetime as dt

                                if isinstance(latest_date, date_type) and not isinstance(latest_date, datetime):
                                    latest_dt = dt.combine(latest_date, dt.min.time()).replace(tzinfo=timezone.utc)
                                elif isinstance(latest_date, datetime) and latest_date.tzinfo is None:
                                    latest_dt = latest_date.replace(tzinfo=timezone.utc)
                                else:
                                    latest_dt = (
                                        latest_date
                                        if isinstance(latest_date, datetime)
                                        else dt.fromisoformat(str(latest_date)).replace(tzinfo=timezone.utc)
                                    )
                                age = (datetime.now(timezone.utc) - latest_dt).days
                                logger.info(f"    [{age}d old] {desc:20s}: {latest_date}")
                            else:
                                logger.info(f"    [EMPTY] {desc:20s}: no data")
                        except (
                            psycopg2.DatabaseError,
                            psycopg2.OperationalError,
                        ) as t_err:
                            logger.warning(f"    [ERROR] {desc:20s}: {t_err}")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(f"  Could not fetch table freshness: {e}")

                try:
                    cur.execute("""
                        SELECT table_name, status, last_updated
                        FROM data_loader_status
                        WHERE table_name IN ('price_daily', 'buy_sell_daily', 'market_health_daily', 'market_exposure_daily')
                        ORDER BY table_name
                    """)
                    logger.info("  Loader Status:")
                    for row in cur.fetchall():
                        logger.info(f"    {row[0]:25s}: {row[1]:10s} (updated {row[2]})")
                except (
                    psycopg2.DatabaseError,
                    psycopg2.OperationalError,
                ) as loader_err:
                    logger.warning(f"    Could not check loader status: {loader_err}")

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"  Health check failed: {e}")

    def verify_task_stopped(
        self,
        ecs: Any,
        cluster: str,
        task_arn: str,
        loader_name: str,
        max_retries: int = 3,
        retry_delay_sec: float = 1.0,
    ) -> bool:
        """Verify that a task actually stopped. Returns True if verified STOPPED, False if verification failed.

        ISSUE #5 FIX: Prevents hung tasks consuming RDS connections by verifying termination.
        Retries with escalating delays because ECS stop_task is async and may fail silently.

        Called by Orchestrator._kill_long_running_loaders() after it issues ecs.stop_task().
        """
        for attempt in range(1, max_retries + 1):
            try:
                response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
                tasks = response.get("tasks")
                if not tasks or not isinstance(tasks, list) or len(tasks) == 0:
                    logger.error(
                        f"[TASK_TERMINATION] Attempt {attempt}: Task {task_arn} not found in describe_tasks response"
                    )
                    if attempt < max_retries:
                        time.sleep(retry_delay_sec)
                        retry_delay_sec *= 1.5
                    continue

                # CRITICAL: Validate ECS task status fields exist (fail-fast if missing)
                task_status = tasks[0].get("lastStatus")
                desired_status = tasks[0].get("desiredStatus")
                if task_status is None or desired_status is None:
                    raise ValueError(
                        f"[TASK_TERMINATION] ECS task missing required status fields. "
                        f"lastStatus={task_status}, desiredStatus={desired_status}. "
                        f"Cannot determine task state. This indicates ECS API contract violation. Task: {tasks[0]}"
                    )

                logger.debug(
                    f"[TASK_TERMINATION] Attempt {attempt}: {loader_name} lastStatus={task_status}, desiredStatus={desired_status}"
                )

                if task_status == "STOPPED":
                    logger.info(f"[TASK_TERMINATION] [OK] {loader_name} task {task_arn} verified STOPPED")
                    return True

                if desired_status == "STOPPED" and task_status in (
                    "RUNNING",
                    "DEPROVISIONING",
                ):
                    if attempt < max_retries:
                        logger.debug(
                            f"[TASK_TERMINATION] Attempt {attempt}: Stop requested, waiting for status transition..."
                        )
                        time.sleep(retry_delay_sec)
                        retry_delay_sec *= 1.5
                        continue

                logger.error(
                    f"[TASK_TERMINATION] Attempt {attempt}: Task status {task_status}/{desired_status} - stop not acknowledged"
                )
                if attempt < max_retries:
                    time.sleep(retry_delay_sec)
                    retry_delay_sec *= 1.5

            except (
                ValueError,
                KeyError,
                AttributeError,
                psycopg2.DatabaseError,
                psycopg2.OperationalError,
            ) as e:
                logger.error(f"[TASK_TERMINATION] Attempt {attempt}: Failed to verify task status: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay_sec)
                    retry_delay_sec *= 1.5

        logger.critical(
            f"[TASK_TERMINATION] FAILED: {loader_name} task {task_arn} did not transition to STOPPED after {max_retries} attempts. "
            "RDS connection may not be released. Manual intervention required."
        )
        return False

    def validate_required_tables(self, cur: Any) -> bool:
        """FIXED Issue #23: Validate that all required tables exist before running phases.

        Returns: True if all tables exist, False if any critical table is missing.
        """
        required_tables = [
            "price_daily",
            "trend_template_data",
            "sector_ranking",
            "market_health_daily",
            "market_exposure_daily",
            "algo_audit_log",
        ]

        try:
            missing_tables = []
            for table_name in required_tables:
                try:
                    cur.execute(
                        """
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                        """,
                        (table_name,),
                    )
                    if not cur.fetchone():
                        missing_tables.append(table_name)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(f"Could not check table {table_name}: {e}")
                    missing_tables.append(table_name)

            if missing_tables:
                logger.error(f"[CRITICAL] Missing required tables: {', '.join(missing_tables)}")
                return False

            logger.info("[OK] All required tables exist")
            return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[PREFLIGHT] Table validation query failed: {e}")
            return False
