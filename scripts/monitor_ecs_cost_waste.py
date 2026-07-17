#!/usr/bin/env python3
"""
Monitor ECS cluster for cost waste in real-time.
Shows: (1) current unhealthy tasks, (2) monthly cost impact, (3) projected savings
"""
import boto3
from datetime import datetime, timezone, timedelta
import sys

ecs = boto3.client('ecs', region_name='us-east-1')

# Fargate pricing (us-east-1)
FARGATE_CPU_COST_PER_HOUR = 0.04288  # 1024 CPU
FARGATE_MEMORY_COST_PER_HOUR = 0.004731 * 2  # 2048 MB

def get_task_cost_per_hour(cpu=1024, memory=2048):
    """Calculate hourly cost for a Fargate task."""
    return (cpu / 1024) * FARGATE_CPU_COST_PER_HOUR + (memory / 1024) * FARGATE_MEMORY_COST_PER_HOUR

def format_cost(cost):
    """Format cost for display."""
    if cost < 0.01:
        return f"${cost*1000:.1f}k"
    return f"${cost:.2f}"

def main():
    # Get all tasks
    tasks_resp = ecs.list_tasks(cluster='algo-cluster')
    task_arns = tasks_resp.get('taskArns', [])

    if not task_arns:
        print("[OK] No tasks running - cluster is clean!")
        return

    details = ecs.describe_tasks(cluster='algo-cluster', tasks=task_arns)

    print(f"\n{'='*70}")
    print(f"ECS COST WASTE MONITOR - {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*70}\n")

    unhealthy_cost_per_hour = 0
    unhealthy_tasks = []
    healthy_tasks = []
    now = datetime.now(timezone.utc)

    for task in details['tasks']:
        task_name = task['containers'][0]['name']
        health = task.get('healthStatus', 'UNKNOWN')
        started_at = task.get('startedAt')
        cpu = int(task.get('cpu', 1024))
        memory = int(task.get('memory', 2048))

        age_seconds = (now - started_at).total_seconds() if started_at else 0
        age_minutes = age_seconds / 60
        hourly_cost = get_task_cost_per_hour(cpu, memory)

        if health in ['UNHEALTHY', 'UNKNOWN']:
            unhealthy_tasks.append({
                'name': task_name,
                'health': health,
                'age_min': age_minutes,
                'cost_per_hour': hourly_cost,
                'cpu': cpu,
                'memory': memory
            })
            unhealthy_cost_per_hour += hourly_cost
        else:
            healthy_tasks.append({
                'name': task_name,
                'health': health,
                'age_min': age_minutes,
                'cost_per_hour': hourly_cost
            })

    # Display unhealthy tasks
    if unhealthy_tasks:
        print("[ALERT] UNHEALTHY/UNKNOWN TASKS (MONEY WASTE):\n")
        for task in unhealthy_tasks:
            status = "UNHEALTHY [FAIL]" if task['health'] == 'UNHEALTHY' else "UNKNOWN [?]"
            print(f"  {task['name']}")
            print(f"    Status: {status}")
            print(f"    Age: {task['age_min']:.0f} minutes")
            print(f"    Cost: {format_cost(task['cost_per_hour'])}/hour = {format_cost(task['cost_per_hour']*24)}/day = {format_cost(task['cost_per_hour']*730)}/month")
            print()
    else:
        print("[OK] No unhealthy tasks\n")

    # Display healthy tasks
    if healthy_tasks:
        print(f"[OK] HEALTHY TASKS ({len(healthy_tasks)}):\n")
        for task in healthy_tasks:
            print(f"  {task['name']}: {task['age_min']:.0f}min ({format_cost(task['cost_per_hour'])}/hr)")
    else:
        print("[OK] No healthy tasks running\n")

    # Calculate cost impact
    print(f"\n{'='*70}")
    print(f"COST IMPACT:\n")

    hourly_waste = unhealthy_cost_per_hour
    daily_waste = hourly_waste * 24
    monthly_waste = hourly_waste * 730  # Approximate days in month

    print(f"  Unhealthy tasks: {len(unhealthy_tasks)}")
    print(f"  Healthy tasks: {len(healthy_tasks)}")
    print(f"  Wasting: {format_cost(hourly_waste)}/hour")
    print(f"  Projected loss (if not stopped):")
    print(f"    Daily:   {format_cost(daily_waste)}")
    print(f"    Monthly: {format_cost(monthly_waste)}")

    if len(unhealthy_tasks) > 0:
        print(f"\n  [ALERT] AUTO-STOP LAMBDA WILL TERMINATE THESE IN ~20-60 MINUTES")
        print(f"  [ALERT] COST SAVINGS: {format_cost(monthly_waste)}/month when cleaned up")
    else:
        print(f"\n  [OK] Cluster is running efficiently")

    print(f"\n{'='*70}\n")

    # Exit with unhealthy count (can be used for monitoring)
    sys.exit(len(unhealthy_tasks))

if __name__ == '__main__':
    main()
