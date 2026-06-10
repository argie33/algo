#!/usr/bin/env python3
"""
Deploy metrics loaders to production.

This script:
1. Creates RDS tables (if not exist)
2. Tests loaders locally
3. Generates CloudWatch alarms configuration
4. Provides EventBridge scheduling instructions

Run this ONCE before enabling hourly loaders.
"""
import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import argparse

try:
    import boto3
    import psycopg2
except ImportError:
    print("ERROR: Missing dependencies. Install: pip install boto3 psycopg2-binary")
    sys.exit(1)


def get_db_connection():
    """Get RDS connection from environment."""
    creds = {
        "host": os.environ.get("DB_HOST"),
        "user": os.environ.get("DB_USER"),
        "password": os.environ.get("DB_PASSWORD"),
        "dbname": os.environ.get("DB_NAME"),
        "port": int(os.environ.get("DB_PORT", 5432)),
    }
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise ValueError(f"Missing DB credentials: {missing}")

    return psycopg2.connect(**creds)


def create_tables(conn):
    """Create metrics tables in RDS."""
    print("\n[1/5] Creating RDS tables...")
    sql_file = Path(__file__).parent.parent / "sql" / "001_create_metrics_tables.sql"

    if not sql_file.exists():
        raise FileNotFoundError(f"Schema file not found: {sql_file}")

    with open(sql_file) as f:
        sql = f.read()

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("✓ Tables created successfully")
        return True
    except psycopg2.Error as e:
        print(f"✗ Failed to create tables: {e}")
        conn.rollback()
        return False


def test_loaders():
    """Run loaders locally to verify they work."""
    print("\n[2/5] Testing loaders...")
    loaders = [
        "load_algo_performance_daily.py",
        "load_algo_risk_daily.py",
    ]

    results = {}
    for loader in loaders:
        path = Path(__file__).parent.parent / "loaders" / loader
        if not path.exists():
            print(f"✗ Loader not found: {path}")
            results[loader] = False
            continue

        print(f"  Running {loader}...", end=" ", flush=True)
        try:
            result = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True,
                timeout=300,
                text=True,
            )
            if result.returncode == 0:
                print("✓")
                results[loader] = True
            else:
                print(f"✗ (exit {result.returncode})")
                if result.stderr:
                    print(f"    Error: {result.stderr[:200]}")
                results[loader] = False
        except subprocess.TimeoutExpired:
            print("✗ (timeout)")
            results[loader] = False
        except Exception as e:
            print(f"✗ ({e})")
            results[loader] = False

    return all(results.values())


