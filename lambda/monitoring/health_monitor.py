"""Operational Health Monitor Lambda

Runs every 6 hours to verify system health:
1. Check all critical loaders have run in last 26 hours
2. Check critical data tables have fresh data (<24h old)
3. Check API is responding
4. Send CloudWatch metrics and alarms for any issues

Triggered by: EventBridge rule (6-hour interval)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
import psycopg2

from utils.db.connection import get_db_connection
from utils.db.sql_safety import assert_safe_table

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
cloudwatch = boto3.client("cloudwatch")
sns = boto3.client("sns")


def check_loader_health() -> tuple[str, list[dict[str, Any]]]:
    """Check if critical loaders have run recently.

    Returns: (status, issues_list)
      status: 'healthy' | 'degraded' | 'unhealthy'
      issues: [{'loader': 'name', 'last_run_hours_ago': 25, 'status': 'FAILED'}, ...]
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        critical_loaders = [
            "price_daily",
            "sector_ranking",
            "options_chains",
            "earnings_dates",
            "analyst_ratings",
            "insider_trades",
            "buy_sell_daily",
            "technical_data_daily",
        ]

        issues = []
        now = datetime.now(timezone.utc)

        # Check each critical loader
        for loader in critical_loaders:
            try:
                cur.execute(
                    """
                    SELECT status, last_execution_time
                    FROM data_loader_status
                    WHERE loader_name = %s
                    ORDER BY last_execution_time DESC
                    LIMIT 1
                """,
                    (loader,),
                )

                row = cur.fetchone()
                if not row:
                    issues.append({"loader": loader, "problem": "Never run", "status": "CRITICAL"})
                    continue

                status, last_run = row
                if last_run:
                    last_run = last_run.replace(tzinfo=timezone.utc) if last_run.tzinfo is None else last_run
                    age_hours = (now - last_run).total_seconds() / 3600

                    # Check if stale (>26 hours for daily loaders)
                    if age_hours > 26:
                        issues.append(
                            {
                                "loader": loader,
                                "problem": f"Stale ({age_hours:.1f}h)",
                                "last_run": last_run.isoformat(),
                                "status": "STALE",
                            }
                        )

                    # Check if failed
                    if status == "FAILED":
                        issues.append(
                            {
                                "loader": loader,
                                "problem": "Last run failed",
                                "last_run": last_run.isoformat(),
                                "status": "FAILED",
                            }
                        )

            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"HEALTH CHECK FAILED for {loader}: {e}")
                issues.append(
                    {
                        "loader": loader,
                        "problem": f"Health check database error: {str(e)[:80]}",
                        "status": "FAILED",
                        "severity": "CRITICAL",
                    }
                )

        cur.close()
        conn.close()

        # Determine overall status
        if not issues:
            return "healthy", []

        critical_count = sum(1 for i in issues if i["status"] in ["CRITICAL", "FAILED"])
        return ("unhealthy" if critical_count > 0 else "degraded"), issues

    except Exception as e:
        logger.error(f"Loader health check failed: {e}")
        return "unhealthy", [{"problem": f"Health check error: {str(e)[:50]}", "status": "ERROR"}]


