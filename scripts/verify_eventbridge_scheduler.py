#!/usr/bin/env python3
"""Verify EventBridge Scheduler configuration

Checks that all loader pipelines are properly configured and enabled.
Helps diagnose why loaders might not be running automatically.

Usage:
  python scripts/verify_eventbridge_scheduler.py       # Full check
  python scripts/verify_eventbridge_scheduler.py --fix # Auto-fix disabled schedules
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# Windows encoding fix (emoji output crashes cp1252 console otherwise)
if sys.platform.startswith("win"):
    import io

    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Schedule names include a project/environment suffix, e.g. "algo-morning-pipeline-dev".
# CI/CD (deploy-all-infrastructure.yml) only ever deploys via terraform.tfvars, so
# ENVIRONMENT should match that file's `environment` value, not assume "prod".
PROJECT_NAME = os.environ.get("TF_PROJECT_NAME", "algo")
ENVIRONMENT = os.environ.get("TF_ENVIRONMENT", "dev")

EXPECTED_SCHEDULES = {
    f"{PROJECT_NAME}-morning-pipeline-{ENVIRONMENT}": {
        "schedule": "cron(0 2 ? * MON-FRI *)",
        "timezone": "America/New_York",
        "description": "Morning data prep: load prices + technicals (2:00 AM ET)",
    },
    f"{PROJECT_NAME}-eod-pipeline-{ENVIRONMENT}": {
        "schedule": "cron(5 16 ? * MON-FRI *)",
        "timezone": "America/New_York",
        "description": "End-of-day analysis & swing scores (4:05 PM ET)",
    },
}


def run_aws_cli(args: list) -> dict | None:
    """Run AWS CLI command and return JSON result."""
    import shutil

    # On Windows, "aws" resolves to aws.cmd/aws.exe via PATHEXT, which
    # subprocess.run() only honors if the executable is pre-resolved
    # (shutil.which) or shell=True is used. Without this, subprocess raises
    # FileNotFoundError even though `aws` works fine from an interactive shell.
    aws_path = shutil.which("aws") or "aws"
    try:
        result = subprocess.run(
            [aws_path] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout else {}
        elif "ResourceNotFoundException" in result.stderr:
            return None
        else:
            print(f"❌ AWS CLI Error: {result.stderr}", file=sys.stderr)
            return {"_cli_error": result.stderr}
    except FileNotFoundError:
        print("❌ AWS CLI not installed. Install with: pip install awscli", file=sys.stderr)
        return {"_cli_error": "AWS CLI not found on PATH"}
    except Exception as e:
        print(f"❌ Error running AWS CLI: {e}", file=sys.stderr)
        return {"_cli_error": str(e)}


def check_schedule(name: str, expected: dict) -> dict:
    # get-schedule returns fields at the top level (no "Schedule" wrapper key);
    # a nonexistent schedule is a nonzero exit + ResourceNotFoundException on
    # stderr, not a missing key in a successful response.
    schedule = run_aws_cli(
        [
            "scheduler",
            "get-schedule",
            "--name",
            name,
            "--region",
            "us-east-1",
        ]
    )

    if schedule is None:
        return {
            "name": name,
            "status": "MISSING",
            "message": f"Schedule '{name}' not found. Check Terraform state.",
            "exists": False,
            "enabled": False,
            "correct": False,
        }

    if "_cli_error" in schedule:
        return {
            "name": name,
            "status": "ERROR",
            "message": f"Failed to query (AWS CLI error): {schedule['_cli_error']}",
            "exists": False,
            "enabled": False,
            "correct": False,
        }

    enabled = schedule.get("State") == "ENABLED"
    correct_expr = schedule.get("ScheduleExpression") == expected["schedule"]
    correct_tz = schedule.get("ScheduleExpressionTimezone") == expected["timezone"]
    correct = correct_expr and correct_tz

    if not enabled:
        status = "DISABLED"
        message = "Schedule exists but is DISABLED. Auto-fix available with --fix."
    elif not correct:
        status = "MISCONFIGURED"
        message = f"Schedule enabled but config mismatch. Expected cron: {expected['schedule']}"
    else:
        status = "OK"
        message = "Schedule properly configured and ENABLED"

    return {
        "name": name,
        "status": status,
        "message": message,
        "exists": True,
        "enabled": enabled,
        "correct": correct,
        "schedule_expr": schedule.get("ScheduleExpression"),
        "timezone": schedule.get("Timezone"),
        "state": schedule.get("State"),
    }


def enable_schedule(name: str) -> bool:
    """Enable a disabled schedule."""
    print(f"  Enabling schedule '{name}'...", end=" ", flush=True)
    result = run_aws_cli(
        [
            "scheduler",
            "update-schedule",
            "--name",
            name,
            "--state",
            "ENABLED",
            "--region",
            "us-east-1",
        ]
    )

    if result is not None:
        print("✅ ENABLED")
        return True
    else:
        print("❌ FAILED")
        return False


def check_all_schedules() -> dict:
    print("\n" + "=" * 70)
    print("EVENTBRIDGE SCHEDULER VERIFICATION")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70 + "\n")

    results = {}
    for name, expected in EXPECTED_SCHEDULES.items():
        results[name] = check_schedule(name, expected)

    # Print report
    for name, data in results.items():
        emoji = "✅" if data["status"] == "OK" else "❌" if data["status"] in ("MISSING", "ERROR") else "⚠️ "
        print(f"{emoji} {name}")
        print(f"   Status: {data['status']}")
        print(f"   {data['message']}")
        if data["exists"] and not data["correct"]:
            print(f"   Got: {data['schedule_expr']} ({data['timezone']})")
        print()

    # Summary
    print("-" * 70)
    ok_count = sum(1 for d in results.values() if d["status"] == "OK")
    total = len(results)
    print(f"Result: {ok_count}/{total} schedules properly configured\n")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Verify EventBridge Scheduler configuration for data loaders")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix disabled schedules (enable them)",
    )

    args = parser.parse_args()

    # Check all schedules
    results = check_all_schedules()

    # Auto-fix if requested
    if args.fix:
        disabled = [name for name, data in results.items() if not data["enabled"] and data["exists"]]
        if disabled:
            print("FIXING DISABLED SCHEDULES:")
            fixed = 0
            for name in disabled:
                if enable_schedule(name):
                    fixed += 1
            print(f"\n✅ Fixed {fixed}/{len(disabled)} schedules")
        else:
            print("✅ No disabled schedules found - nothing to fix")

    # Exit with error if any issues
    issues = sum(1 for d in results.values() if d["status"] != "OK")
    if issues:
        print(f"\n⚠️  {issues} issue(s) found. See above for details.")
        sys.exit(1)
    else:
        print("✅ All scheduler checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
