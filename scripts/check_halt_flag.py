#!/usr/bin/env python3
"""
Check and optionally clear the DynamoDB orchestrator halt flag.

Usage:
    python scripts/check_halt_flag.py          # show current state
    python scripts/check_halt_flag.py --clear  # clear the halt flag

Requires AWS credentials with DynamoDB access (run scripts/refresh-aws-credentials.ps1 first).
"""
import sys
import argparse
import boto3
from datetime import datetime, timezone

TABLE_NAME = 'algo_orchestrator_state'
HALT_KEY = 'orchestrator_halt'

def main():
    parser = argparse.ArgumentParser(description='Check/clear orchestrator halt flag')
    parser.add_argument('--clear', action='store_true', help='Clear the halt flag')
    args = parser.parse_args()

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(TABLE_NAME)

    response = table.get_item(Key={'key': HALT_KEY})
    item = response.get('Item')

    if not item:
        print("Halt flag: NOT SET (no item in DynamoDB — trading not halted)")
        return

    halt_flag = item.get('halt_flag', False)
    reason = item.get('reason', '(no reason)')
    triggered_at = item.get('triggered_at', item.get('reset_at', '(unknown)'))
    check_time = item.get('check_time', '(unknown)')

    print(f"Halt flag:    {'HALTED' if halt_flag else 'CLEAR'}")
    print(f"Reason:       {reason}")
    print(f"Timestamp:    {triggered_at}")
    print(f"Check time:   {check_time}")

    if halt_flag and not args.clear:
        print("\nTrading is HALTED. Run with --clear to reset, or wait for 10 AM ET circuit breaker check.")

    if args.clear:
        table.put_item(Item={
            'key': HALT_KEY,
            'halt_flag': False,
            'reason': 'Manually cleared via check_halt_flag.py',
            'reset_at': datetime.now(timezone.utc).isoformat(),
            'check_time': 'manual',
        })
        print("\nHalt flag CLEARED. Orchestrator will resume trading on next invocation.")

if __name__ == '__main__':
    main()
