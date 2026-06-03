#!/usr/bin/env python3
"""Check DynamoDB lock state."""
import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lock_table = dynamodb.Table('algo-orchestrator-locks')
state_table = dynamodb.Table('algo_orchestrator_state')

try:
    # Check for lock
    response = lock_table.get_item(Key={'lock_key': 'orchestrator-run-lock'})
    if 'Item' in response:
        item = response['Item']
        print("=== LOCK STATE ===")
        print(f"Lock ID: {item.get('lock_id')}")
        print(f"Acquired at: {item.get('acquired_at')}")
        print(f"Expires at: {item.get('expires_at')}")

        expires_dt = datetime.fromisoformat(item.get('expires_at', ''))
        now = datetime.utcnow()
        if expires_dt > now:
            delta = (expires_dt - now).total_seconds()
            print(f"Lock is ACTIVE - expires in: {delta:.0f} seconds")
        else:
            print("Lock EXPIRED (can be reused)")
    else:
        print("No lock found (good - orchestrator can run)")

    # Check halt flag
    print("\n=== HALT FLAG STATE ===")
    response = state_table.scan(FilterExpression='attribute_exists(halt_flag)')
    if response.get('Items'):
        for item in response['Items']:
            print(f"Halt flag: {item}")
    else:
        print("No halt flag set")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
