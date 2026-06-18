# Loader Safeguards: Preventing Hung Loaders

Loaders must not run indefinitely. Step Functions timeout alone does NOT kill ECS tasks—additional safeguards required.

## Safeguards

**1. Hard Timeout (Step Functions):** Configured in terraform/modules/pipeline/main.tf: stock_prices_daily 6h, swing_trader_scores 2h, technical_data_daily 2h, market_health_daily 20 min.

**2. Timeout Guardian Lambda:** Runs every 5 min, checks RUNNING loaders, compares runtime against MAX_DURATION (price: 4h, technical/score: 2h, others: 1h). Kills ECS task if exceeded, updates DB status to TIMEOUT.

**3. Database Constraint:** data_loader_status CHECK that RUNNING status < 24h. Prevents status updates if violated (acceptable—we'd want to know).

**4. CloudWatch Alarms:** Alert if no loader execution in 25+ hours or ECS task exit non-zero (dead-letter queue monitoring).

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
