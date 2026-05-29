# ============================================================
# CloudWatch Metric Alarms — Operational Hardening
# ============================================================

# ============================================================
# API Lambda Alarms
# ============================================================

# Alarm: API Lambda errors exceed threshold
resource "aws_cloudwatch_metric_alarm" "api_lambda_errors" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = var.api_lambda_errors_alarm_name
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "2"
  metric_name        = "Errors"
  namespace          = "AWS/Lambda"
  period             = "300"
  statistic          = "Sum"
  threshold          = "5"
  alarm_description  = "Triggers when API Lambda has 5+ errors in 5 minutes"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    FunctionName = var.api_lambda_name
  }

  tags = var.common_tags
}

# Alarm: API Lambda high concurrency
resource "aws_cloudwatch_metric_alarm" "api_lambda_concurrency" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-api-lambda-concurrency-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "2"
  metric_name        = "ConcurrentExecutions"
  namespace          = "AWS/Lambda"
  period             = "60"
  statistic          = "Maximum"
  threshold          = "40" # Alert if approaching 50 reserved concurrency
  alarm_description  = "Triggers when API Lambda concurrency exceeds 40 (max 50)"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    FunctionName = var.api_lambda_name
  }

  tags = var.common_tags
}

# Alarm: API Lambda timeout approaching
resource "aws_cloudwatch_metric_alarm" "api_lambda_duration" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-api-lambda-duration-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "3"
  metric_name        = "Duration"
  namespace          = "AWS/Lambda"
  period             = "300"
  statistic          = "Maximum"
  threshold          = "25000" # 25 seconds (Lambda timeout is ~30 seconds)
  alarm_description  = "Triggers when API Lambda max duration exceeds 25s (timeout is ~30s)"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    FunctionName = var.api_lambda_name
  }

  tags = var.common_tags
}

# ============================================================
# Algo/Orchestrator Lambda Alarms
# ============================================================

# Alarm: Algo Lambda errors
resource "aws_cloudwatch_metric_alarm" "algo_lambda_errors" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-algo-lambda-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "1"
  metric_name        = "Errors"
  namespace          = "AWS/Lambda"
  period             = "300"
  statistic          = "Sum"
  threshold          = "1"
  alarm_description  = "Triggers when Algo Lambda has execution errors"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    FunctionName = var.algo_lambda_name
  }

  tags = var.common_tags
}

# Alarm: Algo Lambda timeout (4 min = 240000 ms, alert at 3.5 min = 210000 ms)
resource "aws_cloudwatch_metric_alarm" "algo_lambda_duration_timeout" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-algo-lambda-timeout-approaching-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "1"
  metric_name        = "Duration"
  namespace          = "AWS/Lambda"
  period             = "300"
  statistic          = "Maximum"
  threshold          = "210000" # 3.5 minutes (timeout is 4 min)
  alarm_description  = "Triggers when Algo Lambda max duration exceeds 3.5 min (timeout is 4 min)"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    FunctionName = var.algo_lambda_name
  }

  tags = var.common_tags
}

# ============================================================
# API Gateway Alarms
# ============================================================

# Alarm: API Gateway 5xx errors
resource "aws_cloudwatch_metric_alarm" "apigw_5xx_errors" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = var.apigw_5xx_alarm_name
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "2"
  metric_name        = "5XXError"
  namespace          = "AWS/ApiGateway"
  period             = "300"
  statistic          = "Sum"
  threshold          = "5"
  alarm_description  = "Triggers when API Gateway has 5+ 5xx errors in 5 minutes"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    ApiName = var.api_gateway_name
  }

  tags = var.common_tags
}

# Alarm: API Gateway 4xx errors (client errors - high frequency indicates bad requests)
resource "aws_cloudwatch_metric_alarm" "apigw_4xx_errors_high" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-api-4xx-errors-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "2"
  metric_name        = "4XXError"
  namespace          = "AWS/ApiGateway"
  period             = "300"
  statistic          = "Sum"
  threshold          = "20"
  alarm_description  = "Triggers when API Gateway has 20+ 4xx errors in 5 minutes (may indicate client issue)"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    ApiName = var.api_gateway_name
  }

  tags = var.common_tags
}

# Alarm: API Gateway high latency
resource "aws_cloudwatch_metric_alarm" "apigw_latency_high" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-api-latency-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "3"
  metric_name        = "Latency"
  namespace          = "AWS/ApiGateway"
  period             = "60"
  statistic          = "Average"
  threshold          = "2000" # 2 seconds
  alarm_description  = "Triggers when API Gateway avg latency exceeds 2 seconds"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    ApiName = var.api_gateway_name
  }

  tags = var.common_tags
}

# ============================================================
# Database (RDS) Alarms
# ============================================================

# Alarm: RDS high CPU utilization
resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-rds-cpu-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "2"
  metric_name        = "CPUUtilization"
  namespace          = "AWS/RDS"
  period             = "300"
  statistic          = "Average"
  threshold          = "80"
  alarm_description  = "Triggers when RDS CPU utilization exceeds 80%"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    DBInstanceIdentifier = var.rds_identifier
  }

  tags = var.common_tags
}

# Alarm: RDS high number of connections
resource "aws_cloudwatch_metric_alarm" "rds_connections_high" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-rds-connections-high-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "2"
  metric_name        = "DatabaseConnections"
  namespace          = "AWS/RDS"
  period             = "300"
  statistic          = "Average"
  threshold          = "80" # Alert if approaching typical max connections
  alarm_description  = "Triggers when RDS avg connections exceed 80 (may indicate pool exhaustion)"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    DBInstanceIdentifier = var.rds_identifier
  }

  tags = var.common_tags
}

