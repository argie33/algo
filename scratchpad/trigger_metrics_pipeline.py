#!/usr/bin/env python3
import boto3
import json
from datetime import datetime
import time

# Get Step Functions client
sfn = boto3.client('stepfunctions', region_name='us-east-1')

try:
    # Find the computed metrics pipeline
    response = sfn.list_state_machines(maxResults=20)
    computed_metrics_arn = None
    for sm in response['stateMachines']:
        if 'computed-metrics' in sm['name']:
            computed_metrics_arn = sm['stateMachineArn']
            break

    if not computed_metrics_arn:
        print("ERROR: Could not find computed-metrics pipeline")
        exit(1)

    print(f"Triggering: {computed_metrics_arn}")

    # Start execution
    timestamp = int(time.time())
    exec_response = sfn.start_execution(
        stateMachineArn=computed_metrics_arn,
        name=f"manual-trigger-{timestamp}",
        input=json.dumps({
            "execution_name": f"manual-metrics-{timestamp}",
            "trigger_type": "manual"
        })
    )

    print(f"SUCCESS: Started execution")
    print(f"  Execution ARN: {exec_response['executionArn']}")
    print(f"  Started at: {exec_response['startDate']}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
