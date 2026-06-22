#!/usr/bin/env python3
"""
Check for hanging/stuck resources that may be consuming money unnecessarily.
"""

from datetime import datetime, timedelta

import boto3


def check_step_functions():
    """Check for stuck or long-running Step Functions executions"""
    sfn = boto3.client("stepfunctions", region_name="us-east-1")

    print("\n" + "=" * 60)
    print("STEP FUNCTIONS - Stuck Executions")
    print("=" * 60)

    try:
        # List state machines
        machines = sfn.list_state_machines()["stateMachines"]

        if not machines:
            print("[OK] No Step Functions found")
            return

        for machine in machines:
            machine_arn = machine["stateMachineArn"]
            machine_name = machine["name"]

            if "algo" not in machine_name and "-dev" not in machine_name:
                continue

            print(f"\n[*] {machine_name}")

            # Get running executions
            try:
                executions = sfn.list_executions(stateMachineArn=machine_arn, statusFilter="RUNNING")["executions"]

                if executions:
                    print(f"  RUNNING executions: {len(executions)}")
                    for execution in executions:
                        start_time = execution["startDate"]
                        duration = datetime.now(start_time.tzinfo) - start_time
                        print(f"    - {execution['name']}: {duration}")

                        if duration > timedelta(hours=8):
                            print(f"      [WARNING] Running for {duration} - HUNG?")
                else:
                    print("  [OK] No running executions")

                # Get failed executions from last 24h
                failed = sfn.list_executions(
                    stateMachineArn=machine_arn,
                    statusFilter="FAILED",
                    executionFilter={
                        "before": datetime.utcnow(),
                        "after": datetime.utcnow() - timedelta(hours=24),
                    },
                )["executions"]

                if failed:
                    print(f"  [WARNING] {len(failed)} execution(s) failed in last 24h")

            except Exception as e:
                print(f"  [ERROR] {e}")

    except Exception as e:
        print(f"[ERROR] {e}")


def check_rds_connections():
    """Check RDS for connection leaks or excessive usage"""
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

    print("\n" + "=" * 60)
    print("RDS - Connection Pool Health")
    print("=" * 60)

    try:
        # Get current database connections
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName="DatabaseConnections",
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": "algo-db"}],
            StartTime=datetime.utcnow() - timedelta(hours=1),
            EndTime=datetime.utcnow(),
            Period=300,  # 5-minute granularity
            Statistics=["Maximum", "Average"],
        )

        if response["Datapoints"]:
            datapoints = sorted(response["Datapoints"], key=lambda x: x["Timestamp"], reverse=True)
            latest = datapoints[0]

            max_conns = latest.get("Maximum", 0)
            avg_conns = latest.get("Average", 0)

            print(f"[Latest] Max: {max_conns:.0f}, Avg: {avg_conns:.0f} connections")

            # RDS t4g.small has ~100 max connections
            if max_conns > 80:
                print(f"  [WARNING] Connection pool at {max_conns:.0f}% of ~100 limit")
            else:
                print(f"  [OK] Connection pool healthy ({max_conns:.0f}/100)")
        else:
            print("[OK] No recent metrics")

    except Exception as e:
        print(f"[ERROR] {e}")


def check_lambda_duration():
    """Check if Lambda functions are running longer than expected"""
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

    print("\n" + "=" * 60)
    print("LAMBDA - Execution Duration Analysis")
    print("=" * 60)

    lambdas = ["algo-api-dev", "algo-algo-dev"]

    for func_name in lambdas:
        try:
            # Get duration metrics
            response = cloudwatch.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName="Duration",
                Dimensions=[{"Name": "FunctionName", "Value": func_name}],
                StartTime=datetime.utcnow() - timedelta(hours=24),
                EndTime=datetime.utcnow(),
                Period=3600,  # Hourly
                Statistics=["Average", "Maximum"],
            )

            if response["Datapoints"]:
                datapoints = sorted(response["Datapoints"], key=lambda x: x["Timestamp"], reverse=True)
                latest = datapoints[0]

                avg_ms = latest.get("Average", 0)
                max_ms = latest.get("Maximum", 0)

                print(f"\n[OK] {func_name}")
                print(f"  Avg: {avg_ms:.0f}ms, Max: {max_ms:.0f}ms")

                # Check for slow runs (API timeout is 25s = 25000ms)
                if max_ms > 20000:
                    print("  [WARNING] Maximum duration approaching timeout (25s)")
            else:
                print(f"[OK] {func_name} - No recent executions")

        except Exception as e:
            print(f"[ERROR] {func_name}: {e}")


def check_dynamodb_throttling():
    """Check DynamoDB for throttling or excessive reads"""
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

    print("\n" + "=" * 60)
    print("DYNAMODB - Throttling/Performance")
    print("=" * 60)

    # Tables we know exist
    tables = ["halt_flag", "data_loader_status", "circuit_breaker_state"]

    for table_name in tables:
        try:
            # Check for read/write throttling
            response = cloudwatch.get_metric_statistics(
                Namespace="AWS/DynamoDB",
                MetricName="UserErrors",
                Dimensions=[{"Name": "TableName", "Value": table_name}],
                StartTime=datetime.utcnow() - timedelta(hours=24),
                EndTime=datetime.utcnow(),
                Period=3600,
                Statistics=["Sum"],
            )

            if response["Datapoints"]:
                total_errors = sum(dp["Sum"] for dp in response["Datapoints"])
                if total_errors > 0:
                    print(f"\n[WARNING] {table_name}: {total_errors} errors in last 24h")
                else:
                    print(f"\n[OK] {table_name}: No throttling")
            else:
                print(f"\n[OK] {table_name}: No metrics")

        except Exception as e:
            print(f"[ERROR] {table_name}: {e}")


def main():
    print("AWS Infrastructure Hanging Resources Check")
    print(f"Started: {datetime.now().isoformat()}")

    try:
        # Test connection
        sts = boto3.client("sts", region_name="us-east-1")
        identity = sts.get_caller_identity()
        print(f"Account: {identity['Account']}")

        # Run checks
        check_step_functions()
        check_rds_connections()
        check_lambda_duration()
        check_dynamodb_throttling()

        print("\n" + "=" * 60)
        print("Health Check Complete")
        print("=" * 60)
        print("\nCost Optimization Summary:")
        print("- RDS (db.t4g.small): ~$25-30/month (NECESSARY)")
        print("- Lambda Provisioned (API): ~$12/month (NECESSARY - prevents 502 errors)")
        print("- Lambda Orchestrator: ~$0.01-0.10/month (4 runs/day, cold-start OK)")
        print("- Step Functions: ~$0.01/month (low volume)")
        print("- EventBridge Scheduler: FREE (included)")
        print("- S3: ~$0.01-0.10/month (minimal storage)")
        print("- Total Estimated: ~$40-45/month")

    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
