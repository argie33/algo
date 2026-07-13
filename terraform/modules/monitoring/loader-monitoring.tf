# ============================================================
# F-04: Loader Failure Monitoring and Alarms
# ============================================================
# Consolidated monitoring for 28+ supporting loaders via ECS
# CloudWatch metric filters + alarms per loader
# Dashboard for real-time status heatmap

# ============================================================
# 1. CloudWatch Log Group for Loaders (already exists via ECS)
# ============================================================
# Loaders write to /ecs/algo-loader service log group
# This monitoring attaches metric filters to existing logs

# ============================================================
# 2. Metric Filters for Each Loader
# ============================================================
# Pattern: Scan ECS task logs for CRITICAL, FAILED, Exception keywords
# Create custom metrics for each loader with Failure count

locals {
  supporting_loaders = [
    "aaii_sentiment",
    "algo_metrics_daily",
    "analyst_sentiment_analysis",
    "analyst_upgrade_downgrade",
    "balance_sheet",
    "buy_sell_daily",
    "cash_flow",
    "company_profile",
    "earnings_calendar",
    "earnings_history",
    "economic_calendar",
    "fear_greed_index",
    "fred_economic_data",
    "growth_metrics",
    "income_statement",
    "industry_ranking",
    "market_health_daily",
    "naaim",
    "positioning_metrics",
    "prices",
    "quality_metrics",
    "russell2000_constituents",
    "seasonality",
    "sector_performance",
    "sector_ranking",
    "sentiment",
    "sentiment_aggregate",
    "signal_quality_scores",
    "signal_themes",
    "sp500_constituents",
    "stability_metrics",
    "stock_scores",
    "stock_symbols",
    "swing_trader_scores",
    "technical_data_daily",
    "trend_criteria_data",
    "value_metrics",
  ]
}

# CloudWatch Metric Filter for loader failures (DISABLED)
# NOTE: Metric filters cannot extract log content into dimensions after emission.
# Per-loader filtering requires either EMF (Embedded Metric Format) from application code,
# or EventBridge on ECS task state changes (implemented below). We use EventBridge instead.
#
# Keeping metric filter definition for potential future use, but it's not functional
# for per-loader alarms without application-level metric instrumentation.

# ============================================================
# 3. CloudWatch Alarms Per Loader
# ============================================================
# Create individual alarms for high-impact loaders
# Consolidated alarm for all other loaders

# Per-loader CloudWatch alarms (DISABLED)
# These were attempting to filter by LoaderName dimension, but CloudWatch metric filters
# cannot extract log content into dimensions after metric emission. We rely on EventBridge
# task state change rules instead (defined below), which provide per-loader granularity.

# Supporting loaders: Consolidated alarm (any failure in the group triggers alert)
resource "aws_cloudwatch_metric_alarm" "supporting_loader_failures" {
  count               = var.ecs_log_group_name != "" ? 1 : 0
  alarm_name          = "${var.project_name}-supporting-loaders-failed-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "LoaderFailureCount"
  namespace           = "${var.project_name}/Loaders"
  period              = "300" # 5 minutes
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "One or more supporting loaders failed — investigate in CloudWatch Logs"
  treat_missing_data  = "notBreaching"

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# ============================================================
# 4. SNS Topic for Loader Alerts
# ============================================================

resource "aws_sns_topic" "loader_alerts" {
  count             = var.ecs_log_group_name != "" ? 1 : 0
  name              = "${var.project_name}-loader-alerts-${var.environment}"
  display_name      = "Loader Failure Alerts"
  kms_master_key_id = "alias/aws/sns"

  tags = var.common_tags
}

# Email subscription for ops team
resource "aws_sns_topic_subscription" "loader_alerts_email" {
  count     = var.ecs_log_group_name != "" && var.alert_email_to != "" ? 1 : 0
  topic_arn = aws_sns_topic.loader_alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email_to
}

# ============================================================
# 5. CloudWatch Dashboard - Loader Status Heatmap
# ============================================================

resource "aws_cloudwatch_dashboard" "loader_monitoring" {
  count          = var.ecs_log_group_name != "" ? 1 : 0
  dashboard_name = "${var.project_name}-loader-monitoring-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 24
        height = 8
        properties = {
          metrics = [
            ["${var.project_name}/Loaders", "LoaderFailureCount"]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Loader Task Failures (5-min window)"
          view   = "timeSeries"
          yAxis  = { left = { min = 0 } }
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 8
        width  = 24
        height = 10
        properties = {
          query  = "fields @timestamp, @message, @logStream | filter @message like /FAILED|CRITICAL|Exception|Error/ | stats count() as failure_count by @logStream"
          region = var.aws_region
          title  = "Recent Loader Errors (Last 1 hour)"
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 18
        width  = 24
        height = 6
        properties = {
          query  = "fields @timestamp, @logStream, @message | filter @message like /completed|finished|success/ | stats count() as success_count by @logStream | sort success_count desc"
          region = var.aws_region
          title  = "Successful Loader Runs (Last 24 hours)"
        }
      }
    ]
  })
}

