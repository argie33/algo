#!/usr/bin/env python3
"""
Queue all 54 loaders with concurrency control.
Ensures stable RDS connection pool usage (max 4 concurrent).
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

# All 54 loader families (without revision numbers)
LOADERS = [
    'algo-aaiidata-loader',
    'algo-algo_metrics_daily-loader',
    'algo-analyst_sentiment-loader',
    'algo-analyst_upgrades_downgrades-loader',
    'algo-calendar-loader',
    'algo-company_profile-loader',
    'algo-earnings_calendar-loader',
    'algo-earnings_history-loader',
    'algo-earnings_revisions-loader',
    'algo-earnings_surprise-loader',
    'algo-econ_data-loader',
    'algo-eod_bulk_refresh-loader',
    'algo-etf_prices_daily-loader',
    'algo-etf_prices_monthly-loader',
    'algo-etf_prices_weekly-loader',
    'algo-feargreed-loader',
    'algo-financials_annual_balance-loader',
    'algo-financials_annual_cashflow-loader',
    'algo-financials_annual_income-loader',
    'algo-financials_quarterly_balance-loader',
    'algo-financials_quarterly_cashflow-loader',
    'algo-financials_quarterly_income-loader',
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

class LoaderOrchestrator:
    def __init__(self, cluster='algo-cluster', region='us-east-1', max_concurrent=4):
        self.ecs = boto3.client('ecs', region_name=region)
        self.logs = boto3.client('logs', region_name=region)
        self.cluster = cluster
        self.max_concurrent = max_concurrent
        self.running_tasks: Dict[str, str] = {}  # loader_family -> task_arn
        self.completed = []
        self.failed = []

    def get_latest_task_definition(self, family: str) -> str:
        """Get the latest revision of a task definition."""
        response = self.ecs.describe_task_definition(taskDefinition=family)
        return response['taskDefinition']['taskDefinitionArn']

    def run_loader(self, family: str) -> str:
        """Run a single loader and return task ARN."""
        task_def = self.get_latest_task_definition(family)
        log.info(f"Running {family} (task def: {task_def})")

        response = self.ecs.run_task(
            cluster=self.cluster,
            taskDefinition=task_def,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': ['subnet-0ccb7db133dd4071e'],  # algo-cluster subnet
                    'securityGroups': ['sg-0ddae70a1a80b54bd'],  # algo-ecs-tasks-sg
                    'assignPublicIp': 'DISABLED'
                }
            }
        )

        if response['tasks']:
            task_arn = response['tasks'][0]['taskArn']
            return task_arn
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

    def queue_batch(self, loaders: List[str]) -> None:
        """Queue a batch of loaders to run."""
        log.info(f"\n{'='*60}")
        log.info(f"Queueing batch of {len(loaders)} loaders (max {self.max_concurrent} concurrent)")
        log.info(f"{'='*60}")

        for loader in loaders:
            try:
                task_arn = self.run_loader(loader)
                self.running_tasks[loader] = task_arn
                time.sleep(1)  # Small delay between launches
            except Exception as e:
                log.error(f"Failed to run {loader}: {e}")
                self.failed.append((loader, str(e)))

    def wait_for_batch(self) -> None:
        """Wait for all running tasks to complete."""
        log.info(f"\nWaiting for {len(self.running_tasks)} tasks to complete...")

        while self.running_tasks:
            log.info(f"  [{datetime.now().strftime('%H:%M:%S')}] Still running: {len(self.running_tasks)}")

            completed_loaders = []
            for loader, task_arn in list(self.running_tasks.items()):
                status = self.check_task_status(task_arn)

                if status == 'STOPPED':
                    exit_code = self.get_task_exit_code(task_arn)
                    log.info(f"✓ {loader} completed (exit code: {exit_code})")
                    self.completed.append((loader, exit_code))
                    completed_loaders.append(loader)
                elif status in ['STOPPED', 'DELETED']:
                    log.info(f"✓ {loader} stopped/completed")
                    self.completed.append((loader, 'STOPPED'))
                    completed_loaders.append(loader)

            for loader in completed_loaders:
                del self.running_tasks[loader]

            if self.running_tasks:
                time.sleep(10)  # Check every 10 seconds

    def run_all(self) -> None:
        """Run all 54 loaders in batches."""
        log.info(f"\n{'='*60}")
        log.info(f"Starting loader queue for {len(LOADERS)} total loaders")
        log.info(f"Max concurrent: {self.max_concurrent}")
        log.info(f"{'='*60}\n")

        # Queue in batches
        for i in range(0, len(LOADERS), self.max_concurrent):
            batch = LOADERS[i:i+self.max_concurrent]
            self.queue_batch(batch)

            # Wait for this batch before queueing next
            self.wait_for_batch()

            if i + self.max_concurrent < len(LOADERS):
                log.info(f"Batch {i//self.max_concurrent + 1} complete. Waiting 5s before next batch...\n")
                time.sleep(5)

        # Summary
        log.info(f"\n{'='*60}")
        log.info(f"ALL LOADERS COMPLETE")
        log.info(f"{'='*60}")
        log.info(f"Completed successfully: {len(self.completed)}")
        log.info(f"Failed to launch: {len(self.failed)}")

        if self.failed:
            log.error(f"\nFailed loaders:")
            for loader, error in self.failed:
                log.error(f"  - {loader}: {error}")

if __name__ == '__main__':
    orchestrator = LoaderOrchestrator(max_concurrent=4)
    orchestrator.run_all()
