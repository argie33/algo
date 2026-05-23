#!/usr/bin/env python3
"""Queue loaders in batches and test them."""

import boto3
import time
import sys
from collections import defaultdict

ecs = boto3.client('ecs', region_name='us-east-1')

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
            return task_id
    except Exception as e:
        print(f"ERROR queuing {loader_name}: {e}", file=sys.stderr)

    return None


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
    desc_response = ecs.describe_tasks(cluster='algo-cluster', tasks=task_arns)

    for task in desc_response.get('tasks', []):
        task_def_arn = task['taskDefinitionArn']
        task_def_name = task_def_arn.split('/')[-1]
        loader = task_def_name.split(':')[0].replace('algo-', '').replace('-loader', '')
        running[loader] = True

    return running


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: batch_queue_and_test.py <batch_size> [start_index]")
        print("Example: batch_queue_and_test.py 5 0  # Queue first 5 loaders")
        exit(1)

    batch_size = int(sys.argv[1])
    start_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    # Skip loaders already running or recently completed
    running = get_current_running()
    print(f"Currently running: {sorted(running.keys())}")

    # Get loaders that need testing
    pending = [l for l in LOADERS[start_index:] if l not in running]
    to_queue = pending[:batch_size]

    print(f"\nQueuing {len(to_queue)} loaders...")
    for loader in to_queue:
        task_id = queue_loader(loader)
        if task_id:
            print(f"  {loader}")
            time.sleep(1)

    print(f"\nQueued: {', '.join(to_queue)}")
    print(f"\nWaiting for completion (estimated 5-30 min depending on loader complexity)...")
    print("Run 'python3 scripts/queue_all_loaders_systematically.py status' to check progress")
