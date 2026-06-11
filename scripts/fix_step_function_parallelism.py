#!/usr/bin/env python3
"""
Fix Step Function Loader Parallelism Configuration

This script updates AWS Step Functions to use LOADER_PARALLELISM=8 instead of 1.
Requires AWS credentials with states:UpdateStateMachine permissions.

Usage:
    export AWS_PROFILE=<profile-with-admin-access>
    python3 scripts/fix_step_function_parallelism.py
"""

import boto3
import json
import os
import sys

def update_step_function_parallelism(step_function_arn, target_parallelism=8):
    """Update step function to use higher loader parallelism"""
    client = boto3.client('stepfunctions', region_name='us-east-1')

    # Get current definition
    print(f"\n1. Fetching step function: {step_function_arn.split(':')[-1]}")
    response = client.describe_state_machine(stateMachineArn=step_function_arn)
    definition = json.loads(response['definition'])

    # Find and update all LOADER_PARALLELISM settings
    states = definition.get('States', {})
    updates_made = 0

    for state_name, state_def in states.items():
        overrides = state_def.get('Parameters', {}).get('Overrides', {}).get('ContainerOverrides', [])
        if not overrides:
            continue

        for container in overrides:
            env_vars = container.get('Environment', [])
            for env_var in env_vars:
                if env_var['Name'] == 'LOADER_PARALLELISM':
                    old_value = env_var['Value']
                    if old_value != str(target_parallelism):
                        print(f"   Updating {state_name}: LOADER_PARALLELISM {old_value} -> {target_parallelism}")
                        env_var['Value'] = str(target_parallelism)
                        updates_made += 1
                    else:
                        print(f"   {state_name}: already LOADER_PARALLELISM={target_parallelism}")

    if updates_made == 0:
        print("   No changes needed - all loaders already have correct parallelism")
        return True

    # Update the step function
    print(f"\n2. Updating step function definition...")
    new_definition = json.dumps(definition)

    try:
        response = client.update_state_machine(
            stateMachineArn=step_function_arn,
            definition=new_definition
        )
        print(f"   SUCCESS: Updated {step_function_arn.split(':')[-1]}")
        print(f"   Updated at: {response['updateDate']}")
        return True
    except Exception as e:
        print(f"   FAILED: {e}")
        return False

def main():
    """Main execution"""
    print("=" * 70)
    print("STEP FUNCTION LOADER PARALLELISM FIX")
    print("=" * 70)

    step_functions = [
        'arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev',
        'arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev'
    ]

    success_count = 0

    for sfn_arn in step_functions:
        try:
            if update_step_function_parallelism(sfn_arn, target_parallelism=8):
                success_count += 1
        except Exception as e:
            print(f"Error updating {sfn_arn}: {e}")

    print("\n" + "=" * 70)
    print(f"RESULT: {success_count}/{len(step_functions)} step functions updated")
    print("=" * 70)

    if success_count == len(step_functions):
        print("\n✓ All step functions updated successfully!")
        print("  Next: Trigger morning-prep-pipeline-dev to test")
        print("")
        print("  To trigger:")
        print("    aws stepfunctions start-execution \\")
        print("      --state-machine-arn arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev \\")
        print("      --region us-east-1")
        return 0
    else:
        print("\n✗ Some step functions failed to update")
        print("  Check AWS CloudWatch logs for details")
        return 1

if __name__ == '__main__':
    sys.exit(main())