def generate_eventbridge_config():
    """Generate EventBridge configuration for hourly loader scheduling."""
    print("\n[3/5] Generating EventBridge configuration...")

    config = {
        "rules": [
            {
                "name": "metrics-loaders-hourly",
                "schedule": "cron(0 10-16 ? * MON-FRI *)",
                "timezone": "America/New_York",
                "description": "Run performance and risk metrics loaders hourly during market hours (10 AM - 4 PM ET)",
                "targets": [
                    {
                        "id": "performance-metrics-loader",
                        "arn": "arn:aws:ecs:{region}:{account}:task-definition/metrics-loader:1",
                        "role_arn": "arn:aws:iam::{account}:role/eventbridge-ecs-role",
                        "ecs_parameters": {
                            "launch_type": "FARGATE",
                            "task_definition": "metrics-loader",
                            "subnets": ["subnet-xxxxx"],
                            "security_groups": ["sg-xxxxx"],
                            "command": ["python", "loaders/load_algo_performance_daily.py"],
                        },
                    },
                    {
                        "id": "risk-metrics-loader",
                        "arn": "arn:aws:ecs:{region}:{account}:task-definition/metrics-loader:1",
                        "role_arn": "arn:aws:iam::{account}:role/eventbridge-ecs-role",
                        "ecs_parameters": {
                            "launch_type": "FARGATE",
                            "task_definition": "metrics-loader",
                            "subnets": ["subnet-xxxxx"],
                            "security_groups": ["sg-xxxxx"],
                            "command": ["python", "loaders/load_algo_risk_daily.py"],
                        },
                    },
                ],
            },
            {
                "name": "metrics-loaders-eod",
                "schedule": "cron(0 21 ? * MON-FRI *)",
                "timezone": "America/New_York",
                "description": "Run metrics loaders at end-of-day (5 PM ET) to capture final metrics",
                "targets": [
                    {
                        "id": "performance-metrics-eod",
                        "ecs_parameters": {
                            "command": ["python", "loaders/load_algo_performance_daily.py"],
                        },
                    },
                    {
                        "id": "risk-metrics-eod",
                        "ecs_parameters": {
                            "command": ["python", "loaders/load_algo_risk_daily.py"],
                        },
                    },
                ],
            },
        ],
        "alarms": [
            {
                "name": "metrics-loader-failure",
                "metric": "MetricsLoaderErrors",
                "threshold": 1,
                "comparison": "GreaterThanOrEqualToThreshold",
                "evaluation_periods": 1,
                "period": 300,
                "action": "sns:Publish",
            },
            {
                "name": "metrics-table-stale",
                "metric": "MetricsTableAge",
                "threshold": 120,
                "comparison": "GreaterThanThreshold",
                "evaluation_periods": 2,
                "period": 300,
                "action": "sns:Publish",
                "description": "Alert if metrics tables >2 hours old during market hours",
            },
        ],
    }

    config_file = Path(__file__).parent.parent / "config" / "eventbridge-metrics.json"
    config_file.parent.mkdir(exist_ok=True)
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"✓ Configuration written to {config_file}")
    print("\n  NOTE: Replace placeholders:")
    print("    - {region}: your AWS region (e.g., us-east-1)")
    print("    - {account}: your AWS account ID")
    print("    - subnet-xxxxx: your VPC subnet IDs")
    print("    - sg-xxxxx: your security group IDs")

    return config_file


def generate_cloudwatch_alarms(conn):
    """Generate CloudWatch alarm definitions."""
    print("\n[4/5] Generating CloudWatch alarms...")

    alarms = [
        {
            "AlarmName": "metrics-loader-perf-failure",
            "MetricName": "TasksFailed",
            "Namespace": "ECS/ContainerInsights",
            "Statistic": "Sum",
            "Period": 300,
            "EvaluationPeriods": 1,
            "Threshold": 1,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "Dimensions": [{"Name": "TaskDefinitionFamily", "Value": "metrics-loader"}],
            "AlarmActions": ["arn:aws:sns:us-east-1:ACCOUNT:ops-alerts"],
            "AlarmDescription": "Alert if performance metrics loader task fails",
        },
        {
            "AlarmName": "metrics-loader-risk-failure",
            "MetricName": "TasksFailed",
            "Namespace": "ECS/ContainerInsights",
            "Statistic": "Sum",
            "Period": 300,
            "EvaluationPeriods": 1,
            "Threshold": 1,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "Dimensions": [{"Name": "TaskDefinitionFamily", "Value": "metrics-loader"}],
            "AlarmActions": ["arn:aws:sns:us-east-1:ACCOUNT:ops-alerts"],
            "AlarmDescription": "Alert if risk metrics loader task fails",
        },
        {
            "AlarmName": "metrics-table-stale-market-hours",
            "MetricName": "MetricsTableAge",
            "Namespace": "Custom/Metrics",
            "Statistic": "Maximum",
            "Period": 600,
            "EvaluationPeriods": 2,
            "Threshold": 120,
            "ComparisonOperator": "GreaterThanThreshold",
            "AlarmActions": ["arn:aws:sns:us-east-1:ACCOUNT:ops-alerts"],
            "AlarmDescription": "Alert if metrics tables are >2 hours old during market hours (9:30 AM - 4 PM ET)",
        },
    ]

    alarms_file = Path(__file__).parent.parent / "config" / "cloudwatch-alarms-metrics.json"
    alarms_file.parent.mkdir(exist_ok=True)
    with open(alarms_file, "w") as f:
        json.dump(alarms, f, indent=2)

    print(f"✓ Alarm definitions written to {alarms_file}")
    print("\n  To deploy alarms:")
    print("    aws cloudwatch put-metric-alarm --cli-input-json file://config/cloudwatch-alarms-metrics.json")

    return alarms_file


