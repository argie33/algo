#!/usr/bin/env python3
"""Check DynamoDB halt flag status."""
import boto3
import os
import json
from datetime import datetime

# Check environment
try:
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
    table = dynamodb.Table(table_name)

    print(f"\n=== Checking DynamoDB halt flag ===")
    print(f"Table: {table_name}")

    response = table.get_item(Key={'id': 'orchestrator_halt'})

    if 'Item' in response:
        item = response['Item']
        print(f"\nHalt Flag Found:")
        for key, value in sorted(item.items()):
            print(f"  {key}: {value}")
    else:
        print("\nNo halt flag found (OK to run)")

except Exception as e:
    print(f"ERROR checking halt flag: {e}")
    import traceback
    traceback.print_exc()
