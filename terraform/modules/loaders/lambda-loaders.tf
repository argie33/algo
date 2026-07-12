# Lambda functions for quick loaders (<5 min each)
# Replaces ECS tasks for: dxy_index, market_constituents, sector_ranking,
# algo_metrics_daily, market_health_daily, market_sentiment

# Archive existing loader code as Lambda deployment package
data "archive_file" "lambda_loaders_code" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambda/loaders"
  output_path = "${path.module}/../../lambda/loaders.zip"
}

# Base Lambda function configuration (shared across all loaders)
locals {
  lambda_loader_config = {
    runtime       = "python3.11"
    timeout       = 300  # 5 min timeout (can be overridden per loader)
    memory_size   = 512  # Start with 512 MB (increase if needed)
    architecture  = "x86_64"
    environment_variables = {
      LOG_LEVEL                = "INFO"
      LOADER_DISTRIBUTED_LOCK  = "true"  # Enable DynamoDB locking to prevent concurrent runs
      LOADER_LOCK_TABLE        = aws_dynamodb_table.loader_locks.name
      LOADER_STATUS_TABLE      = aws_dynamodb_table.loader_execution_status.name
      RDS_PROXY_ENDPOINT       = var.rds_proxy_endpoint  # Use RDS Proxy for connection pooling
      BACKFILL_DAYS            = "0"     # No backfill for quick loaders
    }
  }
}

# Lambda layer for shared dependencies (psycopg2, pandas, requests, etc.)
resource "aws_lambda_layer_version" "loader_dependencies" {
  filename   = "${path.module}/../../lambda/layers/dependencies.zip"
  layer_name = "${var.project_name}-loader-dependencies-${var.environment}"

  source_code_hash = filebase64sha256("${path.module}/../../lambda/layers/dependencies.zip")

  compatible_runtimes = ["python3.11"]

  depends_on = [
    # Ensure layer is built before Lambda functions reference it
  ]

  tags = var.common_tags
}

# ============================================================
# Lambda: dxy_index (Economic data fetcher)
# ============================================================
resource "aws_lambda_function" "dxy_index" {
  filename      = data.archive_file.lambda_loaders_code.output_path
  function_name = "${var.project_name}-loader-dxy-index-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.dxy_index.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 120  # 2 min timeout
  memory_size   = 256  # Lightweight, I/O bound

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code.output_path)

  layers = [aws_lambda_layer_version.loader_dependencies.arn]

  environment {
    variables = merge(
      local.lambda_loader_config.environment_variables,
      {
        LOADER_NAME = "dxy_index"
      }
    )
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_security_group_id]
  }

  tags = merge(var.common_tags, {
    Loader = "dxy_index"
  })
}

# ============================================================
# Lambda: market_constituents (Index membership data)
# ============================================================
resource "aws_lambda_function" "market_constituents" {
  filename      = data.archive_file.lambda_loaders_code.output_path
  function_name = "${var.project_name}-loader-market-constituents-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.market_constituents.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 300  # 5 min timeout
  memory_size   = 512  # Handles API responses

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code.output_path)

  layers = [aws_lambda_layer_version.loader_dependencies.arn]

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
  filename      = data.archive_file.lambda_loaders_code.output_path
  function_name = "${var.project_name}-loader-sector-ranking-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.sector_ranking.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 300  # 5 min timeout
  memory_size   = 512

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code.output_path)

  layers = [aws_lambda_layer_version.loader_dependencies.arn]

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
  filename      = data.archive_file.lambda_loaders_code.output_path
  function_name = "${var.project_name}-loader-algo-metrics-daily-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.algo_metrics_daily.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 120  # 2 min timeout
  memory_size   = 256  # Lightweight, simple aggregation

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code.output_path)

  layers = [aws_lambda_layer_version.loader_dependencies.arn]

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
  filename      = data.archive_file.lambda_loaders_code.output_path
  function_name = "${var.project_name}-loader-market-health-daily-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.market_health_daily.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 300  # 5 min timeout
  memory_size   = 1024  # Handles VIX + put/call + yield curve fetching

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code.output_path)

  layers = [aws_lambda_layer_version.loader_dependencies.arn]

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
    size = 512  # 512 MB temp storage for intermediate data
  }

  tags = merge(var.common_tags, {
    Loader = "market_health_daily"
  })
}

# ============================================================
# Lambda: market_sentiment (Optional weekly loader)
# ============================================================
resource "aws_lambda_function" "market_sentiment" {
  filename      = data.archive_file.lambda_loaders_code.output_path
  function_name = "${var.project_name}-loader-market-sentiment-${var.environment}"
  role          = aws_iam_role.lambda_loader_execution.arn
  handler       = "handlers.market_sentiment.handler"
  runtime       = local.lambda_loader_config.runtime
  timeout       = 180  # 3 min timeout
  memory_size   = 256  # Lightweight, VIX only

  source_code_hash = filebase64sha256(data.archive_file.lambda_loaders_code.output_path)

  layers = [aws_lambda_layer_version.loader_dependencies.arn]

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
  for_each = toset([
    "dxy-index",
    "market-constituents",
    "sector-ranking",
    "algo-metrics-daily",
    "market-health-daily",
    "market-sentiment"
  ])

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
  description = "ARNs of all Lambda loader functions"
  value = {
    dxy_index              = aws_lambda_function.dxy_index.arn
    market_constituents    = aws_lambda_function.market_constituents.arn
    sector_ranking         = aws_lambda_function.sector_ranking.arn
    algo_metrics_daily     = aws_lambda_function.algo_metrics_daily.arn
    market_health_daily    = aws_lambda_function.market_health_daily.arn
    market_sentiment       = aws_lambda_function.market_sentiment.arn
  }
}
