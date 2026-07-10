// ECS task definitions, EventBridge scheduled rules, IAM roles for data loaders.
// NOTE: Core EOD loaders run via Step Functions (modules/pipeline), not EventBridge cron.
// Task definitions remain here for Step Functions to reference.

# ============================================================
# IAM Roles & Policies
# ============================================================

# EventBridge role to run ECS tasks
resource "aws_iam_role" "eventbridge_run_task" {
  name = "${var.project_name}-svc-eventbridge-run-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

# DynamoDB Table for Orchestrator Distributed Locking
resource "aws_dynamodb_table" "orchestrator_locks" {
  name         = "${var.project_name}-orchestrator-locks-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "lock_key"

  attribute {
    name = "lock_key"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-orchestrator-locks"
  })
}

# DynamoDB Table for Loader Distributed Locking (prevents concurrent instances)
resource "aws_dynamodb_table" "loader_locks" {
  name         = "${var.project_name}-loader-locks-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "lock_key"

  attribute {
    name = "lock_key"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-loader-locks"
  })
}

# DynamoDB Table for Loader Execution Status (separate from lock TTL)
resource "aws_dynamodb_table" "loader_execution_status" {
  name         = "${var.project_name}-loader-status-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "loader_name"
  range_key    = "execution_date"

  attribute {
    name = "loader_name"
    type = "S"
  }

  attribute {
    name = "execution_date"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-loader-status"
  })
}

# DynamoDB Table for Dynamic Loader Configuration
resource "aws_dynamodb_table" "loader_config" {
  name         = "${var.project_name}-loader-config-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "loader_name"

  attribute {
    name = "loader_name"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-loader-config"
  })
}

# Grant ECS tasks permission to read from the loader config table
resource "aws_iam_role_policy" "ecs_task_loader_config_access" {
  name = "${var.project_name}-ecs-loader-config-access"
  role = split("/", var.task_role_arn)[1]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBLoaderConfig"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.loader_config.arn
      }
    ]
  })
}

# Grant ECS tasks permission to access the loader status table
resource "aws_iam_role_policy" "ecs_task_loader_status_access" {
  name = "${var.project_name}-ecs-loader-status-access"
  role = split("/", var.task_role_arn)[1]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBLoaderStatus"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.loader_execution_status.arn
      }
    ]
  })
}

# Grant ECS tasks permission to access the lock tables
resource "aws_iam_role_policy" "ecs_task_lock_access" {
  name = "${var.project_name}-ecs-lock-table-access"
  role = split("/", var.task_role_arn)[1]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBOrchestrationLocks"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = aws_dynamodb_table.orchestrator_locks.arn
      },
      {
        Sid    = "DynamoDBLoaderLocks"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = aws_dynamodb_table.loader_locks.arn
      }
    ]
  })
}

# ============================================================
# SQS Dead-Letter Queue for EventBridge loader failures
# ============================================================

resource "aws_sqs_queue" "loader_dlq" {
  name                      = "${var.project_name}-loader-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-loader-dlq"
  })
}

resource "aws_sqs_queue_policy" "loader_dlq" {
  queue_url = aws_sqs_queue.loader_dlq.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridgeSend"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.loader_dlq.arn
      Condition = {
        ArnLike = {
          "aws:SourceArn" = "arn:aws:events:${var.aws_region}:${var.aws_account_id}:rule/${var.project_name}-*"
        }
      }
    }]
  })
}

# EventBridge IAM policy to run ECS tasks
resource "aws_iam_role_policy" "eventbridge_run_task_policy" {
  name = "${var.project_name}-eventbridge-run-task-policy"
  role = aws_iam_role.eventbridge_run_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRunTask"
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*:*"
      },
      {
        Sid    = "AllowPassRole"
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          var.task_execution_role_arn,
          var.task_role_arn
        ]
      }
    ]
  })
}

