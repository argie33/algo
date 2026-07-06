#!/usr/bin/env python3
import boto3
import json

sfn = boto3.client('stepfunctions', region_name='us-east-1')
response = sfn.list_state_machines(maxResults=20)

for sm in response['stateMachines']:
    if 'computed-metrics' in sm['name']:
        exec_response = sfn.list_executions(
            stateMachineArn=sm['stateMachineArn'],
            maxResults=1
        )
        if exec_response['executions']:
            exec = exec_response['executions'][0]
            print(f"Execution: {exec['name']}")
            print(f"Status: {exec['status']}")

            # Get full execution details
            detail = sfn.describe_execution(executionArn=exec['executionArn'])
            print(f"\nExecution Details:")
            print(f"  Status: {detail['status']}")
            if 'cause' in detail:
                print(f"  Cause: {detail['cause'][:300]}")
            if 'error' in detail:
                print(f"  Error: {detail['error']}")
