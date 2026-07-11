# ============================================================
# Cost Circuit Breaker Lambda + EventBridge Scheduler
# Safety mechanism to prevent runaway AWS costs
# ============================================================

# ============================================================
# 1. IAM Role for Cost Circuit Breaker Lambda
# ============================================================

resource "aws_iam_role" "cost_circuit_breaker" {
  name = "${var.project_name}-cost-circuit-breaker-${var.environment}"
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

# Basic Lambda execution role (logs)
resource "aws_iam_role_policy_attachment" "cost_circuit_breaker_logs" {
  role       = aws_iam_role.cost_circuit_breaker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Cost Explorer API access
resource "aws_iam_role_policy" "cost_circuit_breaker_cost_explorer" {
  name = "${var.project_name}-cost-circuit-breaker-cost-explorer-${var.environment}"
  role = aws_iam_role.cost_circuit_breaker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
        ]
        Resource = "*"
      }
    ]
  })
}

# EventBridge Scheduler control (disable/enable schedules)
resource "aws_iam_role_policy" "cost_circuit_breaker_scheduler" {
  name = "${var.project_name}-cost-circuit-breaker-scheduler-${var.environment}"
  role = aws_iam_role.cost_circuit_breaker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "scheduler:ListSchedules",
          "scheduler:UpdateSchedule",
        ]
        Resource = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
      }
    ]
  })
}

# ECS task suspension (stop running loaders)
resource "aws_iam_role_policy" "cost_circuit_breaker_ecs" {
  name = "${var.project_name}-cost-circuit-breaker-ecs-${var.environment}"
  role = aws_iam_role.cost_circuit_breaker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:ListTasks",
          "ecs:StopTask",
        ]
        Resource = "*"
      }
    ]
  })
}

# SES email (send cost alerts)
resource "aws_iam_role_policy" "cost_circuit_breaker_ses" {
  name = "${var.project_name}-cost-circuit-breaker-ses-${var.environment}"
  role = aws_iam_role.cost_circuit_breaker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
        ]
        Resource = "*"
      }
    ]
  })
}

# CloudWatch metrics (publish cost data)
resource "aws_iam_role_policy" "cost_circuit_breaker_cloudwatch" {
  name = "${var.project_name}-cost-circuit-breaker-cloudwatch-${var.environment}"
  role = aws_iam_role.cost_circuit_breaker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# 2. CloudWatch Log Group
# ============================================================

resource "aws_cloudwatch_log_group" "cost_circuit_breaker" {
  name              = "/aws/lambda/${var.project_name}-cost-circuit-breaker-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cost-circuit-breaker-logs"
  })
}

# ============================================================
# 3. Cost Circuit Breaker Lambda Function
# ============================================================

resource "aws_lambda_function" "cost_circuit_breaker" {
  filename         = "${path.root}/lambda/cost_circuit_breaker.zip"
  function_name    = "${var.project_name}-cost-circuit-breaker-${var.environment}"
  role             = aws_iam_role.cost_circuit_breaker.arn
  handler          = "index.lambda_handler"
  timeout          = 60
  memory_size      = 256
  runtime          = "python3.11"
  source_code_hash = fileexists("${path.root}/lambda/cost_circuit_breaker.zip") ? filebase64sha256("${path.root}/lambda/cost_circuit_breaker.zip") : ""

  environment {
    variables = {
      PROJECT_NAME                = var.project_name
      ENVIRONMENT                 = var.environment
      ALERT_EMAIL_TO              = var.alert_email_address
      ALERT_EMAIL_FROM            = "noreply@${var.project_name}.local"
      DAILY_COST_THRESHOLD_USD    = var.cost_threshold_daily_usd
      ECS_CLUSTER_NAME            = "${var.project_name}-${var.environment}"
      LOG_LEVEL                   = "INFO"
    }
  }

  depends_on = [
    aws_iam_role_policy.cost_circuit_breaker_cost_explorer,
    aws_iam_role_policy.cost_circuit_breaker_scheduler,
    aws_iam_role_policy.cost_circuit_breaker_ecs,
    aws_iam_role_policy.cost_circuit_breaker_ses,
    aws_iam_role_policy.cost_circuit_breaker_cloudwatch,
    aws_cloudwatch_log_group.cost_circuit_breaker,
  ]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cost-circuit-breaker"
  })
}

