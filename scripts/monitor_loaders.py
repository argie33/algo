#!/usr/bin/env python3
"""Monitor ECS loader tasks in real-time - show running tasks and recent logs."""
import subprocess
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

def get_running_tasks():
    """Get all running ECS tasks in algo-cluster."""
    result = subprocess.run(
        ["aws", "ecs", "list-tasks", "--cluster", "algo-cluster",
         "--desired-status", "RUNNING", "--region", "us-east-1"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return []

    data = json.loads(result.stdout)
    return data.get("taskArns", [])

def get_loader_name_from_arn(arn):
    """Extract loader name from task ARN."""
    parts = arn.split("/")
    if len(parts) >= 2:
        return parts[-2].replace("algo-", "").replace("-loader", "")
    return "unknown"

def main():
    print(f"=== LOADER MONITOR [{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] ===\n")

    tasks = get_running_tasks()

    loaders_running = defaultdict(int)
    for task_arn in tasks:
        loader_name = get_loader_name_from_arn(task_arn)
        loaders_running[loader_name] += 1

    if loaders_running:
        print(f"Running ECS Tasks: {len(tasks)} total\n")
        print("Loaders active:")
        for loader, count in sorted(loaders_running.items()):
            print(f"  - {loader}: {count} task(s)")
    else:
        print("No ECS tasks currently running")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
