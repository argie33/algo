# ============================================================
# Circuit Breaker Lambda + EventBridge Schedules
# F-02: Intraday portfolio variance protection
# ============================================================

# ============================================================
# 0. SNS Topic for Circuit Breaker Alerts
# ============================================================

resource "aws_sns_topic" "circuit_breaker_alerts" {
  name              = "${var.project_name}-circuit-breaker-alerts-${var.environment}"
  kms_master_key_id = "alias/aws/sns"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-circuit-breaker-alerts"
  })
}

resource "aws_sns_topic_subscription" "circuit_breaker_email" {
  count     = var.alert_email_address != "" ? 1 : 0
  topic_arn = aws_sns_topic.circuit_breaker_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email_address

  lifecycle {
    ignore_changes = [endpoint_auto_confirms]
  }
}

# ============================================================
# 1. IAM Role for Circuit Breaker Lambda
# ============================================================

resource "aws_iam_role" "circuit_breaker" {
  name = "${var.project_name}-circuit-breaker-${var.environment}"
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

resource "aws_iam_role_policy_attachment" "circuit_breaker_logs" {
  role       = aws_iam_role.circuit_breaker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "circuit_breaker_policy" {
  name = "${var.project_name}-circuit-breaker-policy-${var.environment}"
  role = aws_iam_role.circuit_breaker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:UpdateSecret",
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:algo/orchestrator-*",
          "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:algo/database-*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["rds-db:connect"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/algo_orchestrator_state"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# 2. CloudWatch Log Group for Circuit Breaker Lambda
# ============================================================

resource "aws_cloudwatch_log_group" "circuit_breaker" {
  name              = "/aws/lambda/${var.project_name}-circuit-breaker-${var.environment}"
  retention_in_days = 30

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-circuit-breaker-logs"
  })
}

# ============================================================
# 3. Circuit Breaker Lambda Function
# ============================================================

resource "aws_lambda_function" "circuit_breaker" {
  filename      = "${path.root}/lambda/circuit_breaker.zip"
  function_name = "${var.project_name}-circuit-breaker-${var.environment}"
  role          = aws_iam_role.circuit_breaker.arn
  handler       = "lambda_function.lambda_handler"
  timeout       = 60
  memory_size   = 512
  runtime       = "python3.12"
  source_code_hash = filebase64sha256("${path.root}/lambda/circuit_breaker.zip")

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.rds_security_group_id]
  }

  environment {
    variables = {
      ENVIRONMENT = var.environment
      LOG_LEVEL   = "INFO"
    }
  }

  layers = compact([var.python_dependencies_layer_arn])

  depends_on = [
    aws_iam_role_policy.circuit_breaker_policy,
    aws_cloudwatch_log_group.circuit_breaker,
  ]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-circuit-breaker"
  })
}

# ============================================================
# 4. EventBridge Scheduler permission for Lambda
# ============================================================

resource "aws_lambda_permission" "circuit_breaker_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.circuit_breaker.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
}

# ============================================================
# 5. EventBridge Scheduler: 10 AM ET (mid-morning check)
# Uses America/New_York timezone — auto-handles EDT/EST.
# ============================================================

resource "aws_scheduler_schedule" "circuit_breaker_10am" {
  count                        = var.eventbridge_scheduler_role_arn != "" ? 1 : 0
  name                         = "${var.project_name}-circuit-breaker-10am-${var.environment}"
  description                  = "Mid-morning portfolio variance check: halt trading if drawdown > 15%"
  schedule_expression          = "cron(0 10 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.circuit_breaker.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source     = "eventbridge-scheduler"
      check_time = "10am"
    })
  }

  depends_on = [aws_lambda_permission.circuit_breaker_scheduler]
}

resource "aws_scheduler_schedule" "circuit_breaker_12pm" {
  count                        = var.eventbridge_scheduler_role_arn != "" ? 1 : 0
  name                         = "${var.project_name}-circuit-breaker-12pm-${var.environment}"
  description                  = "Midday portfolio variance check: halt trading if drawdown > 15%"
  schedule_expression          = "cron(0 12 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.circuit_breaker.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source     = "eventbridge-scheduler"
      check_time = "12pm"
    })
  }

  depends_on = [aws_lambda_permission.circuit_breaker_scheduler]
}

# ============================================================
# 6. CloudWatch Alarms for Circuit Breaker Lambda health
# ============================================================

resource "aws_cloudwatch_metric_alarm" "circuit_breaker_errors" {
  alarm_name          = "${var.project_name}-circuit-breaker-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "CRITICAL: Circuit breaker Lambda failed — intraday halt protection is degraded"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.circuit_breaker.function_name
  }

  alarm_actions = [aws_sns_topic.circuit_breaker_alerts.arn]

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "circuit_breaker_duration" {
  alarm_name          = "${var.project_name}-circuit-breaker-duration-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Maximum"
  threshold           = 30000
  alarm_description   = "Circuit breaker check took > 30 seconds — possible DB connection issue"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.circuit_breaker.function_name
  }

  alarm_actions = [aws_sns_topic.circuit_breaker_alerts.arn]

  tags = var.common_tags
}
