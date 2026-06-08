#!/usr/bin/env python3
import boto3
import os
from datetime import datetime, timezone

try:
    ecs = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
    cluster = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

    # List all running tasks
    response = ecs.list_tasks(cluster=cluster, desiredStatus='RUNNING')

    if response.get('taskArns'):
        task_details = ecs.describe_tasks(cluster=cluster, tasks=response['taskArns'])
        print(f"Total running tasks: {len(task_details.get('tasks', []))}")

        # Find swing_trader_scores
        for task in task_details.get('tasks', []):
            task_def_arn = task.get('taskDefinitionArn', '')
            task_id = task.get('taskArn', '').split('/')[-1]

            # Print all swing-related tasks
            if 'swing' in task_def_arn.lower():
                started_at = task.get('startedAt')
                if started_at:
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - started_at).total_seconds() / 3600
                else:
                    age = None

                print(f"\nTask ID: {task_id}")
                print(f"Definition: {task_def_arn.split(':')[0]}")
                print(f"Status: {task.get('lastStatus')}")
                print(f"Started: {started_at}")
                if age is not None:
                    print(f"Age: {age:.1f} hours")
    else:
        print("No running tasks found")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