# ============================================================
# 6. EventBridge Rule to Capture ECS Task Failures
# ============================================================
# Complement the log-based alarms with direct ECS event capture

resource "aws_cloudwatch_event_rule" "loader_task_failure" {
  count       = var.ecs_log_group_name != "" ? 1 : 0
  name        = "${var.project_name}-loader-task-failure-${var.environment}"
  description = "Capture ECS task failures for loaders"

  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn        = [var.ecs_cluster_arn]
      lastStatus        = ["STOPPED", "FAILED"]
      taskDefinitionArn = ["*algo-loader*"]
    }
  })

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "loader_task_failure_sns" {
  count     = var.ecs_log_group_name != "" ? 1 : 0
  rule      = aws_cloudwatch_event_rule.loader_task_failure[0].name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.loader_alerts[0].arn

  input_transformer {
    input_paths = {
      cluster = "$.detail.clusterArn"
      task    = "$.detail.taskArn"
      status  = "$.detail.lastStatus"
      reason  = "$.detail.stoppedReason"
    }
    input_template = jsonencode({
      AlertType = "LoaderTaskFailure"
      Cluster   = "<cluster>"
      Task      = "<task>"
      Status    = "<status>"
      Reason    = "<reason>"
    })
  }
}

resource "aws_sns_topic_policy" "loader_alerts_eventbridge" {
  count = var.ecs_log_group_name != "" ? 1 : 0
  arn   = aws_sns_topic.loader_alerts[0].arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action   = "SNS:Publish"
      Resource = aws_sns_topic.loader_alerts[0].arn
    }]
  })
}

# ============================================================
# 7. CloudWatch Alarms for Pipeline Monitoring (Production SLAs)
# ============================================================