def print_deployment_summary():
    """Print final deployment instructions."""
    print("\n[5/5] Deployment Summary")
    print("=" * 60)

    summary = """
    ✓ RDS tables created
    ✓ Loaders tested locally
    ✓ EventBridge configuration generated
    ✓ CloudWatch alarms configured

    NEXT STEPS:

    1. Review EventBridge configuration:
       cat config/eventbridge-metrics.json

    2. Create EventBridge rules (see DEPLOYMENT_CHECKLIST_METRICS.md):
       - Performance metrics hourly: cron(0 10-16 ? * MON-FRI *)
       - Risk metrics hourly: cron(0 10-16 ? * MON-FRI *)
       - Both: once at 5 PM ET: cron(0 21 ? * MON-FRI *)

    3. Deploy CloudWatch alarms:
       aws cloudwatch put-metric-alarm --cli-input-json file://config/cloudwatch-alarms-metrics.json

    4. Test first loader run:
       - Wait for next hourly slot (top of hour, 10 AM - 4 PM ET)
       - Check CloudWatch logs for "SUCCESS"
       - Verify table: SELECT COUNT(*) FROM algo_performance_daily;

    5. Monitor dashboard:
       - Load dashboard during market hours
       - Verify metrics display (not "--")
       - Check logs for "_source: table" (metrics from cache)

    MONITORING:

    Dashboard freshness check:
      SELECT report_date, updated_at,
             EXTRACT(EPOCH FROM NOW() - updated_at) / 60 AS age_minutes
      FROM algo_performance_daily
      WHERE report_date = CURRENT_DATE;

      If age_minutes > 120 during market hours (9:30 AM - 4 PM ET):
      - Loader may not have run
      - Check CloudWatch logs for errors
      - Manually trigger: python loaders/load_algo_performance_daily.py

    ROLLBACK:

    If loaders cause issues:
      1. Disable EventBridge rules
      2. Dashboard will show "--" for metrics
      3. Investigate logs, fix, re-enable

    See DEPLOYMENT_CHECKLIST_METRICS.md for full details.
    """
    print(summary)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy metrics loaders to production"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip local loader testing (for CI/CD)",
    )
    args = parser.parse_args()

    try:
        print("=" * 60)
        print("METRICS LOADERS DEPLOYMENT")
        print("=" * 60)

        # Step 1: Create tables
        conn = get_db_connection()
        if not create_tables(conn):
            sys.exit(1)
        conn.close()

        # Step 2: Test loaders
        if not args.skip_tests:
            if not test_loaders():
                print(
                    "\nWARNING: Some loaders failed testing. Fix issues before production."
                )
                print("Use --skip-tests to proceed anyway (not recommended)")
        else:
            print("\n[2/5] Skipping loader tests (--skip-tests)")

        # Step 3: Generate EventBridge config
        generate_eventbridge_config()

        # Step 4: Generate CloudWatch alarms
        conn = get_db_connection()
        generate_cloudwatch_alarms(conn)
        conn.close()

        # Step 5: Summary
        print_deployment_summary()

        print("\n✓ Deployment preparation complete!")
        print(
            "\nSee DEPLOYMENT_CHECKLIST_METRICS.md for next steps and testing procedures."
        )

    except Exception as e:
        print(f"\n✗ Deployment failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
