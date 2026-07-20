# ============================================================
# PHASE 2: Form 4 Parsing Failure Monitoring
# ============================================================
# CloudWatch alarms for Form 4 plain-text parsing reliability
# Tracks: insider name extraction, shares owned extraction,
# ownership % extraction, and transaction extraction failures

# Critical success metric: Form 4 data availability for insider_holdings_sec loader
# If Form 4 parsing fails >25% of attempts, insider data becomes unreliable

# ============================================================
# 1. CloudWatch Alarm: Form 4 Parsing Failures Exceed Threshold
# ============================================================
# Alert when parsing failure rate >25% over 1-hour window
# This indicates data quality issues that need investigation

resource "aws_cloudwatch_metric_alarm" "form4_parsing_failures_high" {
  alarm_name          = "${var.project_name}-form4-parsing-failures-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "ParsingFailure"
  namespace           = "Algo/Form4Parsing"
  period              = "3600" # 1-hour window
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "Form 4 parsing failures >=10 in 1 hour. Phase 2 insider data may be incomplete. Check CloudWatch logs for failure reasons."
  treat_missing_data  = "notBreaching"

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}

# ============================================================
# 2. CloudWatch Metric Filters: Track Parsing Failure Patterns
# ============================================================
# Extract failure reasons from application logs to identify
# recurring parsing issues (e.g., HTML stripping, name extraction)

resource "aws_cloudwatch_log_group" "form4_parsing_logs" {
  name              = "/algo/form4-parsing"
  retention_in_days = 14

  tags = var.common_tags
}

# Filter: Track "insider_name_extraction_failed" pattern
resource "aws_cloudwatch_log_metric_filter" "form4_name_extraction_failures" {
  name           = "${var.project_name}-form4-name-extraction-failures"
  log_group_name = aws_cloudwatch_log_group.form4_parsing_logs.name
  pattern        = "[timestamp, level, ...] *insider_name_extraction_failed*"

  metric_transformation {
    name      = "NameExtractionFailure"
    namespace = "Algo/Form4Parsing"
    value     = "1"
    dimensions = {
      FailureType = "NameExtraction"
    }
  }
}

# Filter: Track "shares_owned_extraction_failed" pattern
resource "aws_cloudwatch_log_metric_filter" "form4_shares_extraction_failures" {
  name           = "${var.project_name}-form4-shares-extraction-failures"
  log_group_name = aws_cloudwatch_log_group.form4_parsing_logs.name
  pattern        = "[timestamp, level, ...] *shares_owned_extraction_failed*"

  metric_transformation {
    name      = "SharesExtractionFailure"
    namespace = "Algo/Form4Parsing"
    value     = "1"
    dimensions = {
      FailureType = "SharesExtraction"
    }
  }
}

# Filter: Track "ownership_pct_extraction_failed" pattern
resource "aws_cloudwatch_log_metric_filter" "form4_ownership_extraction_failures" {
  name           = "${var.project_name}-form4-ownership-extraction-failures"
  log_group_name = aws_cloudwatch_log_group.form4_parsing_logs.name
  pattern        = "[timestamp, level, ...] *ownership_pct_extraction_failed*"

  metric_transformation {
    name      = "OwnershipExtractionFailure"
    namespace = "Algo/Form4Parsing"
    value     = "1"
    dimensions = {
      FailureType = "OwnershipExtraction"
    }
  }
}

# ============================================================
# 3. CloudWatch Dashboard: Form 4 Parsing Health
# ============================================================
# Real-time view of Form 4 parsing success/failure rates
# Enables quick diagnosis of Phase 2 data quality issues

resource "aws_cloudwatch_dashboard" "form4_parsing_health" {
  dashboard_name = "${var.project_name}-form4-parsing-health-${var.environment}"

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
            ["Algo/Form4Parsing", "ParsingSuccess", { stat = "Sum" }],
            [".", "ParsingFailure", { stat = "Sum" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Form 4 Parsing Success/Failure (5-min windows)"
          yAxis  = { left = { min = 0 } }
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
            ["Algo/Form4Parsing", "NameExtractionFailure", { stat = "Sum" }],
            [".", "SharesExtractionFailure", { stat = "Sum" }],
            [".", "OwnershipExtractionFailure", { stat = "Sum" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Form 4 Parsing Failure Breakdown by Type"
          yAxis  = { left = { min = 0 } }
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 6
        width  = 24
        height = 8
        properties = {
          query  = "fields @timestamp, symbol, reason | filter @message like /Form4.*extraction_failed/ | stats count() as failure_count by reason | sort failure_count desc"
          region = var.aws_region
          title  = "Most Common Form 4 Parsing Failures (Last 24 hours)"
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 14
        width  = 24
        height = 6
        properties = {
          query  = "fields @timestamp, symbol, reason | filter @message like /parsing_succeeded/ | stats count() as success_count by symbol | sort success_count desc | limit 20"
          region = var.aws_region
          title  = "Top 20 Symbols: Successful Form 4 Parsing (Last 24 hours)"
        }
      }
    ]
  })
}

# ============================================================
# 4. Alarm: Low Form 4 Parsing Success Rate
# ============================================================
# If <10 successful parses per hour, insider data coverage is degraded
# Helps detect systemic issues vs. isolated symbol failures

resource "aws_cloudwatch_metric_alarm" "form4_parsing_success_rate_low" {
  alarm_name          = "${var.project_name}-form4-parsing-low-success-${var.environment}"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "ParsingSuccess"
  namespace           = "Algo/Form4Parsing"
  period              = "3600" # 1-hour window
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Form 4 parsing success rate <5/hour. Phase 2 insider loader may have broader coverage issues."
  treat_missing_data  = "notBreaching"

  alarm_actions = length(aws_sns_topic.loader_alerts) > 0 ? [aws_sns_topic.loader_alerts[0].arn] : []

  tags = var.common_tags
}
