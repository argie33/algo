#!/usr/bin/env python3
"""
AWS CloudFormation Diagnostic and Cleanup Script
Diagnoses and fixes CloudFormation stack issues
"""

import boto3
import json
from datetime import datetime

def run_diagnostics():
    cfn = boto3.client('cloudformation', region_name='us-east-1')
    sts = boto3.client('sts', region_name='us-east-1')

    print("=" * 80)
    print("AWS CLOUDFORMATION DIAGNOSTIC")
    print("=" * 80)
    print()

    # 1. Get caller identity
    print("1. AWS ACCOUNT IDENTITY")
    print("-" * 80)
    try:
        identity = sts.get_caller_identity()
        print(f"Account ID: {identity['Account']}")
        print(f"ARN: {identity['Arn']}")
        print(f"UserId: {identity['UserId']}")
    except Exception as e:
        print(f"ERROR getting identity: {e}")
    print()

    # 2. Check for CloudFormation hooks
    print("2. CLOUDFORMATION HOOKS")
    print("-" * 80)
    try:
        response = cfn.list_hooks()
        if response['Hooks']:
            print(f"FOUND {len(response['Hooks'])} hook(s):")
            for hook in response['Hooks']:
                print(f"  - {hook['HookId']}: {hook.get('Description', 'N/A')}")

                # Get hook details
                try:
                    details = cfn.describe_hooks(HookId=hook['HookId'])
                    print(f"    Status: {hook.get('Status', 'N/A')}")
                except:
                    pass
        else:
            print("✓ No CloudFormation hooks configured")
    except Exception as e:
        print(f"Note checking hooks: {e}")
    print()

    # 3. List all CloudFormation stacks
    print("3. CLOUDFORMATION STACKS")
    print("-" * 80)
    try:
        paginator = cfn.get_paginator('list_stacks')
        pages = paginator.paginate()

        stacks = []
        for page in pages:
            for stack in page['StackSummaries']:
                if stack['StackStatus'] != 'DELETE_COMPLETE':
                    stacks.append(stack)

        if stacks:
            print(f"Found {len(stacks)} stack(s):")
            for stack in sorted(stacks, key=lambda x: x['CreationTime'], reverse=True):
                print(f"\n  Name: {stack['StackName']}")
                print(f"  Status: {stack['StackStatus']}")
                print(f"  Created: {stack['CreationTime']}")
                if 'StackStatusReason' in stack:
                    print(f"  Reason: {stack['StackStatusReason']}")
        else:
            print("✓ No stacks found")
    except Exception as e:
        print(f"ERROR listing stacks: {e}")
    print()

    # 4. Get stocks-core stack details if it exists
    print("4. STOCKS-CORE STACK DETAILS")
    print("-" * 80)
    try:
        response = cfn.describe_stacks(StackName='stocks-core')
        stack = response['Stacks'][0]
        print(f"Status: {stack['StackStatus']}")
        if 'StackStatusReason' in stack:
            print(f"Reason: {stack['StackStatusReason']}")
        print(f"Created: {stack['CreationTime']}")
        if 'LastUpdatedTime' in stack:
            print(f"Last Updated: {stack['LastUpdatedTime']}")

        # Get events
        print("\n  Recent Events (last 15):")
        events_response = cfn.describe_stack_events(StackName='stocks-core')
        events = sorted(events_response['StackEvents'], key=lambda x: x['Timestamp'], reverse=True)[:15]

        for event in events:
            status = event['ResourceStatus']
            resource = event.get('LogicalResourceId', 'N/A')
            reason = event.get('ResourceStatusReason', '')
            timestamp = event['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"    [{timestamp}] {resource}: {status}")
            if reason and len(reason) > 0:
                print(f"      → {reason[:100]}")

    except cfn.exceptions.ClientError as e:
        if 'ValidationError' in str(e):
            print("✓ Stack does not exist (ready for first deployment)")
        else:
            print(f"ERROR: {e}")
    except Exception as e:
        print(f"ERROR: {e}")

    print()
    print("=" * 80)
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)

    return {
        'account_id': identity['Account'],
        'stacks': stacks if 'stacks' in locals() else [],
        'has_hooks': len(response['Hooks']) > 0 if 'response' in locals() else False
    }

def cleanup_bad_stacks():
    """Clean up stacks in bad states"""
    cfn = boto3.client('cloudformation', region_name='us-east-1')

    print("\n" + "=" * 80)
    print("CLEANUP: Removing stacks in failed states")
    print("=" * 80)

    bad_statuses = ['CREATE_FAILED', 'ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS']

    try:
        response = cfn.list_stacks(StackStatusFilter=bad_statuses)
        stacks_to_delete = response['StackSummaries']

        if stacks_to_delete:
            print(f"\nFound {len(stacks_to_delete)} stack(s) in bad state:")
            for stack in stacks_to_delete:
                print(f"\n  Deleting: {stack['StackName']} (Status: {stack['StackStatus']})")
                try:
                    cfn.delete_stack(StackName=stack['StackName'])
                    print(f"    ✓ Deletion initiated")
                except Exception as e:
                    print(f"    ❌ Error: {e}")
        else:
            print("✓ No stacks in bad state found")
    except Exception as e:
        print(f"ERROR during cleanup: {e}")

if __name__ == '__main__':
    result = run_diagnostics()

    # Ask for cleanup if bad stacks found
    if result['stacks']:
        for stack in result['stacks']:
            if stack['StackStatus'] in ['CREATE_FAILED', 'ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS']:
                print("\n⚠️  Bad stacks found - running cleanup...")
                cleanup_bad_stacks()
                break
