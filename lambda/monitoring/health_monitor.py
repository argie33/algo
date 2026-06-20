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
from datetime import datetime, timezone

import boto3

from utils.db.connection import get_db_connection
from utils.db.sql_safety import assert_safe_table


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
cloudwatch = boto3.client("cloudwatch")
sns = boto3.client("sns")


def check_loader_health() -> tuple[str, list[dict]]:
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
                    issues.append(
                        {"loader": loader, "problem": "Never run", "status": "CRITICAL"}
                    )
                    continue

                status, last_run = row
                if last_run:
                    last_run = (
                        last_run.replace(tzinfo=timezone.utc)
                        if last_run.tzinfo is None
                        else last_run
                    )
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
                logger.warning(f"Could not check loader {loader}: {e}")

        cur.close()
        conn.close()

        # Determine overall status
        if not issues:
            return "healthy", []

        critical_count = sum(1 for i in issues if i["status"] in ["CRITICAL", "FAILED"])
        return ("unhealthy" if critical_count > 0 else "degraded"), issues

    except Exception as e:
        logger.error(f"Loader health check failed: {e}")
        return "unhealthy", [
            {"problem": f"Health check error: {str(e)[:50]}", "status": "ERROR"}
        ]


def check_data_freshness() -> tuple[str, list[dict]]:
    """Check if critical data tables have recent data.

    Returns: (status, stale_tables)
      status: 'healthy' | 'degraded' | 'unhealthy'
      stale_tables: [{'table': 'name', 'age_hours': 25.5}, ...]
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        critical_tables = {
            "price_daily": "Daily stock prices",
            "buy_sell_daily": "Buy/sell signals",
            "technical_data_daily": "Technical indicators",
            "sector_ranking": "Sector rankings",
            "algo_trades": "Executed trades",
            "broker_portfolio": "Current positions",
        }

        stale_tables = []
        now = datetime.now(timezone.utc)

        for table_name, description in critical_tables.items():
            try:
                # Find the most recent timestamp in the table
                assert_safe_table(table_name)
                cur.execute(f"""
                    SELECT MAX(created_at) as max_date FROM {table_name}
                    LIMIT 1
                """)

                row = cur.fetchone()
                if row and row[0]:
                    max_date = row[0]
                    if max_date.tzinfo is None:
                        max_date = max_date.replace(tzinfo=timezone.utc)

                    age_hours = (now - max_date).total_seconds() / 3600

                    # Alert if data is >24 hours old
                    if age_hours > 24:
                        stale_tables.append(
                            {
                                "table": table_name,
                                "description": description,
                                "age_hours": round(age_hours, 1),
                                "last_update": max_date.isoformat(),
                            }
                        )

            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"Could not check {table_name}: {e}")

        cur.close()
        conn.close()

        if not stale_tables:
            return "healthy", []

        # CRITICAL: ANY stale critical table is unhealthy (not degraded).
        # Even one stale table means data pipeline has failed — that's a critical issue.
        return "unhealthy", stale_tables

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Data freshness check failed: {e}")
        return "unhealthy", [{"problem": f"Freshness check error: {str(e)[:50]}"}]


def send_metric(
    metric_name: str, value: float, unit: str = "None", dimensions: dict | None = None
):
    """Send custom CloudWatch metric."""
    try:
        cloudwatch.put_metric_data(
            Namespace="Algo/HealthMonitor",
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": unit,
                    "Timestamp": datetime.now(timezone.utc),
                    "Dimensions": [
                        {"Name": k, "Value": v} for k, v in (dimensions or {}).items()
                    ],
                }
            ],
        )
    except Exception as e:
        logger.error(f"Failed to send metric {metric_name}: {e}")


def send_alert(subject: str, message: str):
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


def handler(event, context):
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
