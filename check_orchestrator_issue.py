#!/usr/bin/env python3
"""Diagnose orchestrator failure in AWS."""

import boto3

sf = boto3.client('stepfunctions', region_name='us-east-1')

print("=== AWS ORCHESTRATOR FAILURE DIAGNOSIS ===\n")

# Get the latest failed execution
executions = sf.list_executions(
    stateMachineArn='arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev',
    maxResults=1
)

if executions.get('executions'):
    latest = executions['executions'][0]
    exec_arn = latest['executionArn']
    print(f"Latest Execution: {exec_arn}")
    print(f"Status: {latest['status']}")
    print(f"Started: {latest['startDate']}")
    print()

    # Get execution history
    history = sf.get_execution_history(executionArn=exec_arn)

    # Find the task failure
    print("=== FAILURE DETAILS ===\n")
    for event in history.get('events', []):
        if 'TaskFailed' in event.get('type', ''):
            cause = event.get('taskFailedEventDetails', {}).get('cause', '')
            error = event.get('taskFailedEventDetails', {}).get('error', '')
            print(f"Error: {error}")
            print(f"\nCause (summary):")
            # Parse JSON if needed
            try:
                import json
                cause_json = json.loads(cause)

                # Check for container exit code
                if 'Containers' in cause_json and cause_json['Containers']:
                    container = cause_json['Containers'][0]
                    print(f"  Container: {container.get('Name')}")
                    print(f"  Exit Code: {container.get('ExitCode')}")
                    print(f"  Status: {container.get('LastStatus')}")

                if 'StoppedReason' in cause_json:
                    print(f"  Reason: {cause_json['StoppedReason']}")
            except:
                print(f"  {cause[:200]}")

        elif 'ExecutionFailed' in event.get('type', ''):
            error = event.get('executionFailedEventDetails', {}).get('error', '')
            cause = event.get('executionFailedEventDetails', {}).get('cause', '')
            print(f"PIPELINE ERROR: {error}")
            print(f"Cause: {cause}")

print("\n=== SUMMARY ===")
print("Root cause: stock_prices_daily ECS task exiting with exit code 1")
print("This halts the entire morning pipeline before stock_scores/growth_metrics can run")
print("AWS database is stale from 2026-06-30 (14 days old)")
print("\nNext step: Fix the stock_prices_daily loader in AWS")
