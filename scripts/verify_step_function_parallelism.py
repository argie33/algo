#!/usr/bin/env python3
"""
Verify that step functions have correct LOADER_PARALLELISM settings.
Useful for post-terraform-apply verification.
"""
import boto3
import json
import os

os.environ['AWS_PROFILE'] = os.getenv('AWS_PROFILE', 'algo-developer')

def verify_step_function_parallelism():
    """Verify step functions have correct LOADER_PARALLELISM setting"""
    client = boto3.client('stepfunctions', region_name='us-east-1')

    pipelines = [
        ('morning', 'arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev'),
        ('eod', 'arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev')
    ]

    print("\n=== STEP FUNCTION PARALLELISM VERIFICATION ===\n")

    all_correct = True

    for pipeline_name, arn in pipelines:
        try:
            response = client.describe_state_machine(stateMachineArn=arn)
            definition = json.loads(response['definition'])

            print(f"Pipeline: {pipeline_name.upper()}")
            print(f"  ARN: {arn}")

            # Find all states with LOADER_PARALLELISM
            states = definition.get('States', {})
            found_loaders = False

            for state_name, state_def in states.items():
                overrides = state_def.get('Parameters', {}).get('Overrides', {}).get('ContainerOverrides', [])
                if overrides:
                    for container in overrides:
                        env_vars = {v['Name']: v['Value'] for v in container.get('Environment', [])}
                        if 'LOADER_PARALLELISM' in env_vars:
                            found_loaders = True
                            parallelism = env_vars.get('LOADER_PARALLELISM')
                            intervals = env_vars.get('LOADER_INTERVALS', 'unknown')
                            asset_class = env_vars.get('LOADER_ASSET_CLASSES', 'unknown')

                            status = '✓' if int(parallelism) >= 2 else '✗'
                            all_correct = all_correct and (int(parallelism) >= 2)

                            print(f"    {status} {state_name}")
                            print(f"        Parallelism: {parallelism}")
                            print(f"        Intervals: {intervals}")
                            print(f"        Asset Class: {asset_class}")

            if not found_loaders:
                print(f"    ⚠ No loaders found in this pipeline")

            print()

        except Exception as e:
            print(f"  ERROR checking {pipeline_name}: {e}\n")
            all_correct = False

    # Summary
    if all_correct:
        print("✓ All step functions configured correctly (LOADER_PARALLELISM >= 2)")
        return 0
    else:
        print("✗ Some step functions have incorrect configuration")
        return 1

if __name__ == '__main__':
    exit(verify_step_function_parallelism())
