#!/usr/bin/env python3
"""
Session 199: Auto-terminate stuck ECS tasks that have been unhealthy for > 2 hours.
Triggered by CloudWatch alarms or EventBridge schedule (every 6 hours).
Prevents cost waste from lingering failed tasks (~$45+/month per stuck task).
"""
import os
import sys
import boto3
import json
from datetime import datetime, timezone

ecs = boto3.client('ecs', region_name='us-east-1')
sns = boto3.client('sns', region_name='us-east-1')


def get_unhealthy_tasks(cluster_name):
    """Get all unhealthy and stuck tasks in cluster."""
    try:
        response = ecs.list_tasks(cluster=cluster_name)
        task_arns = response.get('taskArns', [])

        if not task_arns:
            return []

        details = ecs.describe_tasks(cluster=cluster_name, tasks=task_arns)
        unhealthy = []
        now = datetime.now(timezone.utc)

        # Read timeout thresholds from environment
        unhealthy_timeout = int(os.getenv('UNHEALTHY_TIMEOUT', '7200'))  # 2 hours
        unknown_timeout = int(os.getenv('UNKNOWN_TIMEOUT', '10800'))      # 3 hours
        hard_limit_timeout = int(os.getenv('HARD_LIMIT_TIMEOUT', '14400'))# 4 hours

        for task in details['tasks']:
            task_arn = task['taskArn']
            task_name = task['taskDefinitionArn'].split('/')[-1]
            health = task.get('healthStatus', 'UNKNOWN')
            started_at = task.get('startedAt')

            if not started_at:
                continue

            age_seconds = (now - started_at).total_seconds()
            age_hours = age_seconds / 3600
            should_kill = False
            reason = None

            # Criteria for stuck task:
            # 1. UNHEALTHY for > 2 hours (loader failed but didn't exit)
            # 2. UNKNOWN health for > 3 hours (no health check data = stuck)
            # 3. ANY status > 4 hours (way too long regardless)

            if health == 'UNHEALTHY' and age_seconds > unhealthy_timeout:
                should_kill = True
                reason = f'UNHEALTHY for {age_hours:.1f}h (threshold: {unhealthy_timeout//3600}h)'
            elif health == 'UNKNOWN' and age_seconds > unknown_timeout:
                should_kill = True
                reason = f'UNKNOWN (no health check) for {age_hours:.1f}h (threshold: {unknown_timeout//3600}h)'
            elif age_seconds > hard_limit_timeout:
                should_kill = True
                reason = f'Running too long ({age_hours:.1f}h, hard limit: {hard_limit_timeout//3600}h)'

            if should_kill:
                unhealthy.append({
                    'arn': task_arn,
                    'name': task_name,
                    'health': health,
                    'age_hours': age_hours,
                    'reason': reason,
                    'started_at': started_at.isoformat()
                })

        return unhealthy

    except Exception as e:
        print(f"ERROR: Failed to list tasks: {e}")
        raise