# ============================================================
# Scheduled EventBridge Rules - Scheduled Loaders
# ============================================================
# Loaders are scheduled to run at optimal times to:
# 1. Respect data dependencies (prices first, then signals)
# 2. Distribute API load across the trading day
# 3. Avoid resource contention
#
# Schedule Map:
# - 3:30am ET (8:30am UTC): stock_symbols
# - 4:00am ET (9am UTC): price loaders (6 parallel)
# - 10:00am ET (3pm UTC): financial statements (8 parallel)
# - 11:00am ET (4pm UTC): earnings data (4 parallel)
# - 12:00pm ET (5pm UTC): market/economic data (10 parallel)
# - 1:00pm ET (6pm UTC): sentiment/analysis (5 parallel)
# - 5:00pm ET (10pm UTC): trading signals (5 parallel)
# - 5:15pm ET (10:15pm UTC): algo metrics (after signals)

// CRITICAL: Each loader MUST have a parallelism value to prevent RDS connection pool exhaustion.
// Loaders read LOADER_PARALLELISM env var and must respect it in their run() method.
locals {
  loader_file_map = {
    "stock_prices_daily"    = "load_prices.py"
    "technical_data_daily"  = "load_technical_data_daily.py"
    "trend_template_data"   = "load_trend_criteria_data.py"
    "market_exposure_daily" = "load_market_exposure_daily.py"
    "yfinance_snapshot"     = "load_yfinance_snapshot.py"
    "dxy_index"             = "load_dxy_index.py"
    "growth_metrics"        = "load_growth_metrics.py"
    "quality_metrics"       = "load_quality_metrics.py"
    "value_metrics"         = "load_value_metrics.py"
    "positioning_metrics"   = "load_positioning_metrics.py"
    "stability_metrics"     = "load_stability_metrics.py"
    "momentum_metrics"      = "load_momentum_metrics.py"
    "stock_scores"          = "load_stock_scores.py"

    "market_constituents" = "load_market_constituents.py"
    "market_health_daily" = "load_market_health_daily.py"
    "market_sentiment"    = "load_market_sentiment.py"
    # Consolidated market rankings loader (replaces 2 separate loaders)
    "sector_ranking"     = "load_market_rankings.py"
    "industry_ranking"   = "load_market_rankings.py"
    "algo_metrics_daily" = "load_algo_metrics_daily.py"
    "buy_sell_daily"     = "load_buy_sell_daily.py"
    "earnings_history"   = "load_earnings_history.py"
    "earnings_calendar"  = "load_earnings_calendar.py"
    "company_profile"    = "load_company_profile.py"
    # Consolidated analyst loader (replaces 2 separate loaders)
    "analyst_sentiment"           = "load_analyst_analysis.py"
    "analyst_upgrades_downgrades" = "load_analyst_analysis.py"

    # Consolidated financial statements loader (replaces 8 separate loaders)
    "financials_annual_income"      = "load_financial_statements.py"
    "financials_annual_balance"     = "load_financial_statements.py"
    "financials_annual_cashflow"    = "load_financial_statements.py"
    "financials_quarterly_income"   = "load_financial_statements.py"
    "financials_quarterly_balance"  = "load_financial_statements.py"
    "financials_quarterly_cashflow" = "load_financial_statements.py"
    "financials_ttm_income"         = "load_financial_statements.py"
    "financials_ttm_cashflow"       = "load_financial_statements.py"

    "compute_performance_metrics" = "compute_performance_metrics.py"
  }

  scheduled_loaders = {
    # Morning pipeline: 2:15 AM ET (7:15 AM UTC), Mon-Fri
    # Loads fresh market data for 9:30 AM signal generation
    # CRITICAL: Sequenced with sufficient gaps to ensure dependency completion
    "stock_prices_daily" = {
      description = "Load OHLCV prices - morning pipeline (10k+ symbols, ~30 min runtime)"
      schedule    = "cron(15 7 ? * MON-FRI *)" # 2:15 AM ET - starts first
    }
    "technical_data_daily" = {
      description = "Compute 50/200-day SMA - morning pipeline (depends on prices)"
      schedule    = "cron(55 7 ? * MON-FRI *)" # 2:55 AM ET - 40 min after prices start (allows completion)
    }

    # EOD pipeline: 3:00 PM ET (8:00 PM UTC), Mon-Fri - SEC Edgar financial statements (upstream for quality/growth metrics)
    # Must run early enough to complete before quality/growth loaders at 4:20 PM
    "financials_annual_income" = {
      description = "Load annual income statements from SEC EDGAR - EOD pipeline (upstream for quality/growth metrics)"
      schedule    = "cron(0 20 ? * MON-FRI *)" # 3:00 PM ET - starts early for completion
    }
    "financials_annual_balance" = {
      description = "Load annual balance sheets from SEC EDGAR - EOD pipeline (upstream for quality/growth metrics)"
      schedule    = "cron(5 20 ? * MON-FRI *)" # 3:05 PM ET - 5 min after income statement
    }

    # EOD pipeline: 4:05 PM ET (9:05 PM UTC), Mon-Fri
    # Loads end-of-day data for 5:30 PM orchestrator run
    "market_health_daily" = {
      description = "Load market health indicators - EOD pipeline"
      schedule    = "cron(5 21 ? * MON-FRI *)" # 4:05 PM ET
    }
    "market_exposure_daily" = {
      description = "Compute market exposure factors - EOD pipeline"
      schedule    = "cron(10 21 ? * MON-FRI *)" # 4:10 PM ET (after market_health)
    }
    "market_sentiment" = {
      description = "Compute market sentiment (fear/greed index from VIX) - EOD pipeline"
      schedule    = "cron(12 21 ? * MON-FRI *)" # 4:12 PM ET (after market_exposure_daily)
    }
    "dxy_index" = {
      description = "Load DXY/USD economic indicator - EOD pipeline"
      schedule    = "cron(15 21 ? * MON-FRI *)" # 4:15 PM ET
    }

    # Metric loaders: Parallel at 4:20 PM ET (after SEC Edgar financials complete at ~3:30 PM)
    "quality_metrics" = {
      description = "Load quality metrics from SEC - EOD pipeline (depends on financials_annual_income/balance)"
      schedule    = "cron(20 21 ? * MON-FRI *)" # 4:20 PM ET (parallel, after SEC data available)
    }
    "growth_metrics" = {
      description = "Load growth metrics from SEC - EOD pipeline (depends on financials_annual_income)"
      schedule    = "cron(20 21 ? * MON-FRI *)" # 4:20 PM ET (parallel, after SEC data available)
    }
    "value_metrics" = {
      description = "Load value metrics (P/E, P/B, P/S) - EOD pipeline"
      schedule    = "cron(20 21 ? * MON-FRI *)" # 4:20 PM ET (parallel)
    }
    "positioning_metrics" = {
      description = "Load positioning metrics (short interest) - EOD pipeline"
      schedule    = "cron(20 21 ? * MON-FRI *)" # 4:20 PM ET (parallel)
    }
    "stability_metrics" = {
      description = "Load stability metrics (dividend yield) - EOD pipeline"
      schedule    = "cron(20 21 ? * MON-FRI *)" # 4:20 PM ET (parallel)
    }
    "momentum_metrics" = {
      description = "Load momentum metrics (1m/3m/6m/12m returns) - EOD pipeline"
      schedule    = "cron(20 21 ? * MON-FRI *)" # 4:20 PM ET (parallel)
    }

    # Stock scores: 4:30 PM ET (after all metrics complete ~4:25 PM)
    "stock_scores" = {
      description = "Compute composite stock scores - EOD pipeline (depends on all metric loaders)"
      schedule    = "cron(30 21 ? * MON-FRI *)" # 4:30 PM ET (after all metrics)
    }

    # Industry and sector rankings: 4:40 PM ET (after stock_scores complete ~4:35 PM)
    "industry_ranking" = {
      description = "Compute industry rankings from stock scores - EOD pipeline (depends on stock_scores)"
      schedule    = "cron(40 21 ? * MON-FRI *)" # 4:40 PM ET (after stock_scores)
    }
    "sector_ranking" = {
      description = "Compute sector rankings from stock scores - EOD pipeline (depends on stock_scores)"
      schedule    = "cron(45 21 ? * MON-FRI *)" # 4:45 PM ET (after industry_ranking)
    }

    # Signal generation and analytics: 5:00 PM ET (after all data loaded ~4:50 PM)
    "buy_sell_daily" = {
      description = "Generate BUY/SELL signals from technical+fundamental analysis - CRITICAL for trading"
      schedule    = "cron(0 22 ? * MON-FRI *)" # 5:00 PM ET (after sector_ranking)
    }
    "algo_metrics_daily" = {
      description = "Compute daily algo performance metrics - CRITICAL for dashboard/reports"
      schedule    = "cron(5 22 ? * MON-FRI *)" # 5:05 PM ET (after buy_sell_daily)
    }

    # Supporting data: 5:10 PM ET and later
    "earnings_calendar" = {
      description = "Load earnings calendar - needed for earnings blackout logic"
      schedule    = "cron(10 22 ? * MON-FRI *)" # 5:10 PM ET
    }
    "company_profile" = {
      description = "Load company profile (sector, industry) - needed for position tracking"
      schedule    = "cron(15 22 ? * MON-FRI *)" # 5:15 PM ET
    }
    "analyst_sentiment" = {
      description = "Load analyst sentiment scores - dashboard data"
      schedule    = "cron(20 22 ? * MON-FRI *)" # 5:20 PM ET
    }
    "yfinance_snapshot" = {
      description = "Cache yfinance snapshots for quick metric calculations"
      schedule    = "cron(25 22 ? * MON-FRI *)" # 5:25 PM ET
    }
  }
}

