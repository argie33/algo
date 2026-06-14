#!/usr/bin/env python3
"""Kill hanging ECS tasks and Step Functions executions consuming resources."""
import boto3
import sys

ecs = boto3.client('ecs', region_name='us-east-1')
sfn = boto3.client('stepfunctions', region_name='us-east-1')

print("=" * 70)
print("CHECKING FOR HANGING TASKS...")
print("=" * 70)

# List running ECS tasks
try:
    response = ecs.list_tasks(cluster='algo-dev', desiredStatus='RUNNING')
    running_tasks = response.get('taskArns', [])

    if running_tasks:
        print(f"\nFound {len(running_tasks)} running ECS tasks:")
        for arn in running_tasks[:50]:
            task_id = arn.split('/')[-1]
            print(f"  {arn}")

        # Kill them
        print("\nKilling hanging ECS tasks...")
        for arn in running_tasks:
            try:
                ecs.stop_task(cluster='algo-dev', task=arn, reason='Killing hanging loader task consuming resources')
                task_id = arn.split('/')[-1]
                print(f"  [STOPPED] {task_id}")
            except Exception as e:
                print(f"  [ERROR] Failed to stop {arn}: {e}")
    else:
        print("\nNo running ECS tasks found")
except Exception as e:
    print(f"Error listing ECS tasks: {e}")

# Check Step Functions executions
print("\n" + "=" * 70)
print("CHECKING STEP FUNCTIONS...")
print("=" * 70)

state_machines = [
    'arn:aws:states:us-east-1:ACCOUNT:stateMachine:algo-eod-pipeline-dev',
    'arn:aws:states:us-east-1:ACCOUNT:stateMachine:algo-morning-pipeline-dev',
]

try:
    for sm_arn in state_machines:
        try:
            response = sfn.list_executions(stateMachineArn=sm_arn, statusFilter='RUNNING')
            executions = response.get('executions', [])

            if executions:
                print(f"\nFound {len(executions)} stuck executions in {sm_arn.split(':')[-1]}:")
                for exec in executions:
                    print(f"  {exec['name']} - started {exec['startDate']}")
                    # Abort them
                    try:
                        sfn.stop_execution(executionArn=exec['executionArn'])
                        print(f"    [ABORTED]")
                    except Exception as e:
                        print(f"    [ERROR] Could not abort: {e}")
        except Exception as e:
            if 'does not exist' in str(e):
                print(f"State machine {sm_arn.split(':')[-1]} not found (may not be deployed)")
            else:
                print(f"Error checking {sm_arn}: {e}")
except Exception as e:
    print(f"Error with Step Functions: {e}")

print("\n" + "=" * 70)
print("CLEANUP COMPLETE")
print("=" * 70)
