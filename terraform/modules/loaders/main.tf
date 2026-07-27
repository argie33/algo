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
    # DEPRECATED (Session 275): Replaced by SEC loaders (company_info_sec, earnings_calendar_sec, institutional_holdings_13f, etc.)
    # "yfinance_snapshot"     = "load_yfinance_snapshot.py"
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

    # ============================================================
    # PHASE 1-4 OPTIMIZATION: Reduce yfinance dependence (Session 204+)
    # ============================================================
    # Phase 1: SEC-derived valuations (replaces ~5,300 yfinance quoteSummary calls/day)
    "sec_valuations" = "load_sec_valuations.py"

    # Phase 2: Consolidated market status (merges 3 separate loaders → 1 atomic operation)
    # Replaces: market_health_daily + market_exposure_daily + market_sentiment
    "market_status_daily" = "load_market_status_daily.py"

    # Phase 3: Consolidated value/quality/growth metrics (DEPENDS ON Phase 1)
    # Replaces: value_metrics + quality_metrics + growth_metrics (old loaders)
    # Uses: SEC valuations (Phase 1) + yfinance snapshot (enrichment)
    "value_quality_growth_metrics" = "load_value_quality_growth_metrics.py"

    # Phase 4: Consolidated sector/industry loader (unified OptimalLoader framework)
    # Replaces: sector_performance + sector_ranking + industry_ranking
    "sector_industry_daily" = "load_sector_industry_daily.py"

    # ============================================================
    # PHASE 5: SEC Company Info & Earnings Calendar (Session 237+)
    # ============================================================
    # Phase 5a: Company Info from SEC EDGAR (replaces ~15% of yfinance_snapshot)
    # Official company master data: entity name, SIC code, sector classification
    # Annual updates (company info changes rarely)
    "company_info_sec" = "load_company_info_sec.py"

    # Restored 2026-07-27: SEC SIC->GICS sector/industry classification, sourced from
    # company_info_sec (must run after it - only data source). Was deleted 2026-07-26 after
    # being (incorrectly) judged orphaned for lacking terraform wiring; pretrade_checks.py
    # hard-blocks new entries without a company_profile row, and circuit_breaker.py's
    # sector-concentration/sector-drawdown checks both read it - same "restored after being
    # believed superseded" mistake class as company_info_sec/earnings_calendar_sec below.
    "company_profile" = "load_company_profile.py"

    # Phase 5b: Earnings Calendar from SEC EDGAR (replaces ~10% of yfinance_snapshot)
    # Official 10-K/10-Q filing dates (when earnings are announced to SEC)
    # Continuous updates (quarterly and annual filings)
    "earnings_calendar_sec" = "load_earnings_calendar_sec.py"

    # Market-exposure factor inputs (Session 301: restored after being deleted while
    # algo/risk/factors/naaim_factor.py + aaii_sentiment_factor.py — 2 of the Core 12
    # market-exposure factors — kept silently reading the resulting stale tables with
    # no freshness check). Must run before market_status_daily, which computes the
    # regime/exposure score from these tables.
    "naaim"          = "load_naaim.py"
    "aaii_sentiment" = "load_aaii_sentiment.py"

    # Risk metrics: volatility + beta + momentum calculations for position monitoring
    # Single consolidated loader: computes momentum (1m/3m/6m/12m) + stability (vol/beta)
    "stability_metrics" = "load_risk_metrics_daily.py"

    # Positioning: short interest + institutional/insider holdings
    "positioning_metrics" = "load_positioning_metrics.py"
    "short_interest_finra" = "load_short_interest_finra.py"

    # Stock scoring: 6-factor composite
    "stock_scores" = "load_stock_scores.py"

    # Trading signals
    "buy_sell_daily" = "load_buy_sell_daily.py"
    "signal_quality_scores" = "load_signal_quality_scores.py"  # Session 307 restoration: SQS feature
    "algo_metrics_daily" = "load_algo_metrics_daily.py"

    # Reference data
    "market_constituents" = "load_market_constituents.py"

    # SEC holdings (Phase 2 complete - institutional + insider from SEC filings)
    "institutional_holdings_13f" = "load_institutional_holdings_13f.py"
    "insider_holdings_sec" = "load_insider_holdings_sec.py"
    "insider_transaction_velocity" = "load_insider_transaction_velocity.py"

    # SEC cash flow & segment metrics (Session 445: XBRL segment disclosure extraction)
    "sec_cash_flow_metrics" = "load_sec_cash_flow_metrics.py"
    "sec_segment_info" = "load_sec_segment_info.py"  # XBRL ASC 280 segment disclosure parser (source for segment_metrics)
    "sec_segment_metrics" = "load_sec_segment_metrics.py"

    # SEC Current Reports (8-K) and Dividend Data (Session 444: XBRL expansion)
    # 8-K: Material events that may impact trading signals (acquisitions, bankruptcies, etc.)
    # Dividends: Ex-dates, payment dates, yields for position management
    "current_reports_8k" = "load_current_reports_8k.py"
    "dividend_data" = "load_dividend_data.py"
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
    # DEPRECATED (Session 276): market_exposure_daily consolidated into market_status_daily (Phase 2 consolidation)
    # No longer run as separate task; outputs produced atomically by market_status_daily
    # "market_exposure_daily" = { cpu = 256, memory = 512, timeout = 120, parallelism = 1 }
    # DEPRECATED (Session 275+): yfinance_snapshot removed — all loaders now use real data sources
    # (Alpaca prices, SEC EDGAR, FINRA). Python file kept for reference only.
    # "yfinance_snapshot"     = { cpu = 1024, memory = 2048, timeout = 14400, parallelism = 1 }
    # ============================================================
    # PHASE 1-4 OPTIMIZATION: Reduce yfinance dependence (Session 204+)
    # ============================================================
    # Phase 1: SEC-derived valuations (replaces ~5,300 yfinance quoteSummary calls/day)
    # Computes PE/PB/PS/PEG/FCF from SEC audited data + prices
    # Lightweight: SEC data + price lookups + arithmetic (actual ~50MB)
    "sec_valuations" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 2 }

    # Phase 2: Consolidated market status (merges 3 separate loaders → 1 atomic operation)
    # Replaces: market_health_daily (128/256) + market_exposure_daily (256/512) + market_sentiment (256/512)
    # Combined workload: VIX + breadth + yields + regime detection + fear/greed
    # Single pass to reduce API calls and produce consistent market view
    # Timeout: sum of old loaders (1200 + 120 + 60) + 20% headroom = ~1600s
    "market_status_daily" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }

    # Phase 3: Consolidated value/quality/growth metrics (DEPENDS ON Phase 1)
    # Replaces: old value_metrics + quality_metrics + growth_metrics loaders
    # Combined workload: SEC valuations + financial ratios + growth computations (actual ~200MB)
    # Uses optimized sec_valuations (Phase 1) instead of yfinance quoteSummary
    # Timeout: 3600s (heaviest phase), add 20% headroom
    "value_quality_growth_metrics" = { cpu = 1024, memory = 2048, timeout = 4500, parallelism = 2 }

    # Phase 4: Consolidated sector/industry loader (unified OptimalLoader framework)
    # Replaces: old sector_performance + sector_ranking + industry_ranking loaders
    # Combined workload: daily returns + ranking aggregation + momentum calculations
    # Single transaction for atomic updates to all 3 tables (actual ~100MB)
    # Timeout: 1800s (consolidated from old 900s×3)
    "sector_industry_daily" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }

    # PHASE 5: SEC Company Info & Earnings Calendar (Session 237+)
    # Phase 5a: Company Info from SEC EDGAR (lightweight: SEC API calls + metadata parsing, <100MB)
    # Timeout: 600s (typical run <5 min for 5k symbols, 2x headroom)
    # Parallelism: 1-2 (SEC API rate-limited to ~10 req/sec globally, keep under limit)
    "company_info_sec" = { cpu = 256, memory = 512, timeout = 600, parallelism = 2 }

    # Restored 2026-07-27: reads company_info_sec (already in RDS, no external API calls),
    # so it's lighter and faster than company_info_sec itself.
    "company_profile" = { cpu = 128, memory = 256, timeout = 300, parallelism = 2 }

    # Phase 5b: Earnings Calendar from SEC EDGAR (lightweight: submission parsing, <100MB)
    # Timeout: 900s (typical run ~5-15 min for 5k symbols + 10-K/10-Q extraction, 2x headroom)
    # Parallelism: 1-2 (SEC API rate-limited, keep under global limit)
    "earnings_calendar_sec" = { cpu = 256, memory = 512, timeout = 900, parallelism = 2 }

    # ============================================================
    # PHASE 2 COMPLETE: Institutional/Insider Holdings from SEC (Session 274+)
    # ============================================================
    # Replaces yfinance held_percent_institutions/held_percent_insiders
    # Data source: SEC SCHEDULE 13G (institutional) + SEC Form 4/5 (insider)
    # Quality: SEC-published data > yfinance estimates; quarterly updates acceptable for scoring
    # Lightweight: SEC API calls + aggregation (actual ~100MB each)
    "institutional_holdings_13f" = { cpu = 256, memory = 512, timeout = 1200, parallelism = 2 }
    "insider_holdings_sec"       = { cpu = 256, memory = 512, timeout = 1200, parallelism = 2 }

    # ============================================================
    # NEW: Insider Transaction Velocity (Session 444+)
    # ============================================================
    # Insider confidence scoring from SEC Form 3/4/5 transaction counts
    # Data source: Same as insider_holdings_sec (Form 3/4/5 bulk datasets)
    # Detects insider buying sprees, executive departures, lockup periods
    # Lightweight: SEC API calls + aggregation (actual ~100MB, same as insider_holdings_sec)
    "insider_transaction_velocity" = { cpu = 256, memory = 512, timeout = 1200, parallelism = 2 }

    # ============================================================
    # NEW: SEC-Derived Cash Flow & Segment Metrics (Session 274+)
    # ============================================================
    # Working capital, capex, free cash flow from SEC financial statements
    # Segment revenue/income concentration for diversification scoring
    # Lightweight: DB joins + arithmetic calculations (actual ~50MB each)
    "sec_cash_flow_metrics" = { cpu = 256, memory = 512, timeout = 1800, parallelism = 2 }
    "sec_segment_metrics"   = { cpu = 256, memory = 512, timeout = 1800, parallelism = 2 }

    # Core Stock Scoring & Risk Metrics (ACTIVE)
    # Stock scores: 6-factor composite (quality/growth/value/momentum/positioning/stability)
    "stock_scores" = { cpu = 1024, memory = 2048, timeout = 3600, parallelism = 2 }

    # Risk metrics: volatility, beta, momentum for position monitoring (Session 275: consolidated from separate loaders)
    # Single loader computes BOTH momentum and stability metrics in one pass
    # Writes to momentum_metrics table (primary) and stability_metrics table (side effect)
    "stability_metrics" = { cpu = 512, memory = 1024, timeout = 4200, parallelism = 2 }

    # Positioning metrics: short interest (FINRA) + institutional/insider holdings (SEC)
    "positioning_metrics" = { cpu = 512, memory = 1024, timeout = 1800, parallelism = 1 }

    # FINRA short interest (bi-weekly regulatory data)
    "short_interest_finra" = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }

    # Market-exposure factor inputs (Session 301 restoration, see loader_file_map comment)
    # NAAIM: plain HTTP GET + pandas.read_html, no browser needed - lightweight like short_interest_finra
    "naaim" = { cpu = 256, memory = 512, timeout = 300, parallelism = 1 }
    # AAII: needs Playwright/Chromium to bypass Incapsula bot protection (image already has
    # `playwright install chromium` — see repo root Dockerfile). Live-tested locally at ~23s
    # end-to-end including browser launch; sized with headroom for a cold Fargate start.
    "aaii_sentiment" = { cpu = 512, memory = 1024, timeout = 300, parallelism = 1 }

    # Core Market Data
    "market_constituents" = { cpu = 128, memory = 256, timeout = 120, parallelism = 1 }
    "economic_data" = { cpu = 256, memory = 512, timeout = 900, parallelism = 1 }

    # Financial statements (SEC EDGAR, all 8 statement/period combos in single task)
    "financials_all" = { cpu = 512, memory = 1024, timeout = 3600, parallelism = 1 }

    # Signals & algo metrics
    "buy_sell_daily"        = { cpu = 1024, memory = 2048, timeout = 2400, parallelism = 2 }
    "signal_quality_scores" = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }
    "algo_metrics_daily"    = { cpu = 256, memory = 512, timeout = 600, parallelism = 1 }

    # SEC Current Reports & Dividend Data (Session 444: XBRL expansion)
    # 8-K: Form 8-K current reports (material events, SEC API calls + text parsing)
    # Typical run ~5-15 min for 5k symbols + text extraction, lightweight (~100MB)
    "current_reports_8k" = { cpu = 256, memory = 512, timeout = 1200, parallelism = 2 }

    # Dividends: Ex-dates, payment dates, yields (XBRL + 8-K extraction)
    # Typical run ~5-10 min for 5k symbols, lightweight (~100MB)
    "dividend_data" = { cpu = 256, memory = 512, timeout = 900, parallelism = 2 }
  }
  default_loaders = local.all_loaders

  # Loaders that must run on on-demand FARGATE (cannot tolerate interruption)
  critical_loaders = toset([
    # Core pricing & technicals (FAIL-CLOSED dependencies)
    "stock_prices_daily",
    "technical_data_daily",
    "trend_template_data",
    "market_constituents",
    # NOTE: market_exposure_daily removed (consolidated into market_status_daily, Session 276)

    # Metrics & scoring
    "stock_scores",
    "sec_valuations",
    "value_quality_growth_metrics",
    "market_status_daily",
    "sector_industry_daily",
    "positioning_metrics",
    "stability_metrics",

    # SEC data sources
    "financials_all",
    "company_info_sec",
    "company_profile",
    "earnings_calendar_sec",
    "institutional_holdings_13f",
    "insider_holdings_sec",
    "insider_transaction_velocity",
    "sec_cash_flow_metrics",
    "sec_segment_info",
    "sec_segment_metrics",

    # Signals & execution
    "buy_sell_daily",
    "algo_metrics_daily",

    # Economic data
    "economic_data",
    "short_interest_finra",

    # Market-exposure factor inputs (Session 301 restoration)
    "naaim",
    "aaii_sentiment",

    # SEC Current Reports & Dividend Data (Session 444: XBRL expansion)
    "current_reports_8k",
    "dividend_data"
  ])
}

