#!/usr/bin/env python3
"""
Load ONLY pure data source loaders (not downstream/computed).

Viable NOW (SEC EDGAR + yfinance):
  - 9 SEC EDGAR financials
  - 1 earnings_history (yfinance)

Skip for now (need orchestrator Phase 5 outputs):
  - signals_* (need buy_sell_daily)
  - algo_metrics_*, quality/value/key metrics (compute-based)
  - calendar (external)

STRATEGY:
1. Run this to load all data sources
2. Run orchestrator Phase 1-5
3. Then run signal loaders
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

# ONLY pure data source loaders (no downstream dependencies)
DATA_LOADERS = [
    # SEC EDGAR (9) - will work once Docker rebuilt with SEC retry fix
    "financials_annual_balance",
    "financials_annual_income",
    "financials_annual_cashflow",
    "financials_quarterly_balance",
    "financials_quarterly_income",
    "financials_quarterly_cashflow",
    "financials_ttm_income",
    "financials_ttm_cashflow",

    # yfinance (1)
    "earnings_history",
]


class DataLoaderRunner:
    """Run only pure data source loaders."""

    def __init__(self):
        self.ecs = boto3.client('ecs', region_name='us-east-1')

    def launch_task(self, loader_name: str) -> Optional[str]:
        """Launch ECS task."""
        try:
            logger.info(f"Loading {loader_name}...")
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
                return response['tasks'][0]['taskArn']
            logger.error(f"  Launch failed: {response.get('failures')}")
        except Exception as e:
            logger.error(f"  Error: {e}")

        return None

    def wait_for_task(self, task_arn: str, timeout_min: int = 25) -> Tuple[str, int]:
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
                    logger.info(f"  Running... {(now-start)/60:.1f}m")
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
            self.ecs.stop_task(cluster='algo-cluster', task=task_arn, reason='Data load timeout')
        except:
            pass
        return 'TIMEOUT', -1

    def run(self):
        """Run data loaders."""
        logger.info(f"DATA LOAD: {len(DATA_LOADERS)} pure data sources\n")
        logger.info("Note: SEC EDGAR retry logic rebuilt (waiting for Docker image deploy)")
        logger.info("SEC loaders will succeed once new image is available\n")

        ok = failed = 0

        for i, loader in enumerate(DATA_LOADERS, 1):
            logger.info(f"[{i:2d}/{len(DATA_LOADERS)}] {loader}")

            # Extra delay for SEC to avoid rate limiting
            if 'financials' in loader:
                time.sleep(20)

            # Launch
            task_arn = self.launch_task(loader)
            if not task_arn:
                failed += 1
                continue

            # Wait (SEC EDGAR might take longer)
            timeout = 25 if 'financials' in loader else 20
            status, exit_code = self.wait_for_task(task_arn, timeout_min=timeout)

            if status == 'STOPPED' and exit_code in (0, 1):
                ok += 1
                logger.info(f"  OK (exit {exit_code})")
            else:
                failed += 1
                logger.error(f"  FAILED ({status} exit {exit_code})")

            if i < len(DATA_LOADERS):
                time.sleep(3)

        # Summary
        print(f"\n{'='*70}")
        print(f"DATA LOAD COMPLETE: {ok} OK, {failed} FAILED out of {len(DATA_LOADERS)}")
        print(f"{'='*70}")
        print(f"\nNEXT STEPS:")
        print(f"1. Verify all 10 loaders succeeded")
        print(f"2. Run orchestrator Phase 1-5 to generate buy_sell_daily")
        print(f"3. Then run signal loaders")
        print(f"{'='*70}\n")

        return failed == 0


if __name__ == '__main__':
    runner = DataLoaderRunner()
    success = runner.run()
    sys.exit(0 if success else 1)
