# ============================================================
# Trigger Loaders Lambda Function
# ============================================================
# Invokes ECS loader tasks with correct environment overrides
# (LOADER_CHUNK_SIZE=100, LOADER_TIMEOUT_SEC=600)

data "aws_caller_identity" "current" {}

resource "aws_lambda_function" "trigger_loaders" {
  filename         = "${path.module}/trigger-loaders.zip"
  function_name    = "${var.project_name}-trigger-loaders"
  role             = aws_iam_role.trigger_loaders.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  timeout          = 300
  source_code_hash = filebase64sha256("${path.module}/trigger-loaders.zip")

  environment {
    variables = {
      ECS_CLUSTER_ARN           = var.ecs_cluster_arn
      SUBNET_IDS                = join(",", var.private_subnet_ids)
      SECURITY_GROUP_ID         = var.ecs_security_group_id
      PROJECT_NAME              = var.project_name
      DEFAULT_LOADER_TASK_COUNT = "1"
    }
  }

  depends_on = [
    aws_iam_role_policy.trigger_loaders_ecs_policy,
    aws_iam_role_policy_attachment.trigger_loaders_db
  ]

  tags = {
    Environment = var.environment
    Purpose     = "trigger-data-loaders"
  }
}

# IAM role for trigger loaders Lambda
resource "aws_iam_role" "trigger_loaders" {
  name = "${var.project_name}-trigger-loaders-role"

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

  tags = {
    Environment = var.environment
  }
}

# Note: ECS permissions provided via inline policy trigger_loaders_ecs_policy below
# The managed policy AmazonEC2ContainerServiceRoleForEC2 is for EC2 instances only

# Allow Lambda to describe ECS tasks and run tasks
resource "aws_iam_role_policy" "trigger_loaders_ecs_policy" {
  name = "${var.project_name}-trigger-loaders-ecs-policy"
  role = aws_iam_role.trigger_loaders.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeClusters"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = "*"
      }
    ]
  })
}

# Allow Lambda to read from database for validation
resource "aws_iam_role_policy_attachment" "trigger_loaders_db" {
  role       = aws_iam_role.trigger_loaders.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

# CloudWatch log group for Lambda
resource "aws_cloudwatch_log_group" "trigger_loaders" {
  name              = "/aws/lambda/${aws_lambda_function.trigger_loaders.function_name}"
  retention_in_days = 14

  tags = {
    Environment = var.environment
  }
}

# Lambda permission allowing EventBridge Scheduler to invoke trigger-loaders
resource "aws_lambda_permission" "trigger_loaders_eventbridge_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trigger_loaders.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule/*/*"
}