resource "aws_cloudwatch_event_rule" "scheduled_loader" {
  for_each = local.scheduled_loaders

  name                = "${var.project_name}-${each.key}-schedule"
  description         = each.value.description
  schedule_expression = each.value.schedule
  state               = "ENABLED"

  tags = var.common_tags
}

locals {
  all_loaders = {
    # Cost-optimized: Reduced from 1024/2048 (price fetch is I/O bound, not compute intensive)
    "stock_prices_daily" = { cpu = 512, memory = 1024, timeout = 5400, parallelism = 1 }
    # Cost-optimized: Reduced from 2048/4096 (vectorized SQL queries on ~10k rows, moderate compute)
    "technical_data_daily"  = { cpu = 1024, memory = 2048, timeout = 2400, parallelism = 1 }
    "trend_template_data"   = { cpu = 1024, memory = 2048, timeout = 5400, parallelism = 1 }
    "market_exposure_daily" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "yfinance_snapshot"     = { cpu = 1024, memory = 2048, timeout = 7200, parallelism = 1 }
    "dxy_index"             = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }
    # Cost-optimized: Reduced from 1024/2048 (yfinance API fetch + lightweight metric calc)
    "growth_metrics" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 2 }
    # Cost-optimized: Reduced from 1024/2048 (SEC filing parse + DB insert, moderate CPU)
    "quality_metrics" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 2 }
    # Cost-optimized: Reduced from 1024/2048 (simple price ratio calculations)
    "value_metrics"       = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }
    "positioning_metrics" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 2 }
    # Cost-optimized: Reduced from 1024/2048 (dividend + payout ratio queries)
    "stability_metrics" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }
    # Cost-optimized: Reduced from 1024/2048 (return calculations on historical prices)
    "momentum_metrics" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }
    "stock_scores"     = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 2 }

    "market_constituents" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "market_health_daily" = { cpu = 256, memory = 512, timeout = 1200, parallelism = 1 }
    "market_sentiment"    = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }
    "sector_ranking"      = { cpu = 512, memory = 1024, timeout = 900, parallelism = 1 }
    "industry_ranking"    = { cpu = 512, memory = 1024, timeout = 900, parallelism = 1 }
    "algo_metrics_daily"  = { cpu = 1024, memory = 2048, timeout = 10800, parallelism = 1 }
    # Cost-optimized: Reduced from 2048/4096 (signal generation: talib calculations + DB queries, moderate CPU)
    "buy_sell_daily"              = { cpu = 1024, memory = 2048, timeout = 2400, parallelism = 2 }
    "earnings_history"            = { cpu = 512, memory = 1024, timeout = 7200, parallelism = 1 }
    "earnings_calendar"           = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "company_profile"             = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 2 }
    "analyst_sentiment"           = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 2 }
    "analyst_upgrades_downgrades" = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 2 }

    "financials_annual_income"      = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "financials_annual_balance"     = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "financials_annual_cashflow"    = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "financials_quarterly_income"   = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "financials_quarterly_balance"  = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "financials_quarterly_cashflow" = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "financials_ttm_income"         = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }
    "financials_ttm_cashflow"       = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 1 }

    "compute_performance_metrics" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }
  }
  default_loaders = local.all_loaders

  # Loaders that must run on on-demand FARGATE (cannot tolerate interruption)
  critical_loaders = toset([
    "stock_prices_daily",
    "algo_metrics_daily",
    "stock_scores",
    "buy_sell_daily",
    "yfinance_snapshot",
    "dxy_index",
    "financials_annual_income",
    "financials_annual_balance",
    "growth_metrics",
    "quality_metrics",
    "value_metrics",
    "positioning_metrics",
    "stability_metrics",
    "momentum_metrics"
  ])
}

