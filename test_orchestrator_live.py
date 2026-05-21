#!/usr/bin/env python3
"""
Test orchestrator execution and capture detailed logs
"""
import boto3
import time
import sys

region = 'us-east-1'
func_name = 'algo-algo-dev'

lam = boto3.client('lambda', region_name=region)
logs = boto3.client('logs', region_name=region)

print("\n" + "="*80)
print("ORCHESTRATOR EXECUTION TEST")
print("="*80)

# Invoke
print("\n[1] Invoking orchestrator...")
response = lam.invoke(FunctionName=func_name, InvocationType='Event')
print(f"    Status: {response['StatusCode']}")

# Wait for execution
print("[2] Waiting 25 seconds for execution...")
time.sleep(25)

# Get logs
print("[3] Retrieving CloudWatch logs...")
streams = logs.describe_log_streams(
    logGroupName=f'/aws/lambda/{func_name}',
    orderBy='LastEventTime', descending=True, limit=1
)
stream_name = streams['logStreams'][0]['logStreamName']

events = logs.get_log_events(
    logGroupName=f'/aws/lambda/{func_name}',
    logStreamName=stream_name, limit=1000
)

print(f"    Stream: {stream_name}")
print(f"    Total events: {len(events['events'])}\n")

# Print all logs
print("="*80)
print("LOG OUTPUT")
print("="*80)
for evt in events['events']:
    msg = evt['message'].rstrip()
    print(msg)

# Analyze
print("\n" + "="*80)
print("ANALYSIS")
print("="*80)

messages = [evt['message'].lower() for evt in events['events']]
all_text = '\n'.join(messages)

print("\nKey metrics:")
print(f"  Handler entry: {'YES' if any('[handler' in m for m in messages) else 'NO'}")
print(f"  AlgoConfig init: {'YES' if '[algoconfig]' in all_text else 'NO'}")
print(f"  DB connection: {'YES' if '[db]' in all_text else 'NO'}")
print(f"  Orchestrator run: {'YES' if any('phase' in m or 'data patrol' in m or 'circuit breaker' in m for m in messages) else 'NO'}")
print(f"  Success return: {'YES' if 'statuscode' in all_text and '200' in all_text else 'NO'}")
print(f"  Error logged: {'YES' if any('error' in m or 'exception' in m for m in messages) else 'NO'}")