# ECS Task Definitions for 10 production data loaders
# NOTE: CPU/memory in container definition are removed - only task-level values matter for Fargate
resource "aws_ecs_task_definition" "loader" {
  for_each = local.all_loaders

  depends_on = [null_resource.ensure_log_group]

  family = "${var.project_name}-${each.key}-loader"

  # CRITICAL FIX (Session 196): Force Terraform to detect CPU/memory changes
  # Terraform was ignoring cpu/memory changes because family name stayed the same.
  # Incrementing this tag forces a new revision creation.
  tags = merge(var.common_tags, {
    force_rebuild_version = "3"
  })

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
        # CRITICAL FIX (Session 164): Set AWS_EXECUTION_ENV so credential_manager detects AWS environment
        # Without this, credential_manager assumes local dev and doesn't use Secrets Manager fallback
        # This causes DB credential injection to fail, making loaders unable to connect to RDS
        {
          name  = "AWS_EXECUTION_ENV"
          value = "ECS_FARGATE"
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

      # Session 199: Enhanced health check - validates loader is responsive, not just running
      # Checks: (1) Python process exists, (2) health check file is fresh (< 60 seconds old)
      # If file is stale → loader is stuck → marked UNHEALTHY
      # ECS marks UNHEALTHY after 2 failed checks (60s total after grace period)
      healthCheck = {
        command     = ["/healthcheck.sh"]
        interval    = 30  # Check every 30 seconds
        timeout     = 5   # Timeout for health check script
        retries     = 2   # Mark unhealthy after 2 failed checks (60s total after grace period)
        startPeriod = 120 # Grace period before first health check (loaders need 10-20s startup)
      }
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  # Moved tags to top of resource to force detection, merged here
  # tags = var.common_tags  # (now merged in tags block at top)
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
      subnets          = var.public_subnet_ids
      security_groups  = [var.ecs_tasks_sg_id]
      assign_public_ip = true
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
        # CRITICAL FIX (Session 164): Set AWS_EXECUTION_ENV so credential_manager detects AWS environment
        # Without this, credential_manager assumes local dev and doesn't use Secrets Manager fallback
        # This causes DB credential injection to fail, making orchestrator unable to connect to RDS
        { name = "AWS_EXECUTION_ENV", value = "ECS_FARGATE" },
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
        { name = "APCA_API_BASE_URL", value = var.alpaca_api_base_url },
        { name = "PRICE_DATA_SOURCE", value = var.price_data_source },
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
        # CRITICAL FIX (Session 164): Set AWS_EXECUTION_ENV so credential_manager detects AWS environment
        # Without this, credential_manager assumes local dev and doesn't use Secrets Manager fallback
        { name = "AWS_EXECUTION_ENV", value = "ECS_FARGATE" },
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
