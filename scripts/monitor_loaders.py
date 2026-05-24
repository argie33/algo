#!/usr/bin/env python3
"""Monitor ECS loader tasks in real-time - show running tasks and recent logs."""
import subprocess
import json
import sys
import re
from collections import defaultdict
from datetime import datetime, timezone

def get_running_tasks():
    """Get all running ECS tasks in algo-cluster with their loader names."""
    aws_path = r"C:\Users\arger\AppData\Local\Programs\Python\Python311\Scripts\aws.cmd"

    # Get task ARNs
    result = subprocess.run(
        [aws_path, "ecs", "list-tasks", "--cluster", "algo-cluster",
         "--desired-status", "RUNNING", "--region", "us-east-1"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return {}

    task_arns = json.loads(result.stdout).get("taskArns", [])
    if not task_arns:
        return {}

    # Describe tasks to get task definitions
    result = subprocess.run(
        [aws_path, "ecs", "describe-tasks", "--cluster", "algo-cluster",
         "--tasks"] + task_arns + ["--region", "us-east-1"],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode != 0:
        return {}

    loaders = {}
    tasks = json.loads(result.stdout).get("tasks", [])
    for task in tasks:
        arn = task.get("taskDefinitionArn", "")
        match = re.search(r'algo-(.+?)-loader:', arn)
        if match:
            loader_name = match.group(1)
            loaders[loader_name] = loaders.get(loader_name, 0) + 1

    return loaders

def get_loader_name_from_arn(arn):
    """Extract loader name from task definition ARN."""
    match = re.search(r'algo-(.+?)-loader:', arn)
    if match:
        return match.group(1)
    return "unknown"

def main():
    print(f"=== LOADER MONITOR [{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] ===\n")

    loaders_running = get_running_tasks()

    if loaders_running:
        total_tasks = sum(loaders_running.values())
        print(f"Running ECS Tasks: {total_tasks} total\n")
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