# ECS Task Definitions for 10 production data loaders
# NOTE: CPU/memory in container definition are removed - only task-level values matter for Fargate
resource "aws_ecs_task_definition" "loader" {
  for_each = local.all_loaders

  depends_on = [null_resource.ensure_log_group]

  family = "${var.project_name}-${each.key}-loader"

  # Force new task definition version to pick up environment variables (2026-06-04 12:14 UTC)
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-${each.key}"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      essential = true
      command   = ["loaders/${local.loader_file_map[each.key]}"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-${each.key}-loader"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.db_secret_arn}:password::"
        },
        {
          name      = "DB_USER"
          valueFrom = "${var.db_secret_arn}:username::"
        },
        {
          name      = "FRED_API_KEY"
          valueFrom = "${var.algo_secrets_arn}:FRED_API_KEY::"
        },
        {
          name      = "APCA_API_KEY_ID"
          valueFrom = "${var.algo_secrets_arn}:APCA_API_KEY_ID::"
        },
        {
          name      = "APCA_API_SECRET_KEY"
          valueFrom = "${var.algo_secrets_arn}:APCA_API_SECRET_KEY::"
        }
      ]

      environment = concat([
        {
          name  = "LOADER_NAME"
          value = each.key
        },
        {
          name  = "LOADER_PARALLELISM"
          value = tostring(each.value.parallelism)
        },
        {
          name  = "LOADER_TIMEOUT"
          value = tostring(each.value.timeout)
        },
        # AWS batch size configuration (reduce 1000→100 in AWS to avoid yfinance rate limiting)
        {
          name  = "LOADER_CHUNK_SIZE"
          value = "100"
        },
        # AWS memory configuration for ECS task
        {
          name  = "ECS_TASK_MEMORY_LIMIT"
          value = tostring(each.value.memory)
        },
        # AWS configuration (region required by credential_manager)
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        # Database configuration (all required for get_db_config() in credential_manager)
        {
          name  = "DB_HOST"
          value = var.db_host
        },
        {
          name  = "DB_PORT"
          value = tostring(var.db_port)
        },
        {
          name  = "DB_NAME"
          value = var.db_name
        },
        {
          name  = "DB_SSL"
          value = var.db_ssl_mode
        },
        {
          name  = "DB_SECRET_ARN"
          value = var.db_secret_arn
        },
        # Alpaca configuration (ALGO_SECRETS_ARN required by credential_manager)
        {
          name  = "ALGO_SECRETS_ARN"
          value = var.algo_secrets_arn
        },
        {
          name  = "ALPACA_PAPER_TRADING"
          value = tostring(var.alpaca_paper_trading)
        },
        {
          name  = "APCA_API_BASE_URL"
          value = var.alpaca_api_base_url
        },
        # Execution configuration
        {
          name  = "ORCHESTRATOR_EXECUTION_MODE"
          value = var.execution_mode
        },
        {
          name  = "ORCHESTRATOR_DRY_RUN"
          value = tostring(var.orchestrator_dry_run)
        },
        # Data loading
        {
          name  = "BACKFILL_DAYS"
          value = tostring(var.backfill_days)
        },
        {
          name  = "DISABLE_PROVENANCE_TRACKING"
          value = tostring(var.disable_provenance_tracking)
        },
        {
          name  = "SEC_USER_AGENT"
          value = "algo-trading argeropolos@gmail.com"
        },
        # Distributed locking (required by OptimalLoader.load_global/load_symbol)
        {
          name  = "LOADER_LOCKS_TABLE"
          value = aws_dynamodb_table.loader_locks.name
        },
        # Project/environment (required by credential_manager and lock table construction)
        {
          name  = "PROJECT_NAME"
          value = var.project_name
        },
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        # Alerting
        {
          name  = "ALERT_EMAIL_TO"
          value = var.alert_email_to
        },
        {
          name  = "ALERT_WEBHOOK_URL"
          value = var.alert_webhook_url
        },
        # Force task definition re-registration (2026-06-04 13:45 UTC - rebuild after algo/ Dockerfile fix)
        {
          name  = "TASK_DEFINITION_VERSION_TIMESTAMP"
          value = "2026-06-04T13:45:00Z"
        },
        # Python path for module imports (defined in Dockerfile, but set here as redundant safety)
        {
          name  = "PYTHONPATH"
          value = "/app"
        }
        ],
        # Unified price loader: handles all intervals and asset classes
        each.key == "stock_prices_daily" ? [
          {
            name  = "LOADER_INTERVALS"
            value = "1d,1wk,1mo"
          },
          {
            name  = "LOADER_ASSET_CLASSES"
            value = "stock,etf"
          }
        ] : [],
        # Financial loaders: determine period and statement type from task name
        strcontains(each.key, "annual") ? [
          {
            name  = "LOADER_PERIOD"
            value = "annual"
          }
          ] : strcontains(each.key, "quarterly") ? [
          {
            name  = "LOADER_PERIOD"
            value = "quarterly"
          }
          ] : strcontains(each.key, "ttm") ? [
          {
            name  = "LOADER_PERIOD"
            value = "quarterly"
          }
        ] : [],
        # Financial loaders: determine statement type from task name
        strcontains(each.key, "income") ? [
          {
            name  = "LOADER_STATEMENT_TYPE"
            value = "income"
          }
          ] : strcontains(each.key, "balance") ? [
          {
            name  = "LOADER_STATEMENT_TYPE"
            value = "balance"
          }
          ] : strcontains(each.key, "cashflow") ? [
          {
            name  = "LOADER_STATEMENT_TYPE"
            value = "cashflow"
          }
        ] : []
      )

      # FIXED Issue #14: Health check to detect stalled/zombie loaders
      # ECS will mark task as unhealthy if loader doesn't report within timeout period
      healthCheck = {
        command     = ["CMD-SHELL", "ps aux | grep -q '[p]ython.*${each.key}' || exit 1"]
        interval    = 30 # Check every 30 seconds
        timeout     = 5  # Timeout for health check command
        retries     = 2  # Mark unhealthy after 2 failed checks (60s)
        startPeriod = 60 # Grace period before first health check (let loader startup)
      }
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  tags = var.common_tags
}

