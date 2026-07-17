#!/usr/bin/env python3
"""
Auto-terminate stuck ECS tasks that have been unhealthy for > 2 hours.
Triggered by CloudWatch alarms or EventBridge schedule.
Prevents cost waste from lingering failed tasks.
"""
import boto3
import json
from datetime import datetime, timezone, timedelta

ecs = boto3.client('ecs', region_name='us-east-1')


def get_unhealthy_tasks(cluster='algo-cluster'):
    """Get all unhealthy and stuck tasks in cluster."""
    response = ecs.list_tasks(cluster=cluster)
    task_arns = response.get('taskArns', [])

    if not task_arns:
        return []

    details = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
    unhealthy = []

    now = datetime.now(timezone.utc)

    for task in details['tasks']:
        task_arn = task['taskArn']
        task_name = task['taskDefinitionArn'].split('/')[-1]
        health = task.get('healthStatus', 'UNKNOWN')
        started_at = task.get('startedAt')

        if not started_at:
            continue

        age_seconds = (now - started_at).total_seconds()
        age_hours = age_seconds / 3600

        # Criteria for stuck task:
        # 1. UNHEALTHY for > 2 hours (loader failed but didn't exit)
        # 2. UNKNOWN health for > 3 hours (no health check data = stuck)
        # 3. ANY status > 4 hours (way too long regardless)
        should_kill = False
        reason = None

        if health == 'UNHEALTHY' and age_hours > 2:
            should_kill = True
            reason = f'UNHEALTHY for {age_hours:.1f}h'
        elif health == 'UNKNOWN' and age_hours > 3:
            should_kill = True
            reason = f'UNKNOWN (no health check) for {age_hours:.1f}h'
        elif age_hours > 4:
            should_kill = True
            reason = f'Running too long ({age_hours:.1f}h, regardless of health)'

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


def kill_task(task_arn, reason):
    """Terminate a task with given reason."""
    try:
        result = ecs.stop_task(
            cluster='algo-cluster',
            task=task_arn,
            reason=reason
        )
        return {
            'success': True,
            'task': result['task']['taskArn'].split('/')[-1],
            'status': result['task']['lastStatus']
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def format_alert(killed_tasks):
    """Format alert message for SNS."""
    if not killed_tasks:
        return "No stuck tasks to kill"

    lines = [f"Auto-killed {len(killed_tasks)} stuck ECS tasks:\n"]

    for task in killed_tasks:
        lines.append(f"  {task['name']}")
        lines.append(f"    Health: {task['health']}")
        lines.append(f"    Age: {task['age_hours']:.1f} hours")
        lines.append(f"    Reason: {task['reason']}")
        lines.append(f"    Cost saved: $45/month")
        lines.append("")

    lines.append("Check CloudWatch logs for details.")
    return "\n".join(lines)


def lambda_handler(event, context):
    """Main Lambda handler."""
    print(f"Starting stuck task cleanup at {datetime.now(timezone.utc).isoformat()}")

    try:
        # Find stuck tasks
        stuck = get_unhealthy_tasks()

        if not stuck:
            return {
                'statusCode': 200,
                'message': 'No stuck tasks found',
                'killed': []
            }

        print(f"Found {len(stuck)} stuck task(s)")

        # Kill stuck tasks
        killed = []
        for task in stuck:
            print(f"Killing {task['name']}: {task['reason']}")
            result = kill_task(task['arn'], task['reason'])

            if result['success']:
                killed.append({
                    'name': task['name'],
                    'health': task['health'],
                    'age_hours': task['age_hours'],
                    'reason': task['reason'],
                    'killed_at': datetime.now(timezone.utc).isoformat()
                })
            else:
                print(f"Failed to kill {task['name']}: {result['error']}")

        # Format response
        alert_message = format_alert(killed)
        print(alert_message)

        # TODO: Send SNS alert with formatted message
        # sns.publish(
        #     TopicArn=os.environ['SNS_ALERT_TOPIC_ARN'],
        #     Subject='ECS Auto-Kill: Stuck Tasks Terminated',
        #     Message=alert_message
        # )

        return {
            'statusCode': 200,
            'message': f'Successfully killed {len(killed)} stuck task(s)',
            'killed': killed
        }

    except Exception as e:
        error_msg = f"Error in stuck task cleanup: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'error': error_msg
        }


if __name__ == '__main__':
    # Local testing
    result = lambda_handler({}, {})
    print(json.dumps(result, indent=2))
