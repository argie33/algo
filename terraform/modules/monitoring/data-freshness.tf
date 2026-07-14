# ============================================================
# Data Freshness Monitoring Lambda + CloudWatch Alarms
# Issue 2.2: CloudWatch Alarms for Data Freshness
# ============================================================

# ============================================================
# 1. IAM Role for Data Freshness Monitor Lambda
# ============================================================

resource "aws_iam_role" "data_freshness_monitor" {
  name = "${var.project_name}-data-freshness-monitor-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = var.common_tags
}

# Basic execution policy (logs)
resource "aws_iam_role_policy_attachment" "data_freshness_logs" {
  role       = aws_iam_role.data_freshness_monitor.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for CloudWatch metrics and RDS access
resource "aws_iam_role_policy" "data_freshness_metrics" {
  name = "${var.project_name}-data-freshness-metrics-${var.environment}"
  role = aws_iam_role.data_freshness_monitor.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds-db:connect",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-db-credentials-*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/algo_orchestrator_state"
      }
    ]
  })
}

# ============================================================
# 2. Data Freshness Monitor Lambda Function
# ============================================================

locals {
  data_freshness_monitor_zip_path   = "${path.module}/../../lambda/data-freshness-monitor/lambda_function.zip"
  data_freshness_monitor_zip_exists = fileexists(local.data_freshness_monitor_zip_path)
}

resource "aws_lambda_function" "data_freshness_monitor" {
  filename         = local.data_freshness_monitor_zip_path
  source_code_hash = local.data_freshness_monitor_zip_exists ? filebase64sha256(local.data_freshness_monitor_zip_path) : null
  function_name    = "${var.project_name}-data-freshness-monitor-${var.environment}"
  role             = aws_iam_role.data_freshness_monitor.arn
  handler          = "lambda_function.lambda_handler"
  timeout          = 60
  memory_size      = 256
  runtime          = "python3.12"

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.rds_security_group_id]
  }

  environment {
    variables = {
      DB_HOST             = var.db_host
      DB_USER             = var.db_user
      DB_NAME             = var.db_name
      DB_PORT             = var.db_port
      DATABASE_SECRET_ARN = var.database_secret_arn
      DB_SSL              = var.db_ssl_mode
    }
  }

  layers = compact([var.python_dependencies_layer_arn])

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-data-freshness-monitor"
  })

  depends_on = [
    aws_iam_role_policy.data_freshness_metrics,
    aws_iam_role_policy_attachment.data_freshness_logs,
  ]
}

# ============================================================
# 3. EventBridge Schedule to Run Monitor Every 6 Hours
# ============================================================