# Alarm: RDS low free storage
resource "aws_cloudwatch_metric_alarm" "rds_storage_low" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-rds-storage-low-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods = "1"
  metric_name        = "FreeStorageSpace"
  namespace          = "AWS/RDS"
  period             = "300"
  statistic          = "Average"
  threshold          = "10737418240" # 10 GB in bytes
  alarm_description  = "Triggers when RDS free storage drops below 10 GB"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    DBInstanceIdentifier = var.rds_identifier
  }

  tags = var.common_tags
}

# Alarm: RDS low free memory
resource "aws_cloudwatch_metric_alarm" "rds_memory_low" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-rds-memory-low-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods = "2"
  metric_name        = "FreeableMemory"
  namespace          = "AWS/RDS"
  period             = "300"
  statistic          = "Average"
  threshold          = "268435456" # 256 MB in bytes
  alarm_description  = "Triggers when RDS free memory drops below 256 MB"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = {
    DBInstanceIdentifier = var.rds_identifier
  }

  tags = var.common_tags
}

# ============================================================
# Data Loading (Loader) Alarms
# ============================================================

# Alarm: Critical loader failures (stock_prices_daily, stock_symbols)
resource "aws_cloudwatch_metric_alarm" "critical_loader_failures" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-critical-loader-failures-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "1"
  metric_name        = "LoaderFailure"
  namespace          = "Algo/DataLoading"
  period             = "300"
  statistic          = "Sum"
  threshold          = "1"
  alarm_description  = "Triggers when a critical loader (stock_prices or symbols) fails"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = [
    {
      name  = "LoaderName"
      value = "stock_prices_daily"
    }
  ]

  tags = var.common_tags
}

# Alarm: Stock symbols loader failure
resource "aws_cloudwatch_metric_alarm" "stock_symbols_loader_failure" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-stock-symbols-loader-failure-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "1"
  metric_name        = "LoaderFailure"
  namespace          = "Algo/DataLoading"
  period             = "300"
  statistic          = "Sum"
  threshold          = "1"
  alarm_description  = "Triggers when stock_symbols loader fails"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = [
    {
      name  = "LoaderName"
      value = "stock_symbols"
    }
  ]

  tags = var.common_tags
}

# Alarm: Market health loader failure
resource "aws_cloudwatch_metric_alarm" "market_health_loader_failure" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-market-health-loader-failure-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "1"
  metric_name        = "LoaderFailure"
  namespace          = "Algo/DataLoading"
  period             = "300"
  statistic          = "Sum"
  threshold          = "1"
  alarm_description  = "Triggers when market_health_daily loader fails"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = [
    {
      name  = "LoaderName"
      value = "market_health_daily"
    }
  ]

  tags = var.common_tags
}

# Alarm: Technical data loader failure
resource "aws_cloudwatch_metric_alarm" "technical_data_loader_failure" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-technical-data-loader-failure-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods = "1"
  metric_name        = "LoaderFailure"
  namespace          = "Algo/DataLoading"
  period             = "300"
  statistic          = "Sum"
  threshold          = "1"
  alarm_description  = "Triggers when technical_data_daily loader fails"
  treat_missing_data = "notBreaching"
  alarm_actions      = var.sns_alerts_enabled ? [var.sns_alerts_topic_arn] : []

  dimensions = [
    {
      name  = "LoaderName"
      value = "technical_data_daily"
    }
  ]

  tags = var.common_tags
}

# ============================================================
# Composite Alarms (using metric alarms above)
# ============================================================

# Composite alarm: System Health (any critical component failing)
resource "aws_cloudwatch_composite_alarm" "system_health_critical" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-system-health-critical-${var.environment}"
  alarm_description = "Composite: API failing OR Algo Lambda errors OR critical loaders failing"
  actions_enabled   = true
  alarm_actions     = [var.sns_alerts_topic_arn]

  alarm_rule = join(" OR ", [
    "ALARM(\"${aws_cloudwatch_metric_alarm.api_lambda_errors[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.algo_lambda_errors[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.apigw_5xx_errors[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.critical_loader_failures[0].alarm_name}\")",
  ])

  tags = var.common_tags
}

# Composite alarm: Data Loading Issues
resource "aws_cloudwatch_composite_alarm" "data_loading_issues" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-data-loading-issues-${var.environment}"
  alarm_description = "Composite: Any critical loader failing"
  actions_enabled   = true
  alarm_actions     = [var.sns_alerts_topic_arn]

  alarm_rule = join(" OR ", [
    "ALARM(\"${aws_cloudwatch_metric_alarm.stock_symbols_loader_failure[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.market_health_loader_failure[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.technical_data_loader_failure[0].alarm_name}\")",
  ])

  tags = var.common_tags
}

# Composite alarm: Database Health
resource "aws_cloudwatch_composite_alarm" "database_health_critical" {
  count             = var.sns_alerts_enabled ? 1 : 0
  alarm_name        = "${var.project_name}-database-health-critical-${var.environment}"
  alarm_description = "Composite: RDS CPU high OR connections high OR storage low OR memory low"
  actions_enabled   = true
  alarm_actions     = [var.sns_alerts_topic_arn]

  alarm_rule = join(" OR ", [
    "ALARM(\"${aws_cloudwatch_metric_alarm.rds_cpu_high[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.rds_connections_high[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.rds_storage_low[0].alarm_name}\")",
    "ALARM(\"${aws_cloudwatch_metric_alarm.rds_memory_low[0].alarm_name}\")",
  ])

  tags = var.common_tags
}
