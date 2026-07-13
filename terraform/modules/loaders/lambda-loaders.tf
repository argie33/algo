# Lambda functions for quick loaders (<5 min each)
# Replaces ECS tasks for: market_constituents, sector_ranking,
# algo_metrics_daily, market_health_daily, market_sentiment
# NOTE: dxy_index removed (Phase 2) - only ECS task used, not Lambda
#
# STATUS: NOT IMPLEMENTED. lambda/loaders/ source was never committed to this
# repo (zero git history), so data.archive_file below failed with
# "missing directory: modules/loaders/../../lambda/loaders" on every single
# `terraform plan` since this file was added - blocking ALL deploys account-wide,
# including unrelated changes elsewhere in the codebase. None of these
# aws_lambda_function resources have ever been created in AWS (verified via
# get-function: ResourceNotFoundException). The 5 loaders these were meant to
# replace already run successfully as ECS Fargate tasks (see all_loaders in
# main.tf) via Step Functions, so nothing depends on this. Gated behind
# lambda_loaders_source_exists so plan/apply succeed again; flip that local
# (or finish committing lambda/loaders/) to resume this migration.
locals {
  lambda_loaders_source_exists = fileexists("${path.module}/../../lambda/loaders/__init__.py")
}

# Archive existing loader code as Lambda deployment package
data "archive_file" "lambda_loaders_code" {
  count       = local.lambda_loaders_source_exists ? 1 : 0
  type        = "zip"
  source_dir  = "${path.module}/../../lambda/loaders"
  output_path = "${path.module}/../../lambda/loaders.zip"
}

# Base Lambda function configuration (shared across all loaders)
locals {
  lambda_loader_config = {
    runtime      = "python3.11"
    timeout      = 300 # 5 min timeout (can be overridden per loader)
    memory_size  = 512 # Start with 512 MB (increase if needed)
    architecture = "x86_64"
    environment_variables = {
      LOG_LEVEL               = "INFO"
      LOADER_DISTRIBUTED_LOCK = "true" # Enable DynamoDB locking to prevent concurrent runs
      LOADER_LOCK_TABLE       = aws_dynamodb_table.loader_locks.name
      LOADER_STATUS_TABLE     = aws_dynamodb_table.loader_execution_status.name
      RDS_PROXY_ENDPOINT      = var.rds_proxy_endpoint # Use RDS Proxy for connection pooling
      BACKFILL_DAYS           = "0"                    # No backfill for quick loaders
    }
  }
}

# Lambda layer for shared dependencies (psycopg2, pandas, requests, etc.)
# NOTE: Skipped if dependencies.zip doesn't exist (use Lambda inline packages or ECR image instead)
locals {
  lambda_layer_path = "${path.module}/../../lambda/layers/dependencies.zip"
  layer_exists      = fileexists(local.lambda_layer_path)
}

resource "aws_lambda_layer_version" "loader_dependencies" {
  count             = local.layer_exists ? 1 : 0
  filename          = local.lambda_layer_path
  layer_name        = "${var.project_name}-loader-dependencies-${var.environment}"
  source_code_hash  = local.layer_exists ? filebase64sha256(local.lambda_layer_path) : ""
  compatible_runtimes = ["python3.11"]
}

# ============================================================
# Lambda: market_constituents (Index membership data)
# ============================================================
resource "aws_lambda_function" "market_constituents" {
  count         = local.lambda_loaders_source_exists ? 1 : 0
  filename      = data.archive_file.lambda_loaders_code[0].output_path
  function_name = "${var.project_name}-loader-market-constituents-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.market_constituents.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 300 # 5 min timeout
  memory_size   = 512 # Handles API responses

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code[0].output_path)

  layers = try([aws_lambda_layer_version.loader_dependencies[0].arn], [])

  environment {
    variables = merge(
      local.lambda_loader_config.environment_variables,
      {
        LOADER_NAME = "market_constituents"
      }
    )
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_security_group_id]
  }

  tags = merge(var.common_tags, {
    Loader = "market_constituents"
  })
}

