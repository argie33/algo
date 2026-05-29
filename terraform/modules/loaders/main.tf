/**
 * Loaders Module - ECS Task Definitions, EventBridge Scheduled Rules
 *
 * Creates:
 * - 36 ECS task definitions (data loaders)
 * - 26 EventBridge scheduled rules (staggered ET schedule)
 * - IAM roles for EventBridge and ECS task execution
 *
 * NOTE: 13 EOD-critical loaders are now triggered by Step Functions (modules/pipeline)
 * not by EventBridge cron rules. Task definitions remain here for Step Functions to use.

 * Financial loaders run daily at 4am ET (after market close) to maximize data coverage and capture incremental updates
 * Analyst data (sentiment, upgrades/downgrades), earnings calendar, and industry rankings now run daily for better signal coverage
 * Removed: market_overview, sector_performance, relative_performance, social_sentiment
 *   (no real data source; market_overview duplicated price_daily; others wrote zeros/wrong data).
 *
 * All loaders run on Fargate in private subnets with proper resource allocation
 */

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

# ============================================================
# DynamoDB Table for Orchestrator Distributed Locking
# FIXED Issue #8: Replaced filesystem locks with DynamoDB for Fargate
# ============================================================

resource "aws_dynamodb_table" "orchestrator_locks" {
  name         = "${var.project_name}-orchestrator-locks-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "lock_key"

  attribute {
    name = "lock_key"
    type = "S"
  }

  # TTL: lock entries expire after 15 minutes (prevents stale locks)
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-orchestrator-locks"
  })
}

# ============================================================
# DynamoDB Table for Loader Execution Status
# FIXED Issue #30: Separate loader status from lock TTL
# ============================================================
# Tracks successful/failed loader runs independently of locking mechanism.
# Status retained for 1 hour (3600s), giving time for monitoring/debugging.
# Separate from orchestrator_locks which has 15-minute TTL for distributed coordination.

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
    type = "S" # ISO8601 date string
  }

  # TTL: status entries expire after 1 hour (3600 seconds)
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-loader-status"
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

# Grant ECS tasks permission to access the lock table
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
          "dynamodb:DeleteItem"
        ]
        Resource = aws_dynamodb_table.orchestrator_locks.arn
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

