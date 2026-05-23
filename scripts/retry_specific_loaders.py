#!/usr/bin/env python3
"""Retry specific failing loaders."""

import boto3
import sys
import time

ecs = boto3.client('ecs', region_name='us-east-1')

def queue_loader(loader_name):
    """Queue a single loader."""
    task_def = f"algo-{loader_name}-loader"

    try:
        response = ecs.run_task(
            cluster='algo-cluster',
            taskDefinition=task_def,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': ['subnet-0ccb7db133dd4071e'],
                    'securityGroups': ['sg-0ddae70a1a80b54bd'],
                    'assignPublicIp': 'ENABLED'
                }
            }
        )

        if response['tasks']:
            task_id = response['tasks'][0]['taskArn'].split('/')[-1]
            print(f"[OK] Queued {loader_name}: {task_id}")
            return True
    except Exception as e:
        print(f"[ERROR] {loader_name}: {e}")

    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 retry_specific_loaders.py <loader1> [loader2] ...")
        print("Example: python3 retry_specific_loaders.py analyst_sentiment signals_etf_daily")
        exit(1)

    loaders_to_retry = sys.argv[1:]
    print(f"Retrying {len(loaders_to_retry)} loaders: {', '.join(loaders_to_retry)}")

    for loader in loaders_to_retry:
        queue_loader(loader)
        time.sleep(1)

    print("\nQueued for retry")
