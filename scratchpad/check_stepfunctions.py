#!/usr/bin/env python3
import boto3
import json
from datetime import datetime, timedelta, timezone

# Get Step Functions client
sfn = boto3.client('stepfunctions', region_name='us-east-1')

try:
    # List state machines
    print("=== STEP FUNCTIONS STATE MACHINES ===")
    response = sfn.list_state_machines(maxResults=20)
    for sm in response['stateMachines']:
        print(f"  {sm['name']}: {sm['stateMachineArn']}")

    # Find the computed_metrics_pipeline
    computed_metrics_arn = None
    for sm in response['stateMachines']:
        if 'computed-metrics' in sm['name']:
            computed_metrics_arn = sm['stateMachineArn']
            break

    if computed_metrics_arn:
        print(f"\n=== COMPUTED METRICS PIPELINE EXECUTIONS (Last 10) ===")
        response = sfn.list_executions(
            stateMachineArn=computed_metrics_arn,
            maxResults=10
        )
        executions = response.get('executions', [])
        # Sort by startDate descending to show most recent first
        executions.sort(key=lambda x: x['startDate'], reverse=True)
        for execution in executions[:5]:
            status = execution['status']
            started_at = execution['startDate'].strftime('%Y-%m-%d %H:%M:%S UTC')
            print(f"  {execution['name']}: {status} (started {started_at})")
    else:
        print("Could not find computed-metrics pipeline")

    # Find the eod_pipeline
    response = sfn.list_state_machines(maxResults=20)
    eod_arn = None
    for sm in response['stateMachines']:
        if 'eod-pipeline' in sm['name'] and 'computed' not in sm['name']:
            eod_arn = sm['stateMachineArn']
            break

    if eod_arn:
        print(f"\n=== EOD PIPELINE EXECUTIONS (Last 5) ===")
        response = sfn.list_executions(
            stateMachineArn=eod_arn,
            maxResults=10
        )
        executions = response.get('executions', [])
        # Sort by startDate descending to show most recent first
        executions.sort(key=lambda x: x['startDate'], reverse=True)
        for execution in executions[:5]:
            status = execution['status']
            started_at = execution['startDate'].strftime('%Y-%m-%d %H:%M:%S UTC')
            print(f"  {execution['name']}: {status} (started {started_at})")
    else:
        print("Could not find eod-pipeline")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
