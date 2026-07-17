# Cost control automation: auto-stop UNHEALTHY ECS tasks to prevent money waste

resource "aws_lambda_function" "auto_stop_unhealthy_tasks" {
  filename         = "lambda_cost_control.zip"
  function_name    = "${var.project_name}-auto-stop-unhealthy-tasks-${var.environment}"
  role             = aws_iam_role.auto_stop_lambda.arn
  handler          = "auto_stop_unhealthy_tasks.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256
  source_code_hash = filebase64sha256("lambda_cost_control.zip")

  environment {
    variables = {
      CLUSTER_NAME = var.ecs_cluster_name
    }
  }

  tags = var.common_tags
}

resource "aws_iam_role" "auto_stop_lambda" {
  name = "${var.project_name}-auto-stop-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "auto_stop_lambda" {
  name = "${var.project_name}-auto-stop-lambda-policy"
  role = aws_iam_role.auto_stop_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListECSTasks"
        Effect = "Allow"
        Action = [
          "ecs:ListTasks",
          "ecs:DescribeTasks",
          "ecs:StopTask"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-auto-stop-*"
      },
      {
        Sid    = "PublishSNS"
        Effect = "Allow"
        Action = ["sns:Publish"]
        Resource = "*"
      }
    ]
  })
}

# EventBridge rule: run every 5 minutes
resource "aws_cloudwatch_event_rule" "auto_stop_schedule" {
  name                = "${var.project_name}-auto-stop-unhealthy-tasks-${var.environment}"
  description         = "Cost control: auto-stop UNHEALTHY ECS tasks every 5 minutes"
  schedule_expression = "rate(5 minutes)"
  is_enabled          = true

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "auto_stop_lambda" {
  rule      = aws_cloudwatch_event_rule.auto_stop_schedule.name
  target_id = "auto-stop-lambda"
  arn       = aws_lambda_function.auto_stop_unhealthy_tasks.arn
  role_arn  = aws_iam_role.eventbridge_invoke.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auto_stop_unhealthy_tasks.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.auto_stop_schedule.arn
}

resource "aws_iam_role" "eventbridge_invoke" {
  name = "${var.project_name}-eventbridge-invoke-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "events.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge_invoke" {
  name = "${var.project_name}-eventbridge-invoke-policy"
  role = aws_iam_role.eventbridge_invoke.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.auto_stop_unhealthy_tasks.arn
    }]
  })
}

output "auto_stop_lambda_arn" {
  value = aws_lambda_function.auto_stop_unhealthy_tasks.arn
}

output "auto_stop_lambda_name" {
  value = aws_lambda_function.auto_stop_unhealthy_tasks.function_name
}
