# Session 199: Auto-kill Lambda for stuck ECS tasks
# Terminates tasks that are unhealthy/stuck for > 2 hours (prevents $45+/month cost waste)

# ============================================================
# IAM Role for Auto-Kill Lambda
# ============================================================

resource "aws_iam_role" "auto_kill_stuck_tasks" {
  name = "${var.project_name}-auto-kill-stuck-tasks-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.common_tags
}

# Allow Lambda to read logs
resource "aws_iam_role_policy_attachment" "auto_kill_logs" {
  role       = aws_iam_role.auto_kill_stuck_tasks.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow Lambda to stop ECS tasks
resource "aws_iam_role_policy" "auto_kill_ecs" {
  name = "${var.project_name}-auto-kill-ecs-policy"
  role = aws_iam_role.auto_kill_stuck_tasks.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListAndDescribeTasks"
        Effect = "Allow"
        Action = [
          "ecs:ListTasks",
          "ecs:DescribeTasks"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ecs:cluster" = var.cluster_arn
          }
        }
      },
      {
        Sid    = "StopTasks"
        Effect = "Allow"
        Action = [
          "ecs:StopTask"
        ]
        Resource = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task/${var.cluster_name}/*"
      }
    ]
  })
}

# Allow Lambda to publish alerts to SNS
resource "aws_iam_role_policy" "auto_kill_sns" {
  name = "${var.project_name}-auto-kill-sns-policy"
  role = aws_iam_role.auto_kill_stuck_tasks.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "PublishAlerts"
      Effect = "Allow"
      Action = [
        "sns:Publish"
      ]
      Resource = var.sns_alert_topic_arn != "" ? var.sns_alert_topic_arn : "*"
    }]
  })
}

# ============================================================
# Lambda Function: Auto-Kill Stuck Tasks
# ============================================================

resource "aws_lambda_function" "auto_kill_stuck_tasks" {
  filename      = data.archive_file.auto_kill_lambda_zip.output_path
  function_name = "${var.project_name}-auto-kill-stuck-tasks-${var.environment}"
  role          = aws_iam_role.auto_kill_stuck_tasks.arn
  handler       = "index.lambda_handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  environment {
    variables = {
      CLUSTER_NAME       = var.cluster_name
      SNS_ALERT_TOPIC    = var.sns_alert_topic_arn
      PROJECT_NAME       = var.project_name
      ENVIRONMENT        = var.environment
      UNHEALTHY_TIMEOUT  = "7200"  # 2 hours in seconds
      UNKNOWN_TIMEOUT    = "10800" # 3 hours in seconds
      HARD_LIMIT_TIMEOUT = "14400" # 4 hours in seconds
    }
  }

  tags = var.common_tags
}

# ============================================================
# CloudWatch Alarm: Trigger Lambda When Tasks Unhealthy
# ============================================================

resource "aws_cloudwatch_metric_alarm" "ecs_unhealthy_task_count" {
  alarm_name          = "${var.project_name}-ecs-unhealthy-tasks-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1  # Evaluate immediately
  metric_name         = "TaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 60
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "Alert when unhealthy ECS tasks detected"
  alarm_actions       = [aws_lambda_function.auto_kill_stuck_tasks.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName   = var.cluster_name
    HealthStatus  = "UNHEALTHY"
  }

  tags = var.common_tags
}

# Allow CloudWatch to invoke Lambda
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auto_kill_stuck_tasks.function_name
  principal     = "lambda.alarms.cloudwatch.amazonaws.com"
  source_arn    = aws_cloudwatch_metric_alarm.ecs_unhealthy_task_count.arn
}

# ============================================================
# EventBridge Schedule: Run Auto-Kill Every 6 Hours
# ============================================================

resource "aws_scheduler_schedule" "auto_kill_stuck_tasks" {
  name                = "${var.project_name}-auto-kill-stuck-tasks-${var.environment}"
  description         = "Auto-kill stuck ECS tasks every 6 hours (cost waste prevention)"
  schedule_expression = "rate(6 hours)"
  state               = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.auto_kill_stuck_tasks.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda.arn

    input = jsonencode({
      source = "EventBridge"
      reason = "Scheduled cost control check"
    })
  }

  tags = var.common_tags
}

# IAM role for EventBridge Scheduler to invoke Lambda
resource "aws_iam_role" "scheduler_invoke_lambda" {
  name = "${var.project_name}-scheduler-invoke-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  name = "${var.project_name}-scheduler-invoke-lambda-policy"
  role = aws_iam_role.scheduler_invoke_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "lambda:InvokeFunction"
      ]
      Resource = aws_lambda_function.auto_kill_stuck_tasks.arn
    }]
  })
}

# ============================================================
# Archive Lambda Code for Deployment
# ============================================================

data "archive_file" "auto_kill_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../../lambda/auto_kill_stuck_tasks/index.py"
  output_path = "${path.module}/../../lambda/auto_kill_stuck_tasks/lambda_function.zip"
}

# ============================================================
# CloudWatch Log Group for Lambda
# ============================================================

resource "aws_cloudwatch_log_group" "auto_kill_logs" {
  name              = "/aws/lambda/${var.project_name}-auto-kill-stuck-tasks-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = var.common_tags
}

# ============================================================
# Outputs
# ============================================================

output "auto_kill_lambda_arn" {
  value       = aws_lambda_function.auto_kill_stuck_tasks.arn
  description = "ARN of auto-kill Lambda function"
}

output "auto_kill_lambda_name" {
  value       = aws_lambda_function.auto_kill_stuck_tasks.function_name
  description = "Name of auto-kill Lambda function"
}