locals {
  # Maps each Terraform loader key to the actual Python script filename.
  # This maps to the 33 actual loaders in loaders/ directory.
  loader_file_map = {
    # Reference data
    "stock_symbols"             = "load_stock_symbols.py"
    "sp500_constituents"        = "load_sp500_constituents.py"
    "russell2000_constituents"  = "load_russell2000_constituents.py"

    # Pricing data — unified loader handles all intervals/asset classes via env vars
    "stock_prices_daily"        = "load_stock_prices_daily.py"

    # Financial statements
    "financials_annual_income"  = "load_income_statement.py"
    "financials_annual_balance" = "load_balance_sheet.py"
    "financials_annual_cashflow" = "load_cash_flow.py"
    "financials_quarterly_income" = "load_income_statement.py"
    "financials_quarterly_balance" = "load_balance_sheet.py"
    "financials_quarterly_cashflow" = "load_cash_flow.py"
    "financials_ttm_income"     = "load_income_statement.py"
    "financials_ttm_cashflow"   = "load_cash_flow.py"

    # Computed metrics
    "growth_metrics"            = "load_growth_metrics.py"
    "quality_metrics"           = "load_quality_metrics.py"
    "value_metrics"             = "load_value_metrics.py"
    "positioning_metrics"       = "load_positioning_metrics.py"
    "stability_metrics"         = "load_stability_metrics.py"
    "stock_scores"              = "load_stock_scores.py"

    # Earnings data
    "earnings_history"          = "load_earnings_history.py"
    "earnings_calendar"         = "load_earnings_calendar.py"

    # Company & analyst data
    "company_profile"           = "load_company_profile.py"
    "analyst_sentiment"         = "load_analyst_sentiment_analysis.py"
    "analyst_upgrades_downgrades" = "load_analyst_upgrade_downgrade.py"
    "industry_ranking"          = "load_industry_ranking.py"

    # Market sentiment
    "feargreed"                 = "load_fear_greed_index.py"
    "aaiidata"                  = "load_aaii_sentiment.py"
    "naaim_data"                = "load_naaim.py"

    # Sentiment aggregation
    "sentiment"                 = "load_sentiment.py"
    "sentiment_social"          = "load_sentiment_social.py"

    # Trading signals & scores
    "signal_themes"             = "load_signal_themes.py"
    "signal_quality_scores"     = "load_signal_quality_scores.py"
    "buy_sell_daily"            = "load_buy_sell_daily.py"

    # Technical indicators & metrics
    "technical_data_daily"      = "load_technical_data_daily.py"
    "algo_metrics_daily"        = "load_algo_metrics_daily.py"
    "swing_trader_scores"       = "load_swing_trader_scores.py"

    # Market health & economic data
    "market_health_daily"       = "load_market_health_daily.py"
    "fred_economic_data"        = "load_fred_economic_data.py"
    "trend_template_data"       = "load_trend_criteria_data.py"
  }

  scheduled_loaders = {
    # Morning batch — staggered to prevent resource contention
    # 3:25am ET = 8:25am UTC Mon-Fri
    "stock_symbols" = {
      schedule    = "cron(25 8 ? * MON-FRI *)"
      description = "Stock symbols reference data - 3:25am ET"
    }

    # 3:30am ET = 8:30am UTC Mon-Fri (runs after stock_symbols to mark S&P 500 constituents)
    "sp500_constituents" = {
      schedule    = "cron(30 8 ? * MON-FRI *)"
      description = "S&P 500 constituent symbols - 3:30am ET (after stock_symbols)"
    }

    # 3:35am ET = 8:35am UTC Mon-Fri (runs after S&P 500 to mark Russell 2000 constituents)
    "russell2000_constituents" = {
      schedule    = "cron(35 8 ? * MON-FRI *)"
      description = "Russell 2000 small-cap constituent symbols - 3:35am ET (after sp500_constituents)"
    }

    # 4:00am ET = 9am UTC Mon-Fri
    "stock_prices_daily" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Unified price loader: daily, weekly, monthly for stocks and ETFs - 4:00am ET"
    }

    # FIXED Issue #14: Moved from 4:05am to 4:30pm ET to provide fresh data for EOD pipeline
    # Previously ran 4:05am ET but EOD pipeline runs 4:05pm ET same day, making data stale
    # 4:30pm ET = 20:30 UTC Mon-Fri — runs after market close, feeds into EOD market health
    "fred_economic_data" = {
      schedule    = "cron(30 20 ? * MON-FRI *)"
      description = "FRED economic indicators (T10Y2Y, yields, jobless claims) - 4:30pm ET (before EOD pipeline)"
    }

    # 4:30am ET = 9:30am UTC Mon-Fri — runs AFTER stock_prices_daily (4:00am UTC 9:00)
    # so market health is computed from freshly loaded prices, not yesterday's prices
    "market_data_batch" = {
      schedule    = "cron(30 9 ? * MON-FRI *)"
      description = "Market data batch: 8 tiny loaders in parallel - 4:30am ET"
    }

    # Financial statements — run Sunday night only (data changes quarterly, not daily)
    # STAGGERED: 60-minute intervals to prevent concurrent SEC EDGAR rate limit cascades
    # Each loader parallelism=1, 2 req/sec per task, max 1 concurrent = 2 req/sec total (safe)
    "financials_annual_income" = {
      schedule    = "cron(0 3 ? * MON *)"
      description = "Annual income statements - Sunday 10:00pm ET"
    }
    "financials_annual_balance" = {
      schedule    = "cron(0 4 ? * MON *)"
      description = "Annual balance sheets - Sunday 11:00pm ET"
    }
    "financials_annual_cashflow" = {
      schedule    = "cron(0 5 ? * MON *)"
      description = "Annual cash flow - Monday 12:00am ET"
    }
    "financials_quarterly_income" = {
      schedule    = "cron(0 6 ? * MON *)"
      description = "Quarterly income statements - Monday 1:00am ET"
    }
    "financials_quarterly_balance" = {
      schedule    = "cron(0 7 ? * MON *)"
      description = "Quarterly balance sheets - Monday 2:00am ET"
    }
    "financials_quarterly_cashflow" = {
      schedule    = "cron(0 8 ? * MON *)"
      description = "Quarterly cash flow - Monday 3:00am ET"
    }

    # TTM loaders depend on quarterly data — run 1 hour after last quarterly (08:00 + 1h = 09:00)
    # These are pure SQL aggregation (no SEC EDGAR), safe to run sequentially or even together
    # Run at 09:00 and 10:00 to be conservative (1h buffer after quarterly_cashflow at 08:00)
    "financials_ttm_income" = {
      schedule    = "cron(0 9 ? * MON *)"
      description = "TTM income statements - Monday 4:00am ET"
    }
    "financials_ttm_cashflow" = {
      schedule    = "cron(0 10 ? * MON *)"
      description = "TTM cash flow - Monday 5:00am ET"
    }

    # Computed metrics — run daily after market close (4pm ET) so issues can be fixed before next trading day
    # 21:00 UTC = 5pm EDT / 6pm EST (safe margin after 4pm market close)
    # STAGGERED: 2-minute intervals to prevent simultaneous runs
    "growth_metrics" = {
      schedule    = "cron(0 21 ? * MON-FRI *)"
      description = "Growth metrics (revenue/EPS growth) - Daily 5:00pm ET"
    }
    "quality_metrics" = {
      schedule    = "cron(2 21 ? * MON-FRI *)"
      description = "Quality metrics (ROE, margins, D/E) - Daily 5:02pm ET"
    }
    "value_metrics" = {
      schedule    = "cron(4 21 ? * MON-FRI *)"
      description = "Value metrics (P/E, P/B, P/S ratios) - Daily 5:04pm ET"
    }
    "stability_metrics" = {
      schedule    = "cron(6 21 ? * MON-FRI *)"
      description = "Stability metrics (beta, volatility) - Daily 5:06pm ET"
    }
    # stock_scores runs after all per-symbol metric tables (quality/growth/value/stability) are populated
    "stock_scores" = {
      schedule    = "cron(30 21 ? * MON-FRI *)"
      description = "Multi-factor composite stock scores - Daily 5:30pm ET (after all metrics)"
    }

    # Earnings — run Sunday night only (data changes quarterly)
    "earnings_history" = {
      schedule    = "cron(15 4 ? * MON *)"
      description = "Earnings history - Sunday 11:15pm ET"
    }

    # Company and analyst data — yfinance API calls, run daily at 4am ET (after market close previous day)
    # Data sources update frequently, daily refresh captures more coverage (analyst sentiment, earnings calendar changes, etc.)
    "company_profile" = {
      schedule    = "cron(20 4 ? * MON-FRI *)"
      description = "Company profile (sector, industry, name) - Daily 4:20am ET"
    }
    "positioning_metrics" = {
      schedule    = "cron(22 4 ? * MON-FRI *)"
      description = "Positioning metrics (institutional ownership, short interest) - Daily 4:22am ET"
    }
    "analyst_sentiment" = {
      schedule    = "cron(25 4 ? * MON-FRI *)"
      description = "Analyst recommendations - Daily 4:25am ET"
    }
    "analyst_upgrades_downgrades" = {
      schedule    = "cron(27 4 ? * MON-FRI *)"
      description = "Analyst upgrades/downgrades - Daily 4:27am ET"
    }
    "industry_ranking" = {
      schedule    = "cron(10 6 ? * MON-FRI *)"
      description = "Industry rankings - Daily 1:10am ET"
    }
    "earnings_calendar" = {
      schedule    = "cron(29 4 ? * MON-FRI *)"
      description = "Earnings calendar (next 180 days) - Daily 4:29am ET"
    }

    # Market sentiment data — run daily (data published at irregular intervals, daily refresh is fine)
    # STAGGERED: Prevent simultaneous API calls
    "feargreed" = {
      schedule    = "cron(2 22 ? * MON-FRI *)"
      description = "CNN Fear & Greed index - Daily 6:02pm ET"
    }
    "aaiidata" = {
      schedule    = "cron(0 4 ? * FRI *)"
      description = "AAII investor sentiment survey - Weekly Friday 12am ET (survey publishes Thursday)"
    }
    "naaim_data" = {
      schedule    = "cron(5 4 ? * FRI *)"
      description = "NAAIM exposure index - Weekly Friday 12:05am ET (publishes Wednesdays)"
    }

    # Sentiment loaders (aggregate) — run daily at 4am ET
    "sentiment" = {
      schedule    = "cron(32 4 ? * MON-FRI *)"
      description = "Aggregate sentiment index - Daily 4:32am ET"
    }
    "sentiment_social" = {
      schedule    = "cron(34 4 ? * MON-FRI *)"
      description = "Social media sentiment - Daily 4:34am ET"
    }

    # Signal theme — run after signals generated
    # 10:00am UTC = 5:00am ET Mon-Fri
    "signal_themes" = {
      schedule    = "cron(0 10 ? * MON-FRI *)"
      description = "Signal themes (momentum/reversal/breakout) - Daily 5:00am ET"
    }

    # NOTE: These loaders are managed via the Step Functions EOD pipeline:
    # - trend_template_data, signal_quality_scores, technical_data_daily,
    #   algo_metrics_daily, swing_trader_scores, buy_sell_daily
    # Task definitions remain in all_loaders for Step Functions to reference.
  }
}