# Create CloudWatch Log Groups - retry if already exists to avoid state sync issues
resource "null_resource" "ensure_log_group" {
  for_each = local.all_loaders

  provisioner "local-exec" {
    command = "aws logs create-log-group --log-group-name /ecs/${var.project_name}-${each.key}-loader --region ${var.aws_region} 2>/dev/null || true"
  }

  triggers = {
    log_group_name = "/ecs/${var.project_name}-${each.key}-loader"
  }
}

# ============================================================
# EventBridge Targets - ECS Task Execution (Scheduled Loaders)
# ============================================================

resource "aws_cloudwatch_event_target" "scheduled_loader_target" {
  for_each = local.scheduled_loaders

  rule      = aws_cloudwatch_event_rule.scheduled_loader[each.key].name
  target_id = "${upper(replace(each.key, "_", ""))}Target"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.eventbridge_run_task.arn

  ecs_target {
    # launch_type must be null when capacity_provider_strategy is set (AWS rejects both)
    launch_type         = contains(local.critical_loaders, each.key) ? "FARGATE" : null
    task_definition_arn = aws_ecs_task_definition.loader[each.key].arn
    task_count          = 1
    platform_version    = "LATEST"

    # Use capacity provider strategy for flexible on-demand/spot selection
    dynamic "capacity_provider_strategy" {
      for_each = contains(local.critical_loaders, each.key) ? [] : [1]
      content {
        capacity_provider = "FARGATE_SPOT"
        weight            = 100
        base              = 0
      }
    }

    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [var.ecs_tasks_sg_id]
      assign_public_ip = false
    }
  }

  dead_letter_config {
    arn = aws_sqs_queue.loader_dlq.arn
  }
}