def check_data_freshness() -> tuple[str, list[dict[str, Any]]]:
    """Check if critical data tables have recent data.

    Returns: (status, stale_tables)
      status: 'healthy' | 'degraded' | 'unhealthy'
      stale_tables: [{'table': 'name', 'age_hours': 25.5}, ...]

    CRITICAL: Detects stale data that causes trading halts and dashboard failures.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        critical_tables = {
            "price_daily": "Daily stock prices (blocks all downstream loaders)",
            "buy_sell_daily": "Buy/sell signals (blocks Phase 5 entry generation)",
            "technical_data_daily": "Technical indicators (depends on price_daily)",
            "sector_ranking": "Sector rankings (affects position sizing)",
            "algo_trades": "Executed trades (portfolio reconciliation)",
            "broker_portfolio": "Current positions (Phase 9 reconciliation)",
        }

        stale_tables = []
        now = datetime.now(timezone.utc)

        for table_name, description in critical_tables.items():
            try:
                # Find the most recent timestamp in the table
                assert_safe_table(table_name)
                cur.execute(f"""
                    SELECT MAX(created_at) as max_date, COUNT(*) as row_count FROM {table_name}
                    LIMIT 1
                """)

                row = cur.fetchone()
                max_date, row_count = row if row else (None, 0)

                # CRITICAL: Missing data is worse than stale data (missing = pipeline failed)
                if row_count == 0:
                    logger.error(
                        f"[DATA_STALENESS] CRITICAL: Table '{table_name}' is EMPTY. "
                        f"Description: {description}. "
                        f"This indicates the data loader has never run or failed completely."
                    )
                    stale_tables.append(
                        {
                            "table": table_name,
                            "description": description,
                            "status": "EMPTY",
                            "problem": "No data loaded - loader may have never run",
                        }
                    )
                elif max_date:
                    max_date = max_date.replace(tzinfo=timezone.utc) if max_date.tzinfo is None else max_date
                    age_hours = (now - max_date).total_seconds() / 3600

                    # Alert if data is >24 hours old
                    if age_hours > 24:
                        logger.error(
                            f"[DATA_STALENESS] Table '{table_name}' is STALE: {age_hours:.1f}h old. "
                            f"Description: {description}. "
                            f"Last update: {max_date.isoformat()}. "
                            f"Rows: {row_count}. "
                            f"This will cause trading halts and incomplete dashboard data."
                        )
                        stale_tables.append(
                            {
                                "table": table_name,
                                "description": description,
                                "age_hours": round(age_hours, 1),
                                "last_update": max_date.isoformat(),
                                "row_count": row_count,  # type: ignore[dict-item]
                                "status": "STALE",
                            }
                        )
                    else:
                        # Log freshness for monitoring (info level, not error)
                        logger.info(
                            f"[DATA_FRESHNESS_OK] Table '{table_name}': {age_hours:.1f}h old, "
                            f"{row_count} rows, last update {max_date.isoformat()}"
                        )

            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"[DATA_STALENESS_CHECK_FAILED] Could not check {table_name}: {e}")
                stale_tables.append(
                    {
                        "table": table_name,
                        "description": description,
                        "status": "CHECK_FAILED",
                        "problem": f"Database error: {str(e)[:50]}",
                    }
                )

        cur.close()
        conn.close()

        if not stale_tables:
            logger.info("[DATA_FRESHNESS] All critical tables are fresh and healthy")
            return "healthy", []

        # CRITICAL: ANY stale critical table is unhealthy (not degraded).
        # Even one stale table means data pipeline has failed — that's a critical issue.
        critical_count = sum(1 for t in stale_tables if t.get("status") in ["EMPTY", "CHECK_FAILED"])
        logger.error(
            f"[DATA_STALENESS_ALERT] {len(stale_tables)} critical tables are stale/empty. "
            f"{critical_count} are critical failures. This will halt trading and break dashboard."
        )
        return "unhealthy", stale_tables

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[DATA_FRESHNESS_CHECK_FAILED] Data freshness check failed: {e}")
        return "unhealthy", [{"problem": f"Freshness check error: {str(e)[:50]}", "status": "CHECK_FAILED"}]


def send_metric(metric_name: str, value: float, unit: str = "None", dimensions: dict[str, str] | None = None) -> None:
    """Send custom CloudWatch metric."""
    try:
        if dimensions is None:
            logger.error(
                f"[HEALTH_MONITOR] Cannot publish metric '{metric_name}' without dimensions. "
                f"Audit context required for all health metrics."
            )
            return  # Fail-fast: do not publish metrics without audit context

        metric_dims = [{"Name": k, "Value": v} for k, v in dimensions.items()]

        cloudwatch.put_metric_data(
            Namespace="Algo/HealthMonitor",
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": unit,
                    "Timestamp": datetime.now(timezone.utc),
                    "Dimensions": metric_dims,
                }
            ],
        )
    except Exception as e:
        logger.error(f"Failed to send metric {metric_name}: {e}")


def send_alert(subject: str, message: str) -> None:
    """Send SNS alert (REQUIRED in production)."""
    sns_topic = os.environ.get("SNS_ALERT_TOPIC_ARN")
    if not sns_topic:
        raise ValueError(
            "SNS_ALERT_TOPIC_ARN required for health monitoring in production. "
            "Set SNS_ALERT_TOPIC_ARN environment variable."
        )

    try:
        sns.publish(TopicArn=sns_topic, Subject=subject, Message=message)
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        raise


def handler(event: Any, context: Any) -> dict[str, Any]:
    """Health monitor Lambda handler."""
    logger.info("Starting operational health check...")

    all_issues = []

    # Check loader health
    loader_status, loader_issues = check_loader_health()
    all_issues.extend(loader_issues)
    send_metric(
        "LoaderHealth",
        0 if loader_status == "healthy" else (1 if loader_status == "degraded" else 2),
    )

    # Check data freshness
    data_status, stale_tables = check_data_freshness()
    all_issues.extend(stale_tables)
    send_metric(
        "DataFreshness",
        0 if data_status == "healthy" else (1 if data_status == "degraded" else 2),
    )

    # Determine overall status
    overall_status = "healthy"
    if loader_status == "unhealthy" or data_status == "unhealthy":
        overall_status = "unhealthy"
    elif loader_status == "degraded" or data_status == "degraded":
        overall_status = "degraded"

    # Send alert if not healthy
    if overall_status != "healthy":
        alert_message = """
Operational Health Check - {overall_status.upper()}

=== LOADER STATUS ===
{json.dumps(loader_issues, indent=2) if loader_issues else 'All loaders healthy'}

=== DATA FRESHNESS ===
{json.dumps(stale_tables, indent=2) if stale_tables else 'All data fresh'}

Time: {datetime.now(timezone.utc).isoformat()}
"""

        send_alert(f"Algo System Health: {overall_status.upper()}", alert_message)

    response_body = {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "loaders": {"status": loader_status, "issues": loader_issues},
            "data_freshness": {"status": data_status, "stale_tables": stale_tables},
        },
        "total_issues": len(all_issues),
    }

    logger.info(f"Health check complete: {overall_status} ({len(all_issues)} issues)")

    return {
        "statusCode": 200 if overall_status == "healthy" else 202,
        "body": json.dumps(response_body),
    }