# FIXED Issue #29: EventBridge Rule Naming Convention
# Rule name format: {project}-{loader_name}-schedule
# Examples: algo-stock_symbols-schedule, algo-price_daily-schedule, algo-signals_daily-schedule
# Matches task definition naming: {project}-{loader_name}-loader
# Enables operators to correlate rules with tasks by name

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
    # Reference data — tiny lists, parallelism=1
    "stock_symbols"         = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }
    "sp500_constituents"    = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }
    "russell2000_constituents" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }

    # Unified Price Loader — handles all intervals (1d,1wk,1mo) + asset classes (stock,etf)
    # I/O bound, 5000+ symbols, needs 2.5-3h for all combinations; 6h timeout ensures completion
    "stock_prices_daily" = { cpu = 2048, memory = 4096, timeout = 21600, parallelism = 4 }

    # Financial statements — reduce parallelism to 1 to prevent SEC EDGAR rate-limit cascade
    "financials_annual_income"      = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_annual_balance"     = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_annual_cashflow"    = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_quarterly_income"   = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_quarterly_balance"  = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_quarterly_cashflow" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_ttm_income"         = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_ttm_cashflow"       = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }

    # Computed metrics — CPU bound, process 5000+ symbols, need parallelism
    "growth_metrics"      = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }
    "quality_metrics"     = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }
    "value_metrics"       = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }
    "positioning_metrics" = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }
    "stability_metrics"   = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 8 }
    "stock_scores"        = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }

    # Earnings data — reduce parallelism to 1 to prevent SEC EDGAR rate-limit cascade
    "earnings_history"  = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "earnings_calendar" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }

    # Company & analyst data — I/O bound, yfinance API calls, 5000+ symbols
    "company_profile"             = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }
    "analyst_sentiment"           = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }
    "analyst_upgrades_downgrades" = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }
    "industry_ranking"            = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 4 }

    # Market sentiment data — small API calls
    "feargreed"  = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "aaiidata"   = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "naaim_data" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }

    # Sentiment aggregation — combine multiple sentiment sources
    "sentiment"        = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "sentiment_social" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }

    # Signal processing — compute signal themes
    "signal_themes"         = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 4 }
    "signal_quality_scores" = { cpu = 1024, memory = 2048, timeout = 5400, parallelism = 4 }

    # BUY/SELL signals — compute trade signals for all 5000+ symbols
    "buy_sell_daily" = { cpu = 2048, memory = 4096, timeout = 21600, parallelism = 4 }

    # Technical indicators — compute-heavy, 5000+ symbols
    "technical_data_daily" = { cpu = 4096, memory = 8192, timeout = 36000, parallelism = 8 }

    # Market health — reads price_daily, processes 5000+ symbols
    "market_health_daily" = { cpu = 256, memory = 512, timeout = 1200, parallelism = 1 }

    # Algo metrics — compute metrics on 5000+ symbols
    "algo_metrics_daily" = { cpu = 1024, memory = 2048, timeout = 10800, parallelism = 1 }

    # Swing trader scores — compute-heavy scoring
    "swing_trader_scores" = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }

    # FRED macro data — small API calls, 5 time series
    "fred_economic_data" = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }

    # Trend template — compute-heavy scoring
    "trend_template_data" = { cpu = 2048, memory = 4096, timeout = 5400, parallelism = 4 }
  }

  # For backward compatibility
  default_loaders = local.all_loaders

  # Loaders that must run on on-demand FARGATE (cannot tolerate interruption)
  critical_loaders = toset([
    "stock_prices_daily",
    "algo_metrics_daily",
    "stock_scores",
    "buy_sell_daily",
    "signal_quality_scores"
  ])
}

