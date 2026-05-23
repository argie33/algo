#!/usr/bin/env python3
"""
Serial Batch Loader Runner - Prevent rate limiting and resource exhaustion.

Runs ECS loader tasks SERIALLY (one at a time) instead of all-parallel,
avoiding:
  - SEC EDGAR rate limit cascades (429 errors)
  - RDS connection pool exhaustion
  - Thundering herd on external APIs

Run:
    python3 algo_loader_batch_runner.py

BEHAVIOR:
  1. Get list of all loaders
  2. For each loader:
     - Launch ECS task (no freshness check - just run)
     - Poll for completion (timeout: 20 min)
     - Log result
  3. Print summary
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import time
import logging
from datetime import datetime
from typing import List, Optional, Tuple
from utils.structured_logger import get_logger

logger = get_logger(__name__)

# All loaders (order: fast first, SEC heavy last)
LOADERS = [
    # Phase 1: Daily prices (fast)
    "stock_prices_daily",
    "etf_prices_daily",

    # Phase 2: Weekly/monthly
    "stock_prices_weekly",
    "stock_prices_monthly",
    "etf_prices_weekly",
    "etf_prices_monthly",

    # Phase 3: Market data
    "market_indices",
    "market_health_daily",
    "market_data_batch",
    "stock_symbols",
    "sectors",
    "calendar",

    # Phase 4: Economic data
    "econ_data",
    "feargreed",
    "naaim_data",
    "aaiidata",
    "seasonality",
    "eod_bulk_refresh",

    # Phase 5: Earnings (yfinance, moderate)
    "earnings_calendar",
    "earnings_history",
    "earnings_surprise",
    "earnings_revisions",

    # Phase 6: Analyst data
    "analyst_sentiment",
    "analyst_upgrades_downgrades",

    # Phase 7: Technical (compute-based)
    "technical_data_daily",
    "technicals_daily",
    "trend_template_data",

    # Phase 8: Signals (compute-based)
    "signals_daily",
    "signals_weekly",
    "signals_monthly",
    "signals_etf_daily",
    "signals_etf_weekly",
    "signals_etf_monthly",

    # Phase 9: Metrics (compute-based)
    "algo_metrics_daily",
    "stock_scores",
    "swing_trader_scores",
    "quality_metrics",
    "value_metrics",
    "key_metrics",
    "growth_metrics",
    "industry_ranking",

    # Phase 10: SEC EDGAR (HIGH RATE LIMIT RISK - run last with big delays)
    "financials_annual_balance",
    "financials_annual_income",
    "financials_annual_cashflow",
    "financials_quarterly_balance",
    "financials_quarterly_income",
    "financials_quarterly_cashflow",
    "financials_ttm_income",
    "financials_ttm_cashflow",
]


class SimpleBatchRunner:
    """Simple, robust serial loader runner."""

    def __init__(self):
        self.ecs = boto3.client('ecs', region_name='us-east-1')
        self.results = []

    def launch_task(self, loader_name: str) -> Optional[str]:
        """Launch ECS task and return ARN."""
        try:
            logger.info(f"Launching {loader_name}...")
            response = self.ecs.run_task(
                cluster='algo-cluster',
                taskDefinition=f'algo-{loader_name}-loader',
                launchType='FARGATE',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': ['subnet-0ccb7db133dd4071e'],
                        'securityGroups': ['sg-0ddae70a1a80b54bd'],
                        'assignPublicIp': 'DISABLED'
                    }
                }
            )

            if response.get('tasks'):
                task_arn = response['tasks'][0]['taskArn']
                logger.info(f"  OK: {task_arn.split('/')[-1]}")
                return task_arn

            logger.error(f"  FAIL: {response.get('failures', 'unknown error')}")
        except Exception as e:
            logger.error(f"  FAIL: {e}")

        return None

    def wait_for_task(self, task_arn: str, timeout_min: int = 20) -> Tuple[str, int]:
        """Wait for task. Returns (status, exit_code)."""
        start = time.time()
        timeout_sec = timeout_min * 60
        last_check = 0

        while time.time() - start < timeout_sec:
            try:
                task = self.ecs.describe_tasks(
                    cluster='algo-cluster',
                    tasks=[task_arn]
                )['tasks'][0]

                status = task['lastStatus']

                # Log progress every 60s
                now = time.time()
                if now - last_check > 60:
                    elapsed = (now - start) / 60
                    logger.info(f"  Running... {elapsed:.1f}m")
                    last_check = now

                if status == 'STOPPED':
                    exit_code = task['containers'][0].get('exitCode', -1) if task['containers'] else -1
                    return status, exit_code

                time.sleep(10)
            except Exception as e:
                logger.error(f"  Check error: {e}")
                return 'ERROR', -1

        # Timeout - stop the task
        try:
            self.ecs.stop_task(cluster='algo-cluster', task=task_arn, reason='Batch timeout')
        except:
            pass
        return 'TIMEOUT', -1

    def run(self):
        """Run all loaders."""
        logger.info(f"BATCH RUN: {len(LOADERS)} loaders, serial execution\n")

        completed = failed = 0

        for i, loader in enumerate(LOADERS, 1):
            logger.info(f"[{i:2d}/{len(LOADERS)}] {loader}")

            # For SEC loaders, wait extra to avoid rate limit storms
            if 'financial' in loader or 'earnings_history' in loader:
                time.sleep(15)

            # Launch
            task_arn = self.launch_task(loader)
            if not task_arn:
                failed += 1
                self.results.append((loader, 'FAILED_LAUNCH', -1))
                continue

            # Wait
            status, exit_code = self.wait_for_task(task_arn)

            if status == 'STOPPED' and exit_code in (0, 1):
                completed += 1
                self.results.append((loader, 'OK' if exit_code == 0 else 'PARTIAL', exit_code))
                logger.info(f"  Completed (exit {exit_code})")
            else:
                failed += 1
                self.results.append((loader, status, exit_code))
                logger.info(f"  Failed ({status} exit {exit_code})")

            # Small delay between loaders
            if i < len(LOADERS):
                time.sleep(3)

        # Summary
        print(f"\n{'='*70}")
        print(f"BATCH COMPLETE: {completed} OK, {failed} FAILED (total {len(LOADERS)})")
        print(f"{'='*70}\n")

        for loader, status, exit_code in self.results[-10:]:
            print(f"  {loader:45} {status:10} exit={exit_code}")

        return failed == 0


if __name__ == '__main__':
    runner = SimpleBatchRunner()
    success = runner.run()
    sys.exit(0 if success else 1)
