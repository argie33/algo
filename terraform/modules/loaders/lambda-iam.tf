# Lambda IAM roles and policies for quick-load functions
# Supports: dxy_index, market_constituents, sector_ranking, algo_metrics_daily, market_health_daily, market_sentiment

resource "aws_iam_role" "lambda_loader_execution" {
  name = "${var.project_name}-lambda-loader-execution-${var.environment}"

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

# Basic Lambda execution role (CloudWatch logs)
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_loader_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# VPC execution role (RDS access requires VPC)
resource "aws_iam_role_policy_attachment" "lambda_vpc_execution" {
  role       = aws_iam_role.lambda_loader_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# RDS database access
resource "aws_iam_role_policy" "lambda_rds_access" {
  name = "${var.project_name}-lambda-rds-access"
  role = aws_iam_role.lambda_loader_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "RDSConnect"
      Effect = "Allow"
      Action = [
        "rds-db:connect"
      ]
      Resource = "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:dbuser:${var.rds_resource_id}/*"
    }]
  })
}

# DynamoDB distributed locking
resource "aws_iam_role_policy" "lambda_dynamodb_locks" {
  name = "${var.project_name}-lambda-dynamodb-locks"
  role = aws_iam_role.lambda_loader_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBLoaderLocks"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = aws_dynamodb_table.loader_locks.arn
      },
      {
        Sid    = "DynamoDBLoaderStatus"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.loader_execution_status.arn
      }
    ]
  })
}

# Secrets Manager for DB credentials (optional - use RDS Proxy instead in production)
resource "aws_iam_role_policy" "lambda_secrets_manager" {
  name = "${var.project_name}-lambda-secrets-manager"
  role = aws_iam_role.lambda_loader_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SecretsManagerRead"
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"
    }]
  })
}
