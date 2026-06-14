# Loader Safeguards: Preventing Indefinite Execution and Resource Waste

## Overview

Loaders must not run indefinitely. This system enforces hard timeouts, automatic task termination, and alerting to prevent hung loaders from consuming infrastructure resources.

Key principle: Step Functions timeout alone does not guarantee ECS task termination—additional safeguards are required.

## Safeguards

### 1. **Hard Timeout on Step Functions**

Configured in `terraform/modules/pipeline/main.tf`:
- **stock_prices_daily**: 6h timeout (expected: 60-90 min)
- **swing_trader_scores**: 2h timeout (expected: 30+ min)
- **technical_data_daily**: 2h timeout (expected: varies)
- **market_health_daily**: 20 min timeout (expected: 20 min)

**Problem with timeouts:** Step Functions timeout aborts the state machine but may NOT kill the underlying ECS task. The task can keep running even after the state machine abort.

### 2. **ECS Task Hard Timeout**

Add timeout to ECS task definition:

```json
{
  "containerDefinitions": [{
    "image": "...",
    "containerPort": 8080,
    "stopTimeout": 60,  // Seconds to wait after SIGTERM before SIGKILL
    "essential": true
  }],
  "name": "loader-task",
  "requiresCompatibilities": ["FARGATE"]
}
```

**Also add:** Runtime limit in ECS capacity provider or Step Functions integration:
- Kill ECS task after hard timeout (Step Functions timeout + 5 min)

### 3. **Timeout Guardian Lambda**

Implemented in `lambda/loader_timeout_guardian.py`.

**Implementation:**
- Runs every 5 minutes via EventBridge
- Checks all loaders in RUNNING state
- Compares runtime against MAX_DURATION (loader-specific):
  - Price loaders: 4 hours
  - Technical/score loaders: 2 hours
  - Others: 1 hour
- **Kills ECS task** if exceeded
- Updates database status to TIMEOUT + error message
- Fires CloudWatch alarm metric

**Why this is needed:** Step Functions timeout alone doesn't guarantee ECS task termination.

**Deployment:** 
```bash
# Add to terraform/modules/pipeline/main.tf
resource "aws_lambda_function" "timeout_guardian" {
  filename = "lambda_timeout_guardian.zip"
  function_name = "algo-loader-timeout-guardian-${var.environment}"
  role = aws_iam_role.timeout_guardian.arn
  timeout = 60
  environment {
    variables = {
      DB_HOST = var.db_host
      DB_NAME = var.db_name
      # ... other DB vars
    }
  }
}

resource "aws_scheduler_schedule" "guardian_check" {
  name = "algo-loader-timeout-guardian"
  schedule_expression = "rate(5 minutes)"
  target {
    arn = aws_lambda_function.timeout_guardian.arn
    role_arn = var.eventbridge_scheduler_role_arn
  }
}
```

### 4. **Database Constraint: Prevent RUNNING > 24h**

Add check constraint to `data_loader_status`:

```sql
ALTER TABLE data_loader_status
ADD CONSTRAINT max_running_duration CHECK (
  EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - execution_started)) < 86400  -- 24 hours
  OR status != 'RUNNING'
);
```

**Trade-off:** This will prevent INSERTs/UPDATEs that violate the constraint. May cause loader status updates to fail if they exceed 24h (acceptable - we'd want to know).

### 5. **CloudWatch Alarms: Alert on Hung Loaders**

Configure alarms:

```terraform
resource "aws_cloudwatch_metric_alarm" "loader_running_too_long" {
  alarm_name = "algo-loader-running-too-long-${var.environment}"
  metric_name = "LoadersRunningHours"
  threshold = 2  # hours
  comparison_operator = "GreaterThanThreshold"
  alarm_actions = [var.sns_topic_arn]  # Email alert
}

resource "aws_cloudwatch_metric_alarm" "loader_timeout_count" {
  alarm_name = "algo-loader-timeouts-${var.environment}"
  metric_name = "LoaderTimeout"
  statistic = "Sum"
  threshold = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions = [var.sns_topic_arn]  # Email/Slack alert
}
```

### 6. **Monitoring Dashboard** (RECOMMENDED)

**Add to Terraform:**

```terraform
resource "aws_cloudwatch_dashboard" "loaders" {
  dashboard_name = "algo-loader-health"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AlgoLoaders", "LoadersRunning", { stat = "Average" }],
            ["AlgoLoaders", "LoaderTimeout", { stat = "Sum" }],
            ["AlgoLoaders", "LoaderDuration", { stat = "Average" }]
          ]
          period = 300
          stat = "Average"
          region = var.aws_region
        }
      }
    ]
  })
}
```

### 7. **Database-Level Monitoring** (QUICK WIN)

**Create SQL query to run daily:**

```sql
-- Alert if any loader in RUNNING state > 2 hours
SELECT 
  table_name, 
  execution_started,
  EXTRACT(HOUR FROM CURRENT_TIMESTAMP - execution_started) as hours_running
FROM data_loader_status
WHERE status = 'RUNNING' 
  AND execution_started < CURRENT_TIMESTAMP - INTERVAL '2 hours'
ORDER BY execution_started ASC;
```

**Action:** Run this in a CloudWatch-triggered Lambda that alerts if any rows exist.

## References
- Terraform pipeline module: `terraform/modules/pipeline/main.tf` (lines 1270-1362)
- Data loader status schema: `lambda/db-init/schema.sql` (line 1757)
- Timeout guardian code: `lambda/loader_timeout_guardian.py`
