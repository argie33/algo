#!/usr/bin/env python3
import boto3
import json
from datetime import datetime

sfn = boto3.client('stepfunctions', region_name='us-east-1')

execution_arn = 'arn:aws:states:us-east-1:626216981288:execution:algo-morning-prep-pipeline-dev:manual-verify-scores-1784072242'

try:
    response = sfn.describe_execution(executionArn=execution_arn)
    status = response['status']
    start = datetime.fromisoformat(response['startDate'].isoformat())
    
    print(f"Pipeline Execution Status:")
    print(f"  ARN: {execution_arn}")
    print(f"  Status: {status}")
    print(f"  Started: {start}")
    print(f"  Current time: {datetime.now(start.tzinfo)}")
    
    if 'stopDate' in response:
        stop = datetime.fromisoformat(response['stopDate'].isoformat())
        duration = (stop - start).total_seconds()
        print(f"  Completed: {stop}")
        print(f"  Duration: {duration:.1f}s")
    else:
        elapsed = (datetime.now(start.tzinfo) - start).total_seconds()
        print(f"  Elapsed: {elapsed:.1f}s (still running)")
    
    if 'cause' in response:
        print(f"  Failure cause: {response['cause']}")
    
except Exception as e:
    print(f"Error: {e}")
