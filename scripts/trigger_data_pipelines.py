#!/usr/bin/env python3
"""Manually trigger Step Functions data pipelines for immediate data refresh.

Usage:
    python3 scripts/trigger_data_pipelines.py --pipeline eod --mode paper
    python3 scripts/trigger_data_pipelines.py --pipeline all  # Run all pipelines
"""

import argparse
import json
import sys
import boto3
from datetime import datetime, timezone

def trigger_pipeline(pipeline_name: str) -> bool:
    """Trigger a Step Functions state machine execution.

    Args:
        pipeline_name: Name of pipeline (eod, morning, financial, computed_metrics, reference)

    Returns:
        True if triggered successfully, False otherwise
    """
    machine_names = {
        'eod': 'algo-eod-pipeline-dev',
        'morning': 'algo-morning-prep-pipeline-dev',
        'financial': 'algo-financial-data-pipeline-dev',
        'computed_metrics': 'algo-computed-metrics-pipeline-dev',
        'reference': 'algo-reference-data-pipeline-dev'
    }

    if pipeline_name not in machine_names:
        print(f"Unknown pipeline: {pipeline_name}")
        print(f"Available: {', '.join(machine_names.keys())}")
        return False

    try:
        sfn = boto3.client('stepfunctions', region_name='us-east-1')

        # Get the state machine ARN
        response = sfn.list_state_machines()
        sm_arn = None
        for sm in response['stateMachines']:
            if sm['name'] == machine_names[pipeline_name]:
                sm_arn = sm['stateMachineArn']
                break

        if not sm_arn:
            print(f"ERROR: State machine not found for pipeline {pipeline_name}")
            return False

        # Start execution
        execution_name = f"manual-{pipeline_name}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        exec_response = sfn.start_execution(
            stateMachineArn=sm_arn,
            name=execution_name,
            input=json.dumps({'execution_name': execution_name, 'manual_trigger': True})
        )

        print(f"Triggered {pipeline_name} pipeline")
        print(f"  Execution: {exec_response['executionArn']}")
        print(f"  Status: Running...")
        return True

    except Exception as e:
        print(f"ERROR triggering {pipeline_name}: {e}")
        return False

def main() -> int:
    parser = argparse.ArgumentParser(description='Manually trigger Step Functions data pipelines')
    parser.add_argument('--pipeline', default='eod',
                       help='Pipeline to run (eod, morning, financial, computed_metrics, reference, all)')
    args = parser.parse_args()

    if args.pipeline == 'all':
        pipelines = ['morning', 'financial', 'eod', 'computed_metrics', 'reference']
    else:
        pipelines = [args.pipeline]

    print(f"Triggering {len(pipelines)} pipeline(s)...")
    print()

    results = {}
    for pipeline in pipelines:
        results[pipeline] = trigger_pipeline(pipeline)

    print()
    print("=" * 80)
    print("Results:")
    for pipeline, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"  {pipeline}: {status}")

    # Check if all succeeded
    if all(results.values()):
        print("\nAll pipelines triggered successfully!")
        print("Data will be refreshed within 30-45 minutes.")
        return 0
    else:
        print("\nSome pipelines failed to trigger. Check logs above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
