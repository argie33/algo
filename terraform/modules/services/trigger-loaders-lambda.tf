/**
 * Trigger Loaders Lambda
 * Emergency manual loader invocation when EventBridge fails
 * Called by: orchestrator failsafe, manual API, CloudWatch alarms
 */

# Archive the trigger-loaders code
data "archive_file" "trigger_loaders_zip" {
  type        = "zip"
  source_file = "${path.module}/../../lambda/trigger-loaders/lambda_function.py"
  output_path = "${path.module}/../../build/trigger-loaders.zip"
}

# Lambda function
resource "aws_lambda_function" "trigger_loaders" {
  filename         = data.archive_file.trigger_loaders_zip.output_path
  function_name    = "${var.project_name}-trigger-loaders-${var.environment}"
  role             = aws_iam_role.trigger_loaders_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  source_code_hash = data.archive_file.trigger_loaders_zip.output_base64sha256

  environment {
    variables = {
      PROJECT_NAME       = var.project_name
      ENVIRONMENT        = var.environment
      ECS_CLUSTER_ARN    = var.ecs_cluster_arn
      SUBNET_IDS         = join(",", var.private_subnet_ids)
      SECURITY_GROUP_ID  = var.ecs_tasks_sg_id
    }
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.algo_lambda_security_group_id]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-trigger-loaders"
  })
}

# IAM Role for trigger-loaders Lambda
resource "aws_iam_role" "trigger_loaders_role" {
  name = "${var.project_name}-trigger-loaders-role-${var.environment}"

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

# Allow Lambda to write logs
resource "aws_iam_role_policy_attachment" "trigger_loaders_logs" {
  role       = aws_iam_role.trigger_loaders_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Allow Lambda to invoke ECS tasks
resource "aws_iam_role_policy" "trigger_loaders_ecs" {
  name = "${var.project_name}-trigger-loaders-ecs"
  role = aws_iam_role.trigger_loaders_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          var.task_execution_role_arn,
          var.task_role_arn
        ]
      }
    ]
  })
}

# CloudWatch log group
resource "aws_cloudwatch_log_group" "trigger_loaders" {
  name              = "/aws/lambda/${aws_lambda_function.trigger_loaders.function_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = var.common_tags
}

# Output the Lambda ARN for orchestrator to use
output "trigger_loaders_lambda_arn" {
  value       = aws_lambda_function.trigger_loaders.arn
  description = "ARN of trigger-loaders Lambda for emergency loader invocation"
}
