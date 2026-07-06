#!/usr/bin/env python3
import boto3
from datetime import datetime

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
            print(f"Started: {exec['startDate']}")

            # Calculate duration
            started = exec['startDate'].replace(tzinfo=None)
            now = datetime.utcnow()
            duration_minutes = (now - started).total_seconds() / 60
            print(f"Duration: {duration_minutes:.1f} minutes")

            # Get execution history to see which step is stuck
            hist = sfn.get_execution_history(executionArn=exec['executionArn'], maxItems=100)

            print("\nRECENT EXECUTION EVENTS:")
            events = sorted(hist['events'], key=lambda x: x['id'])[-30:]
            for event in events:
                event_type = event['type']
                timestamp = event['timestamp']
                print(f"  {timestamp}: {event_type}")

                if 'stateEnteredEventDetails' in event:
                    state_name = event['stateEnteredEventDetails'].get('name', 'unknown')
                    print(f"    -> Entered state: {state_name}")

                if 'executionFailedEventDetails' in event:
                    error = event['executionFailedEventDetails'].get('error', 'unknown')
                    cause = event['executionFailedEventDetails'].get('cause', '')[:200]
                    print(f"    ERROR: {error}")
                    print(f"    CAUSE: {cause}")

                if 'taskFailedEventDetails' in event:
                    resource = event['taskFailedEventDetails'].get('resource', 'unknown')
                    error = event['taskFailedEventDetails'].get('error', 'unknown')
                    print(f"    TASK FAILED: {resource} - {error}")
