# ============================================================
# Database Initialization via Lambda - Terraform Managed
# ============================================================
# Applies PostgreSQL schema on first deployment.
# Schema is version-controlled in: lambda/db-init/schema.sql (3001 lines)
# No migration runner or version tracking needed (greenfield setup).
#
# Flow:
# 1. Terraform creates RDS (empty instance)
# 2. Terraform creates db-init Lambda function
# 3. Terraform invokes db-init after RDS is ready
# 4. Lambda reads schema.sql and creates all tables/indexes
# 5. Schema is now live and ready for application code

# ============================================================
# IAM Role for db-init Lambda
# ============================================================

resource "aws_iam_role" "db_init" {
  name               = "${var.project_name}-db-init-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.db_init_assume.json

  tags = var.common_tags
}

data "aws_iam_policy_document" "db_init_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# Allow db-init Lambda to write logs
resource "aws_iam_role_policy_attachment" "db_init_logs" {
  role       = aws_iam_role.db_init.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow db-init Lambda to access VPC (for RDS connection)
resource "aws_iam_role_policy_attachment" "db_init_vpc" {
  role       = aws_iam_role.db_init.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Allow db-init Lambda to read RDS credentials from Secrets Manager
resource "aws_iam_role_policy" "db_init_secrets" {
  name   = "${var.project_name}-db-init-secrets"
  role   = aws_iam_role.db_init.id
  policy = data.aws_iam_policy_document.db_init_secrets.json
}

data "aws_iam_policy_document" "db_init_secrets" {
  statement {
    sid    = "ReadRDSCredentials"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      aws_secretsmanager_secret.rds_credentials.arn
    ]
  }
}

# ============================================================
# Lambda Layer - psycopg2 (PostgreSQL Driver)
# ============================================================
# Already created by another module, just reference it here

# ============================================================
# Lambda Function - Database Initialization
# ============================================================

resource "aws_lambda_function" "db_init" {
  filename         = var.db_init_code_file
  function_name    = "${var.project_name}-db-init-${var.environment}"
  role             = aws_iam_role.db_init.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  timeout          = 600 # 10 minutes for schema creation on busy DB
  source_code_hash = filebase64sha256(var.db_init_code_file)

  # VPC access for RDS
  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.ecs_tasks_security_group_id]
  }

  # Environment variables
  environment {
    variables = {
      DB_SECRET_ARN = aws_secretsmanager_secret.rds_credentials.arn
      LOG_LEVEL     = var.orchestrator_log_level
      DB_HOST       = aws_db_instance.main.address
      DB_PORT       = aws_db_instance.main.port
      DB_NAME       = aws_db_instance.main.db_name
    }
  }

  # Dependencies
  layers = try([aws_lambda_layer_version.psycopg2[0].arn], [])

  depends_on = [
    aws_db_instance.main,
    aws_iam_role_policy.db_init_secrets,
    aws_iam_role_policy_attachment.db_init_logs,
    aws_iam_role_policy_attachment.db_init_vpc,
  ]

  tags = var.common_tags
}

# ============================================================
# Lambda Invocation - Run db-init after RDS is Ready
# ============================================================
# Terraform automatically invokes the Lambda to initialize schema.
# This happens ONCE on first apply, or again if Lambda code changes.

resource "aws_lambda_invocation" "db_init" {
  function_name = aws_lambda_function.db_init.function_name
  input         = jsonencode({})

  # Trigger re-execution if Lambda code changes
  triggers = {
    db_init_code_hash = filebase64sha256(var.db_init_code_file)
  }

  depends_on = [aws_lambda_function.db_init]
}

# ============================================================
# Outputs
# ============================================================

output "db_init_lambda_arn" {
  description = "ARN of the database initialization Lambda function"
  value       = aws_lambda_function.db_init.arn
}

output "db_init_invocation_status" {
  description = "Status of database initialization invocation"
  value       = try(aws_lambda_invocation.db_init.result, "pending")
}
