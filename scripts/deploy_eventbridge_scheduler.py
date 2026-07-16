#!/usr/bin/env python3
"""
Direct deployment of EventBridge Scheduler rules without terraform.
Creates the 4 critical data pipeline schedules that orchestrator depends on.
"""

import boto3
import json
from botocore.exceptions import ClientError

def get_scheduler_role_arn():
    """Get the EventBridge Scheduler role ARN from terraform output."""
    import subprocess
    try:
        result = subprocess.run(
            ["terraform", "output", "-json", "eventbridge_scheduler_role_arn"],
            cwd="terraform",
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return json.loads(result.stdout).strip('"')
    except Exception as e:
        print(f"[WARN] Could not get role ARN from terraform: {e}")

    # Fallback: construct the role ARN
    return "arn:aws:iam::626216981288:role/algo-eventbridge-scheduler-role-dev"

def deploy_scheduler_rules():
    """Deploy EventBridge Scheduler rules for data pipelines."""

    region = "us-east-1"
    scheduler = boto3.client("scheduler", region_name=region)
    role_arn = get_scheduler_role_arn()

    # Step Function ARNs (from AWS)
    morning_pipeline_arn = "arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev"
    eod_pipeline_arn = "arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev"
    metrics_pipeline_arn = "arn:aws:states:us-east-1:626216981288:stateMachine:algo-computed-metrics-pipeline-dev"
    reference_pipeline_arn = "arn:aws:states:us-east-1:626216981288:stateMachine:algo-reference-data-pipeline-dev"

    rules = [
        {
            "name": "algo-morning-pipeline-dev",
            "description": "Morning data prep: load prices + technicals (2:00 AM ET MON-FRI)",
            "schedule_expression": "cron(0 2 ? * MON-FRI *)",
            "state_machine_arn": morning_pipeline_arn,
        },
        {
            "name": "algo-eod-pipeline-dev",
            "description": "EOD data pipeline: load metrics + scores (4:05 PM ET MON-FRI)",
            "schedule_expression": "cron(5 4 ? * MON-FRI *)",
            "state_machine_arn": eod_pipeline_arn,
        },
        {
            "name": "algo-computed-metrics-pipeline-dev",
            "description": "Daily computed metrics: quality/growth/value/stability/scores (7:00 PM ET)",
            "schedule_expression": "cron(0 19 ? * MON-FRI *)",
            "state_machine_arn": metrics_pipeline_arn,
        },
        {
            "name": "algo-reference-data-pipeline-dev",
            "description": "Reference data: earnings/company profile/analyst sentiment (9:15 AM ET)",
            "schedule_expression": "cron(15 9 ? * MON-FRI *)",
            "state_machine_arn": reference_pipeline_arn,
        },
    ]

    print("=" * 100)
    print("DEPLOYING EVENTBRIDGE SCHEDULER RULES")
    print("=" * 100)
    print(f"\nRole ARN: {role_arn}")
    print(f"Region: {region}\n")

    results = {"created": [], "failed": [], "already_exists": []}

    for rule in rules:
        try:
            print(f"\n[DEPLOY] {rule['name']}")
            print(f"  Schedule: {rule['schedule_expression']}")
            print(f"  Target: {rule['state_machine_arn'].split(':')[-1]}")

            response = scheduler.create_schedule(
                Name=rule["name"],
                Description=rule["description"],
                ScheduleExpression=rule["schedule_expression"],
                ScheduleExpressionTimezone="America/New_York",
                State="ENABLED",
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": rule["state_machine_arn"],
                    "RoleArn": role_arn,
                    "Input": json.dumps({"execution_name": f"{rule['name']}-<aws.scheduler.execution-id>"}),
                    "RetryPolicy": {
                        "MaximumEventAgeInSeconds": 3600,
                        "MaximumRetryAttempts": 2,
                    },
                }
            )

            print(f"  [OK] CREATED: {response['ScheduleArn']}")
            results["created"].append(rule["name"])

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]

            if "ConflictException" in error_code or "already exists" in error_msg:
                print(f"  [WARN] Already exists (skipping)")
                results["already_exists"].append(rule["name"])
            else:
                print(f"  [FAIL] FAILED: {error_code}")
                print(f"    {error_msg[:100]}")
                results["failed"].append((rule["name"], error_code))

        except Exception as e:
            print(f"  [ERROR] {e}")
            results["failed"].append((rule["name"], str(e)))

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"\nCreated: {len(results['created'])}")
    for name in results["created"]:
        print(f"  ✓ {name}")

    print(f"\nAlready exists: {len(results['already_exists'])}")
    for name in results["already_exists"]:
        print(f"  [EXISTING] {name}")

    if results["failed"]:
        print(f"\nFailed: {len(results['failed'])}")
        for name, error in results["failed"]:
            print(f"  [FAIL] {name}: {error}")
        return False
    else:
        print("\n[SUCCESS] All rules deployed successfully!")
        return True

if __name__ == "__main__":
    import sys
    success = deploy_scheduler_rules()
    sys.exit(0 if success else 1)