# ECS Task Definitions for all 33 data loaders
# NOTE: CPU/memory in container definition are removed - only task-level values matter for Fargate
resource "aws_ecs_task_definition" "loader" {
  for_each = local.all_loaders

  depends_on = [null_resource.ensure_log_group]

  family = "${var.project_name}-${each.key}-loader"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-${each.key}"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      essential = true
      command   = ["python3", "-u", "loaders/${local.loader_file_map[each.key]}"]

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
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
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
          name  = "ALPACA_PAPER_TRADING"
          value = tostring(var.alpaca_paper_trading)
        },
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
        {
          name  = "ORCHESTRATOR_EXECUTION_MODE"
          value = var.execution_mode
        },
        {
          name  = "ORCHESTRATOR_DRY_RUN"
          value = tostring(var.orchestrator_dry_run)
        },
        {
          name  = "ALERT_EMAIL_TO"
          value = var.alert_email_to
        },
        {
          name  = "ALERT_WEBHOOK_URL"
          value = var.alert_webhook_url
        }
        ],
        # Price loaders: set intervals based on task name
        each.key == "stock_prices_daily" ? [
          {
            name  = "LOADER_INTERVALS"
            value = "1d,1wk,1mo"
          },
          {
            name  = "LOADER_ASSET_CLASSES"
            value = "stock,etf"
          }
          ] : each.key == "eod_bulk_refresh" ? [
          {
            name  = "LOADER_INTERVALS"
            value = "1d"
          },
          {
            name  = "LOADER_ASSET_CLASSES"
            value = "stock,etf"
          }
          ] : each.key == "stock_prices_weekly" ? [
          {
            name  = "LOADER_INTERVALS"
            value = "1wk"
          },
          {
            name  = "LOADER_ASSET_CLASSES"
            value = "stock,etf"
          }
        ] : [],
        # Financial loaders: determine period from task name
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
# Continuous Monitor — ECS Task + EventBridge (every 15 min)
# Runs algo_continuous_monitor.py --once; script self-skips outside market hours
# ============================================================

