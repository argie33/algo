#!/usr/bin/env python3
"""
Local Orchestrator Scheduler - Runs orchestrator on schedule without requiring EventBridge.

Usage:
  python3 scripts/orchestrator_scheduler.py [--once] [--interval=4] [--mode=paper]

This provides the scheduling that EventBridge should provide, but locally without AWS permissions.
Runs the orchestrator Lambda every N hours on a schedule matching market hours.
"""

import json
import logging
import sys
import time
import boto3
import schedule
from datetime import datetime, timedelta, timezone
from argparse import ArgumentParser
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class OrchestratorScheduler:
    """Local scheduler for orchestrator Lambda invocations."""

    def __init__(self, execution_mode: str = "paper", interval_hours: int = 4, dry_run: bool = False):
        self.execution_mode = execution_mode
        self.interval_hours = interval_hours
        self.dry_run = dry_run
        self.lambda_client = boto3.client('lambda', region_name='us-east-1')
        self.run_count = 0

    def invoke_orchestrator(self, run_identifier: str = "scheduled", max_retries: int = 3):
        """Invoke orchestrator Lambda with proper parameters and exponential backoff retry.

        Handles Lambda rate limiting with exponential backoff:
        - Attempt 1: immediate
        - Attempt 2: wait 5s
        - Attempt 3: wait 10s
        """
        self.run_count += 1

        payload = {
            "source": "local-scheduler",
            "run_identifier": run_identifier,
            "execution_mode": self.execution_mode,
            "dry_run": self.dry_run,
            "run_date": "now",
            "note": f"Local scheduler run #{self.run_count}"
        }

        logger.info(f"Invoking orchestrator (run #{self.run_count}): {run_identifier} mode={self.execution_mode}")

        for attempt in range(1, max_retries + 1):
            try:
                # Use Event (async) invocation instead of RequestResponse (sync)
                # Async invocation doesn't hit rate limits as hard - returns immediately
                # Orchestrator runs in background and logs results to database
                response = self.lambda_client.invoke(
                    FunctionName='algo-algo-dev',
                    InvocationType='Event',  # Changed from RequestResponse to Event
                    Payload=json.dumps(payload)
                )

                if response['StatusCode'] == 202:
                    # Event invocation returns 202 Accepted
                    logger.info(f"Orchestrator queued successfully (async invocation)")
                    return True
                elif response['StatusCode'] == 200:
                    # Shouldn't happen with Event invocation, but handle it anyway
                    logger.info(f"Orchestrator invoked (sync response)")
                    return True
                else:
                    logger.error(f"Lambda returned status {response['StatusCode']}")
                    return False

            except Exception as e:
                error_msg = str(e)
                is_rate_limit = 'TooManyRequestsException' in error_msg or 'Rate Exceeded' in error_msg
                is_timeout = 'Timeout' in error_msg or 'Read timed out' in error_msg

                if (is_rate_limit or is_timeout) and attempt < max_retries:
                    wait_time = (2 ** (attempt - 1)) * 5  # 5s, 10s, 20s
                    logger.warning(
                        f"[ATTEMPT {attempt}/{max_retries}] Lambda rate limited/timeout. "
                        f"Waiting {wait_time}s before retry... ({error_msg[:100]})"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Failed to invoke orchestrator after {attempt} attempts: {e}")
                    return False

        return False

    def schedule_jobs(self):
        """Set up recurring orchestrator executions."""
        logger.info(f"Starting scheduler (mode={self.execution_mode}, interval={self.interval_hours}h)")

        # Run immediately on start
        self.invoke_orchestrator("startup")

        # Schedule recurring runs at interval (every N hours)
        schedule.every(self.interval_hours).hours.do(
            self.invoke_orchestrator,
            run_identifier=f"scheduled-every-{self.interval_hours}h"
        )

        logger.info(f"Next orchestrator run in {self.interval_hours} hours")

    def run_loop(self):
        """Main scheduler loop - runs indefinitely."""
        self.schedule_jobs()

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check for scheduled jobs every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped")
            return 0

    def run_once(self):
        """Run orchestrator once and exit."""
        logger.info("Running orchestrator once...")
        success = self.invoke_orchestrator("once")
        return 0 if success else 1


def main():
    parser = ArgumentParser(description="Local orchestrator scheduler")
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=4, help='Hours between executions (default: 4)')
    parser.add_argument('--mode', choices=['paper', 'live', 'auto'], default='paper', help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Dry-run mode (no actual trades)')

    args = parser.parse_args()

    # Validate mode
    if args.mode == 'live' and not args.dry_run:
        logger.warning("LIVE trading mode enabled - ensure this is intentional!")
        response = input("Continue with LIVE trading? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Aborted")
            return 1

    scheduler = OrchestratorScheduler(
        execution_mode=args.mode,
        interval_hours=args.interval,
        dry_run=args.dry_run
    )

    logger.info("="*70)
    logger.info("ORCHESTRATOR LOCAL SCHEDULER")
    logger.info("="*70)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Interval: {args.interval} hours")
    logger.info(f"Dry-run: {args.dry_run}")
    logger.info(f"Run once: {args.once}")
    logger.info("="*70)

    if args.once:
        return scheduler.run_once()
    else:
        return scheduler.run_loop()


if __name__ == "__main__":
    # Check if schedule module is available
    try:
        import schedule
    except ImportError:
        print("ERROR: 'schedule' module not found. Install with: pip install schedule")
        sys.exit(1)

    sys.exit(main())
