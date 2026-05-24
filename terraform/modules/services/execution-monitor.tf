/**
 * Execution Monitor Lambda
 * Queries RDS for signals and Alpaca for trades to verify end-to-end execution
 * Can be triggered manually or via EventBridge
 */

# ============================================================
# Lambda Function
# ============================================================

resource "aws_lambda_function" "execution_monitor" {
  count            = var.enable_execution_monitor ? 1 : 0
  filename         = data.archive_file.execution_monitor_zip[0].output_path
  function_name    = "${var.project_name}-execution-monitor-${var.environment}"
  role             = aws_iam_role.execution_monitor[0].arn
  handler          = "index.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  source_code_hash = data.archive_file.execution_monitor_zip[0].output_base64sha256
  layers           = [var.psycopg2_layer_arn]

  environment {
    variables = {
      ALPACA_API_KEY     = var.alpaca_api_key_id
      ALPACA_SECRET_KEY  = var.alpaca_api_secret_key
      RDS_HOST          = var.rds_endpoint
      RDS_PORT          = var.rds_port
      RDS_USER          = var.rds_master_username
      RDS_DATABASE      = var.rds_database_name
    }
  }

  vpc_config {
    subnet_ids         = var.rds_subnet_ids
    security_group_ids = [var.rds_security_group_id]
  }

  depends_on = [
    aws_iam_role_policy.execution_monitor_secrets[0]
  ]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-execution-monitor"
  })
}

# ============================================================
# IAM Role & Policies
# ============================================================

resource "aws_iam_role" "execution_monitor" {
  count = var.enable_execution_monitor ? 1 : 0
  name  = "${var.project_name}-execution-monitor-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "execution_monitor_basic" {
  count      = var.enable_execution_monitor ? 1 : 0
  role       = aws_iam_role.execution_monitor[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "execution_monitor_secrets" {
  count  = var.enable_execution_monitor ? 1 : 0
  name   = "${var.project_name}-execution-monitor-secrets"
  role   = aws_iam_role.execution_monitor[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# Lambda Package
# ============================================================

data "archive_file" "execution_monitor_zip" {
  count       = var.enable_execution_monitor ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/../../../lambda/execution-monitor/index.py"
  output_path = "${path.module}/../../../build/execution-monitor.zip"
}

# ============================================================
# CloudWatch Log Group
# ============================================================

resource "aws_cloudwatch_log_group" "execution_monitor" {
  count             = var.enable_execution_monitor ? 1 : 0
  name              = "/aws/lambda/${aws_lambda_function.execution_monitor[0].function_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = var.common_tags
}

# ============================================================
# EventBridge Trigger (Hourly during trading hours)
# ============================================================

resource "aws_scheduler_schedule" "execution_monitor" {
  count                        = var.enable_execution_monitor && var.enable_execution_monitor_schedule ? 1 : 0
  name                         = "${var.project_name}-execution-monitor-${var.environment}"
  description                  = "Check algo execution: signals in RDS + trades in Alpaca"
  schedule_expression          = "cron(0 10-21/2 ? * MON-FRI *)" # Every 2 hours, 10 AM-9 PM ET
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.execution_monitor[0].arn
    role_arn = var.eventbridge_scheduler_role_arn
  }

  depends_on = [
    aws_lambda_permission.execution_monitor_scheduler[0]
  ]
}

# ============================================================
# Lambda Permissions
# ============================================================

resource "aws_lambda_permission" "execution_monitor_scheduler" {
  count             = var.enable_execution_monitor ? 1 : 0
  statement_id      = "AllowExecutionMonitorScheduler"
  action            = "lambda:InvokeFunction"
  function_name     = aws_lambda_function.execution_monitor[0].function_name
  principal         = "scheduler.amazonaws.com"
  source_arn        = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
}

# ============================================================
# Outputs
# ============================================================

output "execution_monitor_arn" {
  value       = try(aws_lambda_function.execution_monitor[0].arn, null)
  description = "ARN of the execution monitor Lambda function"
}

output "execution_monitor_name" {
  value       = try(aws_lambda_function.execution_monitor[0].function_name, null)
  description = "Name of the execution monitor Lambda function"
}
