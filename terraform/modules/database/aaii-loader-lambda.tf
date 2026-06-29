# ============================================================
# AAII Sentiment Loader Lambda
# ============================================================
# Runs inside VPC with direct RDS access during deployment.
# Populates aaii_sentiment table with 2029 records.
# Invoked by GitHub Actions workflow after Terraform apply.

# Lambda function for AAII Sentiment loading
resource "aws_lambda_function" "aaii_loader" {
  filename      = "${path.module}/aaii_loader.zip"
  function_name = "${var.project_name}-aaii-loader-${var.environment}"
  role          = aws_iam_role.aaii_loader.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  timeout       = 60

  layers = [var.psycopg2_layer_arn != "" ? var.psycopg2_layer_arn : ""]

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.rds_security_group_id]
  }

  environment {
    variables = {
      DB_HOST     = var.db_host != "" ? var.db_host : aws_db_instance.main.address
      DB_PORT     = tostring(var.db_port)
      DB_USER     = local.rds_username
      DB_PASSWORD = local.rds_password
      DB_NAME     = aws_db_instance.main.db_name
    }
  }

  depends_on = [aws_iam_role_policy_attachment.aaii_loader_vpc]
}

# IAM role for AAII Loader Lambda
resource "aws_iam_role" "aaii_loader" {
  name = "${var.project_name}-aaii-loader-role-${var.environment}"

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

# Allow Lambda to write CloudWatch logs
resource "aws_iam_role_policy" "aaii_loader_logs" {
  name = "${var.project_name}-aaii-loader-logs-${var.environment}"
  role = aws_iam_role.aaii_loader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-aaii-loader-${var.environment}:*"
      }
    ]
  })
}

# Allow Lambda to access VPC
resource "aws_iam_role_policy_attachment" "aaii_loader_vpc" {
  role       = aws_iam_role.aaii_loader.id
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Build AAII Loader Lambda ZIP
data "archive_file" "aaii_loader" {
  type        = "zip"
  source_file = "${path.module}/../../scripts/aaii_loader_function.py"
  output_path = "${path.module}/aaii_loader.zip"
}
