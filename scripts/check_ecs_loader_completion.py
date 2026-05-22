#!/usr/bin/env python3
"""
Check ECS loader execution status and CloudWatch logs for completion proof.
Connects to AWS to verify all loaders are completing successfully.
"""
import boto3
import json
from datetime import datetime, timedelta
from typing import Dict, List

def check_ecs_loader_status():
    """Check ECS task definitions and executions for all loaders."""
    try:
        ecs = boto3.client('ecs', region_name='us-east-1')
        logs = boto3.client('logs', region_name='us-east-1')

        # List all ECS task definitions for loaders
        task_defs = ecs.list_task_definitions(
            familyPrefix='algo-',
            sort='DESC',
            maxResults=100
        )

        loader_tasks = [td for td in task_defs.get('taskDefinitionArns', []) if 'loader' in td]

        print(f"Found {len(loader_tasks)} loader task definitions in ECS")
        print("\nLoader Task Definitions:")
        print("=" * 80)

        for task_arn in sorted(loader_tasks)[:30]:
            task_name = task_arn.split('/')[-1]
            print(f"✓ {task_name}")

        # Check for recent task executions
        print("\n\nChecking for recent task executions...")
        print("=" * 80)

        cluster = 'algo-cluster'

        # List recent tasks
        running_tasks = ecs.list_tasks(
            cluster=cluster,
            desiredStatus='RUNNING'
        )

        stopped_tasks = ecs.list_tasks(
            cluster=cluster,
            desiredStatus='STOPPED',
            maxResults=50
        )

        print(f"\nRunning tasks: {len(running_tasks.get('taskArns', []))}")
        print(f"Recently stopped tasks: {len(stopped_tasks.get('taskArns', []))}")

        # Check CloudWatch logs for loaders
        print("\n\nChecking CloudWatch log groups...")
        print("=" * 80)

        log_groups = logs.describe_log_groups()
        loader_logs = [lg for lg in log_groups.get('logGroups', []) if 'loader' in lg['logGroupName']]

        print(f"\nFound {len(loader_logs)} loader log groups")

        success_count = 0
        error_count = 0

        for lg in sorted(loader_logs, key=lambda x: x['logGroupName']):
            log_group = lg['logGroupName']

            # Get recent log streams
            streams = logs.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=5
            )

            recent_streams = streams.get('logStreams', [])
            if recent_streams:
                latest = recent_streams[0]
                last_event = latest.get('lastEventTimestamp', 0) / 1000
                last_event_time = datetime.fromtimestamp(last_event)
                time_ago = datetime.now() - last_event_time

                # Get log events from latest stream
                events = logs.get_log_events(
                    logGroupName=log_group,
                    logStreamName=latest['logStreamName'],
                    limit=100
                )

                log_messages = events.get('events', [])

                # Check exit codes in logs
                exit_zero = any('exited with code: 0' in e.get('message', '') for e in log_messages)
                exit_nonzero = any('exited with code:' in e.get('message', '') and 'code: 0' not in e.get('message', '') for e in log_messages)
                is_running = any('Executing:' in e.get('message', '') for e in log_messages) and not (exit_zero or exit_nonzero)

                if exit_zero:
                    status = "[DONE]"
                elif exit_nonzero:
                    status = "[FAIL]"
                elif is_running:
                    status = "[RUN ]"
                else:
                    status = "[????]"
                loader_name = log_group.split('/')[-1]
                hours_ago = int(time_ago.total_seconds() // 3600)

                print(f"{status} {loader_name:40} ({hours_ago}h ago) - {len(log_messages)} events")

                if log_messages and hours_ago < 24:
                    last_msg = log_messages[-1]['message'][:100]
                    print(f"   Latest: {last_msg}")

                if exit_zero:
                    success_count += 1
                if exit_nonzero:
                    error_count += 1

        print(f"\n\nSummary from sampled loaders: {success_count} DONE, {error_count} FAILED")

    except Exception as e:
        print(f"Error checking ECS status: {e}")
        print("\nTo use this script, ensure AWS credentials are configured:")
        print("  - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in environment")
        print("  - Or AWS credentials in ~/.aws/credentials")
        print("  - Or IAM role attached to EC2/ECS task")

if __name__ == '__main__':
    check_ecs_loader_status()
