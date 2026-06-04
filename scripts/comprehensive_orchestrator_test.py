#!/usr/bin/env python3
"""
Comprehensive orchestrator end-to-end test with detailed logging.
Tests all 7 phases and reports exact results.
"""

import json
import sys
import boto3
from datetime import datetime

sys.path.insert(0, '/c/Users/arger/code/algo')

def test_orchestrator():
    """Run orchestrator and parse results in detail."""
    print("\n" + "="*80)
    print("COMPREHENSIVE ORCHESTRATOR END-TO-END TEST")
    print("="*80 + "\n")

    # Invoke Lambda
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Invoking algo-algo-dev Lambda...")
    client = boto3.client('lambda', region_name='us-east-1')

    try:
        response = client.invoke(
            FunctionName='algo-algo-dev',
            InvocationType='RequestResponse',
            Payload=json.dumps({'dry_run': False})
        )
    except Exception as e:
        print(f"❌ Lambda invocation FAILED: {e}")
        return False

    # Parse response
    status_code = response['StatusCode']
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Lambda returned HTTP {status_code}")

    if status_code != 200:
        print(f"❌ Lambda error: {response.get('FunctionError', 'Unknown error')}")
        return False

    # Parse body
    try:
        body = json.loads(response['Payload'].read())
        if isinstance(body, str):
            body = json.loads(body)
    except Exception as e:
        print(f"❌ Failed to parse response: {e}")
        print(f"Raw response: {response}")
        return False

    # Parse inner body if nested
    if 'body' in body and isinstance(body['body'], str):
        try:
            body = json.loads(body['body'])
        except:
            pass

    print(f"\n[ORCHESTRATOR RUN ID] {body.get('run_id', 'unknown')}")

    # Check phases
    phases = body.get('phases', {})
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] PHASE RESULTS:")
    print("-" * 80)

    all_success = True
    # Sort phases: numeric first, then string keys
    numeric_phases = sorted([int(k) for k in phases.keys() if k.isdigit()])
    string_phases = sorted([k for k in phases.keys() if not k.isdigit()])
    for phase_num in numeric_phases + string_phases:
        phase_key = str(phase_num)
        if phase_key not in phases:
            continue

        phase = phases[phase_key]
        name = phase.get('name', 'unknown')
        status = phase.get('status', 'unknown')
        summary = phase.get('summary', '')

        # Determine outcome
        if status == 'success' or status == 'ok':
            symbol = "[OK]"
        elif status == 'warn':
            symbol = "[WN]"
            all_success = False
        elif status == 'halt':
            symbol = "[HT]"
            all_success = False
        elif status == 'error':
            symbol = "[ER]"
            all_success = False
        else:
            symbol = "[??]"

        print(f"{symbol} Phase {phase_key:2s} ({name:20s}) | {status:10s} | {summary[:60]}")

    print("-" * 80)

    # Summary
    http_status = body.get('statusCode', 500)
    overall = body.get('status', 'unknown')

    print(f"\n[OVERALL RESULT]")
    print(f"  HTTP Status: {http_status}")
    print(f"  Status: {overall}")
    print(f"  All Phases Success: {all_success}")

    if http_status == 200 and all_success and overall == 'success':
        print("\n" + "="*80)
        print("[OK] ORCHESTRATOR PASSED - ALL PHASES WORKING CORRECTLY")
        print("="*80 + "\n")
        return True
    else:
        print("\n" + "="*80)
        print("[ER] ORCHESTRATOR FAILED - ISSUES DETECTED")
        print("="*80 + "\n")
        print("Full response:")
        print(json.dumps(body, indent=2))
        return False

if __name__ == '__main__':
    success = test_orchestrator()
    sys.exit(0 if success else 1)
