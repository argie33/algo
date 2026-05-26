/**
 * Loaders Module - ECS Task Definitions, EventBridge Scheduled Rules
 *
 * Creates:
 * - 34 ECS task definitions (data loaders)
 * - 22 EventBridge scheduled rules (staggered ET schedule)
 * - IAM roles for EventBridge and ECS task execution
 *
 * NOTE: 13 EOD-critical loaders are now triggered by Step Functions (modules/pipeline)
 * not by EventBridge cron rules. Task definitions remain here for Step Functions to use.

 * Financial/earnings loaders run weekly (Sunday night) not daily.
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
# Scheduled EventBridge Rules - All 40 Loaders
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
  # No longer used directly (Docker CMD specifies the loader).
  # Kept for documentation and potential future use.
  loader_file_map = {
    "stock_symbols"                 = "loadstocksymbols.py"
    "stock_prices_daily"            = "loadpricedaily.py"  # UNIFIED: all intervals (1d,1wk,1mo) + asset classes (stock,etf)
    "stock_prices_weekly"           = "loadpricedaily.py"  # Uses unified loader with env vars for weekly interval
    "etf_prices_daily"              = "loadpricedaily.py"
    "etf_prices_weekly"             = "loadpricedaily.py"
    "etf_prices_monthly"            = "loadpricedaily.py"
    "financials_annual_income"      = "load_income_statement.py"
    "financials_annual_balance"     = "load_balance_sheet.py"
    "financials_annual_cashflow"    = "load_cash_flow.py"
    "financials_quarterly_income"   = "load_income_statement.py"
    "financials_quarterly_balance"  = "load_balance_sheet.py"
    "financials_quarterly_cashflow" = "load_cash_flow.py"
    "financials_ttm_income"         = "load_income_statement.py"
    "financials_ttm_cashflow"       = "load_cash_flow.py"
    "growth_metrics"                = "load_growth_metrics.py"
    "quality_metrics"               = "load_quality_metrics.py"
    "value_metrics"                 = "load_value_metrics.py"
    "positioning_metrics"           = "load_positioning_metrics.py"
    "stability_metrics"             = "load_stability_metrics.py"
    "stock_scores"                  = "load_stock_scores.py"
    "earnings_history"              = "loadearningshistory.py"
    "earnings_revisions"            = "loadearningsrevisions.py"
    "earnings_surprise"             = "loadearningssurprise.py"
    "seasonality"                   = "loadseasonality.py"
    "aaiidata"                      = "load_aaii_sentiment.py"
    "naaim_data"                    = "load_naaim.py"
    "feargreed"                     = "load_fear_greed_index.py"
    "earnings_calendar"             = "load_earnings_calendar.py"
    "company_profile"               = "load_company_profile.py"
    "analyst_sentiment"             = "load_analyst_sentiment_analysis.py"
    "analyst_upgrades_downgrades"   = "load_analyst_upgrade_downgrade.py"
    "sectors"                       = "loadsectors.py"
    "industry_ranking"              = "load_industry_ranking.py"
    "trend_template_data"           = "load_trend_criteria_data.py"
    "signals_daily"                 = "load_signals_daily.py"
    "signal_quality_scores"         = "load_signal_quality_scores.py"
    "signals_weekly"                = "load_signal_quality_scores.py"
    "signals_monthly"               = "load_signal_quality_scores.py"
    "signals_etf_daily"             = "load_signal_quality_scores.py"
    "signals_etf_weekly"            = "load_signal_quality_scores.py"
    "signals_etf_monthly"           = "load_signal_quality_scores.py"
    "algo_metrics_daily"            = "load_algo_metrics_daily.py"
    "market_data_batch"             = "load_market_health_daily.py"
    "technical_data_daily"          = "load_technical_data_daily.py"
    "market_health_daily"           = "load_market_health_daily.py"
    "swing_trader_scores"           = "load_swing_trader_scores.py"
    "stock_scores"                  = "load_signal_quality_scores.py"
    "eod_bulk_refresh"              = "load_stock_prices_daily.py"
  }

  scheduled_loaders = {
    # Morning batch — staggered to prevent resource contention
    # 3:25am ET = 8:25am UTC Mon-Fri
    "stock_symbols" = {
      schedule    = "cron(25 8 ? * MON-FRI *)"
      description = "Stock symbols reference data - 3:25am ET"
    }

    # 4:00am ET = 9am UTC Mon-Fri
    "stock_prices_daily" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Unified price loader: daily, weekly, monthly for stocks and ETFs - 4:00am ET"
    }

    # 4:30am ET = 9:30am UTC Mon-Fri — runs AFTER stock_prices_daily (4:00am UTC 9:00)
    # so market health is computed from freshly loaded prices, not yesterday's prices
    "market_data_batch" = {
      schedule    = "cron(30 9 ? * MON-FRI *)"
      description = "Market data batch: 8 tiny loaders in parallel - 4:30am ET"
    }

    # NOTE: technicals_daily and trend_template_data are now managed by the
    # Step Functions EOD pipeline — removed from scheduled_loaders.

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

    # Earnings — run Sunday night only (data changes quarterly)
    # STAGGERED: Spread across 3 minutes to avoid resource exhaustion
    "earnings_history" = {
      schedule    = "cron(15 4 ? * MON *)"
      description = "Earnings history - Sunday 11:15pm ET"
    }
    "earnings_revisions" = {
      schedule    = "cron(16 4 ? * MON *)"
      description = "Earnings revisions - Sunday 11:16pm ET"
    }
    "earnings_surprise" = {
      schedule    = "cron(17 4 ? * MON *)"
      description = "Earnings surprise - Sunday 11:17pm ET"
    }
    # Seasonality — weekly recompute Sunday night (uses price_daily history, SPY-based)
    "seasonality" = {
      schedule    = "cron(0 5 ? * MON *)"
      description = "Market seasonality stats - Sunday 12am ET (weekly recompute)"
    }

    # Company and analyst data — yfinance API calls, run weekly Sunday
    # Already staggered by 10 minutes - no change needed
    "company_profile" = {
      schedule    = "cron(20 4 ? * MON *)"
      description = "Company profile (sector, industry, name) - Sunday 11:20pm ET"
    }
    "positioning_metrics" = {
      schedule    = "cron(22 4 ? * MON *)"
      description = "Positioning metrics (institutional ownership, short interest) - Sunday 11:22pm ET"
    }
    "analyst_sentiment" = {
      schedule    = "cron(25 4 ? * MON *)"
      description = "Analyst recommendations - Sunday 11:25pm ET"
    }
    "analyst_upgrades_downgrades" = {
      schedule    = "cron(30 4 ? * MON *)"
      description = "Analyst upgrades/downgrades - Sunday 11:30pm ET"
    }
    "sectors" = {
      schedule    = "cron(5 6 ? * MON *)"
      description = "Sector performance metrics - Monday 1:05am ET"
    }
    "industry_ranking" = {
      schedule    = "cron(10 6 ? * MON *)"
      description = "Industry rankings - Monday 1:10am ET"
    }
    "earnings_calendar" = {
      schedule    = "cron(35 4 ? * MON *)"
      description = "Earnings calendar (next 180 days) - Sunday 11:35pm ET"
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

    # NOTE: market_overview, relative_performance, social_sentiment deleted — no real data sources.
    # NOTE: factor_metrics, stock_scores are run via Step Functions EOD pipeline.

    # NOTE: signals_daily, signals_weekly, signals_monthly, signals_etf_daily,
    # signals_etf_weekly, signals_etf_monthly, etf_signals, algo_metrics_daily,
    # and eod_bulk_refresh are now managed by the Step Functions EOD pipeline
    # (terraform/modules/pipeline/). Their EventBridge rules are defined there.
    # Task definitions remain in all_loaders below for Step Functions to reference.
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
    # Reference data (3:30am ET)
    # parallelism=1: tiny list, no benefit from threads
    "stock_symbols" = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }

    # UNIFIED Price Loader (4:00am ET) — handles all intervals (1d,1wk,1mo) + asset classes (stock,etf)
    # Runs sequentially for each interval+class combo, parallelizes symbol fetches (yfinance rate-limited)
    # I/O bound, 5000+ symbols, needs 2.5-3h for all combinations; 6h timeout ensures completion
    "stock_prices_daily" = { cpu = 2048, memory = 4096, timeout = 21600, parallelism = 4 }
    "stock_prices_weekly" = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 4 }

    # ETF price loaders (daily, weekly, monthly intervals)
    "etf_prices_daily"   = { cpu = 2048, memory = 4096, timeout = 21600, parallelism = 4 }
    "etf_prices_weekly"  = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 4 }
    "etf_prices_monthly" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }

    # Trend template (4:30am ET) — compute-heavy scoring, now in Step Functions EOD pipeline
    "trend_template_data" = { cpu = 2048, memory = 4096, timeout = 1200, parallelism = 8 }

    # Financial statements (SEC EDGAR) — reduce parallelism to 1 to prevent rate limit cascade
    # Sequential processing needs 60min timeout to handle 5000+ symbols with SEC backoff delays
    "financials_annual_income"      = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_annual_balance"     = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_annual_cashflow"    = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_quarterly_income"   = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_quarterly_balance"  = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_quarterly_cashflow" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_ttm_income"         = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "financials_ttm_cashflow"       = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }

    # Computed metrics (growth, quality, value) — CPU bound, process 10K symbols, need parallelism
    "growth_metrics"      = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }
    "quality_metrics"     = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }
    "value_metrics"       = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }
    "positioning_metrics" = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }

    # Earnings data (SEC EDGAR) — reduce parallelism to 1 to prevent rate limit cascade
    # Increase timeout to 60min for sequential 5000+ symbol processing
    "earnings_history"   = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "earnings_revisions" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "earnings_surprise"  = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }
    "earnings_calendar"  = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }

    # Company & analyst data (11:30am ET) — I/O bound, yfinance API calls, 5000+ symbols
    "company_profile"             = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }
    "analyst_sentiment"           = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }
    "analyst_upgrades_downgrades" = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 8 }
    # Sectors/industry: increased timeout for 5000+ symbol processing with parallelism=4
    "sectors"                     = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 4 }
    "industry_ranking"            = { cpu = 512, memory = 1024, timeout = 1200, parallelism = 4 }

    # Market & economic data — small datasets, single-threaded fine
    "seasonality"    = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }

    # Trading signals (5:00pm ET) — MOST CRITICAL, compute-heavy on 5000+ symbols
    # Fixed: timeout 1800→2400→10800→14400→21600s (30min→40min→3h→4h→6h), parallelism 8→4
    # ETF signals: increased timeout to match heavy computation + yfinance rate limiting for 5000+ ETFs
    "signals_daily"       = { cpu = 2048, memory = 4096, timeout = 21600, parallelism = 4 }
    "signals_weekly"      = { cpu = 1024, memory = 2048, timeout = 1200, parallelism = 4 }
    "signals_monthly"     = { cpu = 1024, memory = 2048, timeout = 1200, parallelism = 4 }
    "signals_etf_daily"   = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 4 }
    "signals_etf_weekly"  = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }
    "signals_etf_monthly" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }

    # Algo metrics (5:15pm ET - after signals) - FARGATE: 256 CPU = min 512 MB; increase timeout for 5000+ symbol processing
    "algo_metrics_daily" = { cpu = 256, memory = 512, timeout = 10800, parallelism = 1 }

    # Market data batch — 8 tiny loaders consolidated into one task (3:30am ET)
    "market_data_batch" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }

    # Technical indicators (EOD pipeline step 2) — compute-heavy, 5000+ symbols
    "technical_data_daily" = { cpu = 2048, memory = 4096, timeout = 21600, parallelism = 4 }

    # Market health (EOD pipeline step 2) — reads price_daily for SPY/VIX, small dataset
    "market_health_daily" = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }

    # Swing trader scores (EOD pipeline final step) — compute-heavy scoring
    "swing_trader_scores" = { cpu = 2048, memory = 4096, timeout = 3600, parallelism = 8 }

    # Market sentiment data — small API calls, run daily/weekly
    "feargreed"    = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "aaiidata"     = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "naaim_data"   = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }

    # Step Functions EOD pipeline tasks (defined in pipeline module, not scheduled directly)
    "signal_quality_scores" = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 4 }
    "stock_scores" = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 4 }
    "eod_bulk_refresh" = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 4 }
  }

  # For backward compatibility
  default_loaders = local.all_loaders

  # Loaders that must run on on-demand FARGATE (cannot tolerate interruption)
  critical_loaders = toset([
    "stock_prices_daily",
    "signals_daily", "signals_weekly", "signals_monthly", "signals_etf_daily", "signals_etf_weekly", "signals_etf_monthly",
    "algo_metrics_daily", "eod_bulk_refresh"
  ])
}

# ECS Task Definitions for all 40 data loaders
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
# EventBridge Targets - ECS Task Execution (All 40 Loaders)
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
