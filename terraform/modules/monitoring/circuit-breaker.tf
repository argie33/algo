# ============================================================
# Circuit Breaker Lambda + CloudWatch Alarms
# F-02: Intraday portfolio variance protection
# ============================================================

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

# Basic execution policy (logs)
resource "aws_iam_role_policy_attachment" "circuit_breaker_logs" {
  role       = aws_iam_role.circuit_breaker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for Secrets Manager and RDS access
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
        Action = [
          "rds-db:connect",
        ]
        Resource = "*"
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
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-circuit-breaker-logs"
  })
}

# ============================================================
# 3. Circuit Breaker Lambda Function
# ============================================================

resource "aws_lambda_function" "circuit_breaker" {
  filename      = "${path.module}/../../lambda/circuit-breaker/index.zip"
  function_name = "${var.project_name}-circuit-breaker-${var.environment}"
  role          = aws_iam_role.circuit_breaker.arn
  handler       = "index.lambda_handler"
  timeout       = 60
  memory_size   = 512
  runtime       = "python3.12"

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

  depends_on = [aws_iam_role_policy.circuit_breaker_policy]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-circuit-breaker"
  })
}

# ============================================================
# 4. CloudWatch Alarms - Trigger Circuit Breaker
# ============================================================

# EventBridge rule to trigger circuit breaker at 10 AM ET and 12 PM ET
resource "aws_cloudwatch_event_rule" "circuit_breaker_schedule" {
  name                = "${var.project_name}-circuit-breaker-schedule-${var.environment}"
  description         = "Trigger circuit breaker check at 10 AM and 12 PM ET on trading days"
  schedule_expression = "cron(0 14,16 ? * MON-FRI *)"  # 10 AM and 12 PM ET in UTC (14:00, 16:00)

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "circuit_breaker_lambda" {
  rule      = aws_cloudwatch_event_rule.circuit_breaker_schedule.name
  target_id = "CircuitBreakerLambda"
  arn       = aws_lambda_function.circuit_breaker.arn
}

# Grant EventBridge permission to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_circuit_breaker" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.circuit_breaker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.circuit_breaker_schedule.arn
}

# ============================================================
# 5. SNS Topic for Circuit Breaker Alerts
# ============================================================

resource "aws_sns_topic" "circuit_breaker_alerts" {
  name              = "${var.project_name}-circuit-breaker-alerts-${var.environment}"
  display_name      = "Circuit Breaker Alerts"
  kms_master_key_id = "alias/aws/sns"

  tags = var.common_tags
}

# CloudWatch Alarm: Monitor Lambda errors
resource "aws_cloudwatch_metric_alarm" "circuit_breaker_errors" {
  alarm_name          = "${var.project_name}-circuit-breaker-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "Alert when circuit breaker Lambda encounters errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.circuit_breaker.function_name
  }

  alarm_actions = [aws_sns_topic.circuit_breaker_alerts.arn]

  tags = var.common_tags
}

# CloudWatch Alarm: Monitor Lambda duration (should be < 30s)
resource "aws_cloudwatch_metric_alarm" "circuit_breaker_duration" {
  alarm_name          = "${var.project_name}-circuit-breaker-duration-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "30000"  # 30 seconds in milliseconds
  alarm_description   = "Alert if circuit breaker check takes > 30 seconds"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.circuit_breaker.function_name
  }

  alarm_actions = [aws_sns_topic.circuit_breaker_alerts.arn]

  tags = var.common_tags
}
