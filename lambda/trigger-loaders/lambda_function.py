#!/usr/bin/env python3
"""
Lambda function to manually trigger data loaders via ECS.
Called when EventBridge fails or for emergency data refresh.

Invoked by: API /api/algo/trigger-loader endpoint or CloudWatch alarm
"""

import json
import boto3
import os
import logging
from datetime import datetime

ecs = boto3.client('ecs')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Trigger ECS loader task.

    Event params:
      - loader_name: (required) 'stock_prices_daily', 'market_health_daily', etc.
      - task_count: (optional, default 1) how many parallel tasks
      - priority: (optional) FARGATE (on-demand) or FARGATE_SPOT
    """
    try:
        # Parse input
        loader_name = event.get('loader_name') or event.get('pathParameters', {}).get('loader')
        if not loader_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'loader_name required'})
            }

        task_count = int(event.get('task_count', 1))
        project_name = os.getenv('PROJECT_NAME', 'algo')
        environment = os.getenv('ENVIRONMENT', 'dev')
        cluster_arn = os.getenv('ECS_CLUSTER_ARN')

        if not cluster_arn:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'ECS_CLUSTER_ARN not configured'})
            }

        # Determine launch type (critical loaders use on-demand)
        critical_loaders = {'stock_prices_daily', 'signals_daily', 'algo_metrics_daily', 'stock_scores'}
        use_fargate = loader_name in critical_loaders
        launch_type = 'FARGATE' if use_fargate else None

        # Run ECS task
        task_def = f"{project_name}-{loader_name}-loader"
        logger.info(f"Triggering loader: {loader_name} (task_def={task_def}, count={task_count})")

        response = ecs.run_task(
            cluster=cluster_arn,
            taskDefinition=task_def,
            launchType='FARGATE' if use_fargate else None,
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': os.getenv('SUBNET_IDS', '').split(','),
                    'securityGroups': [os.getenv('SECURITY_GROUP_ID', '')],
                    'assignPublicIp': 'DISABLED'
                }
            } if use_fargate else None,
            count=task_count,
            capacityProviderStrategy=[{
                'capacityProvider': 'FARGATE_SPOT',
                'weight': 100,
                'base': 0
            }] if not use_fargate else None,
        )

        tasks = response.get('tasks', [])
        if not tasks:
            failures = response.get('failures', [])
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Failed to start task',
                    'failures': [f['reason'] for f in failures]
                })
            }

        task_arns = [t['taskArn'] for t in tasks]
        logger.info(f"✓ Started {len(task_arns)} tasks: {task_arns}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Triggered {loader_name} loader',
                'tasks': task_arns,
                'timestamp': datetime.utcnow().isoformat()
            })
        }

    except Exception as e:
        logger.error(f"Error triggering loader: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