def kill_task(cluster_name, task_arn, reason):
    """Terminate a task with given reason."""
    try:
        result = ecs.stop_task(
            cluster=cluster_name,
            task=task_arn,
            reason=reason
        )
        return {
            'success': True,
            'task': result['task']['taskArn'].split('/')[-1],
            'status': result['task']['lastStatus']
        }
    except Exception as e:
        print(f"ERROR: Failed to stop task {task_arn}: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def format_alert_message(killed_tasks, cluster_name, project_name, environment):
    """Format alert message for SNS."""
    if not killed_tasks:
        return (
            f"ECS Auto-Kill Report\n"
            f"Cluster: {cluster_name}\n"
            f"Status: No stuck tasks found\n"
            f"Cost impact: $0 saved"
        )

    lines = [
        f"ECS Auto-Kill Report - {project_name}-{environment}",
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"Cluster: {cluster_name}",
        f"",
        f"Killed {len(killed_tasks)} stuck task(s):",
        ""
    ]

    total_monthly_savings = len(killed_tasks) * 45  # ~$45/month per task

    for task in killed_tasks:
        lines.append(f"✓ {task['name']}")
        lines.append(f"  Health: {task['health']}")
        lines.append(f"  Age: {task['age_hours']:.1f} hours")
        lines.append(f"  Reason: {task['reason']}")
        lines.append(f"  Cost avoided: $45/month")
        lines.append("")

    lines.append(f"Total cost savings: ${total_monthly_savings}/month")
    lines.append("")
    lines.append("CloudWatch Logs: /aws/lambda/{project_name}-auto-kill-stuck-tasks-{environment}".format(
        project_name=project_name,
        environment=environment
    ))

    return "\n".join(lines)


def send_alert(message, topic_arn, subject):
    """Send SNS alert with formatted message."""
    if not topic_arn:
        print("WARNING: SNS_ALERT_TOPIC not configured, skipping alert")
        return

    try:
        sns.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message
        )
        print(f"Alert sent to SNS: {topic_arn}")
    except Exception as e:
        print(f"WARNING: Failed to send SNS alert: {e}")


def lambda_handler(event, context):
    """
    Main Lambda handler.
    Runs every 6 hours via EventBridge Scheduler.
    Kills stuck tasks and sends alert.
    """
    start_time = datetime.now(timezone.utc)
    print(f"Starting auto-kill check at {start_time.isoformat()}")

    # Get configuration from environment
    cluster_name = os.getenv('CLUSTER_NAME', 'algo-cluster')
    sns_topic_arn = os.getenv('SNS_ALERT_TOPIC', '')
    project_name = os.getenv('PROJECT_NAME', 'algo')
    environment = os.getenv('ENVIRONMENT', 'dev')

    try:
        # Find stuck tasks
        stuck_tasks = get_unhealthy_tasks(cluster_name)
        print(f"Found {len(stuck_tasks)} stuck task(s) to cleanup")

        # Kill stuck tasks
        killed = []
        for task in stuck_tasks:
            print(f"Killing {task['name']}: {task['reason']}")
            result = kill_task(cluster_name, task['arn'], task['reason'])

            if result['success']:
                killed.append({
                    'name': task['name'],
                    'health': task['health'],
                    'age_hours': task['age_hours'],
                    'reason': task['reason'],
                    'killed_at': datetime.now(timezone.utc).isoformat()
                })
                print(f"  ✓ Successfully killed")
            else:
                print(f"  ✗ Failed: {result['error']}")

        # Format and send alert
        alert_message = format_alert_message(killed, cluster_name, project_name, environment)
        subject = f"ECS Auto-Kill: {len(killed)} task(s) terminated" if killed else "ECS Auto-Kill: No stuck tasks"

        print("\n" + alert_message)
        send_alert(alert_message, sns_topic_arn, subject)

        # Return result
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        return {
            'statusCode': 200,
            'message': f'Successfully processed {len(stuck_tasks)} stuck task(s), killed {len(killed)}',
            'killed_count': len(killed),
            'killed_tasks': [t['name'] for t in killed],
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        error_msg = f"FATAL: Auto-kill failed: {str(e)}"
        print(error_msg)

        # Send error alert
        alert_msg = f"{error_msg}\n\nCheck Lambda logs: /aws/lambda/{project_name}-auto-kill-stuck-tasks-{environment}"
        send_alert(alert_msg, sns_topic_arn, f"ERROR: ECS Auto-Kill Failed")

        return {
            'statusCode': 500,
            'error': error_msg,
            'killed_count': 0
        }


if __name__ == '__main__':
    # Local testing
    os.environ.setdefault('CLUSTER_NAME', 'algo-cluster')
    os.environ.setdefault('PROJECT_NAME', 'algo')
    os.environ.setdefault('ENVIRONMENT', 'dev')

    result = lambda_handler({}, None)
    print("\n" + "="*70)
    print("Lambda Result:")
    print(json.dumps(result, indent=2))
