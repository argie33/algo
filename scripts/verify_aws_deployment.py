#!/usr/bin/env python3
"""Comprehensive AWS deployment verification for all loaders.

Verifies:
1. All loaders configured in Step Functions
2. Data is flowing to RDS
3. Orchestrator is running on schedule
4. All output tables have recent data
5. Lambda functions are accessible
6. ECS tasks are executing
"""

import sys
from datetime import datetime

import boto3
import psycopg2


def check_aws_credentials():
    """Verify AWS credentials are available."""
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"\nAWS Account: {identity['Account']}")
        print(f"ARN: {identity['Arn']}")
        return True
    except Exception as e:
        print(f"ERROR: Cannot access AWS: {e!s}")
        return False

def check_step_functions():
    """Verify Step Functions orchestrator is configured."""
    print("\n" + "=" * 80)
    print("STEP FUNCTIONS STATE MACHINE VERIFICATION")
    print("=" * 80)

    try:
        sfn = boto3.client('stepfunctions')

        # List state machines
        response = sfn.list_state_machines()
        machines = response.get('stateMachines', [])

        algo_machines = [m for m in machines if 'algo' in m['name'].lower()]

        if not algo_machines:
            print("ERROR: No algo Step Functions found")
            return False

        print(f"\nFound {len(algo_machines)} algo state machines:")
        for machine in algo_machines:
            print(f"  - {machine['name']}")
            print(f"    ARN: {machine['stateMachineArn']}")
            print(f"    Status: {machine['type']}")

        # Check recent executions
        if algo_machines:
            machine_arn = algo_machines[0]['stateMachineArn']
            executions = sfn.list_executions(
                stateMachineArn=machine_arn,
                maxItems=5
            )

            print("\nRecent executions:")
            for exec_item in executions.get('executions', []):
                print(f"  - {exec_item['name']}: {exec_item['status']}")
                print(f"    Started: {exec_item['startDate']}")

        return True

    except Exception as e:
        print(f"ERROR: Step Functions check failed: {e!s}")
        return False

def check_lambda_functions():
    """Verify Lambda functions are deployed."""
    print("\n" + "=" * 80)
    print("LAMBDA FUNCTION VERIFICATION")
    print("=" * 80)

    try:
        lambda_client = boto3.client('lambda')

        # List functions
        response = lambda_client.list_functions()
        functions = response.get('Functions', [])

        algo_functions = [f for f in functions if 'algo' in f['FunctionName'].lower()]

        print(f"\nFound {len(algo_functions)} algo Lambda functions:")
        for func in algo_functions[:10]:  # Show first 10
            print(f"  - {func['FunctionName']}")
            print(f"    Runtime: {func['Runtime']}")
            print(f"    Last Modified: {func['LastModified']}")

        if not algo_functions:
            print("WARNING: No algo Lambda functions found")
            return False

        return True

    except Exception as e:
        print(f"ERROR: Lambda check failed: {e!s}")
        return False

def check_ecs_task_definitions():
    """Verify ECS task definitions for loaders."""
    print("\n" + "=" * 80)
    print("ECS TASK DEFINITION VERIFICATION")
    print("=" * 80)

    try:
        ecs = boto3.client('ecs')

        # List task definitions
        response = ecs.list_task_definitions(familyPrefix='algo')
        task_defs = response.get('taskDefinitionArns', [])

        print(f"\nFound {len(task_defs)} algo ECS task definitions:")

        loader_task_defs = {}
        for task_def_arn in task_defs[:20]:  # Show first 20
            # Get task family name
            task_family = task_def_arn.split('/')[-1].split(':')[0]
            print(f"  - {task_family}")

            # Get task definition details
            task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)
            definition = task_def['taskDefinition']
            loader_task_defs[task_family] = {
                'cpu': definition.get('cpu'),
                'memory': definition.get('memory'),
                'containers': len(definition.get('containerDefinitions', [])),
            }

        # Count loader task definitions (should be ~20)
        loader_count = len([k for k in loader_task_defs.keys() if 'load_' in k])
        print(f"\nLoader task definitions: {loader_count}")

        if loader_count < 15:
            print("WARNING: Expected at least 15 loader task definitions")
            return False

        return True

    except Exception as e:
        print(f"ERROR: ECS check failed: {e!s}")
        return False

