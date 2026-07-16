#!/usr/bin/env python3
"""Verify EventBridge Scheduler rules are deployed and firing."""

import boto3
import os
import sys
from datetime import datetime, timedelta

def check_eventbridge_scheduler():
    """Check if EventBridge Scheduler rules exist and are enabled."""
    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        scheduler = boto3.client("scheduler", region_name=region)

        # List all schedules
        response = scheduler.list_schedules(MaxResults=50)
        schedules = response.get("Schedules", [])

        print("EventBridge Scheduler Rules:")
        print("=" * 100)

        data_pipeline_rules = [
            s for s in schedules
            if "morning-pipeline" in s["Name"] or "eod-pipeline" in s["Name"]
        ]

        if not data_pipeline_rules:
            print("[FAIL] No data pipeline scheduler rules found!")
            return False

        for schedule in data_pipeline_rules:
            status = "[OK] ENABLED" if schedule["State"] == "ENABLED" else "[FAIL] DISABLED"
            print(f"\n{schedule['Name']}")
            print(f"  State: {status}")
            print(f"  Schedule: {schedule.get('ScheduleExpression', 'N/A')}")
            print(f"  Timezone: {schedule.get('ScheduleExpressionTimezone', 'N/A')}")

        return len(data_pipeline_rules) >= 2  # Both morning and EOD should exist

    except Exception as e:
        print(f"Error checking scheduler: {e}")
        return False


def check_eventbridge_logs():
    """Check EventBridge Scheduler logs for executions."""
    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        logs = boto3.client("logs", region_name=region)

        # Check for log events in the scheduler log group
        response = logs.filter_log_events(
            logGroupName="/aws/scheduler/algo-pipeline-dev",
            startTime=int((datetime.now() - timedelta(hours=1)).timestamp() * 1000),
            limit=10
        )

        events = response.get("events", [])

        if events:
            print("\n\nEventBridge Scheduler Log Events (Last Hour):")
            print("=" * 100)
            for event in events[:5]:
                ts = datetime.fromtimestamp(event["timestamp"] / 1000)
                print(f"  {ts}: {event['message'][:100]}")
            return True
        else:
            print("\n\n[WARN] No EventBridge Scheduler log events in last hour")
            print("   (Scheduler may not have fired yet, or not configured)")
            return False

    except Exception as e:
        print(f"Error checking logs: {e}")
        return False


def check_step_functions_executions():
    """Check Step Functions execution times to see if scheduled or manual."""
    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        sfn = boto3.client("stepfunctions", region_name=region)

        print("\n\nStep Functions Recent Executions:")
        print("=" * 100)

        response = sfn.list_state_machines(maxResults=50)

        for sm in response.get("stateMachines", []):
            if "morning" in sm["name"].lower() or "eod" in sm["name"].lower():
                execs = sfn.list_executions(
                    stateMachineArn=sm["stateMachineArn"],
                    maxResults=3
                )

                print(f"\n{sm['name']}:")
                for exec_info in execs.get("executions", []):
                    exec_name = exec_info["name"]
                    is_manual = "manual" in exec_name.lower()
                    start_time = exec_info.get("startDate")

                    # Check if time matches schedule (2 AM or 4:05 PM)
                    if start_time:
                        hour = start_time.hour
                        minute = start_time.minute
                        scheduled = (hour == 2) or (hour == 16 and minute >= 5)

                        marker = "[SCHEDULED]" if scheduled else "[MANUAL]"
                        print(f"  {marker}: {exec_name} at {start_time.strftime('%H:%M')}")

    except Exception as e:
        print(f"Error checking executions: {e}")


def main():
    """Main verification."""
    print("EventBridge Scheduler Deployment Verification")
    print("=" * 100)
    print(f"AWS Region: {os.getenv('AWS_REGION', 'us-east-1')}")
    print(f"Time: {datetime.now()}\n")

    scheduler_ok = check_eventbridge_scheduler()
    logs_ok = check_eventbridge_logs()

    check_step_functions_executions()

    print("\n\nSUMMARY:")
    print("=" * 100)

    if scheduler_ok:
        print("[OK] EventBridge Scheduler rules deployed")
    else:
        print("[FAIL] EventBridge Scheduler rules NOT deployed or missing")

    if logs_ok:
        print("[OK] Scheduler firing (events in logs)")
    else:
        print("[WARN] No scheduler events yet (may not have fired)")

    return 0 if scheduler_ok else 1


if __name__ == "__main__":
    sys.exit(main())