# ============================================================
# Intraday Swing Trader Scores Updates (1 PM & 3 PM ET)
# Note: Vectorized swing_trader_scores loader supports --today flag for fast intraday updates.
# These can be triggered:
# 1. By EventBridge rules (separate from pipeline)
# 2. By the orchestrator itself when running at 1 PM / 3 PM (existing runs via 2x-daily-orchestrator.tf)
# 3. By Step Functions pipeline with environment variable overrides
#
# For now, relying on the existing 1 PM / 3 PM orchestrator runs (events.tf) to use the faster
# vectorized swing_trader_scores from the morning/EOD pipelines. The orchestrator can be enhanced
# to trigger fresh score loads if needed via internal loader invocation.
# ============================================================

# ============================================================
# Algo Orchestrator ECS Task Definition (7-Phase Trading Logic)
#
# Runs as ECS Fargate task invoked by Step Functions EOD pipeline.
# No longer uses Lambda due to 15-minute timeout limit.
# ECS allows unlimited execution time for complex trading orchestration.
# ============================================================

resource "null_resource" "ensure_orchestrator_log_group" {
  provisioner "local-exec" {
    command = "aws logs create-log-group --log-group-name /ecs/${var.project_name}-algo-orchestrator --region ${var.aws_region} 2>/dev/null || true"
  }
}