# ============================================================
# Lambda: sector_ranking (Market rankings)
# ============================================================
resource "aws_lambda_function" "sector_ranking" {
  count         = local.lambda_loaders_source_exists ? 1 : 0
  filename      = data.archive_file.lambda_loaders_code[0].output_path
  function_name = "${var.project_name}-loader-sector-ranking-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.sector_ranking.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 300 # 5 min timeout
  memory_size   = 512

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code[0].output_path)

  layers = try([aws_lambda_layer_version.loader_dependencies[0].arn], [])

  environment {
    variables = merge(
      local.lambda_loader_config.environment_variables,
      {
        LOADER_NAME = "sector_ranking"
      }
    )
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_security_group_id]
  }

  tags = merge(var.common_tags, {
    Loader = "sector_ranking"
  })
}

# ============================================================
# Lambda: algo_metrics_daily (Orchestrator metrics)
# ============================================================
resource "aws_lambda_function" "algo_metrics_daily" {
  count         = local.lambda_loaders_source_exists ? 1 : 0
  filename      = data.archive_file.lambda_loaders_code[0].output_path
  function_name = "${var.project_name}-loader-algo-metrics-daily-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.algo_metrics_daily.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 120 # 2 min timeout
  memory_size   = 256 # Lightweight, simple aggregation

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code[0].output_path)

  layers = try([aws_lambda_layer_version.loader_dependencies[0].arn], [])

  environment {
    variables = merge(
      local.lambda_loader_config.environment_variables,
      {
        LOADER_NAME = "algo_metrics_daily"
      }
    )
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_security_group_id]
  }

  tags = merge(var.common_tags, {
    Loader = "algo_metrics_daily"
  })
}

# ============================================================
# Lambda: market_health_daily (Market health metrics)
# ============================================================
resource "aws_lambda_function" "market_health_daily" {
  count         = local.lambda_loaders_source_exists ? 1 : 0
  filename      = data.archive_file.lambda_loaders_code[0].output_path
  function_name = "${var.project_name}-loader-market-health-daily-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.market_health_daily.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 300  # 5 min timeout
  memory_size   = 1024 # Handles VIX + put/call + yield curve fetching

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code[0].output_path)

  layers = try([aws_lambda_layer_version.loader_dependencies[0].arn], [])

  environment {
    variables = merge(
      local.lambda_loader_config.environment_variables,
      {
        LOADER_NAME = "market_health_daily"
      }
    )
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_security_group_id]
  }

  # Parallel merge operations (already optimized in load_market_health_daily.py)
  ephemeral_storage {
    size = 512 # 512 MB temp storage for intermediate data
  }

  tags = merge(var.common_tags, {
    Loader = "market_health_daily"
  })
}

# ============================================================
# Lambda: market_sentiment (Optional weekly loader)
# ============================================================
resource "aws_lambda_function" "market_sentiment" {
  count         = local.lambda_loaders_source_exists ? 1 : 0
  filename      = data.archive_file.lambda_loaders_code[0].output_path
  function_name = "${var.project_name}-loader-market-sentiment-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.market_sentiment.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 180 # 3 min timeout
  memory_size   = 256 # Lightweight, VIX only

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code[0].output_path)

  layers = try([aws_lambda_layer_version.loader_dependencies[0].arn], [])

  environment {
    variables = merge(
      local.lambda_loader_config.environment_variables,
      {
        LOADER_NAME = "market_sentiment"
      }
    )
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_security_group_id]
  }

  tags = merge(var.common_tags, {
    Loader = "market_sentiment"
  })
}

# ============================================================
# CloudWatch Log Groups (retention + monitoring)
# ============================================================
resource "aws_cloudwatch_log_group" "lambda_loaders" {
  for_each = local.lambda_loaders_source_exists ? toset([
    "market-constituents",
    "sector-ranking",
    "algo-metrics-daily",
    "market-health-daily",
    "market-sentiment"
  ]) : []

  name              = "/aws/lambda/${var.project_name}-loader-${each.value}-${var.environment}"
  retention_in_days = 14

  tags = merge(var.common_tags, {
    Loader = each.value
  })
}

# ============================================================
# Outputs for Step Functions integration
# ============================================================
output "lambda_loader_functions" {
  description = "ARNs of all Lambda loader functions (empty map until lambda/loaders/ source is committed)"
  value = local.lambda_loaders_source_exists ? {
    market_constituents = aws_lambda_function.market_constituents[0].arn
    sector_ranking      = aws_lambda_function.sector_ranking[0].arn
    algo_metrics_daily  = aws_lambda_function.algo_metrics_daily[0].arn
    market_health_daily = aws_lambda_function.market_health_daily[0].arn
    market_sentiment    = aws_lambda_function.market_sentiment[0].arn
  } : {}
}