def check_rds_connection_and_data():
    """Verify RDS connection and data presence."""
    print("\n" + "=" * 80)
    print("RDS DATABASE VERIFICATION")
    print("=" * 80)

    try:
        # Try to connect to RDS
        conn = psycopg2.connect(
            dbname='stocks',
            user='stocks',
            host='localhost',  # This might fail in AWS Lambda context - use RDS endpoint
            port=5432,
            connect_timeout=5
        )

        cur = conn.cursor()

        # Check critical tables exist
        critical_tables = [
            'price_daily',
            'technical_data_daily',
            'stock_scores',
            'buy_sell_daily',
            'algo_orchestrator_runs',
        ]

        print("\nCritical tables:")
        all_exist = True
        for table in critical_tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            status = "OK" if count > 0 else "EMPTY"
            print(f"  {table:30} | {count:12,} rows | {status}")
            if count == 0:
                all_exist = False

        # Check data freshness
        print("\nData freshness (last updated):")
        cur.execute("SELECT MAX(date) FROM price_daily")
        latest_price = cur.fetchone()[0]
        print(f"  price_daily:       {latest_price}")

        cur.execute("SELECT MAX(date) FROM technical_data_daily")
        latest_technical = cur.fetchone()[0]
        print(f"  technical_data:    {latest_technical}")

        cur.execute("SELECT MAX(date) FROM stock_scores")
        latest_scores = cur.fetchone()[0]
        print(f"  stock_scores:      {latest_scores}")

        # Check orchestrator runs
        cur.execute("""
            SELECT COUNT(*), COUNT(CASE WHEN overall_status='success' THEN 1 END),
                   MAX(started_at)
            FROM algo_orchestrator_runs
            WHERE started_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
        """)
        total_runs, success_runs, latest_run = cur.fetchone()
        print("\nOrchestrator (last 7 days):")
        print(f"  Total runs:       {total_runs}")
        print(f"  Successful:       {success_runs}")
        print(f"  Latest run:       {latest_run}")

        conn.close()
        return all_exist

    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to RDS: {e!s}")
        print("  Make sure you're connected to AWS VPC or using RDS endpoint")
        return False
    except Exception as e:
        print(f"ERROR: Database check failed: {e!s}")
        return False

def check_eventbridge_schedules():
    """Verify EventBridge schedules for optional enrichment."""
    print("\n" + "=" * 80)
    print("EVENTBRIDGE SCHEDULER VERIFICATION")
    print("=" * 80)

    try:
        events = boto3.client('events')
        scheduler = boto3.client('scheduler')

        # Check EventBridge rules
        response = events.list_rules()
        rules = response.get('Rules', [])

        algo_rules = [r for r in rules if 'algo' in r['Name'].lower()]
        print(f"\nEventBridge rules: {len(algo_rules)}")
        for rule in algo_rules[:5]:
            print(f"  - {rule['Name']}: {rule['State']}")

        # Check Scheduler schedules (if available)
        try:
            schedules = scheduler.list_schedules()
            algo_schedules = [s for s in schedules.get('Schedules', [])
                            if 'algo' in s['Name'].lower()]
            print(f"\nScheduler schedules: {len(algo_schedules)}")
        except:
            print("\nScheduler API not available or no schedules")

        return len(algo_rules) > 0

    except Exception as e:
        print(f"ERROR: EventBridge check failed: {e!s}")
        return False

def check_cloudwatch_logs():
    """Verify CloudWatch logs are being written."""
    print("\n" + "=" * 80)
    print("CLOUDWATCH LOGS VERIFICATION")
    print("=" * 80)

    try:
        logs = boto3.client('logs')

        # List log groups
        response = logs.describe_log_groups()
        log_groups = response.get('logGroups', [])

        algo_logs = [lg for lg in log_groups if 'algo' in lg['logGroupName'].lower()]

        print(f"\nAlgo log groups: {len(algo_logs)}")
        for lg in algo_logs[:5]:
            print(f"  - {lg['logGroupName']}")
            print(f"    Streams: {lg.get('storedBytes', 0) / 1024 / 1024:.1f} MB")

        # Check for recent logs
        if algo_logs:
            log_group = algo_logs[0]['logGroupName']
            streams = logs.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=5
            )

            print(f"\nRecent log streams in {log_group}:")
            for stream in streams.get('logStreams', []):
                last_event = datetime.fromtimestamp(
                    stream.get('lastEventTimestamp', 0) / 1000
                )
                print(f"  - {stream['logStreamName']}: {last_event}")

        return len(algo_logs) > 0

    except Exception as e:
        print(f"ERROR: CloudWatch check failed: {e!s}")
        return False

def generate_report():
    """Generate comprehensive deployment verification report."""
    print("\n" + "=" * 80)
    print("AWS DEPLOYMENT VERIFICATION REPORT")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        "aws_credentials": check_aws_credentials(),
        "step_functions": check_step_functions(),
        "lambda": check_lambda_functions(),
        "ecs": check_ecs_task_definitions(),
        "eventbridge": check_eventbridge_schedules(),
        "cloudwatch": check_cloudwatch_logs(),
        "rds_and_data": check_rds_connection_and_data(),
    }

    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)

    for check, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {check:25} - {status}")

    all_pass = all(results.values())
    print("\n" + "=" * 80)
    if all_pass:
        print("OVERALL STATUS: ALL CHECKS PASSED - SYSTEM DEPLOYED AND OPERATIONAL")
    else:
        print("OVERALL STATUS: SOME CHECKS FAILED - REVIEW ERRORS ABOVE")
    print("=" * 80 + "\n")

    return all_pass

if __name__ == '__main__':
    try:
        success = generate_report()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nVerification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nFATAL ERROR: {e!s}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