resource "aws_ecs_task_definition" "algo_orchestrator" {
  depends_on = [null_resource.ensure_orchestrator_log_group]

  family = "${var.project_name}-algo-orchestrator"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-algo-orchestrator"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      essential = true

      # Orchestrator entry point: combined with Dockerfile ENTRYPOINT ["python3", "-u"]
      # → python3 -u algo/algo_orchestrator.py
      # Do NOT prefix with "python3" — ENTRYPOINT already provides the interpreter.
      command = ["algo/algo_orchestrator.py"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-algo-orchestrator"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      secrets = [
        { name = "DB_PASSWORD", valueFrom = "${var.db_secret_arn}:password::" },
        { name = "DB_USER", valueFrom = "${var.db_secret_arn}:username::" },
        { name = "APCA_API_KEY_ID", valueFrom = "${var.algo_secrets_arn}:APCA_API_KEY_ID::" },
        { name = "APCA_API_SECRET_KEY", valueFrom = "${var.algo_secrets_arn}:APCA_API_SECRET_KEY::" }
      ]

      environment = [
        { name = "AWS_REGION", value = var.aws_region },
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_SECRET_ARN", value = var.db_secret_arn },
        { name = "ALGO_SECRETS_ARN", value = var.algo_secrets_arn },
        { name = "DB_SSL", value = var.db_ssl_mode },
        { name = "ECS_CLUSTER_ARN", value = var.ecs_cluster_arn },
        { name = "HALT_FLAG_TABLE", value = "algo_orchestrator_state" },
        { name = "ALPACA_PAPER_TRADING", value = tostring(var.alpaca_paper_trading) },
        { name = "ORCHESTRATOR_LOG_LEVEL", value = var.orchestrator_log_level },
        { name = "ORCHESTRATOR_EXECUTION_MODE", value = var.execution_mode },
        { name = "ORCHESTRATOR_DRY_RUN", value = tostring(var.orchestrator_dry_run) },
        { name = "ORCHESTRATOR_LOCK_TABLE", value = aws_dynamodb_table.orchestrator_locks.name },
        { name = "ALERTS_SNS_TOPIC", value = var.sns_alert_topic_arn },
        { name = "ALERT_EMAIL_TO", value = var.alert_email_to },
        { name = "ALERT_WEBHOOK_URL", value = var.alert_webhook_url },
        { name = "SEC_USER_AGENT", value = "algo-trading argeropolos@gmail.com" },
        { name = "PYTHONPATH", value = "/app" }
      ]
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024" # More CPU for complex calculations than loaders
  memory                   = "2048" # More memory for 7-phase trading orchestration
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  tags = var.common_tags
}

