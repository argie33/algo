#!/usr/bin/env python3
"""
Queue loaders sequentially (one at a time) to prevent API rate limiting cascade.
Each loader runs to completion before next one starts.
"""

import boto3
import time
import sys
import logging
from typing import List, Dict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Prioritize SEC-dependent loaders first (they now have parallelism=1, safe to run)
SEC_LOADERS = [
    'algo-financials_annual_income-loader',
    'algo-financials_annual_balance-loader',
    'algo-financials_annual_cashflow-loader',
    'algo-financials_quarterly_income-loader',
    'algo-financials_quarterly_balance-loader',
    'algo-financials_quarterly_cashflow-loader',
    'algo-earnings_history-loader',
    'algo-earnings_revisions-loader',
    'algo-earnings_surprise-loader',
    'algo-earnings_calendar-loader',
]

# Other loaders
OTHER_LOADERS = [
    'algo-algo_metrics_daily-loader',
    'algo-analyst_sentiment-loader',
    'algo-analyst_upgrades_downgrades-loader',
    'algo-aaiidata-loader',
    'algo-company_profile-loader',
    'algo-econ_data-loader',
    'algo-eod_bulk_refresh-loader',
    'algo-etf_prices_daily-loader',
    'algo-etf_prices_monthly-loader',
    'algo-etf_prices_weekly-loader',
    'algo-feargreed-loader',
    'algo-financials_ttm_cashflow-loader',
    'algo-financials_ttm_income-loader',
    'algo-growth_metrics-loader',
    'algo-industry_ranking-loader',
    'algo-key_metrics-loader',
    'algo-market_data_batch-loader',
    'algo-market_health_daily-loader',
    'algo-market_indices-loader',
    'algo-naaim_data-loader',
    'algo-quality_metrics-loader',
    'algo-seasonality-loader',
    'algo-sectors-loader',
    'algo-signals_daily-loader',
    'algo-signals_etf_daily-loader',
    'algo-signals_etf_monthly-loader',
    'algo-signals_etf_weekly-loader',
    'algo-signals_monthly-loader',
    'algo-signals_weekly-loader',
    'algo-stock_prices_daily-loader',
    'algo-stock_prices_monthly-loader',
    'algo-stock_prices_weekly-loader',
    'algo-stock_scores-loader',
    'algo-stock_symbols-loader',
    'algo-swing_trader_scores-loader',
    'algo-technical_data_daily-loader',
    'algo-technicals_daily-loader',
    'algo-trend_template_data-loader',
    'algo-value_metrics-loader',
]

class SequentialLoaderQueue:
    def __init__(self, cluster='algo-cluster', region='us-east-1'):
        self.ecs = boto3.client('ecs', region_name=region)
        self.cluster = cluster
        self.completed = []
        self.failed = []

    def get_latest_task_definition(self, family: str) -> str:
        """Get the latest revision of a task definition."""
        response = self.ecs.describe_task_definition(taskDefinition=family)
        return response['taskDefinition']['taskDefinitionArn']

    def run_loader(self, family: str) -> str:
        """Run a single loader and return task ARN."""
        task_def = self.get_latest_task_definition(family)
        log.info(f"Running {family}")

        response = self.ecs.run_task(
            cluster=self.cluster,
            taskDefinition=task_def,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': ['subnet-0ccb7db133dd4071e'],
                    'securityGroups': ['sg-0ddae70a1a80b54bd'],
                    'assignPublicIp': 'DISABLED'
                }
            }
        )

        if response['tasks']:
            return response['tasks'][0]['taskArn']
        else:
            raise RuntimeError(f"Failed to launch {family}")

    def check_task_status(self, task_arn: str) -> str:
        """Get the status of a task."""
        response = self.ecs.describe_tasks(
            cluster=self.cluster,
            tasks=[task_arn]
        )
        if response['tasks']:
            return response['tasks'][0]['lastStatus']
        return 'UNKNOWN'

    def get_task_exit_code(self, task_arn: str):
        """Get the exit code of a completed task."""
        response = self.ecs.describe_tasks(
            cluster=self.cluster,
            tasks=[task_arn]
        )
        if response['tasks']:
            task = response['tasks'][0]
            if task['containers']:
                return task['containers'][0].get('exitCode')
        return None

    def wait_for_task(self, task_arn: str, loader_name: str) -> int:
        """Wait for a single task to complete, return exit code."""
        start_time = time.time()
        max_wait = 7200  # 2 hours max per task

        while time.time() - start_time < max_wait:
            status = self.check_task_status(task_arn)

            if status == 'STOPPED':
                exit_code = self.get_task_exit_code(task_arn)
                elapsed = int(time.time() - start_time)
                log.info(f"✓ {loader_name} completed (exit {exit_code}, {elapsed}s)")
                return exit_code

            log.info(f"  [{datetime.now().strftime('%H:%M:%S')}] {loader_name}: {status}")
            time.sleep(30)

        log.error(f"✗ {loader_name} exceeded max wait time (2h)")
        return -1

    def run_sequential(self, loaders: List[str]) -> None:
        """Run loaders one at a time."""
        log.info(f"\n{'='*60}")
        log.info(f"Starting sequential loader queue: {len(loaders)} total")
        log.info(f"{'='*60}\n")

        for i, loader in enumerate(loaders, 1):
            try:
                log.info(f"\n[{i}/{len(loaders)}] Queueing {loader}...")
                task_arn = self.run_loader(loader)
                exit_code = self.wait_for_task(task_arn, loader)

                if exit_code == 0 or exit_code == 1:  # 0=success, 1=partial success
                    self.completed.append((loader, exit_code))
                else:
                    self.failed.append((loader, exit_code))

                # Small gap between loaders
                if i < len(loaders):
                    log.info(f"Waiting 30s before next loader...\n")
                    time.sleep(30)

            except Exception as e:
                log.error(f"Failed to run {loader}: {e}")
                self.failed.append((loader, str(e)))

        # Summary
        log.info(f"\n{'='*60}")
        log.info(f"QUEUE COMPLETE")
        log.info(f"{'='*60}")
        log.info(f"Completed: {len(self.completed)}")
        log.info(f"Failed: {len(self.failed)}")

        if self.completed:
            log.info(f"\nSuccessful:")
            for loader, code in self.completed:
                log.info(f"  ✓ {loader} (exit {code})")

        if self.failed:
            log.error(f"\nFailed:")
            for loader, code in self.failed:
                log.error(f"  ✗ {loader} (exit {code})")

if __name__ == '__main__':
    queue = SequentialLoaderQueue()

    # Run SEC loaders first, then others
    all_loaders = SEC_LOADERS + OTHER_LOADERS

    queue.run_sequential(all_loaders)
