#!/usr/bin/env python3
"""
Retry only the loaders that failed or timed out.

Don't waste money re-running 8 that already succeeded.
Focus on fixing the 20 that failed (mostly SEC rate limiting).
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

# Only the 20 that failed or timed out (exclude 8 that succeeded)
FAILED_LOADERS = [
    # SEC EDGAR (rate limit fixes applied)
    "financials_annual_balance",
    "financials_annual_income",
    "financials_annual_cashflow",
    "financials_quarterly_balance",
    "financials_quarterly_income",
    "financials_quarterly_cashflow",
    "financials_ttm_income",
    "financials_ttm_cashflow",

    # Signals (may be ready now if data is available)
    "signals_daily",
    "signals_weekly",
    "signals_monthly",
    "signals_etf_daily",
    "signals_etf_weekly",
    "signals_etf_monthly",

    # Other failed
    "algo_metrics_daily",
    "earnings_history",
    "calendar",
    "quality_metrics",
    "value_metrics",
    "key_metrics",
]


class RetryRunner:
    """Run only the loaders that failed."""

    def __init__(self):
        self.ecs = boto3.client('ecs', region_name='us-east-1')
        self.results = []

    def launch_task(self, loader_name: str) -> Optional[str]:
        """Launch ECS task."""
        try:
            logger.info(f"Retry {loader_name}...")
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
                return task_arn

            logger.error(f"  Launch failed: {response.get('failures')}")
        except Exception as e:
            logger.error(f"  Error: {e}")

        return None

    def wait_for_task(self, task_arn: str, timeout_min: int = 20) -> Tuple[str, int]:
        """Wait for task completion."""
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

                # Log progress
                now = time.time()
                if now - last_check > 60:
                    logger.info(f"  Still running... {(now-start)/60:.1f}m")
                    last_check = now

                if status == 'STOPPED':
                    exit_code = task['containers'][0].get('exitCode', -1) if task['containers'] else -1
                    return status, exit_code

                time.sleep(10)
            except Exception as e:
                logger.error(f"  Check error: {e}")
                return 'ERROR', -1

        # Timeout
        try:
            self.ecs.stop_task(cluster='algo-cluster', task=task_arn, reason='Retry timeout')
        except:
            pass
        return 'TIMEOUT', -1

    def run(self):
        """Run only the failed loaders."""
        logger.info(f"RETRY RUN: {len(FAILED_LOADERS)} failed loaders, serial execution\n")

        ok = failed = 0

        for i, loader in enumerate(FAILED_LOADERS, 1):
            logger.info(f"[{i:2d}/{len(FAILED_LOADERS)}] {loader}")

            # Extra wait for SEC loaders (rate limit recovery)
            if 'financial' in loader or 'earnings_history' in loader:
                time.sleep(15)

            # Launch
            task_arn = self.launch_task(loader)
            if not task_arn:
                failed += 1
                logger.error(f"  Failed to launch")
                continue

            # Wait
            status, exit_code = self.wait_for_task(task_arn)

            if status == 'STOPPED' and exit_code in (0, 1):
                ok += 1
                logger.info(f"  OK (exit {exit_code})")
            else:
                failed += 1
                logger.error(f"  Failed ({status} exit {exit_code})")

            # Delay between tasks
            if i < len(FAILED_LOADERS):
                time.sleep(3)

        # Summary
        print(f"\n{'='*70}")
        print(f"RETRY COMPLETE: {ok} OK, {failed} FAILED")
        print(f"{'='*70}\n")

        return failed == 0


if __name__ == '__main__':
    runner = RetryRunner()
    success = runner.run()
    sys.exit(0 if success else 1)
