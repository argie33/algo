#!/usr/bin/env python3
"""Monitor loaders, detect failures, and retry automatically."""

import boto3
import time
import sys
from collections import defaultdict
from datetime import datetime

ecs = boto3.client('ecs', region_name='us-east-1')

LOADERS = [
    "aaiidata", "algo_metrics_daily", "analyst_sentiment", "analyst_upgrades_downgrades",
    "company_profile", "earnings_calendar", "earnings_history", "earnings_revisions",
    "earnings_surprise", "econ_data", "eod_bulk_refresh", "etf_prices_daily",
    "etf_prices_monthly", "etf_prices_weekly", "feargreed", "financials_annual_balance",
    "financials_annual_cashflow", "financials_annual_income", "financials_quarterly_balance",
    "financials_quarterly_cashflow", "financials_quarterly_income", "financials_ttm_cashflow",
    "financials_ttm_income", "growth_metrics", "industry_ranking", "key_metrics",
    "market_data_batch", "market_health_daily", "market_indices", "naaim_data",
    "quality_metrics", "seasonality", "sectors", "signals_daily",
    "signals_etf_daily", "signals_etf_monthly", "signals_etf_weekly", "signals_monthly",
    "signals_weekly", "stock_prices_daily", "stock_prices_monthly", "stock_prices_weekly",
    "stock_scores", "stock_symbols", "swing_trader_scores", "technical_data_daily",
    "trend_template_data", "value_metrics",
]


def get_running_loaders():
    """Get set of currently running loaders."""
    response = ecs.list_tasks(cluster='algo-cluster', desiredStatus='RUNNING', maxResults=100)
    task_arns = response.get('taskArns', [])

    if not task_arns:
        return set()

    desc = ecs.describe_tasks(cluster='algo-cluster', tasks=task_arns)
    running = set()

    for task in desc.get('tasks', []):
        task_def_arn = task['taskDefinitionArn']
        task_def_name = task_def_arn.split('/')[-1]
        loader = task_def_name.split(':')[0].replace('algo-', '').replace('-loader', '')
        running.add(loader)

    return running


def get_latest_status(loader):
    """Get latest status for a loader."""
    # Get stopped tasks
    response = ecs.list_tasks(cluster='algo-cluster', desiredStatus='STOPPED', maxResults=100)
    task_arns = response.get('taskArns', [])

    if not task_arns:
        return None

    desc = ecs.describe_tasks(cluster='algo-cluster', tasks=task_arns)

    latest = None
    for task in desc.get('tasks', []):
        task_def_arn = task['taskDefinitionArn']
        task_def_name = task_def_arn.split('/')[-1]
        task_loader = task_def_name.split(':')[0].replace('algo-', '').replace('-loader', '')

        if task_loader == loader:
            exit_code = task['containers'][0].get('exitCode') if task['containers'] else None
            stopped_at = task.get('stoppedAt', 0)

            if latest is None or stopped_at > latest['stopped_at']:
                latest = {
                    'exit_code': exit_code,
                    'stopped_at': stopped_at,
                    'status': 'PASS' if exit_code == 0 else f'FAIL({exit_code})'
                }

    return latest


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
            return True
    except Exception as e:
        print(f"  ERROR queuing {loader_name}: {e}")

    return False


def report_status():
    """Generate and print status report."""
    running = get_running_loaders()

    passing = []
    failing = []
    not_run = []

    for loader in LOADERS:
        status = get_latest_status(loader)

        if loader in running:
            # Still running
            pass
        elif status is None:
            not_run.append(loader)
        elif status['status'] == 'PASS':
            passing.append(loader)
        else:
            failing.append(loader)

    print(f"\n{'=' * 70}")
    print(f"STATUS REPORT — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 70}")
    print(f"Running: {len(running)}")
    print(f"Passing: {len(passing)}/{len(LOADERS)}")
    print(f"Failing: {len(failing)}")
    print(f"Pending: {len(not_run)}")

    if failing:
        print(f"\nFailing loaders to retry:")
        for loader in failing:
            status = get_latest_status(loader)
            print(f"  {loader}: {status['status']}")

    return {'passing': len(passing), 'failing': len(failing), 'running': len(running), 'pending': len(not_run), 'failing_list': failing}


def main():
    """Main monitoring loop."""
    print("Starting loader monitor...")

    check_interval = 30  # seconds
    max_runtime = 7200   # 2 hours
    start_time = time.time()

    while time.time() - start_time < max_runtime:
        running = get_running_loaders()

        # Report progress
        status = report_status()

        # If some are failing and not currently running, retry them
        if status['failing_list'] and len(running) < 20:
            print(f"\nRetrying {len(status['failing_list'])} failed loaders...")
            for loader in status['failing_list'][:3]:  # Retry 3 at a time
                if queue_loader(loader):
                    print(f"  Requeued: {loader}")
                    time.sleep(1)

        # Stop if no more running and all tested
        if len(running) == 0 and status['pending'] == 0:
            print("\n✅ All loaders completed!")
            print(f"Final: {status['passing']} passing, {status['failing']} failing")
            break

        time.sleep(check_interval)

    print("\nMonitoring complete.")


if __name__ == '__main__':
    main()
