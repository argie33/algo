#!/usr/bin/env python3
"""Queue all loaders systematically and track completion."""

import boto3
import json
import time
import re
from datetime import datetime
from collections import defaultdict

ecs = boto3.client('ecs', region_name='us-east-1')

# List of all 48 loaders from Terraform mapping
LOADERS = [
    "aaiidata",
    "algo_metrics_daily",
    "analyst_sentiment",
    "analyst_upgrades_downgrades",
    "company_profile",
    "earnings_calendar",
    "earnings_history",
    "earnings_revisions",
    "earnings_surprise",
    "econ_data",
    "eod_bulk_refresh",
    "etf_prices_daily",
    "etf_prices_monthly",
    "etf_prices_weekly",
    "feargreed",
    "financials_annual_balance",
    "financials_annual_cashflow",
    "financials_annual_income",
    "financials_quarterly_balance",
    "financials_quarterly_cashflow",
    "financials_quarterly_income",
    "financials_ttm_cashflow",
    "financials_ttm_income",
    "growth_metrics",
    "industry_ranking",
    "key_metrics",
    "market_data_batch",
    "market_health_daily",
    "market_indices",
    "naaim_data",
    "quality_metrics",
    "seasonality",
    "sectors",
    "signals_daily",
    "signals_etf_daily",
    "signals_etf_monthly",
    "signals_etf_weekly",
    "signals_monthly",
    "signals_weekly",
    "stock_prices_daily",
    "stock_prices_monthly",
    "stock_prices_weekly",
    "stock_scores",
    "stock_symbols",
    "swing_trader_scores",
    "technical_data_daily",
    "trend_template_data",
    "value_metrics",
]

def get_current_running():
    """Get currently running tasks."""
    response = ecs.list_tasks(
        cluster='algo-cluster',
        desiredStatus='RUNNING',
        maxResults=100
    )

    task_arns = response.get('taskArns', [])
    if not task_arns:
        return {}

    running = {}
    # Batch describe all tasks
    desc_response = ecs.describe_tasks(cluster='algo-cluster', tasks=task_arns)

    for task in desc_response.get('tasks', []):
        task_def_arn = task['taskDefinitionArn']
        # Extract loader name from task definition ARN
        task_def_name = task_def_arn.split('/')[-1]
        loader = task_def_name.split(':')[0].replace('algo-', '').replace('-loader', '')
        task_id = task['taskArn'].split('/')[-1]
        running[loader] = task_id

    return running


def queue_loader(loader_name):
    """Queue a single loader."""
    task_def = f"algo-{loader_name}-loader"

    # Determine launch overrides based on loader type
    container_overrides = []

    if 'etf' in loader_name and 'signals' in loader_name:
        # Signal ETF variants need --asset-class
        container_overrides = [{
            'name': f'algo-{loader_name}',
            'environment': [
                {'name': 'LOADER_TYPE', 'value': loader_name}
            ]
        }]
    elif 'signals' in loader_name:
        # Signal stock variants need --timeframe
        timeframe = 'daily' if 'daily' in loader_name else 'weekly' if 'weekly' in loader_name else 'monthly'
        container_overrides = [{
            'name': f'algo-{loader_name}',
            'environment': [
                {'name': 'LOADER_TYPE', 'value': loader_name}
            ]
        }]

    try:
        response = ecs.run_task(
            cluster='algo-cluster',
            taskDefinition=task_def,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': ['subnet-0988e8d04bba87486'],
                    'securityGroups': ['sg-0e6c1a2b3c4d5e6f7'],
                    'assignPublicIp': 'ENABLED'
                }
            },
            containerOverrides=container_overrides if container_overrides else []
        )

        if response['tasks']:
            task_id = response['tasks'][0]['taskArn'].split('/')[-1]
            print(f"Queued {loader_name}: {task_id}")
            return task_id
    except Exception as e:
        print(f"ERROR queueing {loader_name}: {e}")

    return None


def get_stopped_tasks_summary():
    """Get summary of all stopped tasks."""
    response = ecs.list_tasks(
        cluster='algo-cluster',
        desiredStatus='STOPPED',
        maxResults=100
    )

    task_arns = response.get('taskArns', [])
    if not task_arns:
        return {}

    loaders = defaultdict(lambda: {'success': 0, 'failed': 0})

    # Batch describe all stopped tasks
    desc_response = ecs.describe_tasks(cluster='algo-cluster', tasks=task_arns)

    for task in desc_response.get('tasks', []):
        task_def_arn = task['taskDefinitionArn']
        # Extract loader name from task definition ARN
        task_def_name = task_def_arn.split('/')[-1]
        loader = task_def_name.split(':')[0].replace('algo-', '').replace('-loader', '')

        exit_code = task['containers'][0].get('exitCode') if task['containers'] else None
        if exit_code == 0:
            loaders[loader]['success'] += 1
        else:
            loaders[loader]['failed'] += 1

    return loaders


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'queue-all':
        # Queue all loaders
        running = get_current_running()
        print(f"Currently running: {len(running)}")
        for loader in running:
            print(f"  - {loader}")

        queued = []
        for loader in LOADERS:
            if loader not in running:
                task_id = queue_loader(loader)
                if task_id:
                    queued.append(loader)
                    time.sleep(1)  # Rate limit

        print(f"\nQueued: {len(queued)}")

    elif len(sys.argv) > 1 and sys.argv[1] == 'status':
        # Show status summary
        running = get_current_running()
        stopped = get_stopped_tasks_summary()

        print("LOADER STATUS SUMMARY")
        print(f"Currently running: {len(running)}")
        for loader in sorted(running.keys()):
            print(f"  [RUNNING] {loader}")

        print(f"\nCompleted/Failed:")
        for loader in sorted(LOADERS):
            if loader in stopped:
                s = stopped[loader]['success']
                f = stopped[loader]['failed']
                status = "PASS" if f == 0 else "FAIL"
                print(f"  [{status}] {loader:<35} {s} success, {f} failed")
            elif loader in running:
                print(f"  [QUEUED] {loader}")
            else:
                print(f"  [PENDING] {loader}")

    else:
        print("Usage:")
        print("  python3 queue_all_loaders_systematically.py queue-all")
        print("  python3 queue_all_loaders_systematically.py status")
