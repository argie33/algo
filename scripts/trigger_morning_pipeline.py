#!/usr/bin/env python3
"""
Manual trigger for morning data pipeline (prices + technical indicators).
Simulates EventBridge Scheduler execution when automatic scheduling is unavailable.
Usage: python scripts/trigger_morning_pipeline.py
"""

import boto3
import json
import sys
from datetime import datetime
from botocore.exceptions import ClientError

def trigger_morning_pipeline():
    """Manually invoke the morning data pipeline Step Function."""

    region = "us-east-1"
    state_machine_arn = "arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev"

    sfn = boto3.client("stepfunctions", region_name=region)

    execution_name = f"manual-morning-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    try:
        response = sfn.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps({"execution_name": execution_name})
        )

        print(f"[SUCCESS] Morning pipeline triggered")
        print(f"  Execution: {response['executionArn']}")
        print(f"  Start time: {response['startDate']}")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"[ERROR] Failed to trigger pipeline: {error_code}")
        print(f"  Message: {e.response['Error']['Message']}")
        return False

if __name__ == "__main__":
    success = trigger_morning_pipeline()
    sys.exit(0 if success else 1)
