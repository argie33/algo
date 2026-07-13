# ============================================================
# AAII Sentiment Loader Lambda
# ============================================================
# STATUS (2026-07-13): non-functional. scripts/aaii_loader_function.py -- the only
# real implementation this ever had -- was a fabricated-data generator (deterministic
# formula, zero connection to the actual AAII investor sentiment survey) and was
# deleted in commit 676a415c5 as presumed test cruft. deploy-all-infrastructure.yml's
# "Build AAII Sentiment Loader Lambda" step now silently falls back to a stub
# (`lambda_handler` returning 501) whenever the source file is missing, so this
# resource currently deploys a no-op. Do not restore the fake generator -- if AAII
# data is wanted, wire up a real source and a recurring schedule (this Lambda was
# also never scheduled: invoked once per Terraform apply, not on a cadence, so even
# a working loader would only refresh on redeploys, not weekly with the survey).
# aaii_sentiment is IMP-role (non-critical); loaders/load_market_sentiment.py treats
# missing/stale AAII data as NULL with data_unavailable reasoning, not fabricated.

# Lambda function for AAII Sentiment loading
# ZIP file is pre-built by GitHub Actions workflow before Terraform runs
resource "aws_lambda_function" "aaii_loader" {
  filename         = "${path.module}/aaii_loader.zip"
  function_name    = "${var.project_name}-aaii-loader-${var.environment}"
  role             = aws_iam_role.aaii_loader.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  source_code_hash = filebase64sha256("${path.module}/aaii_loader.zip")
  layers           = try([aws_lambda_layer_version.psycopg2[0].arn], [])

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.rds_security_group_id]
  }

  environment {
    variables = {
      DB_HOST     = var.db_host != "" ? var.db_host : aws_db_instance.main.address
      DB_PORT     = tostring(var.db_port)
      DB_USER     = var.db_master_username
      DB_PASSWORD = local.rds_password
      DB_NAME     = aws_db_instance.main.db_name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.aaii_loader_vpc,
    aws_lambda_layer_version.psycopg2
  ]
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
