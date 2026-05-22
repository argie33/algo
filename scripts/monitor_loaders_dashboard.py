#!/usr/bin/env python3
"""Monitor dashboard for all ECS loader execution."""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from datetime import datetime
from collections import defaultdict

ecs = boto3.client('ecs', region_name='us-east-1')

def get_cluster_status():
    """Get comprehensive loader status."""
    try:
        # Get all tasks
        response = ecs.list_tasks(
            cluster='algo-cluster',
            maxResults=100
        )

        task_arns = response['taskArns']
        if not task_arns:
            return {}

        # Describe all tasks
        tasks_response = ecs.describe_tasks(
            cluster='algo-cluster',
            tasks=task_arns
        )

        tasks = tasks_response['tasks']
        status_map = defaultdict(list)

        for task in tasks:
            # Extract loader name from task definition
            task_def_arn = task['taskDefinitionArn']
            # Format: arn:aws:ecs:region:account:task-definition/algo-{name}-loader:N
            parts = task_def_arn.split('/')[-1].split(':')[0]
            # algo-{name}-loader -> {name}
            loader_name = parts.replace('algo-', '').replace('-loader', '')

            status = task['lastStatus']
            exit_code = task.get('containers', [{}])[0].get('exitCode')

            status_map[status].append({
                'name': loader_name,
                'exit_code': exit_code,
                'created': task.get('createdAt'),
                'stopped': task.get('stoppedAt'),
            })

        return dict(status_map)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return {}

def print_dashboard():
    """Print loader status dashboard."""
    status = get_cluster_status()

    running = status.get('RUNNING', [])
    stopped = status.get('STOPPED', [])
    provisioning = status.get('PROVISIONING', [])

    print(f"\n{'='*80}")
    print(f"LOADER EXECUTION DASHBOARD — {datetime.now().strftime('%H:%M:%S UTC')}")
    print(f"{'='*80}")

    print(f"\nSUMMARY")
    print(f"  Running:      {len(running)}")
    print(f"  Provisioning: {len(provisioning)}")
    print(f"  Stopped:      {len(stopped)}")
    print(f"  Total:        {len(running) + len(provisioning) + len(stopped)}")

    if provisioning:
        print(f"\nPROVISIONING ({len(provisioning)})")
        for task in sorted(provisioning, key=lambda x: x['name']):
            print(f"  - {task['name']}")

    if running:
        print(f"\nRUNNING ({len(running)})")
        for task in sorted(running, key=lambda x: x['name']):
            print(f"  - {task['name']}")

    if stopped:
        success = [t for t in stopped if t['exit_code'] == 0]
        failed = [t for t in stopped if t['exit_code'] != 0]

        if success:
            print(f"\nCOMPLETED ({len(success)})")
            for task in sorted(success, key=lambda x: x['name'])[:10]:
                print(f"  - {task['name']}")
            if len(success) > 10:
                print(f"  ... and {len(success) - 10} more")

        if failed:
            print(f"\nFAILED ({len(failed)})")
            for task in sorted(failed, key=lambda x: x['name']):
                exit_code = task['exit_code'] if task['exit_code'] else 'N/A'
                print(f"  - {task['name']} (exit: {exit_code})")

    print(f"\n{'='*80}\n")
    return len(failed) == 0 if stopped else True

if __name__ == '__main__':
    success = print_dashboard()
    sys.exit(0 if success else 1)
