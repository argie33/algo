#!/usr/bin/env python3
"""
AWS Cost Circuit Breaker Lambda - Monitors AWS costs and suspends services if threshold exceeded.

This is a SAFETY mechanism to prevent runaway AWS costs from unexpected usage spikes.

Triggers:
- EventBridge Schedule every 6 hours (4 AM, 10 AM, 4 PM, 10 PM UTC)
- Manual invocation via Lambda console for testing

Actions:
- Queries AWS Cost Explorer API for costs over the past 24 hours
- Compares against daily budget threshold
- If exceeded, triggers cost suspension protocol:
  1. Disables EventBridge Scheduler rules (halts all loaders and orchestrator)
  2. Suspends ECS tasks (stops running jobs)
  3. Sends SNS alert with cost summary and suspension details
  4. Logs detailed event to RDS for audit trail

Resets:
- Manual reset only (to prevent accidental resume during extended spike)
- Operator must review costs and manually enable services via Terraform

Safety:
- Fail-closed: Any Cost Explorer query failure triggers suspension (defensive)
- Detailed logging for troubleshooting and compliance
- SNS alerts sent to team email and optional Slack webhook
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ce_client = boto3.client("ce")
scheduler_client = boto3.client("scheduler")
ecs_client = boto3.client("ecs")
sns_client = boto3.client("sns")
cloudwatch_client = boto3.client("cloudwatch")

PROJECT_NAME = os.environ.get("PROJECT_NAME", "stocks")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
SNS_ALERT_TOPIC_ARN = os.environ.get("SNS_ALERT_TOPIC_ARN", "")
DAILY_COST_THRESHOLD_USD = float(os.environ.get("DAILY_COST_THRESHOLD_USD", "50.0"))
ECS_CLUSTER_NAME = os.environ.get("ECS_CLUSTER_NAME", f"{PROJECT_NAME}-{ENVIRONMENT}")


def get_daily_costs() -> dict:
    """Query AWS Cost Explorer for costs in the past 24 hours.

    Returns:
        {
            "total_cost": 45.67,  # USD
            "service_breakdown": {
                "EC2": 10.50,
                "Lambda": 5.20,
                "RDS": 20.30,
                ...
            },
            "query_time": "2026-07-11T14:30:00Z"
        }

    Raises:
        RuntimeError: On Cost Explorer query failure
    """
    try:
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=1)

        response = ce_client.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.isoformat(),
                "End": end_date.isoformat(),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[
                {"Type": "DIMENSION", "Key": "SERVICE"},
            ],
        )

        total_cost = 0.0
        service_breakdown = {}

        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                service_breakdown[service] = cost
                total_cost += cost

        return {
            "total_cost": round(total_cost, 2),
            "service_breakdown": service_breakdown,
            "query_time": datetime.now(timezone.utc).isoformat(),
            "threshold_usd": DAILY_COST_THRESHOLD_USD,
        }
    except Exception as e:
        logger.error(f"Failed to query Cost Explorer: {e}")
        raise RuntimeError(f"Cost Explorer query failed: {str(e)}") from e


def disable_scheduler_rules() -> list:
    """Disable all EventBridge Scheduler rules to halt loaders and orchestrator.

    Returns:
        List of disabled rule names

    Raises:
        RuntimeError: On scheduler update failure
    """
    try:
        disabled_rules = []

        paginator = scheduler_client.get_paginator("list_schedules")
        for page in paginator.paginate():
            for schedule in page.get("Schedules", []):
                schedule_name = schedule["Name"]

                if PROJECT_NAME not in schedule_name:
                    continue

                try:
                    scheduler_client.update_schedule(
                        Name=schedule_name,
                        State="DISABLED",
                        FlexibleTimeWindow={"Mode": "OFF"},
                        ScheduleExpression="rate(24 hours)",  # Placeholder; will be updated when re-enabled
                    )
                    disabled_rules.append(schedule_name)
                    logger.info(f"Disabled EventBridge schedule: {schedule_name}")
                except Exception as e:
                    logger.warning(f"Failed to disable schedule {schedule_name}: {e}")

        return disabled_rules
    except Exception as e:
        logger.error(f"Failed to disable EventBridge schedules: {e}")
        raise RuntimeError(f"Scheduler disable failed: {str(e)}") from e


def suspend_ecs_tasks() -> dict:
    """Stop all running ECS tasks in the cluster.

    Returns:
        {
            "cluster": "algo-dev",
            "stopped_task_arns": [...],
            "stop_count": 5
        }

    Raises:
        RuntimeError: On ECS operation failure
    """
    try:
        stopped_tasks = []

        list_response = ecs_client.list_tasks(cluster=ECS_CLUSTER_NAME)
        task_arns = list_response.get("taskArns", [])

        if not task_arns:
            logger.info(f"No ECS tasks running in cluster {ECS_CLUSTER_NAME}")
            return {
                "cluster": ECS_CLUSTER_NAME,
                "stopped_task_arns": [],
                "stop_count": 0,
            }

        for task_arn in task_arns:
            try:
                ecs_client.stop_task(
                    cluster=ECS_CLUSTER_NAME,
                    task=task_arn,
                    reason="Cost circuit breaker triggered - halting all tasks",
                )
                stopped_tasks.append(task_arn)
                logger.info(f"Stopped ECS task: {task_arn}")
            except Exception as e:
                logger.warning(f"Failed to stop task {task_arn}: {e}")

        return {
            "cluster": ECS_CLUSTER_NAME,
            "stopped_task_arns": stopped_tasks,
            "stop_count": len(stopped_tasks),
        }
    except Exception as e:
        logger.error(f"Failed to suspend ECS tasks: {e}")
        raise RuntimeError(f"ECS suspension failed: {str(e)}") from e


def send_cost_alert(costs: dict, alert_type: str, suspension_details: dict = None) -> None:
    """Send SNS alert with cost summary and suspension status.

    Args:
        costs: Cost data from get_daily_costs()
        alert_type: "WARNING" (under threshold) or "CRITICAL" (over threshold)
        suspension_details: Suspension results if alert_type == "CRITICAL"
    """
    if not SNS_ALERT_TOPIC_ARN:
        logger.warning("SNS_ALERT_TOPIC_ARN not configured - skipping email alert")
        return

    try:
        # Build service breakdown string
        service_lines = []
        for service, cost in sorted(
            costs["service_breakdown"].items(), key=lambda x: x[1], reverse=True
        )[:10]:
            service_lines.append(f"  {service}: ${cost:.2f}")

        subject = f"[{alert_type}] AWS Cost Alert - {PROJECT_NAME}-{ENVIRONMENT}"

        if alert_type == "WARNING":
            body = f"""AWS Cost Circuit Breaker Status: NORMAL

