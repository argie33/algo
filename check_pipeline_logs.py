#!/usr/bin/env python3
import boto3
import json

sfn = boto3.client('stepfunctions', region_name='us-east-1')
logs = boto3.client('logs', region_name='us-east-1')

execution_arn = 'arn:aws:states:us-east-1:626216981288:execution:algo-morning-prep-pipeline-dev:manual-verify-scores-1784072242'

try:
    # Get execution history
    history = sfn.get_execution_history(executionArn=execution_arn)
    
    print("Recent Execution Events:")
    for event in history['events'][-10:]:
        event_type = event['type']
        timestamp = event['timestamp']
        
        # Extract relevant details based on event type
        detail_str = ""
        if event_type == 'TaskStateEntered':
            detail = event.get('stateEnteredEventDetails', {})
            detail_str = f"  Enter: {detail.get('name')}"
        elif event_type == 'TaskStateExited':
            detail = event.get('stateExitedEventDetails', {})
            detail_str = f"  Exit: {detail.get('name')}"
        elif event_type == 'TaskStarted':
            detail_str = "  Task started"
        elif event_type == 'TaskSucceeded':
            detail_str = "  Task succeeded"
        elif event_type == 'TaskFailed':
            detail = event.get('taskFailedEventDetails', {})
            detail_str = f"  Task failed: {detail.get('error')}"
        elif event_type == 'ExecutionStarted':
            detail_str = "  Pipeline started"
        else:
            detail_str = f"  {event_type}"
        
        print(f"  {timestamp}: {detail_str}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
