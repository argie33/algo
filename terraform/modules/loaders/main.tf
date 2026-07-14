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

# ============================================================
# SQS Dead-Letter Queue for EventBridge Scheduler (Step Functions)
# ============================================================
# Captures failed Step Functions invocations from EventBridge Scheduler
# (Separate from loader_dlq which handles EventBridge Event Rules)

resource "aws_sqs_queue" "scheduler_dlq" {
  name                      = "${var.project_name}-scheduler-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-scheduler-dlq"
  })
}

resource "aws_sqs_queue_policy" "scheduler_dlq" {
  queue_url = aws_sqs_queue.scheduler_dlq.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowSchedulerSend"
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.scheduler_dlq.arn
    }]
  })
}

# ============================================================
# CloudWatch Log Group for EventBridge Scheduler Execution Logs
# ============================================================

resource "aws_cloudwatch_log_group" "scheduler_logs" {
  name              = "/aws/scheduler/${var.project_name}-pipeline-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-scheduler-logs"
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
    "technical_data_daily"  = "load_technical_indicators.py"
    "trend_template_data"   = "load_trend_analysis.py"
    "market_exposure_daily" = "load_market_exposure_daily.py"
    "yfinance_snapshot"     = "load_yfinance_snapshot.py"
    # Consolidated: both quality + growth from single loader (fetch SEC once, compute both)
    # Computed metrics from SEC financials (DEPENDS ON: financials_annual_income, financials_annual_balance)
    # Reads annual_income_statement & annual_balance_sheet tables populated by load_financial_statements.py
    "quality_metrics" = "load_quality_growth_metrics.py"
    "growth_metrics"  = "load_quality_growth_metrics.py"
    # Consolidated yfinance readers: 1 loader → 7 output tables (read snapshot once, write to 7 tables in parallel)
    # Output tables: value_metrics, positioning_metrics, company_profile, analyst_sentiment_analysis,
    #               analyst_upgrade_downgrade, earnings_calendar, earnings_history
    "value_metrics"       = "load_yfinance_derived_metrics.py"
    "positioning_metrics" = "load_yfinance_derived_metrics.py"
    "company_profile"     = "load_yfinance_derived_metrics.py"
    "earnings_history"    = "load_yfinance_derived_metrics.py"
    "earnings_calendar"   = "load_yfinance_derived_metrics.py"
    # Consolidated: Both metrics from single loader (Phase 5 optimization - single pass, unified watermark)
    "stability_metrics" = "load_risk_metrics_daily.py"
    "momentum_metrics"  = "load_risk_metrics_daily.py"
    "stock_scores"      = "load_stock_scores.py"

    "market_constituents" = "load_market_constituents.py"
    "market_health_daily" = "load_market_health_daily.py"
    "market_sentiment"    = "load_market_sentiment.py"
    # Consolidated market rankings loader (replaces 2 separate loaders)
    "sector_ranking"     = "load_sector_rankings.py"
    "industry_ranking"   = "load_sector_rankings.py"
    "algo_metrics_daily" = "load_algo_metrics_daily.py"
    "buy_sell_daily"     = "load_buy_sell_daily.py"

    # Consolidated economic data: FRED (T10Y2Y, FEDFUNDS, BAMLH0A0HYM2, ICSA) + DXY
    # Feeds into market_exposure calculations for regime detection
    # CONSOLIDATION: Merged load_fred_economic_data.py + load_dxy_index.py to eliminate
    # race condition (both were writing economic_data table with different schedules)
    "economic_data" = "load_economic_data.py"

    # Consolidated financial statements loader (replaces 8 separate loaders)
    # ACTIVATED (2026-07-12): Loader now supports LOADER_STATEMENT_TYPE="all"
    # to load all 8 statement/period combinations in sequence within single container.
    # Single task replaces 8 parallel branches, saving $8-15/mo + 40-80s per execution
    "financials_all" = "load_financial_statements.py"

    # Sector performance loader (optional, not in critical path)
    "sector_performance" = "load_sector_performance.py"
  }

  # ============================================================
  # CRITICAL: ALL PRODUCTION LOADERS NOW SCHEDULED VIA STEP FUNCTIONS
  # ============================================================
  # Morning pipeline (2:00 AM ET): stock prices, technical indicators
  # Evening pipeline (4:00 PM ET): all metrics, scores, rankings, signals
  # See: terraform/modules/pipeline/main.tf for complete dependency graph
  #
  # EventBridge is NOW ONLY for OPTIONAL enrichment data (weekly).
  # All critical loaders consolidated into Step Functions for:
  # - Explicit dependency ordering (not time-based guessing)
  # - Single source of truth (readable in terraform)
  # - No duplicate execution (was running same loaders via both systems)
  # - Cost savings (eliminated $100-150/month in duplicates)
  # ============================================================

  scheduled_loaders = {
    # ALL LOADERS NOW RUN VIA STEP FUNCTIONS PIPELINE (modules/pipeline/main.tf)
    # EventBridge has been fully consolidated into Step Functions for:
    # - Explicit dependency ordering (not time-based guessing)
    # - Single source of truth (readable in terraform)
    # - No duplicate execution (was running same loaders via both systems)
    # - Cost savings (eliminated ~$100-150/month in duplicates)
    #
    # This map is empty but kept for reference (infrastructure already provisioned)
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
    # REVERTED (session 113): 512/1024 cost-cut was OOM-killing this task in prod
    # (ExitCode 137, "container killed due to memory usage" - confirmed via
    # Step Functions execution history + CloudWatch logs). Root cause: AWS_REGION
    # wasn't reaching the container at runtime (see undeployed-fixes finding), so
    # the loader ran with local-dev batch_size=500 instead of AWS batch_size=20,
    # loading far more into memory per batch than this config assumed.
    # Restoring 1024/2048 as a safety margin; batch_size=20 fix should let this
    # run comfortably once deploys are unblocked and AWS_REGION is confirmed live.
    "stock_prices_daily" = { cpu = 1024, memory = 2048, timeout = 5400, parallelism = 1 }
    # FIXED (2026-07-12): Reduced from 4096 to 1024 (actual peak ~300MB, 3-4x headroom sufficient)
    # FIXED (2026-07-13): memory=1024 is not a valid Fargate combo for cpu=1024 (min is 2048) -
    # ECS RegisterTaskDefinition rejected this outright, blocking every terraform apply.
    # FIXED (2026-07-13, later): the "~300MB peak" estimate assumed normal single-day
    # incremental runs. After the multi-day price-loader stall (stock_prices_daily lock
    # bug), this task had a multi-day backlog to recompute in one run and was OOM-killed
    # (exit 137) twice in a row at 2048MB. Bumped to 4096MB for backlog-catch-up headroom.
    "technical_data_daily" = { cpu = 1024, memory = 4096, timeout = 2400, parallelism = 1 }
    "trend_template_data"  = { cpu = 1024, memory = 2048, timeout = 5400, parallelism = 1 }
    # FIXED (2026-07-12): Reduced timeout 600s→120s (actual runtime ~10-30s, 2x headroom)
    "market_exposure_daily" = { cpu = 256, memory = 512, timeout = 120, parallelism = 1 }
    "yfinance_snapshot"     = { cpu = 1024, memory = 2048, timeout = 7200, parallelism = 1 }
    # Cost-optimized: Reduced from 2048 to 512 (yfinance API fetch + lightweight metric calc, <100MB actual)
    "growth_metrics" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 2 }
    # Cost-optimized: Reduced from 2048 to 512 (SEC filing parse + DB insert, <100MB actual)
    "quality_metrics" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 2 }
    # Consolidated yfinance readers: All read from yfinance_snapshot, write to different tables
    # Previously 6 separate tasks (value, positioning, company_profile, analyst×2, earnings×2)
    # Now consolidated into 1 loader that reads snapshot once, writes to 6 tables in parallel
    # FIXED: Parallelism reduced from 4 to 1 to match config.py constraints and prevent yfinance rate limiting
    # Shared NAT IP across 6 ECS tasks causes cascade failures when parallelism > 1
    "value_metrics"       = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }
    "positioning_metrics" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }
    # Reduced memory from 1024 to 512 (actual peak usage <100MB for parsing metadata)
    "company_profile"   = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }
    "earnings_history"  = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }
    "earnings_calendar" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }
    # Cost-optimized: Reduced from 1024 to 512 (dividend + payout ratio queries, <50MB actual)
    "stability_metrics" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }
    # Cost-optimized: Reduced from 1024 to 512 (return calculations on historical prices, <80MB actual)
    "momentum_metrics" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }
    # Cost-optimized: Reduced from 2048 to 1024 (score aggregation, vectorized SQL, moderate memory for DF ops)
    # FIXED (2026-07-13): memory=1024 is not a valid Fargate combo for cpu=1024 (min is 2048) -
    # ECS RegisterTaskDefinition rejected this outright, blocking every terraform apply.
    "stock_scores" = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 2 }

    # FIXED (2026-07-12): Reduced timeout 600s→120s (actual runtime ~30-60s, 2x headroom)
    "market_constituents" = { cpu = 256, memory = 512, timeout = 120, parallelism = 1 }
    "market_health_daily" = { cpu = 256, memory = 512, timeout = 1200, parallelism = 1 }
    # FIXED (2026-07-12): Reduced timeout 300s→60s (actual runtime ~3-5s, 10x+ over-provisioned)
    "market_sentiment" = { cpu = 256, memory = 512, timeout = 60, parallelism = 1 }
    # Consolidated economic data loader: FRED series + DXY (lightweight: API calls + DB writes)
    "economic_data" = { cpu = 256, memory = 512, timeout = 900, parallelism = 1 }
    # Cost-optimized: Reduced from 1024 to 512 (sector ranking DB queries, <50MB actual)
    "sector_ranking"   = { cpu = 512, memory = 1024, timeout = 900, parallelism = 1 }
    "industry_ranking" = { cpu = 512, memory = 1024, timeout = 900, parallelism = 1 }
    # FIXED (2026-07-12): Reduced memory 2048→512 (actual ~150MB), timeout 10800s→600s (actual ~5-10m, 2x headroom)
    # FIXED (2026-07-13): cpu=1024/memory=512 is not a valid Fargate combo (1024 cpu needs
    # memory>=2048) - ECS RegisterTaskDefinition rejected this, blocking every terraform apply.
    # Actual usage (~150MB) doesn't need 1024 cpu either, so drop to 256/512 (valid, cheaper,
    # matches the other lightweight reporting loaders below) instead of bumping memory to 2048.
    "algo_metrics_daily" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    # Cost-optimized: Reduced from 2048/4096 (signal generation: talib calculations + DB queries, moderate CPU)
    "buy_sell_daily" = { cpu = 1024, memory = 2048, timeout = 2400, parallelism = 2 }
    # NOTE: analyst_sentiment + analyst_upgrades_downgrades are outputs from load_yfinance_derived_metrics.py, not separate tasks
    # They share ECS task definition with other yfinance-derived metrics (value, positioning, company_profile, earnings*)

    # FIXED (2026-07-12): Reduced timeout 15000s→3600s (actual ~16-20m, 3x headroom still generous)
    # Consolidated: All 8 statement types in single task (runs sequentially)
    "financials_all" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }

    # Cost-optimized: Reduced from 1024 to 512 (sector performance ranking, <50MB actual)
    "sector_performance" = { cpu = 512, memory = 1024, timeout = 900, parallelism = 1 }
  }
  default_loaders = local.all_loaders

  # Loaders that must run on on-demand FARGATE (cannot tolerate interruption)
  critical_loaders = toset([
    "stock_prices_daily",
    "algo_metrics_daily",
    "stock_scores",
    "buy_sell_daily",
    "yfinance_snapshot",
    "economic_data",  # Consolidated (FRED + DXY)
    "financials_all", # Consolidated financial statements (replaces 8 individual tasks)
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
        # DATABASE insert chunk (rows per staged COPY+upsert). This is NOT an API batch —
        # the old value of 100 was justified as yfinance rate limiting, which chunking of
        # DB writes has nothing to do with; it just multiplied staging-table cycles.
        {
          name  = "LOADER_CHUNK_SIZE"
          value = "5000"
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
        # Daily-bar OHLCV source (source_router: alpaca = batched SIP bars with
        # automatic yfinance fallback; caret index symbols always stay on yfinance)
        {
          name  = "PRICE_DATA_SOURCE"
          value = var.price_data_source
        },
        # Alpaca data feed: sip = consolidated-tape (all 13 exchanges, default)
        # iex = IEX exchange only (smaller volume, not recommended)
        {
          name  = "ALPACA_DATA_FEED"
          value = "sip"
        },
        # Alpaca data rate limit (free plan allows 200/min, we use 190 for safety margin)
        {
          name  = "ALPACA_DATA_RATE_LIMIT_PER_MIN"
          value = "190"
        },
        # Alpaca data symbols per request (max 200 per API docs, we use 200)
        {
          name  = "ALPACA_DATA_SYMBOLS_PER_REQUEST"
          value = "200"
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
        },
        # Redis price cache endpoint (90% yfinance API reduction)
        {
          name  = "REDIS_URL"
          value = var.redis_endpoint_address != "" ? "redis://${var.redis_endpoint_address}:${var.redis_port}/0" : ""
        }
        ],
        # Unified price loader: handles all intervals and asset classes
        # OPTIMIZATION 2026-07-10: Load daily only (removed unused weekly/monthly)
        # SESSION 106 FIX: Load stocks only (no ETFs), parallelism=1 to prevent yfinance rate limiting
        each.key == "stock_prices_daily" ? [
          {
            name  = "LOADER_INTERVALS"
            value = "1d"
          },
          {
            name  = "LOADER_ASSET_CLASSES"
            value = "stock"
          },
          {
            name  = "LOADER_PARALLELISM"
            value = "1"
          }
        ] : [],
        # Financial loaders: determine period and statement type from task name
        each.key == "financials_all" ? [
          {
            name  = "LOADER_STATEMENT_TYPE"
            value = "all"
          }
          ] : strcontains(each.key, "annual") ? [
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
        # Statement type (income/balance/cashflow) applies to all period types
        each.key != "financials_all" ? (
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
        ) : []
      )

      # FIXED Issue #14 & Session 101: Health check to detect stalled/zombie loaders
      # ECS will mark task as unhealthy if loader doesn't report within timeout period
      # CRITICAL FIX (Session 101): Increase startPeriod from 60s to 120s
      # Loaders need time to: connect to DB, load config, initialize fetchers
      # If initialization fails, we want quick retry (not blocking for 60+ seconds)
      healthCheck = {
        command     = ["CMD-SHELL", "ps aux | grep -q '[p]ython.*${each.key}' || exit 1"]
        interval    = 30  # Check every 30 seconds
        timeout     = 5   # Timeout for health check command
        retries     = 2   # Mark unhealthy after 2 failed checks (60s total after grace period)
        startPeriod = 120 # Grace period before first health check (was 60s, increased to 120s)
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
