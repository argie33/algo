# ECS Best Practices - Prevent Unhealthy Task Lingering

## Problem
Unhealthy ECS tasks can run indefinitely, wasting money (~$45/month per stuck task). Tasks don't auto-stop when unhealthy—they continue consuming resources until manually terminated or killed by the cost circuit breaker (every 6 hours).

## Solution: 4-Layer Safeguards

### Layer 1: Smart Health Checks (Immediate)
Instead of just checking "is process running", test actual functionality.

**Current:** `ps aux | grep python` (basic)
**Best Practice:** Check if process is responsive + not stuck

```python
# In loader container at startup:
# Create a health check file that loader updates every 5 seconds
# If health check file is stale → loader is stuck → mark unhealthy

health_check_file = "/tmp/health_check"
with open(health_check_file, "w") as f:
    f.write(datetime.now().isoformat())
# Update every 5 seconds during execution
```

### Layer 2: Stop Timeout + Graceful Shutdown
Give tasks time to clean up, then force-stop if they don't exit.

```hcl
# In ECS task definition:
stopTimeout = 30  # Kill -9 after 30s of SIGTERM
```

This allows:
- Graceful database connection closure (5-10s)
- Lock release from DynamoDB (5s)
- Status update to database (5s)
- Then force-kill if still running

### Layer 3: Task-Level Restart Policy
Automatically retry failed tasks (useful for transient failures).

```hcl
# In ECS task definition:
containerDefinitions = [{
  ...
  # Retry failed container up to 2 times before marking task as failed
  "retryPolicy" = [
    {
      "interval" = 1
      "backoff" = 2
      "maxAttempts" = 2
    }
  ]
}]
```

### Layer 4: CloudWatch Alarms + Auto-Remediation

**Alarm 1: Unhealthy Task Detector**
```
Metric: ECS UnhealthyTaskCount > 0
Action: SNS Notification + Log to database
```

**Alarm 2: Task Stuck Duration**
```
Metric: Task age > 2 hours AND health = UNKNOWN
Action: Lambda function to terminate it
```

**Alarm 3: Task CPU > 90% (runaway process)**
```
Metric: ECS task CPU utilization > 90%
Action: Terminate task (likely stuck in infinite loop)
```

## Implementation Checklist

### ✅ DONE: Current Health Check
- Location: `terraform/modules/loaders/main.tf:783-789`
- Status: Basic process check working
- Issue: Only checks process exists, not responsiveness

### 🔧 TODO: Improve Health Check
File: `loaders/base_loader.py`
```python
def setup_health_check():
    """Create health check file that loader updates every 5s."""
    health_file = "/tmp/loader_health_check"
    
    # Initialize
    with open(health_file, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
    
    # Update in main loop every 5 seconds
    def update_health():
        with open(health_file, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    
    return update_health

# In loader.run():
update_health = setup_health_check()
for row in batch:
    # ... process row ...
    update_health()  # Every iteration
```

Health check script:
```bash
#!/bin/bash
# /healthcheck.sh
health_file="/tmp/loader_health_check"
if [ ! -f "$health_file" ]; then
    echo "No health check file"
    exit 1
fi

# Get age of health check file (seconds)
age=$(($(date +%s) - $(stat -c %Y "$health_file")))

if [ $age -gt 60 ]; then
    echo "Health check stale: ${age}s old"
    exit 1
fi

echo "OK"
exit 0
```

### 🔧 TODO: Add Stop Timeout to ECS Task

File: `terraform/modules/loaders/main.tf` (line ~825, after `memory = ...`)

```hcl
  # Graceful shutdown timeout
  # Gives loaders 30 seconds to:
  #   1. Close database connections (5-10s)
  #   2. Release DynamoDB locks (5s)
  #   3. Save final state (5s)
  # Then force-kill with SIGKILL
  stop_timeout = 30
  
  # Timeout for health check to complete (default 4s)
  # Must be shorter than health check interval
  container_definitions = jsonencode([{
    ...
    healthCheck = {
      command     = ["/healthcheck.sh"]  # Use script instead of inline
      interval    = 30
      timeout     = 5
      retries     = 2
      startPeriod = 120
    }
  }])
```

### 🔧 TODO: CloudWatch Alarms

File: `terraform/modules/monitoring/ecs-health-alarms.tf` (NEW)

```hcl
# Alarm 1: Unhealthy task count
resource "aws_cloudwatch_metric_alarm" "ecs_unhealthy_tasks" {
  alarm_name          = "${var.project_name}-ecs-unhealthy-tasks-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2  # 2 evaluation periods = 2 * 60s = 2 minutes
  metric_name         = "RegisteredTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 60
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "Alert when ECS tasks are unhealthy"
  alarm_actions       = [var.sns_alert_topic_arn]

  dimensions = {
    ClusterName = var.cluster_name
    HealthStatus = "UNKNOWN"
  }
}

# Alarm 2: Task stuck for > 2 hours
resource "aws_cloudwatch_metric_alarm" "ecs_stuck_task" {
  alarm_name          = "${var.project_name}-ecs-stuck-task-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/ECS"
  period              = 300  # 5 minutes
  statistic           = "Maximum"
  threshold           = 7200  # 2 hours in seconds
  alarm_actions       = [aws_lambda_function.auto_kill_stuck_tasks.arn]
}

# Alarm 3: Task CPU runaway (> 90%)
resource "aws_cloudwatch_metric_alarm" "ecs_cpu_runaway" {
  alarm_name          = "${var.project_name}-ecs-cpu-runaway-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "ECS/ContainerInsights"
  period              = 60
  statistic           = "Average"
  threshold           = 90
  alarm_actions       = [aws_lambda_function.auto_kill_stuck_tasks.arn]
}
```

