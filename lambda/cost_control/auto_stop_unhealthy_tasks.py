"""
Emergency cost control: Auto-stop UNHEALTHY ECS tasks after 20 minutes.
Triggered every 5 minutes via EventBridge rule.
Prevents accumulation of zombie tasks that burn money.
"""
import boto3
import json
from datetime import datetime, timezone, timedelta

ecs = boto3.client('ecs')
sns = boto3.client('sns')

def lambda_handler(event, context):
    cluster = 'algo-cluster'
    unhealthy_threshold_minutes = 20
    unknown_threshold_minutes = 60
    alert_topic = 'arn:aws:sns:us-east-1:626216981288:algo-alerts'

    try:
        # Get all tasks
        tasks_resp = ecs.list_tasks(cluster=cluster)
        task_arns = tasks_resp.get('taskArns', [])

        if not task_arns:
            return {'statusCode': 200, 'body': 'No tasks running'}

        # Describe all tasks
        details = ecs.describe_tasks(cluster=cluster, tasks=task_arns)

        stopped_tasks = []
        alerts = []

        for task in details['tasks']:
            health = task.get('healthStatus', 'UNKNOWN')
            task_arn = task['taskArn']
            task_name = task['containers'][0]['name']
            started_at = task.get('startedAt')

            if not started_at:
                continue

            age_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            age_minutes = age_seconds / 60

            # UNHEALTHY for >20min OR UNKNOWN for >60min = stop it
            should_stop = False
            reason = None

            if health == 'UNHEALTHY' and age_minutes > unhealthy_threshold_minutes:
                should_stop = True
                reason = f'UNHEALTHY for {age_minutes:.0f}min (threshold: {unhealthy_threshold_minutes}min)'
            elif health == 'UNKNOWN' and age_minutes > unknown_threshold_minutes:
                should_stop = True
                reason = f'UNKNOWN for {age_minutes:.0f}min (threshold: {unknown_threshold_minutes}min)'

            if should_stop:
                # Stop the task
                ecs.stop_task(
                    cluster=cluster,
                    task=task_arn,
                    reason=f'[AUTO-COST-CONTROL] {reason}'
                )
                stopped_tasks.append(f'{task_name}: {reason}')
                alerts.append(f'Stopped {task_name} ({health} for {age_minutes:.0f}min)')

        # Send alert if we stopped anything
        if alerts:
            message = f'Cost Control Alert:\n\n' + '\n'.join(alerts) + \
                     f'\n\nTotal stopped: {len(alerts)} tasks\n' + \
                     f'Cluster: {cluster}\n' + \
                     f'Time: {datetime.now(timezone.utc).isoformat()}'

            sns.publish(
                TopicArn=alert_topic,
                Subject=f'ECS Auto-Stop: {len(alerts)} Tasks Terminated',
                Message=message
            )

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'action': 'stopped_unhealthy_tasks',
                    'count': len(alerts),
                    'tasks': alerts
                })
            }

        return {'statusCode': 200, 'body': 'All tasks healthy'}

    except Exception as e:
        print(f'ERROR: {str(e)}')
        # Alert on error too
        sns.publish(
            TopicArn=alert_topic,
            Subject='ECS Auto-Stop Lambda Error',
            Message=f'Failed to check/stop tasks:\n\n{str(e)}'
        )
        raise
