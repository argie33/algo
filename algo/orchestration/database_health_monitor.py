#!/usr/bin/env python3
"""Database health monitoring specialist for Orchestrator.

Extracted responsibilities:
- Database connectivity checks
- Connection pool monitoring
- Table validation
- Long-running task termination
- System diagnostics

Eliminates divergent change in Orchestrator by centralizing all DB health logic.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2

from algo.infrastructure import MarketCalendar
from utils.db import DatabaseContext, assert_safe_table
from utils.infrastructure import (
    EASTERN_TZ,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    ORCHESTRATOR_KILL_BUFFER_MINUTES,
    ORCHESTRATOR_RUN_TIMES_TUPLE,
)

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
            logger.debug(f"Could not check connection pool health: {e}")

    def health_check_diagnostics(self) -> None:
        """Log system health status: what's working, what's not, what's stale."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SET statement_timeout = 10000")  # 10s timeout

                tables_to_check = [
                    ("price_daily", "Prices"),
                    ("market_health_daily", "Market health"),
                    ("market_exposure_daily", "Market exposure"),
                    ("buy_sell_daily", "Buy/sell signals (Phase 5)"),
                    ("trend_template_data", "Trend template"),
                    ("sector_ranking", "Sector ranking"),
                    ("swing_trader_scores", "Swing scores (legacy)"),
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
                    logger.debug(f"    Could not check loader status: {loader_err}")

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"  Health check failed: {e}")

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
                    f"[TASK_TERMINATION] Attempt {attempt}: Task status {task_status}/{desired_status} — stop not acknowledged"
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

    def kill_long_running_loaders(self, log_phase_result: Any) -> None:
        """CRITICAL: Kill hung loaders if approaching next orchestrator run.

        Analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics)
        iterate 5000+ symbols with yfinance rate limits and can run 6+ hours.

        Critical-path loaders (swing_trader_scores_vectorized, trend_template_data, sector_ranking,
        market_health_daily, market_exposure_daily, algo_metrics_daily) should complete within
        30-90 minutes. If still running 15 min before next orchestrator run, they're hung and
        consuming RDS connections.

        Args:
            log_phase_result: Callback to log phase results
        """
        try:
            import boto3

            ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))
            cluster = os.getenv("ECS_CLUSTER_ARN", "algo-cluster")

            analytics_loaders = {
                "company_profile",
                "analyst_sentiment",
                "stability_metrics",
                "value_metrics",
            }
            critical_path_loaders = {
                "swing_trader_scores_vectorized",
                "trend_template_data",
                "sector_ranking",
                "market_health_daily",
                "market_exposure_daily",
                "algo_metrics_daily",
            }
            monitored_loaders = analytics_loaders | critical_path_loaders

            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)

            next_orch_et = None
            for orch_hour, orch_minute in ORCHESTRATOR_RUN_TIMES_TUPLE:
                orch_time = now_et.replace(hour=orch_hour, minute=orch_minute, second=0, microsecond=0)
                if orch_time > now_et:
                    next_orch_et = orch_time
                    break

            if next_orch_et is None:
                next_orch_et = (now_et + timedelta(days=1)).replace(
                    hour=MARKET_OPEN_HOUR,
                    minute=MARKET_OPEN_MINUTE,
                    second=0,
                    microsecond=0,
                )
                while not MarketCalendar.is_trading_day(next_orch_et.date()):
                    next_orch_et += timedelta(days=1)

            kill_threshold_et = next_orch_et - timedelta(minutes=ORCHESTRATOR_KILL_BUFFER_MINUTES)
            max_runtime = kill_threshold_et - now_et

            if max_runtime.total_seconds() <= 0:
                logger.debug("[OOM_PREVENTION] Next orchestrator run is imminent, using 5 min max runtime")
                max_runtime = timedelta(minutes=5)

            logger.debug(
                f"[OOM_PREVENTION] Next orchestrator run at {next_orch_et.strftime('%H:%M')} ET. "
                f"Kill timeout: {max_runtime.total_seconds() / 60:.0f} minutes"
            )

            response = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING")
            task_arns = response.get("taskArns")
            if not task_arns:
                return
            if not isinstance(task_arns, list):
                logger.error(f"[OOM_PREVENTION] Unexpected taskArns type: {type(task_arns)}, expected list")
                return

            task_details = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
            now = datetime.now(timezone.utc)

            if not isinstance(task_details, dict):
                logger.error(f"[OOM_PREVENTION] Unexpected task_details type: {type(task_details)}, expected dict")
                return

            tasks = task_details.get("tasks")
            if not isinstance(tasks, list):
                logger.error(f"[OOM_PREVENTION] Unexpected tasks type: {type(tasks)}, expected list")
                return

            failed_terminations = []
            for task in tasks:
                task_def = task.get("taskDefinitionArn", "")
                loader_name = None
                for loader in monitored_loaders:
                    if loader in task_def:
                        loader_name = loader
                        break

                if not loader_name:
                    continue

                started_at = task.get("startedAt")
                if not started_at:
                    task_arn = task.get("taskArn", "unknown")
                    raise ValueError(
                        f"[CRITICAL] Task missing startedAt field — cannot assess if hung. "
                        f"This indicates ECS metadata corruption or schema change. "
                        f"Cannot proceed with OOM prevention. Task: {task_arn}"
                    )

                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)

                age = now - started_at
                if age > max_runtime:
                    task_arn = task.get("taskArn")
                    logger.warning(
                        f"[OOM_PREVENTION] Killing {loader_name} task (running {age.total_seconds() / 3600:.1f}h, "
                        f"max {max_runtime.total_seconds() / 3600:.1f}h before next orch run): {task_arn}"
                    )

                    try:
                        ecs.stop_task(
                            cluster=cluster,
                            task=task_arn,
                            reason="Loader hung beyond timeout before next orchestrator run",
                        )
                    except (ValueError, KeyError, AttributeError) as stop_err:
                        logger.critical(
                            f"[TASK_TERMINATION] CRITICAL: Failed to kill hung loader {loader_name}: {stop_err}. "
                            f"Task will continue consuming resources. Manual intervention required: {task_arn}"
                        )
                        failed_terminations.append((loader_name, task_arn, str(stop_err)))
                        # Mark health monitor as degraded — don't silently continue
                        log_phase_result(
                            0,
                            "oom_prevention",
                            "failure",
                            f"Failed to kill hung {loader_name} task. Manual intervention required: {stop_err}",
                        )

                    if self.verify_task_stopped(ecs, cluster, task_arn, loader_name):
                        log_phase_result(
                            0,
                            "oom_prevention",
                            "success",
                            f"Killed {loader_name} task running {age.total_seconds() / 3600:.1f}h",
                        )
                    else:
                        failed_terminations.append((loader_name, task_arn, "verification timeout"))

            if failed_terminations:
                error_details = "; ".join([f"{name}: {err}" for name, arn, err in failed_terminations])
                logger.critical(
                    f"[TASK_TERMINATION] ESCALATION: {len(failed_terminations)} task termination(s) failed. "
                    f"{error_details}"
                )
                try:
                    self.alerts.send_position_alert(
                        "TASK_TERMINATION",
                        "HUNG_LOADER_TERMINATION_FAILED",
                        f"Failed to terminate {len(failed_terminations)} hung loaders. RDS connections may not be released. "
                        f"Check CloudWatch logs and manually stop: {', '.join([arn.split('/')[-1] for _, arn, _ in failed_terminations])}",
                        {
                            "failed_tasks": [
                                {"loader": name, "task_arn": arn, "error": err}
                                for name, arn, err in failed_terminations
                            ]
                        },
                    )
                except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                    logger.error(f"[TASK_TERMINATION] Could not send escalation alert: {alert_err}")

        except (
            ValueError,
            KeyError,
            AttributeError,
            psycopg2.DatabaseError,
            psycopg2.OperationalError,
        ) as e:
            logger.warning(f"[OOM_PREVENTION] Could not check/kill long-running loaders: {e}")

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