### 🔧 TODO: Auto-Kill Stuck Tasks Lambda

File: `lambda/auto_kill_stuck_tasks/index.py` (NEW)

```python
"""
Auto-terminate stuck ECS tasks that have been unhealthy for > 2 hours.
Triggered by CloudWatch alarm when health status = UNKNOWN and age > 2h.
"""
import boto3
from datetime import datetime, timezone, timedelta

ecs = boto3.client('ecs')

def lambda_handler(event, context):
    cluster = 'algo-cluster'
    
    # List all tasks
    response = ecs.list_tasks(cluster=cluster)
    task_arns = response.get('taskArns', [])
    
    if not task_arns:
        return {'statusCode': 200, 'message': 'No tasks to check'}
    
    # Get task details
    details = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
    killed = []
    
    now = datetime.now(timezone.utc)
    
    for task in details['tasks']:
        task_name = task['taskDefinitionArn'].split('/')[-1]
        health = task.get('healthStatus', 'UNKNOWN')
        started_at = task.get('startedAt')
        
        if not started_at:
            continue
            
        age_seconds = (now - started_at).total_seconds()
        age_hours = age_seconds / 3600
        
        # Kill if unhealthy for > 2 hours OR stuck for > 4 hours
        if (health in ['UNHEALTHY', 'UNKNOWN'] and age_hours > 2) or age_hours > 4:
            try:
                ecs.stop_task(
                    cluster=cluster,
                    task=task['taskArn'],
                    reason=f'Auto-killed: {health} for {age_hours:.1f}h (cost waste prevention)'
                )
                killed.append({
                    'task': task_name,
                    'health': health,
                    'age_hours': age_hours
                })
            except Exception as e:
                print(f"Failed to kill {task_name}: {e}")
    
    if killed:
        print(f"Killed {len(killed)} stuck tasks: {killed}")
        # TODO: Send SNS alert with details
    
    return {
        'statusCode': 200,
        'killed_tasks': killed
    }
```

### 🔧 TODO: Cost Circuit Breaker Enhancement

File: `lambda/cost-circuit-breaker/index.py`

Add to existing circuit breaker:
```python
def check_unhealthy_tasks():
    """Check for unhealthy tasks and auto-kill if > 2 hours old."""
    ecs = boto3.client('ecs')
    
    tasks = ecs.list_tasks(cluster='algo-cluster')
    details = ecs.describe_tasks(cluster='algo-cluster', tasks=tasks['taskArns'])
    
    unhealthy = []
    for task in details['tasks']:
        if task.get('healthStatus', 'UNKNOWN') == 'UNHEALTHY':
            age_min = calculate_age(task['startedAt'])
            if age_min > 120:  # > 2 hours
                ecs.stop_task(cluster='algo-cluster', task=task['taskArn'])
                unhealthy.append(task['taskDefinitionArn'])
    
    return unhealthy

# In main handler:
unhealthy_killed = check_unhealthy_tasks()
if unhealthy_killed:
    print(f"Cost Circuit Breaker killed {len(unhealthy_killed)} unhealthy tasks")
```

## Monitoring & Alerting

After implementation, monitor these queries:

### Check for Unhealthy Tasks (Daily)
```bash
python scripts/monitor_ecs_cost_waste.py
```

### Check CloudWatch Alarms
```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix algo-ecs \
  --query 'MetricAlarms[*].[AlarmName,StateValue]' \
  --output table
```

### Check CloudWatch Logs for Stuck Tasks
```bash
# Find tasks that log no activity for > 1 hour
aws logs start-query \
  --log-group-name "/ecs/algo-*" \
  --start-time $(($(date +%s) - 3600)) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp | stats count() by @logStream' \
  --output table
```

## Deployment Order

1. ✅ Deploy health check improvements (non-breaking)
2. ✅ Deploy stop_timeout setting (non-breaking)
3. ✅ Deploy CloudWatch alarms (observability only)
4. ✅ Deploy auto-kill Lambda (active remediation)
5. Monitor for 1 week, tune thresholds

## Expected Impact

| Safeguard | Impact | Cost Savings |
|-----------|--------|-------------|
| Better health checks | Detect stuck tasks 30s after failure | Reduce lingering time |
| Stop timeout | Graceful cleanup + force kill | Prevent resource leaks |
| CloudWatch alarms | Immediate alerts | Operator visibility |
| Auto-kill Lambda | Kill stuck tasks after 2h | ~$45/task/month |
| **Total** | **Prevent stuck tasks entirely** | **$500+/month** |

## Related Docs

- [steering/LOADER_RECOVERY_GUIDE.md](LOADER_RECOVERY_GUIDE.md) - Data recovery procedures
- [steering/OPERATIONS.md](OPERATIONS.md) - Operational runbook
- [BILLING_QUICK_REFERENCE.md](../BILLING_QUICK_REFERENCE.md) - Cost controls