# ============================================================
# Data Patrol ECS Task Definition (On-Demand Data Monitoring)
#
# Invoked via API endpoint /api/algo/patrol to validate data freshness.
# Checks: stock_symbols count, latest price dates, signal computation status.
# ============================================================

resource "null_resource" "ensure_patrol_log_group" {
  provisioner "local-exec" {
    command = "aws logs create-log-group --log-group-name /ecs/${var.project_name}-data-patrol --region ${var.aws_region} 2>/dev/null || true"
  }
}

resource "aws_ecs_task_definition" "data_patrol" {
  depends_on = [null_resource.ensure_patrol_log_group]

  family = "${var.project_name}-data-patrol"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-data-patrol"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      essential = true

      # Do NOT prefix with "python3" — ENTRYPOINT ["python3", "-u"] already provides the interpreter.
      command = ["algo/algo_data_patrol.py"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-data-patrol"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      secrets = [
        { name = "DB_PASSWORD", valueFrom = "${var.db_secret_arn}:password::" },
        { name = "DB_USER", valueFrom = "${var.db_secret_arn}:username::" }
      ]

      environment = [
        { name = "AWS_REGION", value = var.aws_region },
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_SECRET_ARN", value = var.db_secret_arn },
        { name = "ALGO_SECRETS_ARN", value = var.algo_secrets_arn },
        { name = "DB_SSL", value = var.db_ssl_mode },
        { name = "SEC_USER_AGENT", value = "algo-trading argeropolos@gmail.com" },
        { name = "PYTHONPATH", value = "/app" }
      ]
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"  # Smaller than orchestrator (256 was too small)
  memory                   = "1024" # Basic monitoring task
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  tags = var.common_tags
}

# ============================================================
# CloudWatch Alarm — SQS DLQ depth (any loader failure lands here)
# ============================================================

resource "aws_cloudwatch_metric_alarm" "loader_dlq_messages" {
  alarm_name          = "${var.project_name}-loader-dlq-messages-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "One or more EventBridge loader targets failed and landed in the DLQ"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.loader_dlq.name
  }

  alarm_actions = var.sns_alert_topic_arn != "" ? [var.sns_alert_topic_arn] : []

  tags = var.common_tags
}

# ============================================================
# Outputs
# ============================================================

output "orchestrator_locks_table_name" {
  value       = aws_dynamodb_table.orchestrator_locks.name
  description = "Name of the DynamoDB table for distributed orchestrator locking"
}