# Pipeline Timing Alarm: stock_prices_daily > 120 minutes (yfinance bottleneck) — prod only
resource "aws_cloudwatch_metric_alarm" "stock_prices_daily_slow" {
  count               = var.ecs_log_group_name != "" && var.enable_performance_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-loader-stock-prices-slow-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "OperationDuration"
  namespace           = "AlgoTrading/Operations"
  period              = "300" # 5 minutes
  statistic           = "Maximum"
  threshold           = "7200" # 120 minutes in seconds
  alarm_description   = "stock_prices_daily loader exceeded 120 min — yfinance rate limiting likely bottleneck"
  treat_missing_data  = "notBreaching"

  dimensions = {
    Operation = "load_prices_daily"
  }

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# Pipeline Timing Alarm: morning prep pipeline > 300 minutes (5 hours) — prod only
# Alert before the 9:30 AM deadline (prep starts at 2:00 AM, runs 7.5h window)
resource "aws_cloudwatch_metric_alarm" "morning_prep_slow" {
  count               = var.ecs_log_group_name != "" && var.enable_performance_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-morning-prep-slow-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "OperationDuration"
  namespace           = "AlgoTrading/Operations"
  period              = "300" # 5 minutes
  statistic           = "Maximum"
  threshold           = "18000" # 300 minutes in seconds
  alarm_description   = "Morning prep pipeline (Step Functions) exceeded 300 min — approaching 9:30 AM deadline"
  treat_missing_data  = "notBreaching"

  dimensions = {
    Operation = "morning_prep_pipeline"
  }

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# ============================================================
# 8. EventBridge Scheduler Failure Detection (Critical for Loaders)
# ============================================================
# ALERT: Morning pipeline didn't execute at scheduled 2:00 AM ET
# This catches situations where EventBridge Scheduler silently fails to trigger

resource "aws_cloudwatch_metric_alarm" "morning_pipeline_no_execution" {
  count               = var.ecs_log_group_name != "" ? 1 : 0
  alarm_name          = "${var.project_name}-morning-pipeline-no-exec-${var.environment}"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "ExecutionCount"
  namespace           = "AWS/States"
  period              = "3600" # Check hourly (1 hour = 3600 sec)
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "Morning pipeline (Step Functions) did not execute at 2:00 AM ET. EventBridge Scheduler may have failed."
  treat_missing_data  = "breaching" # Treat missing data as alarm (no executions = failed)

  dimensions = {
    StateMachineArn = "arn:aws:states:${var.aws_region}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.project_name}-morning-prep-pipeline-${var.environment}"
  }

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# Data freshness alarm: price_daily not updated by 3 AM ET (1 hour after scheduled run)
# If 2:00 AM pipeline executes successfully, prices should be loaded by 3 AM
resource "aws_cloudwatch_metric_alarm" "price_data_not_fresh_after_morning_pipeline" {
  count               = var.ecs_log_group_name != "" ? 1 : 0
  alarm_name          = "${var.project_name}-prices-stale-after-morning-${var.environment}"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "PriceDailyRecordCount"
  namespace           = "${var.project_name}/DataFreshness"
  period              = "3600"
  statistic           = "Average"
  threshold           = "500" # Less than 500 records = data not loaded
  alarm_description   = "price_daily has <500 rows after 3 AM ET. Morning pipeline may have failed silently."
  treat_missing_data  = "breaching"

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# Scheduler DLQ Alarm: Dead Letter Queue receiving failed invocations
# If EventBridge Scheduler has a DLQ configured, messages here indicate trigger failures
resource "aws_cloudwatch_metric_alarm" "scheduler_dlq_messages" {
  count               = var.scheduler_dlq_arn != "" ? 1 : 0
  alarm_name          = "${var.project_name}-scheduler-dlq-events-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "EventBridge Scheduler DLQ receiving messages. Pipeline trigger failures detected."
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = element(split(":", var.scheduler_dlq_arn), length(split(":", var.scheduler_dlq_arn)) - 1)
  }

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# RDS Connection Pool Alarm: > 40 connections (warn threshold before 100 limit) — prod only
resource "aws_cloudwatch_metric_alarm" "rds_connections_high_warning" {
  count               = var.ecs_log_group_name != "" && var.enable_resource_alarms ? 1 : 0
  alarm_name          = "${var.project_name}-rds-connections-warning-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "40" # Warn at 40, allow 20-30 normal, critical at 100
  alarm_description   = "RDS connections elevated (>40) — monitor for slow queries; expected 20-30 during peak"
  treat_missing_data  = "notBreaching"

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# CloudWatch Dashboard: Pipeline Performance Monitoring
resource "aws_cloudwatch_dashboard" "pipeline_monitoring" {
  count          = var.ecs_log_group_name != "" ? 1 : 0
  dashboard_name = "${var.project_name}-pipeline-monitoring-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AlgoTrading/Operations", "OperationDuration"],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "stock_prices_daily Loader Timing (SLA: <120 min)"
          yAxis  = { left = { min = 0, max = 14400 } } # 240 min = 14400 sec
          annotations = {
            horizontal = [
              {
                value = 7200
                label = "SLA Threshold (120 min)"
                fill  = "above"
              }
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/RDS", "DatabaseConnections"],
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "RDS Connection Pool Usage (Alert: >40)"
          yAxis  = { left = { min = 0, max = 100 } }
          annotations = {
            horizontal = [
              {
                value = 40
                label = "Warning (40 connections)"
                fill  = "above"
              },
              {
                value = 100
                label = "Critical (100 connections)"
                fill  = "above"
              }
            ]
          }
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 6
        width  = 24
        height = 8
        properties = {
          query  = "fields @timestamp, @duration, @operation | filter @operation like /(load_prices|morning_prep|stock_prices)/ | stats max(@duration) as max_duration, avg(@duration) as avg_duration, count() as run_count by @operation | sort max_duration desc"
          region = var.aws_region
          title  = "Pipeline Timing Summary (Last 7 days)"
        }
      }
    ]
  })
}