# ============================================================
# 4. EventBridge Scheduler Permission
# ============================================================

resource "aws_lambda_permission" "cost_circuit_breaker_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_circuit_breaker.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
}

# ============================================================
# 5. EventBridge Scheduler: Every 6 hours (4 AM, 10 AM, 4 PM, 10 PM UTC)
# Runs 4 times per day to catch cost spikes early
# ============================================================

resource "aws_scheduler_schedule" "cost_circuit_breaker_4am" {
  count                        = var.eventbridge_scheduler_role_arn != "" ? 1 : 0
  name                         = "${var.project_name}-cost-breaker-4am-${var.environment}"
  description                  = "Cost circuit breaker check: 4 AM UTC (overnight)"
  schedule_expression          = "cron(0 4 * * ? *)"
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.cost_circuit_breaker.arn
    role_arn = var.eventbridge_scheduler_role_arn
  }

  depends_on = [aws_lambda_permission.cost_circuit_breaker_scheduler]
}

resource "aws_scheduler_schedule" "cost_circuit_breaker_10am" {
  count                        = var.eventbridge_scheduler_role_arn != "" ? 1 : 0
  name                         = "${var.project_name}-cost-breaker-10am-${var.environment}"
  description                  = "Cost circuit breaker check: 10 AM UTC"
  schedule_expression          = "cron(0 10 * * ? *)"
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.cost_circuit_breaker.arn
    role_arn = var.eventbridge_scheduler_role_arn
  }

  depends_on = [aws_lambda_permission.cost_circuit_breaker_scheduler]
}

resource "aws_scheduler_schedule" "cost_circuit_breaker_4pm" {
  count                        = var.eventbridge_scheduler_role_arn != "" ? 1 : 0
  name                         = "${var.project_name}-cost-breaker-4pm-${var.environment}"
  description                  = "Cost circuit breaker check: 4 PM UTC"
  schedule_expression          = "cron(0 16 * * ? *)"
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.cost_circuit_breaker.arn
    role_arn = var.eventbridge_scheduler_role_arn
  }

  depends_on = [aws_lambda_permission.cost_circuit_breaker_scheduler]
}

resource "aws_scheduler_schedule" "cost_circuit_breaker_10pm" {
  count                        = var.eventbridge_scheduler_role_arn != "" ? 1 : 0
  name                         = "${var.project_name}-cost-breaker-10pm-${var.environment}"
  description                  = "Cost circuit breaker check: 10 PM UTC"
  schedule_expression          = "cron(0 22 * * ? *)"
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.cost_circuit_breaker.arn
    role_arn = var.eventbridge_scheduler_role_arn
  }

  depends_on = [aws_lambda_permission.cost_circuit_breaker_scheduler]
}

# ============================================================
# 6. CloudWatch Alarms for Cost Circuit Breaker Lambda
# ============================================================

resource "aws_cloudwatch_metric_alarm" "cost_circuit_breaker_errors" {
  alarm_name          = "${var.project_name}-cost-circuit-breaker-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "CRITICAL: Cost circuit breaker Lambda failed"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.cost_circuit_breaker.function_name
  }

  alarm_actions = var.sns_alerts_topic_arn != "" ? [var.sns_alerts_topic_arn] : []

  tags = var.common_tags
}

# ============================================================
# 7. CloudWatch Dashboard Widget for Cost Monitoring
# ============================================================

resource "aws_cloudwatch_log_group" "cost_monitoring" {
  name              = "/aws/costmonitoring/${var.project_name}-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cost-monitoring-logs"
  })
}
