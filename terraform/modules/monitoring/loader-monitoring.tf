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

# CloudWatch Metric Filter: Generic loader failure pattern
# Applies to all loaders, creates per-loader metrics
resource "aws_cloudwatch_log_metric_filter" "loader_failure_pattern" {
  count          = var.ecs_log_group_name != "" ? 1 : 0
  name           = "LoaderFailurePattern"
  log_group_name = var.ecs_log_group_name
  filter_pattern = "[... ERROR, FAILED, EXCEPTION, CRITICAL ...]"

  metric_transformation {
    name      = "LoaderFailureCount"
    namespace = "${var.project_name}/Loaders"
    value     = "1"

    # Extract loader name from log (pattern: [loader_name] ERROR ...)
    # This allows per-loader filtering in CloudWatch
    default_value = 0
  }
}

# ============================================================
# 3. CloudWatch Alarms Per Loader
# ============================================================
# Create individual alarms for high-impact loaders
# Consolidated alarm for all other loaders

# Critical loaders (core data): stock_symbols, stock_prices_daily, technical_data_daily, market_health_daily
resource "aws_cloudwatch_metric_alarm" "per_loader_failures" {
  for_each = toset([
    "stock_symbols",
    "technical_data_daily",
    "market_health_daily",
  ])

  alarm_name          = "${var.project_name}-loader-${each.value}-failed-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "LoaderFailureCount"
  namespace           = "${var.project_name}/Loaders"
  period              = "300"  # 5 minutes
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "CRITICAL: Loader ${each.value} failed — may cause stale data"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoaderName = each.value
  }

  alarm_actions = [aws_sns_topic.loader_alerts[0].arn]

  tags = var.common_tags
}

# Supporting loaders: Consolidated alarm (any failure in the group triggers alert)
resource "aws_cloudwatch_metric_alarm" "supporting_loader_failures" {
  count               = var.ecs_log_group_name != "" ? 1 : 0
  alarm_name          = "${var.project_name}-supporting-loaders-failed-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "LoaderFailureCount"
  namespace           = "${var.project_name}/Loaders"
  period              = "300"  # 5 minutes
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "One or more supporting loaders failed — investigate in CloudWatch Logs"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.loader_alerts[0].arn]

  tags = var.common_tags
}

# ============================================================
# 4. SNS Topic for Loader Alerts
# ============================================================

resource "aws_sns_topic" "loader_alerts" {
  count         = var.ecs_log_group_name != "" ? 1 : 0
  name          = "${var.project_name}-loader-alerts-${var.environment}"
  display_name  = "Loader Failure Alerts"
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
        type = "metric"
        properties = {
          metrics = [
            [
              { expression = "STATS(m1)", label = "All Loader Failures" },
              { id = "m1", expression = "SUM(INSIGHTS([\"LoaderFailureCount\"], LogGroupName=/aws/ecs/algo-loader/))" }
            ]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Loader Failures - Last Hour"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      {
        type = "log"
        properties = {
          query = <<-EOQ
            fields @timestamp, @message, loader_name
            | filter @message like /FAILED|CRITICAL|Exception/
            | stats count() as failure_count by loader_name
            | sort failure_count desc
          EOQ
          region = var.aws_region
          title  = "Loader Failure Summary (Last 1 hour)"
        }
      },
      {
        type = "metric"
        properties = {
          metrics = concat(
            [
              ["${var.project_name}/Loaders", "LoaderFailureCount", { stat = "Sum" }]
            ]
          )
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Per-Loader Failure Count"
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
  count         = var.ecs_log_group_name != "" ? 1 : 0
  name          = "${var.project_name}-loader-task-failure-${var.environment}"
  description   = "Capture ECS task failures for loaders"

  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn = [var.ecs_cluster_arn]
      lastStatus = ["STOPPED", "FAILED"]
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
  count  = var.ecs_log_group_name != "" ? 1 : 0
  arn    = aws_sns_topic.loader_alerts[0].arn
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
