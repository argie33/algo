#!/usr/bin/env python3
"""Queue loaders in small batches with monitoring to avoid DB connection exhaustion."""

import boto3
import time
import sys
from datetime import datetime

ecs = boto3.client('ecs', region_name='us-east-1')

# Prioritize loaders: start with most critical (quickest/lightest)
QUICK_LOADERS = [
    "stock_symbols", "sectors", "company_profile", "market_indices"
]

MEDIUM_LOADERS = [
    "aaiidata", "feargreed", "econ_data", "market_health_daily",
    "analyst_sentiment", "analyst_upgrades_downgrades", "earnings_calendar",
    "earnings_history", "earnings_revisions", "earnings_surprise", "stock_scores"
]

HEAVY_LOADERS = [
    "stock_prices_daily", "stock_prices_monthly", "stock_prices_weekly",
    "etf_prices_daily", "etf_prices_monthly", "etf_prices_weekly",
    "technical_data_daily", "algo_metrics_daily", "growth_metrics", "key_metrics",
    "quality_metrics", "value_metrics", "swing_trader_scores",
    "financials_annual_balance", "financials_annual_cashflow", "financials_annual_income",
    "financials_quarterly_balance", "financials_quarterly_cashflow", "financials_quarterly_income",
    "financials_ttm_cashflow", "financials_ttm_income",
    "signals_daily", "signals_weekly", "signals_monthly",
    "signals_etf_daily", "signals_etf_weekly", "signals_etf_monthly",
    "eod_bulk_refresh", "naaim_data", "seasonality", "trend_template_data",
    "industry_ranking"
]

def queue_loader(loader_name):
    """Queue a single loader task."""
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
        return bool(response['tasks'])
    except Exception as e:
        print(f"ERROR {loader_name}: {e}")
        return False

def get_running_task_count():
    """Get current number of running ECS tasks."""
    try:
        response = ecs.list_tasks(cluster='algo-cluster')
        return len(response.get('taskArns', []))
    except:
        return 0

def queue_batch(loaders, batch_name, max_concurrent=4):
    """Queue a batch of loaders with concurrency control."""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === {batch_name} ({len(loaders)} loaders) ===")
    queued = 0
    failed = []

    for loader in loaders:
        # Wait for previous tasks to start before queueing next
        running = get_running_task_count()
        while running >= max_concurrent:
            print(f"  [WAIT] {running} tasks running, waiting for slots...")
            time.sleep(5)
            running = get_running_task_count()

        if queue_loader(loader):
            queued += 1
            print(f"  [OK] {loader}")
            time.sleep(0.2)
        else:
            failed.append(loader)
            print(f"  [FAIL] {loader}")

    print(f"  Result: {queued}/{len(loaders)} queued")
    return queued, failed

# Queue in priority order
print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting batch queue strategy")
print(f"  Max concurrent: 4 loaders (to keep DB connection usage < 10 connections)")

total_queued = 0
total_failed = []

# Batch 1: Quick loaders (4 items, ~2-3 min each)
q, f = queue_batch(QUICK_LOADERS, "BATCH 1: Quick Loaders", max_concurrent=4)
total_queued += q
total_failed.extend(f)

# Wait for batch 1 to finish
print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting 5 min for Batch 1 to complete...")
time.sleep(300)

# Batch 2: Medium loaders (11 items)
q, f = queue_batch(MEDIUM_LOADERS, "BATCH 2: Medium Loaders", max_concurrent=3)
total_queued += q
total_failed.extend(f)

# Wait for batch 2
print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting 10 min for Batch 2 to complete...")
time.sleep(600)

# Batch 3: Heavy loaders (remainder)
q, f = queue_batch(HEAVY_LOADERS, "BATCH 3: Heavy Loaders", max_concurrent=2)
total_queued += q
total_failed.extend(f)

print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === FINAL RESULT ===")
print(f"Total queued: {total_queued}")
if total_failed:
    print(f"Failed: {total_failed}")
else:
    print("All loaders queued successfully!")
