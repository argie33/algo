#!/usr/bin/env python3
"""Manually trigger the computed metrics pipeline (Step Functions).

This script starts the Step Functions state machine that loads all metric data:
- Financial statements (SEC Edgar)
- SEC valuations (PE/PB/PS/PEG)
- Value/Quality/Growth metrics (consolidated loader)
- Positioning metrics (institutional/insider/short)
- Stability metrics (volatility/beta)
- Stock scores (composite calculation)

Usage:
    python3 scripts/trigger_metrics_pipeline.py                # Trigger once
    python3 scripts/trigger_metrics_pipeline.py --watch        # Watch execution
    python3 scripts/trigger_metrics_pipeline.py --production   # Trigger in prod

Requires AWS credentials for step functions and sns.
"""

import argparse
import json
import sys
import time
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# State machine ARNs by environment
STATE_MACHINES = {
    "dev": "arn:aws:states:us-east-1:123456789012:stateMachine:algo-computed-metrics-pipeline-dev",
    "staging": "arn:aws:states:us-east-1:123456789012:stateMachine:algo-computed-metrics-pipeline-staging",
    "production": "arn:aws:states:us-east-1:123456789012:stateMachine:algo-computed-metrics-pipeline-prod",
}


def trigger_pipeline(environment: str = "dev") -> str | None:
    """Trigger the computed metrics pipeline in the specified environment.

    Args:
        environment: dev, staging, or production

    Returns:
        Execution ARN if successful, None if failed
    """
    try:
        sfn = boto3.client("stepfunctions", region_name="us-east-1")

        state_machine_arn = STATE_MACHINES.get(environment)
        if not state_machine_arn:
            print(f"[ERR] Unknown environment: {environment}")
            return None

        execution_name = f"manual-trigger-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        print(f"[TRIGGER] Starting {environment} metrics pipeline")
        print(f"  State Machine: {state_machine_arn}")
        print(f"  Execution:     {execution_name}")

        response = sfn.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps({"manual_trigger": True, "timestamp": datetime.now().isoformat()}),
        )

        execution_arn = response["executionArn"]
        print("[OK] Pipeline triggered successfully")
        print(f"  Execution ARN: {execution_arn}")
        return execution_arn

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "InvalidArn":
            print("[ERR] State machine not found (invalid ARN)")
            print("  Check that terraform apply has been run recently")
            print(f"  And that the state machine exists in {environment} environment")
        elif error_code == "AccessDenied":
            print("[ERR] Access denied - check IAM permissions for step functions:StartExecution")
        else:
            print(f"[ERR] {error_code}: {e.response['Error']['Message']}")
        return None

    except (BotoCoreError, Exception) as e:
        if "Unable to locate credentials" in str(e):
            print("[ERR] AWS credentials not found")
            print("  Run: aws configure")
            print("  Or set AWS_PROFILE environment variable")
        else:
            print(f"[ERR] {type(e).__name__}: {e}")
        return None


def watch_execution(execution_arn: str, poll_interval: int = 10, max_wait_minutes: int = 120) -> bool:
    """Watch a Step Functions execution until it completes.

    Args:
        execution_arn: ARN of the execution to watch
        poll_interval: Seconds between status checks
        max_wait_minutes: Maximum time to wait before giving up

    Returns:
        True if execution succeeded, False if failed or timed out
    """
    try:
        sfn = boto3.client("stepfunctions", region_name="us-east-1")
        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60

        print(f"\n[WATCH] Monitoring execution (checking every {poll_interval}s)")
        print(f"  Max wait: {max_wait_minutes} minutes")
        print()

        while time.time() - start_time < max_wait_seconds:
            response = sfn.describe_execution(executionArn=execution_arn)

            status = response["status"]
            start = response.get("startDate", "")
            end = response.get("stopDate", "")

            # Print status line
            elapsed = time.time() - start_time
            print(f"[{elapsed:6.0f}s] Status: {status:12s} | StartDate: {start} | StopDate: {end}")

            if status == "SUCCEEDED":
                print("\n[OK] Execution succeeded!")
                return True

            elif status == "FAILED":
                print("\n[FAIL] Execution failed")
                # Try to get error details
                if "cause" in response:
                    print(f"  Cause: {response['cause']}")
                return False

            elif status == "TIMED_OUT":
                print("\n[TIMEOUT] Execution timed out")
                return False

            elif status == "ABORTED":
                print("\n[ABORT] Execution was aborted")
                return False

            time.sleep(poll_interval)

        print(f"\n[TIMEOUT] Gave up after {max_wait_minutes} minutes of waiting")
        return False

    except Exception as e:
        print(f"\n[ERR] Error watching execution: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manually trigger the computed metrics pipeline"
    )
    parser.add_argument(
        "--environment",
        choices=["dev", "staging", "production"],
        default="dev",
        help="Environment to trigger (default: dev)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch the execution until it completes",
    )
    parser.add_argument(
        "--wait-minutes",
        type=int,
        default=120,
        help="Max minutes to wait if using --watch (default: 120)",
    )

    args = parser.parse_args()

    # Trigger the pipeline
    execution_arn = trigger_pipeline(args.environment)
    if not execution_arn:
        return 1

    # Watch if requested
    if args.watch:
        success = watch_execution(execution_arn, max_wait_minutes=args.wait_minutes)
        return 0 if success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