resource "null_resource" "ensure_continuous_monitor_log_group" {
  provisioner "local-exec" {
    command = "aws logs create-log-group --log-group-name /ecs/${var.project_name}-continuous-monitor --region ${var.aws_region} 2>/dev/null || true"
  }
}

resource "aws_ecs_task_definition" "continuous_monitor" {
  depends_on = [null_resource.ensure_continuous_monitor_log_group]

  family = "${var.project_name}-continuous-monitor"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-continuous-monitor"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      essential = true
      command   = ["python3", "-u", "loaders/algo_continuous_monitor.py"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-continuous-monitor"
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
        { name = "LOADER_FILE", value = "algo_continuous_monitor.py" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "ALPACA_PAPER_TRADING", value = tostring(var.alpaca_paper_trading) }
      ]
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  tags = var.common_tags
}

resource "aws_cloudwatch_event_rule" "continuous_monitor" {
  name                = "${var.project_name}-continuous-monitor-${var.environment}"
  description         = "Run continuous monitor every 15 minutes (script skips when market closed)"
  schedule_expression = "rate(15 minutes)"
  state               = "ENABLED"

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "continuous_monitor" {
  rule      = aws_cloudwatch_event_rule.continuous_monitor.name
  target_id = "ContinuousMonitorTarget"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.eventbridge_run_task.arn

  ecs_target {
    launch_type         = "FARGATE"
    task_definition_arn = aws_ecs_task_definition.continuous_monitor.arn
    task_count          = 1
    platform_version    = "LATEST"

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

      # Orchestrator entry point: python3 algo/algo_orchestrator.py [args]
      # Step Functions passes mode and dry_run as environment variables
      command = ["python3", "algo/algo_orchestrator.py"]

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
        { name = "ALPACA_PAPER_TRADING", value = tostring(var.alpaca_paper_trading) },
        { name = "ORCHESTRATOR_LOG_LEVEL", value = var.orchestrator_log_level },
        { name = "ORCHESTRATOR_EXECUTION_MODE", value = var.execution_mode },
        { name = "ORCHESTRATOR_DRY_RUN", value = tostring(var.orchestrator_dry_run) },
        { name = "ORCHESTRATOR_LOCK_TABLE", value = aws_dynamodb_table.orchestrator_locks.name },
        { name = "SEC_USER_AGENT", value = "algo-trading argeropolos@gmail.com" }
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

      command = ["python3", "algo_data_patrol.py"]

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
        { name = "SEC_USER_AGENT", value = "algo-trading argeropolos@gmail.com" }
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
# Weight Optimization ECS Task Definition (Daily Continuous Improvement Loop)
#
# Invoked daily at 6:00 PM ET (after orchestrator completes)
# Populates signal_trade_performance → computes IC → optimizes swing_score weights
# Reads closed trades, computes information coefficients, adapts component weights
# ============================================================

resource "null_resource" "ensure_weight_optimization_log_group" {
  provisioner "local-exec" {
    command = "aws logs create-log-group --log-group-name /ecs/${var.project_name}-weight-optimization --region ${var.aws_region} 2>/dev/null || true"
  }
}

resource "aws_ecs_task_definition" "weight_optimization" {
  depends_on = [null_resource.ensure_weight_optimization_log_group]

  family = "${var.project_name}-weight-optimization"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-weight-optimization"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      essential = true

      command = ["python3", "-m", "loaders.load_weight_optimization"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-weight-optimization"
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
        { name = "LOG_LEVEL", value = "info" }
      ]
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"  # Lightweight computation (IC + weight optimization)
  memory                   = "1024" # Moderate memory for in-memory IC calculations
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  tags = var.common_tags
}

# Weight Optimization — triggered via EventBridge Scheduler in services/2x-daily-orchestrator.tf
# No longer triggered here via classic EventBridge (consolidated in services module)

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
