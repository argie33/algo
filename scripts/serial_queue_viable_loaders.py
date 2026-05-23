#!/usr/bin/env python3
"""Serial queue for viable data loaders — one at a time, proper delays to avoid SEC rate limiting."""

import boto3
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

VIABLE_LOADERS = [
    "financials_annual_balance",
    "financials_annual_income",
    "financials_annual_cashflow",
    "financials_quarterly_balance",
    "financials_quarterly_income",
    "financials_quarterly_cashflow",
    "financials_ttm_income",
    "financials_ttm_cashflow",
    "earnings_history",
]

def launch_task(ecs, loader_name: str):
    """Launch a single ECS task."""
    try:
        logger.info(f"Launching: {loader_name}")
        response = ecs.run_task(
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
            logger.info(f"  Task launched: {task_arn}")
            return task_arn
        else:
            logger.error(f"  Launch failed: {response.get('failures')}")
            return None
    except Exception as e:
        logger.error(f"  Error: {e}")
        return None

def wait_for_task(ecs, task_arn: str, timeout_min: int = 35) -> tuple:
    """Wait for task completion with periodic logging."""
    start = time.time()
    timeout_sec = timeout_min * 60
    check_interval = 30  # Check every 30s
    last_log = 0

    while time.time() - start < timeout_sec:
        try:
            task = ecs.describe_tasks(
                cluster='algo-cluster',
                tasks=[task_arn]
            )['tasks'][0]

            status = task['lastStatus']
            now = time.time()
            elapsed = (now - start) / 60

            # Log progress every 2 minutes
            if now - last_log > 120:
                logger.info(f"  Running... {elapsed:.1f}m / {timeout_min}m")
                last_log = now

            if status == 'STOPPED':
                exit_code = task['containers'][0].get('exitCode', -1)
                elapsed_str = f"{elapsed:.1f}m"
                logger.info(f"  Completed: exit {exit_code} ({elapsed_str})")
                return status, exit_code

            time.sleep(check_interval)
        except Exception as e:
            logger.error(f"  Check error: {e}")
            return 'ERROR', -1

    # Timeout
    logger.error(f"  TIMEOUT after {timeout_min}m, stopping task")
    try:
        ecs.stop_task(cluster='algo-cluster', task=task_arn, reason='Serial queue timeout')
    except:
        pass
    return 'TIMEOUT', -1

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')

    logger.info(f"SERIAL QUEUE: {len(VIABLE_LOADERS)} viable data loaders")
    logger.info("Running ONE AT A TIME with 90s delay between launches\n")

    ok = failed = 0
    failed_loaders = []

    for i, loader in enumerate(VIABLE_LOADERS, 1):
        logger.info(f"\n[{i}/{len(VIABLE_LOADERS)}] {loader}")

        # Launch
        task_arn = launch_task(ecs, loader)
        if not task_arn:
            failed += 1
            failed_loaders.append(loader)
            logger.warning(f"  FAILED to launch")
            if i < len(VIABLE_LOADERS):
                time.sleep(90)  # Still wait before next
            continue

        # Wait (SEC EDGAR needs 30-35 minutes due to rate limiting)
        timeout = 35 if 'financials' in loader else 30
        status, exit_code = wait_for_task(ecs, task_arn, timeout_min=timeout)

        if status == 'STOPPED' and exit_code in (0, 1):
            ok += 1
            logger.info(f"  ✓ SUCCESS")
        else:
            failed += 1
            failed_loaders.append(loader)
            logger.error(f"  ✗ FAILED ({status} exit {exit_code})")

        # Delay before next loader (90s = 1.5 min)
        if i < len(VIABLE_LOADERS):
            logger.info(f"  Waiting 90s before next loader...")
            time.sleep(90)

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info(f"SERIAL QUEUE COMPLETE: {ok} OK, {failed} FAILED out of {len(VIABLE_LOADERS)}")
    if failed_loaders:
        logger.info(f"Failed loaders: {', '.join(failed_loaders)}")
    logger.info(f"{'='*70}\n")

    return failed == 0

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