resource "aws_cloudwatch_event_rule" "data_freshness_schedule" {
  count               = var.enable_data_freshness_monitoring && var.enable_data_quality_monitors ? 1 : 0
  name                = "${var.project_name}-data-freshness-monitor-${var.environment}"
  description         = "Trigger data freshness check hourly during pre-market (2 AM - 10 AM ET Mon-Fri)"
  schedule_expression = "cron(0 2-10 ? * MON-FRI *)"
  state               = "ENABLED"

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "data_freshness_lambda" {
  count     = var.enable_data_freshness_monitoring && var.enable_data_quality_monitors ? 1 : 0
  rule      = aws_cloudwatch_event_rule.data_freshness_schedule[0].name
  target_id = "DataFreshnessLambda"
  arn       = aws_lambda_function.data_freshness_monitor.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  count         = var.enable_data_freshness_monitoring && var.enable_data_quality_monitors ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_freshness_monitor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.data_freshness_schedule[0].arn
}

# ============================================================
# 4. CloudWatch Alarms for Critical Tables
# ============================================================

# Template for individual table alarms
locals {
  critical_tables = [
    "stock_symbols",
    "price_daily",
    "buy_sell_daily",
    "stock_scores",
    "economic_data",
    "fear_greed_index",
    "market_health_daily",
  ]
}

# CRITICAL: Table is empty (0 rows) — prod only
resource "aws_cloudwatch_metric_alarm" "data_empty" {
  for_each = var.enable_data_quality_monitors ? toset(local.critical_tables) : toset([])

  alarm_name          = "${var.project_name}-data-${each.value}-empty-${var.environment}"
  alarm_description   = "CRITICAL: ${each.value} table has 0 rows (data loading failed)"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "DataLoader_${each.value}_RowCount"
  namespace           = "AlgoDataFreshness"
  period              = 300
  statistic           = "Average"
  threshold           = 0
  alarm_actions       = var.sns_alerts_enabled && var.sns_alerts_topic_arn != "" ? [var.sns_alerts_topic_arn] : []
  treat_missing_data  = "breaching"

  tags = merge(var.common_tags, {
    Severity = "CRITICAL"
    Table    = each.value
  })
}

# WARNING: Table is stale (>3 days) — prod only
resource "aws_cloudwatch_metric_alarm" "data_stale_warning" {
  for_each = var.enable_resource_alarms ? toset(local.critical_tables) : toset([])

  alarm_name          = "${var.project_name}-data-${each.value}-stale-warning-${var.environment}"
  alarm_description   = "WARNING: ${each.value} data is >3 days old (needs investigation)"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "DataLoader_${each.value}_AgeDays"
  namespace           = "AlgoDataFreshness"
  period              = 300
  statistic           = "Average"
  threshold           = 3
  alarm_actions       = var.sns_alerts_enabled && var.sns_alerts_topic_arn != "" ? [var.sns_alerts_topic_arn] : []
  treat_missing_data  = "notBreaching"

  tags = merge(var.common_tags, {
    Severity = "WARNING"
    Table    = each.value
  })
}

# CRITICAL: Table is very stale (>7 days) — prod only
resource "aws_cloudwatch_metric_alarm" "data_stale_critical" {
  for_each = var.enable_data_quality_monitors ? toset(local.critical_tables) : toset([])

  alarm_name          = "${var.project_name}-data-${each.value}-stale-critical-${var.environment}"
  alarm_description   = "CRITICAL: ${each.value} data is >7 days old (loader likely broken)"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "DataLoader_${each.value}_AgeDays"
  namespace           = "AlgoDataFreshness"
  period              = 300
  statistic           = "Average"
  threshold           = 7
  alarm_actions       = var.sns_alerts_enabled && var.sns_alerts_topic_arn != "" ? [var.sns_alerts_topic_arn] : []
  treat_missing_data  = "breaching"

  tags = merge(var.common_tags, {
    Severity = "CRITICAL"
    Table    = each.value
  })
}

# ============================================================
# 5. Composite Alarm: Data Freshness Overall Health — prod only
# ============================================================

resource "aws_cloudwatch_composite_alarm" "data_freshness_unhealthy" {
  count             = var.sns_alerts_enabled && var.enable_data_quality_monitors ? 1 : 0
  alarm_name        = "${var.project_name}-data-freshness-unhealthy-${var.environment}"
  alarm_description = "Composite: Data freshness critical (empty or >7 days stale)"
  actions_enabled   = true
  alarm_actions     = var.sns_alerts_topic_arn != "" ? [var.sns_alerts_topic_arn] : []

  # Combine all CRITICAL empty + very_stale alarms (exclude warning alarms which are prod-only)
  alarm_rule = join(" OR ", concat(
    [for table in local.critical_tables : "ALARM(\"${var.project_name}-data-${table}-empty-${var.environment}\")"],
    [for table in local.critical_tables : "ALARM(\"${var.project_name}-data-${table}-stale-critical-${var.environment}\")"]
  ))

  tags = merge(var.common_tags, {
    Name     = "Data Freshness Health"
    Severity = "CRITICAL"
  })

  depends_on = [
    aws_cloudwatch_metric_alarm.data_empty,
    aws_cloudwatch_metric_alarm.data_stale_critical
  ]
}
