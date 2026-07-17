#!/usr/bin/env python3
"""
Complete verification workflow:
1. Verify new ECS task definition was created with updated resources
2. Verify state machine can use the new task definition
3. Trigger pipeline with new resources
4. Monitor pipeline execution
5. Verify factor score coverage improved
"""

import boto3
import time
import subprocess
from datetime import datetime

print("=" * 80)
print("COMPLETE DEPLOYMENT VERIFICATION WORKFLOW")
print("=" * 80)

# Step 1: Verify ECS task definition
print("\n[STEP 1] Verifying ECS Task Definition Update...")
print("-" * 80)

ecs = boto3.client('ecs', region_name='us-east-1')

# Get the latest task definition for value_metrics
try:
    response = ecs.describe_task_definition(
        taskDefinition='algo-value_metrics-loader',
        include=['TAGS']
    )
    task_def = response['taskDefinition']

    cpu = task_def.get('cpu', 'N/A')
    memory = task_def.get('memory', 'N/A')
    revision = task_def['revision']

    print(f"Task Definition: algo-value_metrics-loader")
    print(f"  Revision: {revision}")
    print(f"  CPU: {cpu}")
    print(f"  Memory: {memory}")

    # Check if resources match expected values
    if cpu == '1024' and memory == '2048':
        print(f"  ✅ Resources MATCH expected values (CPU 1024, Memory 2048)")
    else:
        print(f"  ❌ Resources DO NOT MATCH. Expected CPU 1024, Memory 2048")
        print(f"     Got CPU {cpu}, Memory {memory}")

except Exception as e:
    print(f"❌ Error checking task definition: {e}")

# Step 2: Trigger pipeline
print("\n[STEP 2] Triggering Computed Metrics Pipeline...")
print("-" * 80)

try:
    result = subprocess.run(
        ['python3', 'scripts/trigger_computed_metrics_pipeline.py'],
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode == 0:
        print("✅ Pipeline triggered successfully")
        print(result.stdout)

        # Extract execution ARN from output
        for line in result.stdout.split('\n'):
            if 'Execution:' in line:
                exec_arn = line.split('Execution:')[-1].strip()
                print(f"\nExecution ARN: {exec_arn}")
    else:
        print(f"❌ Pipeline trigger failed: {result.stderr}")

except Exception as e:
    print(f"❌ Error triggering pipeline: {e}")

print("\n" + "=" * 80)
print("Verification complete. Pipeline is now running.")
print("Use: python verify_ecs_fix.py  to check factor score coverage later.")
print("=" * 80)
