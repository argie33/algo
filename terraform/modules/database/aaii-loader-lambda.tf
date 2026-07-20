# ============================================================
# AAII Sentiment Loader Lambda
# ============================================================
# STATUS (2026-07-20, Session 301): SUPERSEDED, should be decommissioned.
# scripts/aaii_loader_function.py -- the only real implementation this Lambda ever
# had -- was a fabricated-data generator (deterministic formula, zero connection to
# the actual AAII investor sentiment survey) and was deleted in commit 676a415c5 as
# presumed test cruft. This Lambda has been a no-op stub since (deploy workflow falls
# back to a 501 handler when the source file is missing). It was also never actually
# scheduled -- invoked once per Terraform apply, not on a cadence.
#
# The REAL loader (loaders/load_aaii_sentiment.py, standard ECS-loader pattern,
# Playwright-based Incapsula bypass + XLS parse from aaii.com) was separately deleted
# on 2026-07-03 (commit 6a227277f, mislabeled "unused") while algo/risk/factors/
# aaii_sentiment_factor.py -- a live Core-12 market-exposure factor -- kept silently
# reading the resulting increasingly-stale aaii_sentiment table with no freshness
# check. Restored the real loader Session 301; verified live (2,032 records, fresh
# through 2026-07-16). It needs a Playwright+Chromium runtime, not a bare Lambda zip.
# This aaii_loader Lambda resource is now redundant -- recommend removing it (and its
# IAM role/policies below) once the restored loader is wired into the standard ECS
# loader pipeline (terraform/modules/loaders/main.tf) on a real schedule.
# The prior claim that "loaders/load_market_sentiment.py treats missing/stale AAII
# data as NULL" was stale docs -- that file does not exist in this repo.

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
