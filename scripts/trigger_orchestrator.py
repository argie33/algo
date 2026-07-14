#!/usr/bin/env python3
"""
Manual Orchestrator Trigger - Run when EventBridge schedules are disabled.

Usage:
  python3 scripts/trigger_orchestrator.py [--dry-run] [--mode paper|live|auto]

This script manually invokes the algo-algo-dev Lambda function with proper EventBridge parameters,
simulating what the scheduled triggers would do. Use this when EventBridge schedules are disabled
or when you need to manually run the orchestrator.
"""

import json
import logging
import sys
from argparse import ArgumentParser

import boto3

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def invoke_orchestrator(
    run_identifier: str = "morning",
    execution_mode: str = "paper",
    dry_run: bool = False,
    region: str = "us-east-1",
    function_name: str = "algo-algo-dev",
) -> dict:
    """Invoke orchestrator Lambda with proper EventBridge payload."""

    client = boto3.client("lambda", region_name=region)

    payload = {
        "source": "eventbridge-scheduler",
        "run_identifier": run_identifier,
        "execution_mode": execution_mode,
        "dry_run": dry_run,
        "note": f"Manual trigger via {__file__}",
        "run_date": "now",
    }

    logger.info(f"Invoking {function_name} with payload:")
    logger.info(json.dumps(payload, indent=2))

    try:
        # CRITICAL FIX: Use async invocation (Event) not sync (RequestResponse)
        # Orchestrator Lambda takes 11-15 minutes, but boto3 client timeout is 60s
        # Async invocation returns immediately when queued successfully
        # Lambda execution happens asynchronously and logs to CloudWatch
        response = client.invoke(
            FunctionName=function_name,
            InvocationType="Event",  # Async invocation - returns immediately
            Payload=json.dumps(payload),
            # Note: LogType='Tail' only works with RequestResponse (sync mode)
        )

        status_code = response["StatusCode"]
        logger.info(f"Lambda invocation queued with StatusCode: {status_code}")
        request_id = response.get("ResponseMetadata", {}).get("HTTPHeaders", {}).get("x-amzn-requestid", "unknown")
        logger.info(f"Request ID: {request_id}")

        if status_code == 202:
            # 202 Accepted = successfully queued for async execution
            logger.info(
                f"Orchestrator queued successfully for async execution.\n"
                f"Execution mode: {payload['execution_mode']}\n"
                f"Run identifier: {payload['run_identifier']}\n"
                f"Check CloudWatch Logs for execution progress:\n"
                f"  aws logs tail /aws/lambda/{function_name} --follow"
            )
            return {
                "success": True,
                "message": "Orchestrator invocation queued successfully",
                "request_id": request_id,
                "invocation_type": "async",
                "payload": payload,
            }
        else:
            logger.error(f"Lambda invocation failed with status {status_code}")
            if "FunctionError" in response:
                logger.error(f"FunctionError: {response['FunctionError']}")
            return {"error": f"StatusCode {status_code}"}

    except Exception as e:
        logger.error(f"Error invoking Lambda: {e}")
        raise


def main():
    parser = ArgumentParser(description="Manually trigger orchestrator Lambda")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (no actual trades)")
    parser.add_argument("--mode", choices=["paper", "live", "auto"], default="paper", help="Execution mode")
    parser.add_argument(
        "--run",
        choices=["premarket", "morning", "afternoon", "preclose", "evening"],
        default="morning",
        help="Run identifier",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("ORCHESTRATOR MANUAL TRIGGER")
    logger.info("=" * 70)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Run: {args.run}")
    logger.info(f"Dry-run: {args.dry_run}")
    logger.info("=" * 70)

    result = invoke_orchestrator(run_identifier=args.run, execution_mode=args.mode, dry_run=args.dry_run)

    if "error" in result:
        logger.error(f"Failed: {result['error']}")
        return 1

    logger.info("Orchestrator execution completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
