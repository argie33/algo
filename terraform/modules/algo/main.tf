/**
 * Algo Module - Algorithm Orchestrator Lambda
 *
 * Creates:
 * - Lambda function for algorithm orchestration
 * - EventBridge scheduler rule
 * - SNS topic for alerts
 * - CloudWatch log group
 *
 * Reference: template-algo.yml
 */


# IAM role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-algo-lambda-role"

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

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow Lambda to read from Secrets Manager
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "${var.project_name}-algo-lambda-secrets"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.db_secret_arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "arn:aws:s3:::${var.algo_artifacts_bucket_name}/*"
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-algo-orchestrator"
  retention_in_days = 14

  tags = var.common_tags
}

# SNS Topic for alerts
resource "aws_sns_topic" "algo_alerts" {
  name = "${var.project_name}-algo-alerts"

  tags = var.common_tags
}

# EventBridge rule to trigger Lambda daily
resource "aws_cloudwatch_event_rule" "algo_schedule" {
  name                = "${var.project_name}-algo-schedule"
  description         = "Daily algorithm orchestrator trigger"
  schedule_expression = "cron(30 0 ? * * *)"  # 12:30 AM UTC

  tags = var.common_tags
}

# Placeholder Lambda (implementation in progress)
resource "aws_lambda_function" "algo_orchestrator" {
  filename      = "lambda_placeholder.zip"
  function_name = "${var.project_name}-algo-orchestrator"
  role          = aws_iam_role.lambda_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  environment {
    variables = {
      DB_SECRET_ARN      = var.db_secret_arn
      ARTIFACTS_BUCKET   = var.algo_artifacts_bucket_name
      AWS_REGION         = var.aws_region
    }
  }

  tags = var.common_tags

  depends_on = [
    aws_iam_role_policy.lambda_secrets,
    aws_cloudwatch_log_group.lambda
  ]
}

output "lambda_arn" {
  value = aws_lambda_function.algo_orchestrator.arn
}

output "schedule_arn" {
  value = aws_cloudwatch_event_rule.algo_schedule.arn
}

output "alert_topic_arn" {
  value = aws_sns_topic.algo_alerts.arn
}
