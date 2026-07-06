#!/usr/bin/env python3
import boto3

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
            if exec['status'] == 'RUNNING':
                exec_name = exec['name']
                exec_arn = exec['executionArn']
                print(f'Stopping hung execution: {exec_name}')
                sfn.stop_execution(executionArn=exec_arn, cause='Pipeline exceeded timeout threshold (5+ hours)')
                print('Execution stopped successfully')
            else:
                print(f'Execution is not running (status: {exec["status"]})')
