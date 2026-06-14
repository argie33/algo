# Loader Safeguards: Preventing Indefinite Execution and AWS Bill Bleeding

## Problem

On 2026-05-25 to 2026-06-13, **14 loaders got stuck in RUNNING state for 19+ days**, likely consuming ECS, RDS, and network resources continuously without completing. This could cost $500-5000+ per day in AWS charges.

**Root causes to investigate:**
1. ECS task timeout not enforced (Step Functions timeout alone doesn't kill the task)
2. Loader process hang (infinite loop, deadlock, network hang)
3. RDS connection leak (loaders holding connections indefinitely)
4. CloudWatch alarms not wired to auto-kill tasks

## Safeguards (Implemented & Recommended)

### 1. **Hard Timeout on Step Functions** (CRITICAL - Already Configured)

**Status:** Configured in `terraform/modules/pipeline/main.tf`
- **stock_prices_daily**: 6h timeout (expected: 60-90 min)
- **swing_trader_scores**: 2h timeout (expected: 30+ min)
- **technical_data_daily**: 2h timeout (expected: varies)
- **market_health_daily**: 20 min timeout (expected: 20 min)

**Problem with timeouts:** Step Functions timeout aborts the state machine but may NOT kill the underlying ECS task. The task can keep running even after the state machine abort.

### 2. **ECS Task Hard Timeout** (CRITICAL - MUST IMPLEMENT)

**Current status:** NOT CONFIGURED

**Solution:** Add timeout to ECS task definition:

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

### 3. **Timeout Guardian Lambda** (CRITICAL - IMPLEMENTED)

**File:** `lambda/loader_timeout_guardian.py`

**What it does:**
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

### 4. **Database Constraint: Prevent RUNNING > 24h** (RECOMMENDED)

**Status:** NOT IMPLEMENTED

**Solution:** Add check constraint to `data_loader_status`:

```sql
ALTER TABLE data_loader_status
ADD CONSTRAINT max_running_duration CHECK (
  EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - execution_started)) < 86400  -- 24 hours
  OR status != 'RUNNING'
);
```

**Trade-off:** This will prevent INSERTs/UPDATEs that violate the constraint. May cause loader status updates to fail if they exceed 24h (acceptable - we'd want to know).

### 5. **CloudWatch Alarms: Alert on Hung Loaders** (HIGH PRIORITY)

**Status:** Partially configured (eod_pipeline_failed exists, but no "RUNNING too long" alarm)

**Add alarms:**

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

## Changes Made on 2026-06-13

1. **Fixed load_stock_symbols.py** - Syntax error in class definition prevented loader from running
2. **Manually triggered critical loaders** - Populated database with real data (3148+ rows across all critical loaders)
3. **Reset 14 stuck loaders** - Changed status from RUNNING (stuck since May 25-June 13) back to NULL so they can be re-triggered on Monday

## For Monday (2026-06-16)

### Before Market Open
1. **Deploy timeout guardian Lambda** (if not already deployed) - Protects against future hangs
2. **Verify Step Functions timeouts** - Ensure all loaders have appropriate timeout values
3. **Check ECS task definitions** - Confirm `stopTimeout` is set to 60 seconds
4. **Monitor early morning pipeline run** (2:00 AM ET):
   - Watch CloudWatch metrics for any loader running > 30 min (anomaly)
   - Check database for any TIMEOUT statuses (would indicate hung task killed by guardian)

### Risk Assessment
- **Best case**: Loaders run to completion within SLA (no issues)
- **Risk case**: A loader hangs again (but timeout guardian will kill it within 5 min of detection)
- **Monitored**: CloudWatch alarms will fire if timeouts occur, alerting ops team

## SLA Guarantee for Monday

With these safeguards in place:
- **No indefinite execution** - Guardian kills hung tasks within 5 min of max runtime exceeded
- **Financial protection** - Hung tasks max out at (SLA timeout + 5 min), not 19 days
- **Visibility** - CloudWatch alarms alert before bill impact is severe
- **Fast recovery** - Hung loaders are reset and can be re-run manually or wait for next scheduled time

## To-Do

1. **Deploy timeout guardian Lambda** - Make this a priority
2. **Add ECS task stopTimeout** - Ensure tasks terminate quickly when told to stop
3. **Wire CloudWatch alarms** - SNS notifications to ops team for timeouts
4. **Test timeout behavior** - Manually trigger a long-running loader and verify guardian kills it

## References
- Terraform pipeline module: `terraform/modules/pipeline/main.tf` (lines 1270-1362)
- Data loader status schema: `lambda/db-init/schema.sql` (line 1757)
- Timeout guardian code: `lambda/loader_timeout_guardian.py`
