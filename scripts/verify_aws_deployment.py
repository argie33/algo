#!/usr/bin/env python3
"""Post-deployment verification for AWS_EXECUTION_ENV fixes.

Run this after GitHub Actions Terraform deployment completes.
"""

import boto3
import time
from datetime import datetime, timedelta
import os

def check_ecs_task_definition():
    """Verify ECS task definitions have AWS_EXECUTION_ENV set."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    tasks_to_check = [
        'algo-price-daily-loader',
        'algo-technical-indicators-loader',
        'algo-orchestrator',
        'algo-data-patrol'
    ]
    
    results = {}
    for task_name in tasks_to_check:
        try:
            # Get latest task definition
            response = ecs.describe_task_definition(taskDefinition=task_name)
            task_def = response['taskDefinition']
            
            # Check for AWS_EXECUTION_ENV in container environment
            for container in task_def.get('containerDefinitions', []):
                env_vars = {e['name']: e['value'] for e in container.get('environment', [])}
                has_aws_env = 'AWS_EXECUTION_ENV' in env_vars
                results[task_name] = {
                    'revision': task_def['revision'],
                    'has_aws_execution_env': has_aws_env,
                    'value': env_vars.get('AWS_EXECUTION_ENV', 'NOT SET')
                }
        except Exception as e:
            results[task_name] = {'error': str(e)}
    
    return results

if __name__ == '__main__':
    print("Post-Deployment Verification")
    print("=" * 60)
    
    print("
Checking ECS Task Definitions...")
    task_results = check_ecs_task_definition()
    
    for task, status in task_results.items():
        if 'error' in status:
            print(f"  [{task}] ERROR: {status['error']}")
        else:
            aws_env_status = "[OK]" if status['has_aws_execution_env'] else "[FAIL]"
            print(f"  [{task}] {aws_env_status} AWS_EXECUTION_ENV={status['value']} (v{status['revision']})")
    
    print("\nNote: This requires AWS CLI access to ECS.")