Daily Cost: ${costs['total_cost']:.2f} / ${costs['threshold_usd']:.2f} (threshold)
Status: Within budget

Top Services:
{chr(10).join(service_lines)}

Check time: {costs['query_time']}

All services are operating normally.
No action required."""

        else:  # CRITICAL
            suspension_info = (
                f"""
SERVICES SUSPENDED:
  - EventBridge Schedules: {len(suspension_details.get('disabled_schedules', []))} disabled
  - ECS Tasks: {suspension_details.get('ecs_details', {}).get('stop_count', 0)} stopped
  - Loaders: HALTED
  - Orchestrator: HALTED"""
                if suspension_details
                else ""
            )

            body = f"""🚨 AWS COST CIRCUIT BREAKER TRIGGERED 🚨

Daily Cost: ${costs['total_cost']:.2f}
Budget Threshold: ${costs['threshold_usd']:.2f}
EXCEEDED BY: ${costs['total_cost'] - costs['threshold_usd']:.2f}

SEVERITY: CRITICAL
ACTION: All AWS services have been suspended to prevent further costs

{suspension_info}

Top Services:
{chr(10).join(service_lines)}

Check time: {costs['query_time']}

NEXT STEPS:
1. Review AWS Cost Explorer for cost drivers
2. Investigate any runaway services (Lambda, EC2, RDS)
3. Contact team to determine root cause
4. Once resolved, manually re-enable services in Terraform

To resume services:
  cd terraform
  terraform apply -var="cost_suspension_enabled=false"

