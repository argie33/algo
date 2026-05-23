#!/usr/bin/env python3
"""Requeue only the 10 known-failing loaders after fixes."""

import boto3
import time
from datetime import datetime

ecs = boto3.client('ecs', region_name='us-east-1')

# Only the 10 that were failing before
FAILED_LOADERS = [
    "naaim_data",
    "seasonality",
    "signals_etf_daily",
    "signals_etf_weekly",
    "swing_trader_scores",
    "stock_prices_daily",
    "stock_prices_monthly",
    "stock_prices_weekly",
    "etf_prices_daily",
    "etf_prices_monthly",
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
        return bool(response['tasks'])
    except Exception as e:
        print(f"ERROR {loader_name}: {e}")
        return False

print(f"[{datetime.now().strftime('%H:%M:%S')}] Requeuing {len(FAILED_LOADERS)} failed loaders only")
print(f"With fixes: RDS timeout 300s, character encoding fixed, batch concurrency 4\n")

queued = 0
failed = []

for loader in FAILED_LOADERS:
    if queue_loader(loader):
        queued += 1
        print(f"[OK] {loader}")
        time.sleep(0.5)
    else:
        failed.append(loader)
        print(f"[FAIL] {loader}")

print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Result: {queued}/{len(FAILED_LOADERS)} queued")
if failed:
    print(f"Failed to queue: {failed}")
