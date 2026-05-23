#!/usr/bin/env python3
"""Run failing loaders sequentially in controlled batches."""

import boto3
import time
import sys

ecs = boto3.client('ecs', region_name='us-east-1')

FAILED_LOADERS = [
    "algo_metrics_daily",
    "analyst_sentiment",
    "eod_bulk_refresh",
    "etf_prices_daily",
    "etf_prices_monthly",
    "etf_prices_weekly",
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
    "quality_metrics",
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

BATCH_SIZE = 3  # Run 3 at a time
TASK_TIMEOUT = 1800  # 30 minutes per batch

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
                    'subnets': ['subnet-0988e8d04bba87486', 'subnet-0ccb7db133dd4071e'],
                    'securityGroups': ['sg-0ddae70a1a80b54bd'],
                    'assignPublicIp': 'ENABLED'
                }
            }
        )

        if response['tasks']:
            task_id = response['tasks'][0]['taskArn'].split('/')[-1]
            return task_id
    except Exception as e:
        print(f"ERROR queueing {loader_name}: {e}")

    return None

def wait_for_batch_completion(batch_loaders):
    """Wait for a batch of loaders to complete."""
    print(f"\nBatch: {', '.join(batch_loaders)}")
    start_time = time.time()

    while True:
        running = ecs.list_tasks(
            cluster='algo-cluster',
            desiredStatus='RUNNING',
            maxResults=100
        ).get('taskArns', [])

        # Check if any of our loaders are still running
        still_running = []
        if running:
            desc = ecs.describe_tasks(cluster='algo-cluster', tasks=running)
            for task in desc.get('tasks', []):
                task_def = task['taskDefinitionArn'].split('/')[-1]
                loader = task_def.replace('algo-', '').replace('-loader', '')
                if loader in batch_loaders:
                    still_running.append(loader)

        elapsed = int(time.time() - start_time)
        if still_running:
            print(f"  [{elapsed}s] Still running: {len(still_running)} tasks")
        else:
            print(f"  [{elapsed}s] All tasks completed")
            break

        if elapsed > TASK_TIMEOUT:
            print(f"  TIMEOUT after {TASK_TIMEOUT}s")
            break

        time.sleep(15)

if __name__ == '__main__':
    print(f"Running {len(FAILED_LOADERS)} failed loaders in batches of {BATCH_SIZE}")

    # Run in batches
    for i in range(0, len(FAILED_LOADERS), BATCH_SIZE):
        batch = FAILED_LOADERS[i:i+BATCH_SIZE]

        # Queue this batch
        print(f"\nQueuing batch {i//BATCH_SIZE + 1}: {batch}")
        for loader in batch:
            task_id = queue_loader(loader)
            if task_id:
                print(f"  Queued {loader}: {task_id}")
            time.sleep(1)

        # Wait for batch to complete
        wait_for_batch_completion(batch)

        print(f"Batch complete. Waiting 10s before next batch...")
        time.sleep(10)

    print("\n✅ All batches complete")