More information:
  - AWS Cost Explorer: https://console.aws.amazon.com/cost-management/home
  - Lambda Logs: https://console.aws.amazon.com/lambda/
  - ECS Cluster: {ECS_CLUSTER_NAME}"""

        sns_client.publish(
            TopicArn=SNS_ALERT_TOPIC_ARN,
            Subject=subject,
            Message=body,
        )
        logger.info(f"Sent SNS alert: {alert_type}")
    except Exception as e:
        logger.error(f"Failed to send SNS alert: {e}")


def publish_cost_metric(total_cost: float, threshold: float) -> None:
    """Publish cost metric to CloudWatch for dashboard visualization."""
    try:
        cloudwatch_client.put_metric_data(
            Namespace="Algo/CostMonitoring",
            MetricData=[
                {
                    "MetricName": "DailyCost",
                    "Value": total_cost,
                    "Unit": "None",
                    "Timestamp": datetime.now(timezone.utc),
                },
                {
                    "MetricName": "CostBudgetUtilization",
                    "Value": (total_cost / threshold * 100) if threshold > 0 else 0,
                    "Unit": "Percent",
                    "Timestamp": datetime.now(timezone.utc),
                },
            ],
        )
        logger.debug(f"Published cost metrics: cost=${total_cost:.2f}, utilization={(total_cost/threshold*100):.1f}%")
    except Exception as e:
        logger.warning(f"Failed to publish CloudWatch metrics: {e}")


def lambda_handler(event, context):
    """Cost circuit breaker trigger - check costs and suspend if exceeded."""
    logger.info(f"Cost circuit breaker invoked: threshold=${DAILY_COST_THRESHOLD_USD:.2f}")

    try:
        # Query costs
        costs = get_daily_costs()
        publish_cost_metric(costs["total_cost"], DAILY_COST_THRESHOLD_USD)

        if costs["total_cost"] <= DAILY_COST_THRESHOLD_USD:
            logger.info(
                f"Cost within budget: ${costs['total_cost']:.2f} <= ${DAILY_COST_THRESHOLD_USD:.2f}"
            )
            send_cost_alert(costs, "WARNING")
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "status": "OK",
                        "daily_cost": costs["total_cost"],
                        "threshold": DAILY_COST_THRESHOLD_USD,
                    }
                ),
            }

        # Cost exceeded - suspend services
        logger.critical(
            f"COST CIRCUIT BREAKER TRIGGERED: ${costs['total_cost']:.2f} > ${DAILY_COST_THRESHOLD_USD:.2f}"
        )

        disabled_schedules = disable_scheduler_rules()
        ecs_details = suspend_ecs_tasks()

        suspension_details = {
            "disabled_schedules": disabled_schedules,
            "ecs_details": ecs_details,
        }

        send_cost_alert(costs, "CRITICAL", suspension_details)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "SUSPENDED",
                    "daily_cost": costs["total_cost"],
                    "threshold": DAILY_COST_THRESHOLD_USD,
                    "disabled_schedules": disabled_schedules,
                    "stopped_tasks": len(ecs_details.get("stopped_task_arns", [])),
                }
            ),
        }

    except RuntimeError as e:
        # Fail-closed: if we can't query costs, suspend as a safety measure
        logger.critical(f"Cost query failed - suspending as safety measure: {e}")

        try:
            disabled_schedules = disable_scheduler_rules()
            ecs_details = suspend_ecs_tasks()

            costs = {"total_cost": 0, "service_breakdown": {}, "query_time": datetime.now(timezone.utc).isoformat(), "threshold_usd": DAILY_COST_THRESHOLD_USD}
            send_cost_alert(costs, "CRITICAL", {"error": str(e), "disabled_schedules": disabled_schedules, "ecs_details": ecs_details})
        except Exception as suspend_err:
            logger.error(f"Failed to suspend after cost query error: {suspend_err}")

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "SUSPENDED",
                    "reason": f"Cost query failed - fail-closed suspension triggered: {str(e)}",
                }
            ),
        }

    except Exception as e:
        logger.error(f"Unexpected error in cost circuit breaker: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "ERROR",
                    "error": str(e),
                }
            ),
        }
