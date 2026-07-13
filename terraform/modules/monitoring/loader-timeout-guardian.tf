# ============================================================
# Loader Timeout Guardian: kills ECS loader tasks stuck past their
# own configured LOADER_TIMEOUT. Fargate has no built-in task-level
# execution limit -- only this Lambda (or the loader's own code)
# stops a hung task, so this is the backstop against runaway Fargate
# cost from a loader that hangs (network stall, DB lock wait, etc).
# ============================================================

# ============================================================
# 1. IAM Role for Loader Timeout Guardian Lambda
# ============================================================

resource "aws_iam_role" "loader_timeout_guardian" {
  name = "${var.project_name}-loader-timeout-guardian-${var.environment}"
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

resource "aws_iam_role_policy_attachment" "loader_timeout_guardian_logs" {
  role       = aws_iam_role.loader_timeout_guardian.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Minimal, read-mostly ECS access scoped to this one cluster, plus the one
# StopTask action this Lambda's whole purpose depends on.
resource "aws_iam_role_policy" "loader_timeout_guardian_ecs" {
  name = "${var.project_name}-loader-timeout-guardian-ecs-${var.environment}"
  role = aws_iam_role.loader_timeout_guardian.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:ListTasks",
          "ecs:DescribeTasks",
        ]
        Resource = "*"
        Condition = {
          ArnEquals = {
            "ecs:cluster" = var.ecs_cluster_arn
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeTaskDefinition",
        ]
        # DescribeTaskDefinition does not support the ecs:cluster condition key
        # (it isn't a cluster-scoped call) -- scope by ARN prefix instead.
        Resource = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:StopTask",
        ]
        Resource = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task/*"
        Condition = {
          ArnEquals = {
            "ecs:cluster" = var.ecs_cluster_arn
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
        ]
        Resource = "*"
      },
    ]
  })
}

# ============================================================
# 2. Loader Timeout Guardian Lambda Function
# ============================================================

resource "aws_lambda_function" "loader_timeout_guardian" {
  filename      = "${path.module}/../../lambda/loader-timeout-guardian/lambda_function.zip"
  function_name = "${var.project_name}-loader-timeout-guardian-${var.environment}"
  role          = aws_iam_role.loader_timeout_guardian.arn
  handler       = "lambda_function.lambda_handler"
  timeout       = 60
  memory_size   = 256
  runtime       = "python3.12"

  # No VPC config needed -- this Lambda only talks to the ECS/CloudWatch APIs, not
  # RDS, so it has no cold-start VPC ENI dependency and can't be blocked by it.

  environment {
    variables = {
      ECS_CLUSTER_NAME = split("/", var.ecs_cluster_arn)[1]
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-loader-timeout-guardian"
  })

  depends_on = [
    aws_iam_role_policy.loader_timeout_guardian_ecs,
    aws_iam_role_policy_attachment.loader_timeout_guardian_logs,
  ]
}

# ============================================================
# 3. EventBridge Schedule: run every 5 minutes
# ============================================================

resource "aws_cloudwatch_event_rule" "loader_timeout_guardian_schedule" {
  name                = "${var.project_name}-loader-timeout-guardian-${var.environment}"
  description         = "Kill ECS loader tasks stuck past their own configured timeout"
  schedule_expression = "rate(5 minutes)"
  state               = "ENABLED"

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "loader_timeout_guardian_lambda" {
  rule      = aws_cloudwatch_event_rule.loader_timeout_guardian_schedule.name
  target_id = "LoaderTimeoutGuardianLambda"
  arn       = aws_lambda_function.loader_timeout_guardian.arn
}

resource "aws_lambda_permission" "loader_timeout_guardian_allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.loader_timeout_guardian.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.loader_timeout_guardian_schedule.arn
}
