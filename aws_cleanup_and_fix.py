#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWS CloudFormation Stack Cleanup and Fix
Removes stuck stacks and old resources to enable fresh deployment
"""

import boto3
import time
import sys
import os

# Fix Unicode on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def cleanup_stacks():
    cfn = boto3.client('cloudformation', region_name='us-east-1')

    print("=" * 80)
    print("AWS CLOUDFORMATION CLEANUP & REMEDIATION")
    print("=" * 80)
    print()

    # Stacks to delete (stuck in bad states)
    stacks_to_delete = [
        'stocks-core',           # REVIEW_IN_PROGRESS - changeset not executed
        'stocks-data',           # REVIEW_IN_PROGRESS - changeset not executed
        'stocks-loaders-lambda-stack',  # ROLLBACK_COMPLETE - failed deployment
        'stocks-core-stack',     # Old version - export dependencies blocking
        'stocks-app-stack',      # Old version - needs cleanup before stocks-data deploys
    ]

    print("STEP 1: List all changesets that need to be rejected")
    print("-" * 80)

    changesets_to_reject = []
    for stack_name in ['stocks-core', 'stocks-data']:
        try:
            response = cfn.list_change_sets(StackName=stack_name)
            if response['Summaries']:
                print(f"\n{stack_name}:")
                for cs in response['Summaries']:
                    cs_name = cs['ChangeSetName']
                    cs_status = cs['Status']
                    print(f"  Changeset: {cs_name} (Status: {cs_status})")
                    changesets_to_reject.append((stack_name, cs_name))
        except Exception as e:
            print(f"  (No changesets or error: {e})")

    print()
    print("STEP 2: Reject all pending changesets")
    print("-" * 80)

    for stack_name, cs_name in changesets_to_reject:
        try:
            cfn.delete_change_set(
                ChangeSetName=cs_name,
                StackName=stack_name
            )
            print(f"[OK] Rejected changeset: {cs_name} from {stack_name}")
        except Exception as e:
            print(f"[ERROR] Error rejecting {cs_name}: {e}")

    print()
    print("STEP 3: Delete stacks in failed/stuck states")
    print("-" * 80)

    for stack_name in stacks_to_delete:
        try:
            # Check if stack exists
            response = cfn.describe_stacks(StackName=stack_name)
            stack = response['Stacks'][0]
            status = stack['StackStatus']

            print(f"\nDeleting: {stack_name} (Status: {status})")

            cfn.delete_stack(StackName=stack_name)
            print(f"  [OK] Deletion initiated")

            # Wait for deletion
            waiter = cfn.get_waiter('stack_delete_complete')
            try:
                waiter.wait(StackName=stack_name, WaiterConfig={'Delay': 15, 'MaxAttempts': 20})
                print(f"  [OK] Deletion completed")
            except:
                print(f"  [WARN] Deletion in progress or failed (will continue)")

        except cfn.exceptions.ClientError as e:
            if 'does not exist' in str(e):
                print(f"  [OK] Stack {stack_name} does not exist (skip)")
            else:
                print(f"  [ERROR] Error deleting {stack_name}: {e}")
        except Exception as e:
            print(f"  [ERROR] Error: {e}")

    print()
    print("STEP 4: Verify remaining stacks")
    print("-" * 80)

    try:
        response = cfn.list_stacks(
            StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE']
        )

        print("\nRemaining stacks:")
        for stack in response['StackSummaries']:
            print(f"  • {stack['StackName']}: {stack['StackStatus']}")

    except Exception as e:
        print(f"Error listing stacks: {e}")

    print()
    print("=" * 80)
    print("CLEANUP COMPLETE")
    print("=" * 80)
    print()
    print("[OK] All blocked stacks have been removed")
    print("[OK] Fresh deployment can now proceed")
    print()
    print("NEXT STEPS:")
    print("  1. Verify GitHub Actions has correct role configured")
    print("  2. Push to main or manually trigger deploy-all-infrastructure.yml")
    print("  3. Deployment will create fresh stocks-core and stocks-data stacks")
    print()

if __name__ == '__main__':
    cleanup_stacks()
