#!/usr/bin/env python3
"""PROPER: Trigger data pipelines SEQUENTIALLY to avoid rate limits and connection pool exhaustion.

CRITICAL: DO NOT run all 5 pipelines simultaneously. They must run in order with delays.

Proper execution order (matches Terraform cron schedule priorities):
1. EOD (4:05 PM ET) - Most critical: buy/sell signals, portfolio reconciliation
2. Wait 5+ minutes for completion
3. Computed Metrics (7:00 PM ET) - Depends on EOD data, metric calculations
4. Wait 5+ minutes
5. Financial Data (4:05 PM ET) - Independent, can run after EOD
6. Reference Data (9:15 AM ET) - Least critical, runs independently
7. Morning Prep (2:00 AM ET) - Runs earliest, least impact

LESSON LEARNED (Session 15):
Triggering all 5 simultaneously caused:
- Parallel yfinance requests (rate limit risk)
- RDS connection pool contention
- ECS resource contention
Staggered schedule exists for good reasons.
"""

import argparse
import json
import sys
import time
import boto3
from datetime import datetime, timezone

def trigger_pipeline_sequential(pipelines_to_run: list[str], wait_minutes: int = 5) -> bool:
    """Trigger pipelines in sequence with delays between them.

    Args:
        pipelines_to_run: List of pipeline names in order
        wait_minutes: Minutes to wait between pipeline completions

    Returns:
        True if all triggered successfully
    """
    machine_names = {
        'eod': 'algo-eod-pipeline-dev',
        'morning': 'algo-morning-prep-pipeline-dev',
        'financial': 'algo-financial-data-pipeline-dev',
        'computed_metrics': 'algo-computed-metrics-pipeline-dev',
        'reference': 'algo-reference-data-pipeline-dev'
    }

    sfn = boto3.client('stepfunctions', region_name='us-east-1')

    print(f"SEQUENTIAL PIPELINE TRIGGER (spacing: {wait_minutes} min between starts)")
    print("=" * 100)
    print(f"Order: {' -> '.join(pipelines_to_run)}")
    print("=" * 100)

    all_success = True

    for idx, pipeline_name in enumerate(pipelines_to_run):
        if pipeline_name not in machine_names:
            print(f"ERROR: Unknown pipeline {pipeline_name}")
            return False

        try:
            # Get state machine ARN
            response = sfn.list_state_machines()
            sm_arn = None
            for sm in response['stateMachines']:
                if sm['name'] == machine_names[pipeline_name]:
                    sm_arn = sm['stateMachineArn']
                    break

            if not sm_arn:
                print(f"ERROR: State machine not found for {pipeline_name}")
                all_success = False
                continue

            # Trigger execution
            execution_name = f"seq-{idx+1}-{pipeline_name}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
            exec_response = sfn.start_execution(
                stateMachineArn=sm_arn,
                name=execution_name,
                input=json.dumps({'execution_name': execution_name, 'sequential_trigger': True})
            )

            print(f"\n[{idx+1}] {pipeline_name}:")
            print(f"    Triggered: {execution_name}")
            print(f"    ARN: {exec_response['executionArn']}")

            # Wait before next trigger (except for last pipeline)
            if idx < len(pipelines_to_run) - 1:
                print(f"    Waiting {wait_minutes}min before next pipeline...")
                time.sleep(wait_minutes * 60)

        except Exception as e:
            print(f"ERROR: Failed to trigger {pipeline_name}: {e}")
            all_success = False

    print("\n" + "=" * 100)
    if all_success:
        print("SUCCESS: All pipelines triggered in sequence")
        print("Monitor with: aws stepfunctions list-executions --state-machine-arn <arn>")
    else:
        print("FAILED: Some pipelines failed to trigger")

    return all_success

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Trigger data pipelines SEQUENTIALLY (proper way)',
        epilog='Example: python3 trigger_data_pipelines_sequential.py --order eod computed_metrics financial'
    )
    parser.add_argument(
        '--order',
        nargs='+',
        default=['eod', 'computed_metrics', 'financial', 'reference'],
        help='Pipeline execution order (default: eod computed_metrics financial reference)'
    )
    parser.add_argument(
        '--wait',
        type=int,
        default=5,
        help='Minutes to wait between pipeline starts (default: 5)'
    )
    args = parser.parse_args()

    if not trigger_pipeline_sequential(args.order, args.wait):
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())
